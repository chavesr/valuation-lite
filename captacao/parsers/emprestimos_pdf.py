"""Posições de empréstimos/financiamentos em PDF (BB e Sicredi) → saldo devedor por contrato.

Formatos suportados:
  * BB "Extrato de empréstimos" consolidado (uma linha por operação, agrupadas por linha de crédito)
  * BB extrato de uma operação ("Saldo devedor total … D") e histórico de posição ("Saldo Devedor(em dd/mm/aaaa)")
  * Sicredi "Documento Descritivo de Crédito" (rótulos numa linha, valores na seguinte)
  * Sicredi "Consulta Empréstimos" (rótulo e valor na mesma linha; números às vezes em formato americano)

A dívida bancária entra no valuation como dívida líquida (preço = valor da firma − dívida + caixa) e é
conferida com a linha de empréstimos do Balanço.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from pathlib import Path

from pydantic import BaseModel

from captacao.schemas import Metodo, Proveniencia
from captacao.util import normalizar_texto


class EmprestimoNaoLido(Exception):
    pass


class Divida(BaseModel):
    banco: str
    contrato: str
    modalidade: str | None = None
    saldo_devedor: float
    data_posicao: date | None = None
    valor_contratado: float | None = None
    contratacao: date | None = None
    vencimento_final: date | None = None
    parcelas_restantes: int | None = None
    taxa_aa: float | None = None  # % ao ano (efetiva quando informada)
    taxa_am: float | None = None  # % ao mês
    indexador: str | None = None
    situacao: str | None = None
    proveniencia: Proveniencia


_DATA = r"\d{2}/\d{2}/\d{4}"


def _d(txt: str | None) -> date | None:
    return datetime.strptime(txt, "%d/%m/%Y").date() if txt else None


def _n(txt: str | None) -> float | None:
    """Aceita 1.234,56 (BR) e 1,234.56 (americano)."""
    if not txt:
        return None
    t = txt.strip().replace("R$", "").strip()
    if re.fullmatch(r"[\d,]+\.\d{2}", t):
        return float(t.replace(",", ""))
    return float(t.replace(".", "").replace(",", "."))


def _depois(rotulo: str, texto: str, padrao: str) -> str | None:
    """Valor na mesma linha do rótulo ou, se não houver, na linha seguinte."""
    m = re.search(rf"{rotulo}[^\n]*?({padrao})", texto) or re.search(rf"{rotulo}[^\n]*\n[^\n]*?({padrao})", texto)
    return m.group(1) if m else None


def identificar(texto: str) -> str | None:
    n = normalizar_texto(texto[:1500])
    if "DOCUMENTO DESCRITIVO DE CREDITO" in n:
        return "sicredi_descritivo"
    if "CONSULTA EMPRESTIMOS" in n and "NRO DO TITULO" in n:
        return "sicredi_consulta"
    if "EXTRATO DE EMPRESTIMOS" in n and "SALDO DEVEDOR TOTAL" in normalizar_texto(texto):
        return "bb_operacao"
    if "EXTRATO DE EMPRESTIMOS" in n:
        return "bb_consolidado"
    if "CONSULTAR EMPRESTIMOS" in n and "SALDO DEVEDOR(EM" in n.replace(" (", "("):
        return "bb_historico"
    return None


def ler_emprestimos(caminho: str | Path, texto: str | None = None) -> list[Divida]:
    caminho = Path(caminho)
    if texto is None:
        import pdfplumber

        with pdfplumber.open(caminho) as pdf:
            texto = "\n".join((p.extract_text() or "") for p in pdf.pages)
    formato = identificar(texto)
    if formato is None:
        raise EmprestimoNaoLido("não é posição de empréstimo conhecida")
    prov = Proveniencia(arquivo=caminho.name, localizacao=formato, metodo=Metodo.PARSER)
    n = normalizar_texto(texto)

    if formato == "bb_consolidado":
        dividas, modalidade = [], None
        posicao = re.search(_DATA, texto)
        for linha in texto.splitlines():
            m = re.match(rf"^(\d{{6,}})\s+(\w+)\s+({_DATA})\s+({_DATA})\s+({_DATA})?\s*([\d.]+,\d{{2}})$", linha.strip())
            if m:
                dividas.append(Divida(banco="001", contrato=m.group(1), situacao=m.group(2), modalidade=modalidade,
                                      contratacao=_d(m.group(3)), vencimento_final=_d(m.group(4)),
                                      saldo_devedor=_n(m.group(6)), data_posicao=_d(posicao.group(0)) if posicao else None,
                                      proveniencia=prov))
            elif re.match(r"^BB |^CREDITO|^FINANCIAMENTO|^CDC|^PRONAMPE", normalizar_texto(linha)) \
                    and "OPERACAO" not in normalizar_texto(linha):
                modalidade = linha.strip()
        if not dividas:
            raise EmprestimoNaoLido("nenhuma operação na tabela do BB")
        return dividas

    if formato == "bb_operacao":
        contrato = re.search(r"^(\d{6,})\s+Extrato", texto, flags=re.M) or re.search(r"(\d{6,})", caminho.stem)
        return [Divida(
            banco="001", contrato=contrato.group(1) if contrato else caminho.stem,
            modalidade=(re.search(r"^(BB [A-Z ]+?)(?:\s+DDC|\s+Parcela|$)", texto, flags=re.M) or [None, None])[1],
            saldo_devedor=_n(re.search(r"Saldo devedor total\s+([\d.]+,\d{2})", texto).group(1)),
            data_posicao=_d(_depois("Posição em", texto, _DATA)),
            valor_contratado=_n(_depois("Valor contratado", texto, r"[\d.]+,\d{2}")),
            contratacao=_d(_depois("Data contratação", texto, _DATA)),
            vencimento_final=_d(_depois("Data última parcela", texto, _DATA)),
            parcelas_restantes=int(x) if (x := _depois("Quantidade remanescente", texto, r"\d+")) else None,
            taxa_aa=_n(_depois("Encargos Efetivos", texto, r"[\d.]+,\d+")),
            proveniencia=prov)]

    if formato == "bb_historico":
        m = re.search(rf"Saldo Devedor\s*\(em ({_DATA})\):[^\n]*\n\s*([\d.]+,\d{{2}})\s+([\d.]+,\d{{2}})", texto)
        op = re.search(r"Nr Opera\S*:\s*\n.*?(\d{6,})\s*$", texto, flags=re.M)
        if not m:
            raise EmprestimoNaoLido("saldo devedor não encontrado no histórico do BB")
        datas = re.search(rf"Contrata\S*:[^\n]*\n\s*({_DATA})\s+({_DATA})\s+({_DATA})", texto)
        return [Divida(banco="001", contrato=op.group(1) if op else caminho.stem, saldo_devedor=_n(m.group(3)),
                       valor_contratado=_n(m.group(2)), data_posicao=_d(m.group(1)),
                       contratacao=_d(datas.group(1)) if datas else None,
                       vencimento_final=_d(datas.group(3)) if datas else None, proveniencia=prov)]

    if formato == "sicredi_descritivo":
        saldo = re.search(rf"Saldo Devedor Atualizado:\s*\n\s*({_DATA})\s+R\$\s*([\d.]+,\d{{2}})", texto)
        contrato = re.search(r"OID:[^\n]*\n\s*(\S+)\s*/\s*\S+\s+(.+)$", texto, flags=re.M)
        parcelas = re.search(r"Total de Parcelas[^\n]*\n\s*(\d+)\s+(\d+)", texto)
        taxas = re.search(r"Taxa de Juros Efetiva % a\.a\.:[^\n]*\n\s*([\d,]+)", texto)
        datas = re.search(rf"Data da Libera\S* da Opera\S*:[^\n]*\n\s*({_DATA})\s+({_DATA})", texto)
        indexador = re.search(r"Indexador:\s*\n\s*\S+\s+(\S+)", texto)
        if not saldo:
            raise EmprestimoNaoLido("saldo devedor não encontrado no descritivo do Sicredi")
        return [Divida(banco="748", contrato=contrato.group(1) if contrato else caminho.stem,
                       modalidade=contrato.group(2).strip() if contrato else None,
                       saldo_devedor=_n(saldo.group(2)), data_posicao=_d(saldo.group(1)),
                       parcelas_restantes=int(parcelas.group(2)) if parcelas else None,
                       taxa_aa=_n(taxas.group(1)) if taxas else None,
                       contratacao=_d(datas.group(1)) if datas else None,
                       vencimento_final=_d(datas.group(2)) if datas else None,
                       indexador=indexador.group(1) if indexador else None, proveniencia=prov)]

    # sicredi_consulta
    def campo(rotulo: str, padrao: str = r"[\d.,]+") -> str | None:
        m = re.search(rf"{rotulo}\s*(?:\(R\$\))?\s*({padrao})", texto)
        return m.group(1) if m else None

    saldo = campo("Saldo Devedor")
    if saldo is None:
        raise EmprestimoNaoLido("saldo devedor não encontrado na consulta do Sicredi")
    total = campo("Total de Parcelas", r"\d+")
    pagas = campo("Parcelas Pagas", r"\d+")
    impresso = re.search(rf"Impresso em ({_DATA})", texto) or re.search(rf"^({_DATA})", texto, flags=re.M)
    return [Divida(banco="748", contrato=campo("Nro do T\\S+", r"\S+") or caminho.stem, saldo_devedor=_n(saldo),
                   valor_contratado=_n(campo("Valor Liberado")), contratacao=_d(campo("Data de Libera\\S+", _DATA)),
                   taxa_am=_n(campo("Taxa de Juros ao M\\S+", r"[\d.,]+")),
                   indexador=campo("Corre\\S+ Monet\\S+ Mensal", r"[A-Z]+"),
                   situacao=campo("Situa\\S+", r"[A-Z]+"),
                   parcelas_restantes=int(total) - int(pagas) if total and pagas else None,
                   vencimento_final=_d(campo("Pr\\S+ximo Vencimento", _DATA)) if total == "1" else None,
                   data_posicao=_d(impresso.group(1)) if impresso else None, proveniencia=prov)]


def consolidar_dividas(dividas: list[Divida]) -> list[Divida]:
    """Um registro por (banco, contrato): fica a posição mais recente; completa campos vazios com as outras."""
    por: dict[tuple[str, str], Divida] = {}
    for d in sorted(dividas, key=lambda d: d.data_posicao or date.min):
        chave = (d.banco, d.contrato)
        if chave in por:
            antiga = por[chave]
            dados = {k: v if v is not None else getattr(antiga, k) for k, v in d.model_dump().items()}
            dados["proveniencia"] = d.proveniencia
            por[chave] = Divida(**dados)
        else:
            por[chave] = d
    return sorted(por.values(), key=lambda d: -d.saldo_devedor)
