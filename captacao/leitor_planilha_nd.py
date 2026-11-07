"""Leitor da Planilha ND de Captação preenchida pelo empreendedor.

Usa a mesma definição de abas/colunas que gera o modelo (captacao.planilha_nd.ABAS), então
qualquer mudança no modelo vale automaticamente para a leitura. Nenhum token é gasto.

Uso:
    python -m captacao.leitor_planilha_nd Planilha_preenchida.xlsx [--saida planilha_nd.json]
"""

from __future__ import annotations

import argparse
import re
from datetime import date, datetime
from pathlib import Path

from openpyxl import load_workbook
from pydantic import BaseModel, Field

from captacao.planilha_nd import ABAS, LISTAS, R, Aba, Coluna
from captacao.schemas import GerencialMes, Metodo, Proveniencia
from captacao.util import apenas_digitos, normalizar_texto, parse_numero_br

LINHA_CABECALHO = 4
LIMITE_SIMPLES = 4_800_000.0
ABA_FATURAMENTO = "4_Faturamento"


def chave(titulo: str) -> str:
    """'Saldo devedor hoje (R$)' → 'saldo_devedor_hoje_r' · '% de participação' → 'pct_de_participacao'."""
    return re.sub(r"[^a-z0-9]+", "_", normalizar_texto(titulo.replace("%", " pct ")).lower()).strip("_")


class FaturamentoMes(BaseModel):
    cnpj: str
    competencia: str
    valor: float


class PlanilhaND(BaseModel):
    abas: dict[str, list[dict]] = Field(default_factory=dict)  # aba → linhas {chave_coluna: valor}
    faturamento: list[FaturamentoMes] = Field(default_factory=list)
    observacoes_faturamento: dict[str, str] = Field(default_factory=dict)  # competência → observação
    alertas: list[str] = Field(default_factory=list)
    proveniencia: Proveniencia

    def faturamento_mensal_total(self) -> dict[str, float]:
        tot: dict[str, float] = {}
        for f in self.faturamento:
            tot[f.competencia] = tot.get(f.competencia, 0.0) + f.valor
        return dict(sorted(tot.items()))

    def gerencial(self) -> list[GerencialMes]:
        """Faturamento total do grupo por mês, no formato usado pelo GCI (fonte gerencial)."""
        prov = self.proveniencia.model_copy(update={"localizacao": ABA_FATURAMENTO, "confianca": "media"})
        return [GerencialMes(competencia=c, receita=v, proveniencia=prov)
                for c, v in self.faturamento_mensal_total().items()]

    def cnpjs_grupo(self) -> list[str]:
        return [l["cnpj"] for l in self.abas.get("1_Grupo", []) if l.get("cnpj")]


# --------------------------------------------------------------------------- conversões


def _texto(v) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def _numero(v, onde: str, alertas: list[str]) -> float | None:
    if v is None or (isinstance(v, str) and not v.strip()):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return parse_numero_br(str(v).replace("%", ""))
    except ValueError:
        alertas.append(f"{onde}: número não reconhecido ({v!r}).")
        return None


def _percentual(v: float | None, coluna: Coluna) -> float | None:
    """Excel guarda 5% como 0,05; quem digita '5' numa célula de % gera 5 (= 500%). Normaliza para fração."""
    if v is None:
        return None
    limite = 0.2 if "juros" in coluna.titulo.lower() else 1.0  # juros acima de 20% a.m. é digitação em %
    return v / 100 if v > limite else v


def _competencia(v) -> str | None:
    if isinstance(v, (datetime, date)):
        return f"{v.year:04d}-{v.month:02d}"
    s = _texto(v)
    if not s:
        return None
    m = re.fullmatch(r"(\d{4})[-/](\d{1,2})", s) or re.fullmatch(r"(\d{1,2})[-/](\d{4})", s)
    if not m:
        return None
    a, b = m.groups()
    ano, mes = (a, b) if len(a) == 4 else (b, a)
    return f"{int(ano):04d}-{int(mes):02d}"


def _documento(v, onde: str, alertas: list[str], aceita_cpf: bool = False) -> str | None:
    s = _texto(v)
    if not s:
        return None
    dig = apenas_digitos(s)
    validos = {14, 11} if aceita_cpf else {14}
    if len(dig) not in validos:
        alertas.append(f"{onde}: documento com {len(dig)} dígitos ({s!r}).")
    return dig or s


# --------------------------------------------------------------------------- leitura das abas


