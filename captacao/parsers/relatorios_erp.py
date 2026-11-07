"""Relatórios exportados do ERP (.xls/.xlsx): contas a receber, contas a pagar/pagas, faturamento por produto
e estoque com custo. Nível 0 do funil — zero tokens.

O tipo é reconhecido pelas COLUNAS do cabeçalho (não pelo nome do arquivo), para servir a ERPs diferentes
que exportam relatórios parecidos. Estabelecimento (matriz/filial), canal (fulfillment) e mês de referência
vêm do nome do arquivo quando existirem (ex.: "Faturamento Matriz fulfillment 0726.xls" → 2026-07).
"""

from __future__ import annotations

import os
import re
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from captacao.schemas import Metodo, Proveniencia
from captacao.util import brl, normalizar_texto, parse_numero_br

TipoRelatorio = Literal["contas_receber", "contas_pagar", "faturamento_produto", "estoque", "colaboradores_pj",
                        "ranking_clientes", "ranking_produtos"]

ASSINATURAS: dict[TipoRelatorio, list[set[str]]] = {
    # cada conjunto: palavras que precisam aparecer no cabeçalho; ordem importa (o mais específico primeiro)
    "estoque": [{"PRODUTO", "QUANTIDADE", "VALOR UNITARIO"}, {"PRODUTO", "QUANTIDADE", "CUSTO"}],
    "contas_receber": [{"VENCIMENTO", "CLIENTE", "SALDO"}],
    "contas_pagar": [{"VENCIMENTO", "FORNECEDOR", "SALDO"}],
    "colaboradores_pj": [{"VALOR", "SERVICO PRESTADO"}],
    "ranking_clientes": [{"NOME", "NOTAS EMITIDAS", "TOTAL DE VENDA"}, {"CLIENTE", "TOTAL DE VENDA"}],
    "ranking_produtos": [{"PRODUTO", "QUANTIDADE VENDIDA", "TOTAL DE VENDA"}],
    "faturamento_produto": [{"PRODUTO", "QUANTIDADE", "TOTAL"}, {"PRODUTO", "SKU", "VALOR"}],
}
ALERTA_PASSIVO = re.compile(r"DIVIDA ATIVA|DIVITA ATIVA|PGFN|PARCELAMENTO DE (IMPOST|TRIBUT|DEBIT)|REFIS|"
                            r"EXECUCAO FISCAL|AUTO DE INFRACAO")


class RelatorioNaoReconhecido(Exception):
    pass


def abrir_planilha(caminho: str | Path) -> dict[str, list[list]]:
    """{nome da aba: linhas}. .xls de ERPs costuma vir com defeito de formato tolerável."""
    caminho = Path(caminho)
    if caminho.suffix.lower() == ".xls":
        import xlrd

        with open(os.devnull, "w") as nulo:
            wb = xlrd.open_workbook(caminho, ignore_workbook_corruption=True, logfile=nulo)
        return {s.name: [s.row_values(r) for r in range(s.nrows)] for s in wb.sheets()}
    from openpyxl import load_workbook

    wb = load_workbook(caminho, read_only=True, data_only=True)
    abas = {}
    for ws in wb.worksheets:
        if hasattr(ws, "reset_dimensions"):
            ws.reset_dimensions()  # exportações de ERP gravam a área de dados errada (ex.: só 3 colunas)
        abas[ws.title] = [list(r) for r in ws.iter_rows(values_only=True)]
    return abas


def _cab(linha: list) -> list[str]:
    return [normalizar_texto(str(c or "")).replace("(", "").replace(")", "") for c in linha]


def identificar_relatorio(abas: dict[str, list[list]]) -> tuple[TipoRelatorio, str, int] | None:
    """→ (tipo, aba, linha do cabeçalho)."""
    for aba, linhas in abas.items():
        for i, linha in enumerate(linhas[:10]):
            cab = " | ".join(_cab(linha))
            for tipo, conjuntos in ASSINATURAS.items():
                if any(all(p in cab for p in c) for c in conjuntos):
                    return tipo, aba, i
    return None


def _num(v) -> float:
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return parse_numero_br(str(v)) or 0.0
    except ValueError:
        return 0.0


def _data(v) -> date | None:
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    m = re.match(r"(\d{2})/(\d{2})/(\d{4})", str(v or ""))
    return date(int(m.group(3)), int(m.group(2)), int(m.group(1))) if m else None


