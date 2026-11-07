"""Leitor do SPED Fiscal — EFD ICMS/IPI (.txt, também dentro de .zip). Nível 0 do funil: zero tokens.

O arquivo é texto delimitado por '|', um registro por linha. Usamos:
  0000  cabeçalho: período, CNPJ do estabelecimento, finalidade (0 = original, 1 = substituto)
  0150  participantes (clientes/fornecedores)
  C100  nota fiscal (entrada/saída, situação, participante)   → C190: totais da nota por CST/CFOP
  E110  apuração do ICMS                                         H005: inventário (quando houver)

O CFOP de cada C190 separa o que é VENDA do que é TRANSFERÊNCIA entre estabelecimentos (matriz × filial),
DEVOLUÇÃO, COMPRA e REMESSA. Para empresas fora do Simples, a venda líquida mensal é a "receita
declarada" que o GCI compara com o caixa (o papel que o PGDAS cumpre no Simples).
"""

from __future__ import annotations

import html
import re
import zipfile
from collections import defaultdict
from pathlib import Path

from pydantic import BaseModel, Field

from captacao.schemas import Metodo, Proveniencia

CANCELADAS = {"02", "03", "04", "05"}  # cancelada, cancelada extemporânea, denegada, inutilizada

# sufixo do CFOP (3 últimos dígitos) → natureza
VENDA = {f"{n}" for n in range(101, 126)} | {"401", "402", "403", "405", "501", "502", "651", "652", "653",
                                               "654", "655", "656", "933"}
TRANSFERENCIA = {"151", "152", "153", "155", "156", "208", "209", "408", "409", "552", "557", "658", "659"}
DEVOLUCAO = {"201", "202", "203", "204", "410", "411", "660", "661", "662", "918", "919"}
COMPRA = {"101", "102", "111", "113", "116", "117", "118", "120", "121", "122", "126", "128", "401", "403", "406",
          "407", "551", "556", "651", "652", "653"}


class EFDNaoLido(Exception):
    pass


class Participante(BaseModel):
    codigo: str
    nome: str
    documento: str | None = None
    pessoa_fisica: bool = False
    valor: float = 0.0


class EFDMensal(BaseModel):
    cnpj: str
    nome: str
    uf: str | None
    competencia: str
    substituto: bool
    vendas: float = 0.0  # saídas com CFOP de venda (notas não canceladas)
    devolucoes_venda: float = 0.0  # entradas de devolução de venda
    transferencias_saida: float = 0.0  # para outro estabelecimento/empresa do grupo
    transferencias_entrada: float = 0.0
    devolucoes_compra: float = 0.0
    outras_saidas: float = 0.0  # remessas, conserto, demonstração, bonificação…
    compras: float = 0.0
    importacoes: float = 0.0  # compras com CFOP 3xxx (parte de `compras`)
    outras_entradas: float = 0.0
    notas_saida: int = 0
    notas_canceladas: int = 0
    icms_a_recolher: float | None = None
    estoque_declarado: float | None = None
    por_cfop: dict[str, float] = Field(default_factory=dict)
    clientes: list[Participante] = Field(default_factory=list)  # por valor de venda, decrescente
    fornecedores: list[Participante] = Field(default_factory=list)
    proveniencia: Proveniencia

    @property
    def venda_liquida(self) -> float:
        return round(self.vendas - self.devolucoes_venda, 2)


def _num(txt: str) -> float:
    return float(txt.replace(".", "").replace(",", ".")) if txt else 0.0


def _competencia(ddmmaaaa: str) -> str:
    return f"{ddmmaaaa[4:8]}-{ddmmaaaa[2:4]}"


def eh_efd_icms(primeira_linha: str) -> bool:
    campos = primeira_linha.strip().split("|")
    return len(campos) > 8 and campos[1] == "0000" and re.fullmatch(r"\d{3}", campos[2] or "") is not None \
        and re.fullmatch(r"\d{8}", campos[4] or "") is not None and campos[2] != "LECD"