def _mapear_cabecalho(ws, aba: Aba, alertas: list[str]) -> dict[int, Coluna]:
    esperado = {normalizar_texto(c.titulo): c for c in aba.colunas}
    mapa: dict[int, Coluna] = {}
    for j, cel in enumerate(ws[LINHA_CABECALHO], start=1):
        titulo = _texto(cel.value)
        if not titulo:
            continue
        col = esperado.get(normalizar_texto(titulo))
        if col:
            mapa[j] = col
        else:
            alertas.append(f"{aba.nome}: coluna desconhecida {titulo!r} ignorada.")
    faltam = [c.titulo for c in aba.colunas if c not in mapa.values()]
    if faltam:
        alertas.append(f"{aba.nome}: colunas não encontradas: {', '.join(faltam)}.")
    return mapa


def _ler_aba(ws, aba: Aba, alertas: list[str]) -> list[dict]:
    mapa = _mapear_cabecalho(ws, aba, alertas)
    linhas = []
    for i, row in enumerate(ws.iter_rows(min_row=LINHA_CABECALHO + 1), start=LINHA_CABECALHO + 1):
        valores = {j: row[j - 1].value for j in mapa if j - 1 < len(row)}
        if all(_texto(v) is None for v in valores.values()):
            continue
        reg: dict = {"_linha": i}
        for j, col in mapa.items():
            v, onde = valores.get(j), f"{aba.nome}!{row[j - 1].column_letter}{i}"
            k = chave(col.titulo)
            if col.formato == R or (col.formato and "%" in col.formato) or k.startswith(("ano", "horas", "parcelas",
                                                                                            "funcionarios", "terceiros",
                                                                                            "duracao", "cliente_desde")):
                n = _numero(v, onde, alertas)
                reg[k] = _percentual(n, col) if col.formato and "%" in col.formato else n
            elif k in {"cnpj", "cnpj_devedor"} or k.startswith("cnpj_ou_cpf"):
                reg[k] = _documento(v, onde, alertas, aceita_cpf=k.startswith("cnpj_ou_cpf"))
            else:
                reg[k] = _texto(v)
            if col.lista and reg[k] is not None and reg[k] not in LISTAS[col.lista]:
                alertas.append(f"{onde}: valor fora da lista ({reg[k]!r}).")
        linhas.append(reg)
    return linhas


def _ler_faturamento(ws, alertas: list[str]) -> tuple[list[FaturamentoMes], dict[str, str]]:
    cab = [_texto(c.value) for c in ws[LINHA_CABECALHO]]
    norm = [normalizar_texto(c or "") for c in cab]
    try:
        j_total = next(j for j, c in enumerate(norm) if c.startswith("TOTAL"))
    except StopIteration:
        alertas.append(f"{ABA_FATURAMENTO}: coluna 'Total (R$)' não encontrada; aba ignorada.")
        return [], {}
    j_obs = next((j for j, c in enumerate(norm) if c.startswith("OBSERVA")), None)
    empresas = {}  # índice da coluna → cnpj
    for j in range(1, j_total):
        titulo = cab[j]
        if not titulo:
            continue
        if normalizar_texto(titulo).startswith("CNPJ EMPRESA"):
            empresas[j] = None  # cabeçalho não trocado pelo CNPJ
        else:
            empresas[j] = _documento(titulo, f"{ABA_FATURAMENTO} cabeçalho", alertas)

    itens, obs, sem_cnpj = [], {}, set()
    for i, row in enumerate(ws.iter_rows(min_row=LINHA_CABECALHO + 1, values_only=True),
                            start=LINHA_CABECALHO + 1):
        comp = _competencia(row[0] if row else None)
        if comp is None:
            if row and any(_texto(v) for v in row[1:j_total]):
                alertas.append(f"{ABA_FATURAMENTO}!A{i}: mês inválido ({row[0]!r}); linha ignorada.")
            continue
        for j, cnpj in empresas.items():
            v = _numero(row[j] if j < len(row) else None, f"{ABA_FATURAMENTO} linha {i}", alertas)
            if v is None:
                continue
            if cnpj is None:
                sem_cnpj.add(cab[j])
                continue
            itens.append(FaturamentoMes(cnpj=cnpj, competencia=comp, valor=v))
        if j_obs is not None and j_obs < len(row) and _texto(row[j_obs]):
            obs[comp] = _texto(row[j_obs])
    for c in sorted(sem_cnpj):
        alertas.append(f"{ABA_FATURAMENTO}: coluna '{c}' tem valores mas o cabeçalho não foi trocado pelo CNPJ; "
                       "valores ignorados.")
    return itens, obs


# --------------------------------------------------------------------------- verificações cruzadas