def _colunas(cabecalho: list) -> dict[str, int]:
    cols: dict[str, int] = {}
    for i, c in enumerate(_cab(cabecalho)):
        if c and c not in cols:  # coluna repetida (tabela auxiliar ao lado): vale a primeira
            cols[c] = i
    return cols


def _achar(cols: dict[str, int], *opcoes: str) -> int | None:
    for op in opcoes:
        for nome, i in cols.items():
            if nome == op or nome.startswith(op):
                return i
    return None


def _contexto_arquivo(nome: str) -> tuple[str | None, str | None, bool]:
    """(estabelecimento, competência, fulfillment) a partir do nome do arquivo."""
    n = normalizar_texto(nome)
    estab = "Matriz" if "MATRIZ" in n else "Filial" if "FILIAL" in n else None
    m = re.search(r"\b(\d{2})(\d{2})\b", n)
    comp = f"20{m.group(2)}-{m.group(1)}" if m and 1 <= int(m.group(1)) <= 12 else None
    return estab, comp, "FULFILLMENT" in n or "FULL" in n.split()


# --------------------------------------------------------------------------- modelos de saída


class Titulo(BaseModel):
    vencimento: date | None
    emissao: date | None
    contraparte: str
    historico: str = ""
    valor: float
    saldo: float  # em aberto
    estabelecimento: str | None = None


class RelatorioERP(BaseModel):
    tipo: TipoRelatorio
    estabelecimento: str | None = None
    competencia: str | None = None
    fulfillment: bool = False
    titulos: list[Titulo] = Field(default_factory=list)  # contas a receber/pagar
    vendas_total: float = 0.0  # faturamento por produto
    devolucoes_total: float = 0.0
    produtos: dict[str, float] = Field(default_factory=dict)  # produto → valor vendido
    estoque_total: float = 0.0
    estoque_itens: int = 0
    estoque_negativos: int = 0  # itens com quantidade negativa (erro de controle)
    estoque_sem_custo: int = 0  # itens com quantidade e custo zero (subavalia o estoque)
    pj_quantidade: int = 0  # prestadores PJ recorrentes (nomes não são guardados)
    pj_total_mensal: float = 0.0
    ranking: list[dict] = Field(default_factory=list)  # clientes/produtos: nome (PF sem nome), valor
    alertas: list[str] = Field(default_factory=list)
    proveniencia: Proveniencia

    def saldo_aberto(self) -> float:
        return round(sum(t.saldo for t in self.titulos), 2)

    def aging(self, data_base: date) -> dict[str, float]:
        faixas = {"vencido": 0.0, "0-30": 0.0, "31-60": 0.0, "61-90": 0.0, "91+": 0.0}
        for t in self.titulos:
            if not t.saldo or not t.vencimento:
                continue
            dias = (t.vencimento - data_base).days
            chave = "vencido" if dias < 0 else "0-30" if dias <= 30 else "31-60" if dias <= 60 else \
                "61-90" if dias <= 90 else "91+"
            faixas[chave] += t.saldo
        return {k: round(v, 2) for k, v in faixas.items()}


