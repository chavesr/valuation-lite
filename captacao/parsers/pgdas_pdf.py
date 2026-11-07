"""Simples Nacional em PDF: Extrato do PGDAS-D (mensal) e DEFIS (anual). Nível 0 do funil — zero tokens.

Extrato do PGDAS-D (Receita Federal)
  * receita bruta do PA (mercado interno + externo), RBT12, RBA, RBAA, limite/sublimite
  * "2.2 Receitas Brutas Anteriores": a receita declarada dos meses anteriores (até ~18) — um único
    extrato recente já cobre quase todo o período de análise
  * tributos por atividade e total do DAS; dados do pagamento (seção 6.2), quando houver
  * apuração original ou retificadora

DEFIS (declaração anual do Simples)
  * estoque e caixa no início e no fim do ano, compras, despesas
  * empregados no início e no fim do ano
  * rendimentos pagos aos sócios (isentos = distribuição de lucros; tributáveis = pró-labore)
"""

from __future__ import annotations

import re
from datetime import date, datetime
from pathlib import Path

from pydantic import BaseModel, Field

from captacao.schemas import Metodo, PGDASMes, Proveniencia
from captacao.util import apenas_digitos, brl, normalizar_texto

_NUM = r"[\d.]+,\d{2}"
TRIBUTOS = ["IRPJ", "CSLL", "COFINS", "PIS", "INSS/CPP", "ICMS", "IPI", "ISS"]


class SimplesNaoLido(Exception):
    pass


def _n(txt: str | None) -> float | None:
    return float(txt.replace(".", "").replace(",", ".")) if txt else None


def _d(txt: str | None) -> date | None:
    return datetime.strptime(txt, "%d/%m/%Y").date() if txt else None


def _comp(mm_aaaa: str) -> str:
    m, a = mm_aaaa.split("/")
    return f"{a}-{m}"


def identificar(texto: str) -> str | None:
    n = normalizar_texto(texto[:800])
    if "EXTRATO DO SIMPLES NACIONAL" in n and "PERIODO DE APURACAO" in normalizar_texto(texto[:3000]):
        return "pgdas"
    if "DEFIS" in n and "RECIBO DE ENTREGA" in n:
        return "defis_recibo"
    if "DEFIS" in n or "DECLARACAO DE INFORMACOES SOCIOECONOMICAS E FISCAIS" in n:
        return "defis"
    return None


# --------------------------------------------------------------------------- PGDAS-D


class ApuracaoPGDAS(BaseModel):
    cnpj: str  # estabelecimento matriz (14 dígitos) ou CNPJ básico (8)
    nome: str | None
    competencia: str
    retificadora: bool
    apurado_em: datetime | None
    receita_pa: float
    rbt12: float | None
    rba: float | None
    rbaa: float | None
    sublimite: float | None
    tributos: dict[str, float] = Field(default_factory=dict)
    total_das: float | None = None
    das_vencimento: date | None = None
    das_pago_em: date | None = None
    das_valor_pago: float | None = None
    atividades: dict[str, float] = Field(default_factory=dict)  # descrição da atividade → receita
    receitas_anteriores: dict[str, float] = Field(default_factory=dict)  # competência → receita (interno+externo)
    estabelecimentos: list[str] = Field(default_factory=list)
    abertura: date | None = None
    proveniencia: Proveniencia

    @property
    def aliquota_efetiva(self) -> float | None:
        return round(self.total_das / self.receita_pa, 4) if self.total_das and self.receita_pa else None


def _secao(texto: str, inicio: str, fim: str) -> str:
    i = texto.find(inicio)
    if i < 0:
        return ""
    j = texto.find(fim, i + len(inicio))
    return texto[i: j if j > 0 else None]