def ler_efd_texto(texto: str, arquivo: str) -> EFDMensal:
    linhas = texto.splitlines()
    if not linhas or not eh_efd_icms(linhas[0]):
        raise EFDNaoLido("não é EFD ICMS/IPI (registro 0000 não reconhecido)")
    c0 = linhas[0].split("|")
    efd = EFDMensal(cnpj=c0[7], nome=c0[6], uf=c0[9] or None, competencia=_competencia(c0[4]),
                    substituto=c0[3] == "1",
                    proveniencia=Proveniencia(arquivo=arquivo, localizacao="EFD ICMS/IPI", metodo=Metodo.PARSER))
    participantes: dict[str, tuple[str, str | None, bool]] = {}
    por_cfop: dict[str, float] = defaultdict(float)
    vendas_part: dict[str, float] = defaultdict(float)
    compras_part: dict[str, float] = defaultdict(float)
    nota: list[str] | None = None
    for linha in linhas:
        c = linha.split("|")
        if len(c) < 3:
            continue
        reg = c[1]
        if reg == "0150":
            doc = c[5] or c[6] or None
            participantes[c[2]] = (html.unescape(c[3]).strip(), doc, bool(c[6]) and not c[5])
        elif reg == "C100":
            nota = c
            if c[2] == "1" and c[3] == "0":
                efd.notas_saida += 1
                if c[6] in CANCELADAS:
                    efd.notas_canceladas += 1
        elif reg == "C190" and nota is not None:
            if nota[6] in CANCELADAS:
                continue
            cfop, valor = c[3], _num(c[5])
            por_cfop[cfop] += valor
            sufixo, saida = cfop[1:], cfop[:1] in "567"
            if saida:
                if sufixo in VENDA:
                    efd.vendas += valor
                    vendas_part[nota[4]] += valor
                elif sufixo in TRANSFERENCIA:
                    efd.transferencias_saida += valor
                elif sufixo in DEVOLUCAO:
                    efd.devolucoes_compra += valor
                else:
                    efd.outras_saidas += valor
            else:
                if sufixo in DEVOLUCAO:
                    efd.devolucoes_venda += valor
                elif sufixo in TRANSFERENCIA:
                    efd.transferencias_entrada += valor
                elif sufixo in COMPRA:
                    efd.compras += valor
                    compras_part[nota[4]] += valor
                    if cfop.startswith("3"):
                        efd.importacoes += valor
                else:
                    efd.outras_entradas += valor
        elif reg == "E110" and len(c) > 13:
            efd.icms_a_recolher = _num(c[13])
        elif reg == "H005" and len(c) > 3:
            efd.estoque_declarado = (efd.estoque_declarado or 0.0) + _num(c[3])

    def ranking(valores: dict[str, float]) -> list[Participante]:
        saida = []
        for cod, v in sorted(valores.items(), key=lambda kv: -kv[1]):
            nome, doc, pf = participantes.get(cod, (cod, None, False))
            saida.append(Participante(codigo=cod, nome=nome, documento=doc, pessoa_fisica=pf, valor=round(v, 2)))
        return saida

    for campo in ("vendas", "devolucoes_venda", "transferencias_saida", "transferencias_entrada", "devolucoes_compra",
                  "outras_saidas", "compras", "importacoes", "outras_entradas"):
        setattr(efd, campo, round(getattr(efd, campo), 2))
    efd.por_cfop = {k: round(v, 2) for k, v in sorted(por_cfop.items())}
    efd.clientes = ranking(vendas_part)
    efd.fornecedores = ranking(compras_part)
    return efd


def _decodificar(dados: bytes) -> str:
    for cod in ("utf-8", "latin-1"):
        try:
            return dados.decode(cod)
        except UnicodeDecodeError:
            continue
    return dados.decode("latin-1", errors="replace")


def ler_efd(caminho: str | Path) -> list[EFDMensal]:
    """Lê um .txt de EFD ou todos os EFD de dentro de um .zip (sem extrair na pasta)."""
    caminho = Path(caminho)
    if caminho.suffix.lower() == ".zip":
        saida = []
        with zipfile.ZipFile(caminho) as zf:
            for info in zf.infolist():
                if info.is_dir() or "__MACOSX" in info.filename or not info.filename.lower().endswith(".txt"):
                    continue
                with zf.open(info) as f:
                    primeira = _decodificar(f.readline())
                if eh_efd_icms(primeira):
                    saida.append(ler_efd_texto(_decodificar(zf.read(info)),
                                               f"{caminho.name}/{Path(info.filename).name}"))
        if not saida:
            raise EFDNaoLido("o .zip não contém EFD ICMS/IPI")
        return saida
    return [ler_efd_texto(_decodificar(caminho.read_bytes()), caminho.name)]


def consolidar(efds: list[EFDMensal]) -> list[EFDMensal]:
    """Um arquivo por estabelecimento e mês: o substituto (retificadora) prevalece sobre o original."""
    escolhidos: dict[tuple[str, str], EFDMensal] = {}
    for e in efds:
        atual = escolhidos.get((e.cnpj, e.competencia))
        if atual is None or (e.substituto and not atual.substituto):
            escolhidos[(e.cnpj, e.competencia)] = e
    return sorted(escolhidos.values(), key=lambda e: (e.competencia, e.cnpj))


def concentracao_clientes(efds: list[EFDMensal], raiz_cnpj_grupo: set[str] | None = None) -> dict:
    """Concentração de vendas entre clientes EMPRESA (todos os estabelecimentos do grupo, sem transferências
    internas). Vendas a pessoas físicas são varejo/e-commerce pulverizado: entram só como participação total."""
    pj: dict[str, float] = defaultdict(float)
    nomes: dict[str, str] = {}
    pf = 0.0
    for e in efds:
        for p in e.clientes:
            if raiz_cnpj_grupo and p.documento and p.documento[:8] in raiz_cnpj_grupo:
                continue
            if p.pessoa_fisica:
                pf += p.valor
                continue
            chave = p.documento or p.nome
            pj[chave] += p.valor
            nomes[chave] = p.nome
    total = sum(pj.values()) + pf
    ranking = sorted(pj.items(), key=lambda kv: -kv[1])
    if not total:
        return {"total_vendas": 0.0, "clientes_pj": 0, "pessoas_fisicas": 0.0, "maior": 0.0, "top5": 0.0,
                "top10": 0.0, "ranking": []}
    return {
        "total_vendas": round(total, 2),
        "clientes_pj": len(pj),
        "pessoas_fisicas": round(pf / total, 4),  # participação das vendas a consumidor final
        "maior": round(ranking[0][1] / total, 4) if ranking else 0.0,
        "top5": round(sum(v for _, v in ranking[:5]) / total, 4),
        "top10": round(sum(v for _, v in ranking[:10]) / total, 4),
        "ranking": [{"cliente": nomes[k], "valor": round(v, 2), "participacao": round(v / total, 4)}
                    for k, v in ranking[:10]],
    }