def ler_relatorio_erp(caminho: str | Path) -> RelatorioERP:
    caminho = Path(caminho)
    abas = abrir_planilha(caminho)
    achado = identificar_relatorio(abas)
    if not achado:
        raise RelatorioNaoReconhecido("cabeçalho não corresponde a nenhum relatório de ERP conhecido")
    tipo, aba, i_cab = achado
    linhas = abas[aba]
    cols = _colunas(linhas[i_cab])
    estab, comp, full = _contexto_arquivo(caminho.name)
    rel = RelatorioERP(tipo=tipo, estabelecimento=estab, competencia=comp, fulfillment=full,
                       proveniencia=Proveniencia(arquivo=caminho.name, localizacao=aba, metodo=Metodo.PARSER))
    corpo = [l for l in linhas[i_cab + 1:] if any(c not in (None, "") for c in l)]

    if tipo in ("contas_receber", "contas_pagar"):
        iv, ie = _achar(cols, "VENCIMENTO"), _achar(cols, "DATA DE EMISSAO", "EMISSAO")
        ip = _achar(cols, "CLIENTE", "FORNECEDOR")
        ih, ivl, isd = _achar(cols, "HISTORICO"), _achar(cols, "VALOR"), _achar(cols, "SALDO")
        iestab = _achar(cols, "EMPRESA", "ESTABELECIMENTO")
        passivos = defaultdict(float)
        for l in corpo:
            if ip is None or ivl is None or not l[ip]:
                continue
            historico = " ".join(str(l[j]) for j in (ih, _achar(cols, "N DOCUMENTO", "NO DOCUMENTO", "NUMERO DO DOCUMENTO", "DOCUMENTO")) if j is not None and l[j])
            t = Titulo(vencimento=_data(l[iv]) if iv is not None else None,
                       emissao=_data(l[ie]) if ie is not None else None,
                       contraparte=str(l[ip]).strip(), historico=historico.strip(), valor=_num(l[ivl]),
                       saldo=_num(l[isd]) if isd is not None else 0.0,
                       estabelecimento=str(l[iestab]) if iestab is not None and l[iestab] else estab)
            rel.titulos.append(t)
            if tipo == "contas_pagar" and ALERTA_PASSIVO.search(normalizar_texto(f"{t.contraparte} {historico}")):
                passivos[re.sub(r"\s+", " ", normalizar_texto(historico))[:60]] += t.valor
        for desc, v in sorted(passivos.items(), key=lambda kv: -kv[1]):
            rel.alertas.append(f"Pagamento de passivo fiscal: '{desc}' — R$ {brl(v)} no relatório "
                               "(pedir o extrato do parcelamento/dívida ativa)")

    elif tipo == "faturamento_produto":
        ip, it = _achar(cols, "PRODUTO"), _achar(cols, "TOTAL", "VALOR")
        for l in corpo:
            if ip is None or it is None or not l[ip]:
                continue
            rel.produtos[str(l[ip]).strip()] = rel.produtos.get(str(l[ip]).strip(), 0.0) + _num(l[it])
        rel.vendas_total = round(sum(rel.produtos.values()), 2)
        for nome, outras in abas.items():  # aba de devoluções no mesmo arquivo
            if nome != aba and "DEVOLU" in normalizar_texto(nome) and outras:
                c2 = _colunas(outras[0])
                j = _achar(c2, "TOTAL", "VALOR")
                rel.devolucoes_total = round(sum(_num(l[j]) for l in outras[1:] if j is not None and l and l[0]), 2)

    elif tipo in ("ranking_clientes", "ranking_produtos"):
        inome = _achar(cols, "NOME", "CLIENTE", "PRODUTO")
        ivalor = _achar(cols, "PRECO TOTAL DE VENDA", "TOTAL DE VENDA", "VALOR TOTAL")
        idoc = _achar(cols, "CPF/CNPJ", "CPF", "CNPJ")
        for l in corpo:
            if inome is None or ivalor is None or not l[inome]:
                continue
            doc = re.sub(r"\D", "", str(l[idoc] or "")) if idoc is not None else ""
            pf = tipo == "ranking_clientes" and 0 < len(doc) <= 11
            rel.ranking.append({"nome": "Pessoa física" if pf else str(l[inome]).strip(), "documento": None if pf else doc or None,
                                "pessoa_fisica": pf, "valor": _num(l[ivalor])})
        rel.ranking.sort(key=lambda r: -r["valor"])

    elif tipo == "colaboradores_pj":
        iv = _achar(cols, "VALOR")
        valores = [_num(l[iv]) for l in corpo if iv is not None and _num(l[iv]) > 0]
        rel.pj_quantidade, rel.pj_total_mensal = len(valores), round(sum(valores), 2)

    elif tipo == "estoque":
        iq = _achar(cols, "QUANTIDADE")
        iu = _achar(cols, "VALOR UNITARIO", "CUSTO UNITARIO", "CUSTO")
        itot = _achar(cols, "VALOR TOTAL", "TOTAL")
        for l in corpo:
            q = _num(l[iq]) if iq is not None else 0.0
            u = _num(l[iu]) if iu is not None else 0.0
            tot = _num(l[itot]) if itot is not None else q * u
            rel.estoque_itens += 1
            rel.estoque_negativos += q < 0
            rel.estoque_sem_custo += q > 0 and u == 0
            rel.estoque_total += max(tot, 0.0)
        rel.estoque_total = round(rel.estoque_total, 2)
        if rel.estoque_negativos:
            rel.alertas.append(f"{rel.estoque_negativos} item(ns) com quantidade negativa no estoque (controle falho).")
        if rel.estoque_sem_custo:
            rel.alertas.append(f"{rel.estoque_sem_custo} item(ns) com quantidade em estoque e custo zero "
                               "(estoque subavaliado no relatório).")
    return rel