def ler_extrato_pgdas(texto: str, arquivo: str) -> ApuracaoPGDAS:
    pa = re.search(r"Per\S+odo de Apura\S+ \(PA\):\s*(\d{2}/\d{4})", texto)
    if not pa:
        raise SimplesNaoLido("período de apuração não encontrado no extrato do PGDAS-D")
    rpa = re.search(rf"Receita Bruta do PA \(RPA\)[^\n]*?({_NUM})\s+({_NUM})\s+({_NUM})", texto)
    def acumulado(rotulo: str) -> float | None:
        m = re.search(rf"{rotulo}[^\n]*\n?\s*({_NUM})\s+({_NUM})\s+({_NUM})", texto)
        return _n(m.group(3)) if m else None

    estabs = [apenas_digitos(c) for c in re.findall(r"CNPJ Estabelecimento:\s*([\d./-]+)", texto)]
    basico = re.search(r"CNPJ B\S+sico:\s*([\d.]+)", texto)
    nome = re.search(r"Nome Empresarial:\s*(.+)", texto)

    anteriores: dict[str, float] = {}
    for bloco in ("2.2.1)", "2.2.2)"):  # mercado interno e externo somados
        sec = _secao(texto, bloco, "2.2.2)" if bloco == "2.2.1)" else "2.3)")
        for comp, valor in re.findall(rf"(\d{{2}}/\d{{4}})\s+({_NUM})", sec):
            anteriores[_comp(comp)] = round(anteriores.get(_comp(comp), 0.0) + _n(valor), 2)

    total = _secao(texto, "4) Total Geral da Empresa", "5)") or texto
    linha_trib = re.search(r"IRPJ CSLL COFINS PIS/Pasep INSS/CPP ICMS IPI ISS Total\s*\n\s*((?:" + _NUM + r"\s*){9})", total)
    tributos, total_das = {}, None
    if linha_trib:
        valores = [_n(v) for v in re.findall(_NUM, linha_trib.group(1))]
        tributos = dict(zip(TRIBUTOS, valores[:8]))
        total_das = valores[8]

    atividades = {}
    for m in re.finditer(rf"Valor do D\S+bito por Tributo para a Atividade \(R\$\):\s*\n(.+?)Receita Bruta Informada:\s*R\$\s*({_NUM})",
                         texto, flags=re.S):
        atividades[re.sub(r"\s+", " ", m.group(1)).strip()[:160]] = _n(m.group(2))

    pagamento = re.search(rf"Informa\S+es da Arrecada\S+o do DAS[^\n]*\n[^\n]*\n\s*(\d{{2}}/\d{{2}}/\d{{4}})\s+\S+\s+({_NUM})",
                          texto)
    vencimento = re.search(r"Data limite para acolhimento:\s*(\d{2}/\d{2}/\d{4})", texto)
    apurado = re.search(r"Apurado em (\d{2}/\d{2}/\d{4} \d{2}:\d{2}:\d{2})", texto)
    sublimite = re.search(rf"Sublimite de Receita Anual \(R\$\):\s*({_NUM})", texto)

    receita = (_n(rpa.group(3)) if rpa else None)
    if receita is None:
        raise SimplesNaoLido("receita bruta do PA não encontrada")
    return ApuracaoPGDAS(
        cnpj=estabs[0] if estabs else apenas_digitos(basico.group(1)) if basico else "",
        nome=nome.group(1).strip() if nome else None, competencia=_comp(pa.group(1)),
        retificadora="RETIFICADORA" in normalizar_texto(texto[:400]),
        apurado_em=datetime.strptime(apurado.group(1), "%d/%m/%Y %H:%M:%S") if apurado else None,
        receita_pa=receita, rbt12=acumulado(r"Receita bruta acumulada nos doze meses anteriores ao PA\s*\n?"),
        rba=acumulado(r"Receita bruta acumulada no ano-calend\S+rio corrente \(RBA\)"),
        rbaa=acumulado(r"Receita bruta acumulada no ano-calend\S+rio anterior"),
        sublimite=_n(sublimite.group(1)) if sublimite else None,
        tributos=tributos, total_das=total_das,
        das_vencimento=_d(vencimento.group(1)) if vencimento else None,
        das_pago_em=_d(pagamento.group(1)) if pagamento else None,
        das_valor_pago=_n(pagamento.group(2)) if pagamento else None,
        atividades=atividades, receitas_anteriores=anteriores, estabelecimentos=estabs,
        abertura=_d((re.search(r"Data de Abertura:\s*(\d{2}/\d{2}/\d{4})", texto) or [None, None])[1]),
        proveniencia=Proveniencia(arquivo=arquivo, localizacao=f"PGDAS-D PA {pa.group(1)}", metodo=Metodo.PARSER))


def pgdas_mensal(apuracoes: list[ApuracaoPGDAS]) -> tuple[list[PGDASMes], list[str]]:
    """Série mensal de receita declarada. Prioridade: a apuração do próprio mês (a mais recente, se houver
    retificação) > o valor citado como "receita anterior" no extrato mais recente. Diferenças entre o valor
    apurado e o citado depois indicam retificação."""
    alertas: list[str] = []
    proprias: dict[str, ApuracaoPGDAS] = {}
    for a in sorted(apuracoes, key=lambda a: a.apurado_em or datetime.min):
        proprias[a.competencia] = a  # a última apuração do PA prevalece
    citadas: dict[str, tuple[float, ApuracaoPGDAS]] = {}
    for a in sorted(apuracoes, key=lambda a: a.competencia):
        for comp, valor in a.receitas_anteriores.items():
            citadas[comp] = (valor, a)  # o extrato mais recente prevalece

    saida: list[PGDASMes] = []
    for comp in sorted(set(proprias) | set(citadas)):
        if comp in proprias:
            a = proprias[comp]
            saida.append(PGDASMes(cnpj=a.cnpj, competencia=comp, receita_bruta=a.receita_pa, rbt12=a.rbt12,
                                  aliquota_efetiva=a.aliquota_efetiva, valor_das=a.total_das, proveniencia=a.proveniencia))
            if comp in citadas and abs(citadas[comp][0] - a.receita_pa) > 1.0:
                alertas.append(f"PGDAS {comp}: apurado R$ {brl(a.receita_pa)}, mas o extrato de "
                               f"{citadas[comp][1].competencia} cita R$ {brl(citadas[comp][0])} (retificação?).")
        else:
            valor, origem = citadas[comp]
            prov = origem.proveniencia.model_copy(
                update={"localizacao": f"receitas anteriores do PGDAS-D {origem.competencia}", "confianca": "alta"})
            saida.append(PGDASMes(cnpj=origem.cnpj, competencia=comp, receita_bruta=valor, proveniencia=prov))
    for a in proprias.values():
        if a.total_das and a.das_valor_pago is None:
            alertas.append(f"DAS do PA {a.competencia} (R$ {brl(a.total_das)}) sem pagamento registrado no extrato.")
    return saida, alertas