def _verificar(p: PlanilhaND) -> None:
    a = p.alertas
    grupo = p.abas.get("1_Grupo", [])
    cnpjs = set(p.cnpjs_grupo())
    if not grupo:
        a.append("1_Grupo vazia: o grupo econômico não foi informado.")

    socios = p.abas.get("2_Socios", [])
    participacoes = [s["pct_de_participacao"] for s in socios if s.get("pct_de_participacao") is not None]
    if participacoes and abs(sum(participacoes) - 1) > 0.01:
        a.append(f"2_Socios: participações somam {sum(participacoes):.1%} (esperado 100%).")

    # faturamento: CNPJs fora do grupo, meses sem valor e limite do Simples
    por_cnpj: dict[str, dict[str, float]] = {}
    for f in p.faturamento:
        por_cnpj.setdefault(f.cnpj, {})[f.competencia] = f.valor
    for cnpj in sorted(set(por_cnpj) - cnpjs):
        a.append(f"{ABA_FATURAMENTO}: CNPJ {cnpj} tem faturamento mas não está na aba 1_Grupo.")
    for cnpj in sorted(cnpjs - set(por_cnpj)):
        a.append(f"{ABA_FATURAMENTO}: CNPJ {cnpj} do grupo sem faturamento informado.")

    todos_meses = sorted({f.competencia for f in p.faturamento})
    for cnpj, meses in por_cnpj.items():
        faltam = [m for m in todos_meses if m not in meses and min(meses) <= m <= max(meses)]
        if faltam:
            a.append(f"{ABA_FATURAMENTO}: CNPJ {cnpj} sem valor em {len(faltam)} mês(es) no meio do período "
                     f"({', '.join(faltam[:3])}{'…' if len(faltam) > 3 else ''}).")

    regimes = {l["cnpj"]: l.get("regime_tributario") for l in grupo if l.get("cnpj")}
    if todos_meses:
        ult12 = todos_meses[-12:]
        for cnpj, meses in por_cnpj.items():
            rbt12 = sum(meses.get(m, 0.0) for m in ult12)
            if regimes.get(cnpj) == "Simples Nacional" and rbt12 > LIMITE_SIMPLES:
                a.append(f"CNPJ {cnpj} no Simples com faturamento informado de R$ {rbt12:,.0f} nos últimos 12 meses "
                         f"(limite R$ {LIMITE_SIMPLES:,.0f}).".replace(",", "."))
        total12 = sum(p.faturamento_mensal_total().get(m, 0.0) for m in ult12)
        no_simples = [c for c, r in regimes.items() if r == "Simples Nacional"]
        if len(no_simples) > 1 and total12 > LIMITE_SIMPLES:
            a.append(f"Grupo com {len(no_simples)} CNPJs no Simples e faturamento somado de R$ {total12:,.0f} em 12 "
                     "meses: possível divisão para ficar no Simples (verificar grupo econômico)."
                     .replace(",", "."))


# --------------------------------------------------------------------------- entrada


def ler_planilha_nd(caminho: str | Path) -> PlanilhaND:
    caminho = Path(caminho)
    wb = load_workbook(caminho, data_only=True)
    alertas: list[str] = []
    abas: dict[str, list[dict]] = {}
    faturamento, obs = [], {}
    for aba in ABAS:
        if aba.nome not in wb.sheetnames:
            alertas.append(f"Aba {aba.nome} não encontrada (renomeada ou apagada).")
            continue
        ws = wb[aba.nome]
        if aba.nome == ABA_FATURAMENTO:
            faturamento, obs = _ler_faturamento(ws, alertas)
        else:
            abas[aba.nome] = _ler_aba(ws, aba, alertas)
    p = PlanilhaND(abas=abas, faturamento=faturamento, observacoes_faturamento=obs, alertas=alertas,
                   proveniencia=Proveniencia(arquivo=caminho.name, metodo=Metodo.PARSER))
    _verificar(p)
    return p


def main() -> None:
    ap = argparse.ArgumentParser(description="Lê a Planilha ND de Captação preenchida")
    ap.add_argument("arquivo")
    ap.add_argument("--saida", help="grava o resultado em JSON")
    args = ap.parse_args()
    p = ler_planilha_nd(args.arquivo)
    if args.saida:
        Path(args.saida).write_text(p.model_dump_json(indent=2), encoding="utf-8")
    for nome, linhas in p.abas.items():
        print(f"{nome:14} {len(linhas):3} linha(s)")
    meses = p.faturamento_mensal_total()
    if meses:
        print(f"{ABA_FATURAMENTO:14} {len(meses):3} mês(es), {len({f.cnpj for f in p.faturamento})} CNPJ(s), "
              f"total R$ {sum(meses.values()):,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
    for al in p.alertas:
        print(f"ALERTA: {al}")


if __name__ == "__main__":
    main()