# --------------------------------------------------------------------------- DEFIS


class DEFISAnual(BaseModel):
    cnpj: str
    ano: int
    retificadora: bool
    empregados_inicio: int | None = None
    empregados_fim: int | None = None
    estoque_inicial: float | None = None
    estoque_final: float | None = None
    caixa_inicial: float | None = None
    caixa_final: float | None = None
    aquisicoes: float | None = None
    importacoes: float | None = None
    total_entradas: float | None = None
    total_despesas: float | None = None
    devolucoes_vendas: float | None = None
    socios: list[dict] = Field(default_factory=list)  # nome, cpf, participação, rendimentos isentos/tributáveis
    proveniencia: Proveniencia

    @property
    def distribuicao_socios(self) -> float:
        return round(sum(s.get("isentos", 0.0) for s in self.socios), 2)

    @property
    def pro_labore_socios(self) -> float:
        return round(sum(s.get("tributaveis", 0.0) for s in self.socios), 2)


def ler_defis(texto: str, arquivo: str) -> DEFISAnual:
    ano = re.search(r"Ano-Calend\S+rio (\d{4})", texto)
    cnpj = re.search(r"CNPJ Matriz:\s*(\d{14})", texto) or re.search(r"Estabelecimento:\s*([\d./-]+)", texto)
    if not ano or not cnpj:
        raise SimplesNaoLido("ano-calendário ou CNPJ não encontrados na DEFIS")

    def valor(rotulo: str) -> float | None:
        m = re.search(rf"{rotulo}[^\n]*?R\$\s*({_NUM})", texto)
        return _n(m.group(1)) if m else None

    def inteiro(rotulo: str) -> int | None:
        m = re.search(rf"{rotulo}[^\n]*?(\d+)\s*$", texto, flags=re.M)
        return int(m.group(1)) if m else None

    socios = []
    for bloco in re.split(r"CPF do s\S+cio:", texto)[1:]:
        bloco = bloco.split("2.3 ")[0]
        nome = re.search(r"Nome:\s*(.+)", bloco)
        cpf = re.match(r"\s*([\d.\-*]+)", bloco)
        partic = re.search(r"Percentual de participa\S+o[^\n]*?([\d,]+)%", bloco)
        socios.append({
            "nome": nome.group(1).strip() if nome else None,
            "cpf": apenas_digitos(cpf.group(1)) if cpf else None,
            "participacao": _n(partic.group(1) if partic and "," in partic.group(1) else None) if partic else None,
            "isentos": _n((re.search(rf"Rendimentos isentos[^\n]*?R\$\s*({_NUM})", bloco) or [0, None])[1]) or 0.0,
            "tributaveis": _n((re.search(rf"Rendimentos tribut\S+veis[^\n]*?R\$\s*({_NUM})", bloco) or [0, None])[1]) or 0.0,
        })
    return DEFISAnual(
        cnpj=apenas_digitos(cnpj.group(1)), ano=int(ano.group(1)),
        retificadora="RETIFICADORA" in normalizar_texto(texto[:400]),
        empregados_inicio=inteiro(r"Quantidade de empregados no in\S+cio do per\S+odo abrangido pela"),
        empregados_fim=inteiro(r"Quantidade de empregados no final do per\S+odo abrangido pela"),
        estoque_inicial=valor(r"Estoque inicial"), estoque_final=valor(r"Estoque final"),
        caixa_inicial=valor(r"Saldo em caixa/banco no in\S+cio"), caixa_final=valor(r"Saldo em caixa/banco no final"),
        aquisicoes=valor(r"Total de aquisi\S+es de mercadorias"), importacoes=valor(r"^Importa\S+es"),
        total_entradas=valor(r"Total de entradas no per\S+odo"), total_despesas=valor(r"Total de despesas no per\S+odo"),
        devolucoes_vendas=valor(r"Total de devolu\S+es de vendas"),
        socios=socios,
        proveniencia=Proveniencia(arquivo=arquivo, localizacao=f"DEFIS {ano.group(1)}", metodo=Metodo.PARSER))


def ler_simples(caminho: str | Path, texto: str | None = None) -> ApuracaoPGDAS | DEFISAnual:
    caminho = Path(caminho)
    if texto is None:
        import pdfplumber

        with pdfplumber.open(caminho) as pdf:
            texto = "\n".join((p.extract_text() or "") for p in pdf.pages)
    tipo = identificar(texto)
    if tipo == "pgdas":
        return ler_extrato_pgdas(texto, caminho.name)
    if tipo == "defis":
        return ler_defis(texto, caminho.name)
    raise SimplesNaoLido("recibo de entrega (sem dados)" if tipo == "defis_recibo" else "não é PGDAS-D nem DEFIS")
