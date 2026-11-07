"""F3 — Grau de Confiabilidade da Informação (GCI).

Triangula a receita entre caixa (extratos), fisco (PGDAS), contabilidade (DRE) e gerencial, mede a
cobertura documental e devolve um índice de 0 a 100 (100 = mais confiável) e o nível A/B/C, que
define o caminho da análise. Os limites abaixo são iniciais e devem ser calibrados com os cases.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Literal

from pydantic import BaseModel

from captacao.classificacao import pct_creditos_nao_classificados, receita_caixa_mensal
from captacao.schemas import DadosBrutos
from captacao.util import meses_entre

LIMITE_SIMPLES = 4_800_000.0

# penalidade = peso × fração entre (tolerância → saturação)
PARAMETROS = {
    "gap_fiscal": {"peso": 40, "tolerancia": 0.05, "saturacao": 0.50},
    "div_contabil": {"peso": 15, "tolerancia": 0.05, "saturacao": 0.40, "ausente": 10},
    "div_gerencial": {"peso": 10, "tolerancia": 0.10, "saturacao": 0.50, "ausente": 5},
    "cobertura_extratos": {"peso": 20},
    "cobertura_pgdas": {"peso": 10},
    "nao_classificado": {"peso": 10, "tolerancia": 0.02, "saturacao": 0.30},
}
NIVEL_A_MIN, NIVEL_B_MIN = 75, 50
GAP_MAX_NIVEL_A, GAP_MIN_NIVEL_C = 0.10, 0.35


class ResultadoGCI(BaseModel):
    indice: float
    nivel: Literal["A", "B", "C"]
    metricas: dict[str, float | None]
    penalidades: dict[str, float]
    receita_caixa_12m: float
    receita_fiscal_12m: float
    receita_nao_declarada_12m: float
    excede_limite_simples: bool
    alertas: list[str]


def _penalidade(valor: float | None, p: dict) -> float:
    if valor is None:
        return float(p.get("ausente", 0))
    fracao = (abs(valor) - p["tolerancia"]) / (p["saturacao"] - p["tolerancia"])
    return round(p["peso"] * min(max(fracao, 0.0), 1.0), 2)


def _soma(serie: dict[str, float], meses: list[str]) -> float:
    return sum(serie.get(m, 0.0) for m in meses)


def calcular_gci(dados: DadosBrutos) -> ResultadoGCI:
    meses = meses_entre(dados.periodo_inicio, dados.periodo_fim)
    ultimos_12 = meses[-12:]
    alertas: list[str] = []

    caixa = receita_caixa_mensal(dados.extratos)
    fiscal: dict[str, float] = defaultdict(float)
    for p in dados.pgdas:
        fiscal[p.competencia] += p.receita_bruta
    for f in dados.fiscal_mensal:
        fiscal[f.competencia] += f.receita_bruta - f.devolucoes
    gerencial: dict[str, float] = defaultdict(float)
    for g in dados.gerencial:
        if g.cliente is None:
            gerencial[g.competencia] += g.receita
    contabil_anual: dict[int, float] = defaultdict(float)
    for d in dados.dres:
        if d.receita_bruta is not None and d.meses == 12:
            contabil_anual[d.exercicio] += d.receita_bruta

    meses_com_extrato = {m for e in dados.extratos for t in e.transacoes
                         if (m := f"{t.data.year:04d}-{t.data.month:02d}") in meses}
    cobertura_extratos = len(meses_com_extrato) / len(meses)
    cobertura_pgdas = len([m for m in meses if m in fiscal]) / len(meses)

    # caixa x fiscal (positivo = recebido acima do declarado)
    meses_cf = [m for m in meses if m in fiscal and m in meses_com_extrato]
    caixa_cf, fiscal_cf = _soma(caixa, meses_cf), _soma(fiscal, meses_cf)
    gap_fiscal = (caixa_cf - fiscal_cf) / caixa_cf if caixa_cf else None
    fonte_declarada = "PGDAS" if dados.pgdas or not dados.fiscal_mensal else dados.fiscal_mensal[0].fonte
    if gap_fiscal is None and not dados.pgdas and not dados.fiscal_mensal:
        # fora do Simples (ou sem PGDAS): compara o caixa com a DRE contábil de um período coberto pelos extratos
        for d in sorted(dados.dres, key=lambda d: -d.exercicio):
            if not d.receita_bruta or (d.proveniencia.localizacao or "").startswith(("gerencial", "comparativo")):
                continue
            meses_dre = [f"{d.exercicio}-{m:02d}" for m in range(13 - d.meses if d.meses == 12 else 1, d.meses + 1)]
            if all(m in meses_com_extrato for m in meses_dre):
                caixa_dre = _soma(caixa, meses_dre)
                if caixa_dre:
                    gap_fiscal = (caixa_dre - d.receita_bruta) / caixa_dre
                    fonte_declarada = f"DRE contábil {meses_dre[0]} a {meses_dre[-1]}"
                    alertas.append(f"Sem PGDAS: caixa comparado com a {fonte_declarada} (receita bruta "
                                   f"R$ {d.receita_bruta:,.0f} × créditos operacionais R$ {caixa_dre:,.0f})."
                                   .replace(",", "."))
                    break

    # contábil x fiscal (anos completos), ou contábil x caixa se não houver PGDAS do ano
    divergencias_contabeis = []
    for ano, valor in contabil_anual.items():
        meses_ano = [f"{ano}-{m:02d}" for m in range(1, 13)]
        if all(m in fiscal for m in meses_ano):
            base = _soma(fiscal, meses_ano)
        elif all(m in meses_com_extrato for m in meses_ano):
            base = _soma(caixa, meses_ano)
        else:
            continue
        if base:
            divergencias_contabeis.append(abs(valor - base) / base)
    div_contabil = max(divergencias_contabeis) if divergencias_contabeis else None

    # gerencial x caixa
    meses_gc = [m for m in meses if m in gerencial and m in meses_com_extrato]
    caixa_gc = _soma(caixa, meses_gc)
    div_gerencial = abs(_soma(gerencial, meses_gc) - caixa_gc) / caixa_gc if caixa_gc else None

    nao_class = pct_creditos_nao_classificados(dados.extratos)

    p = PARAMETROS
    penalidades = {
        "gap_fiscal": _penalidade(gap_fiscal, p["gap_fiscal"]) if gap_fiscal is not None else 25.0,
        "div_contabil": _penalidade(div_contabil, p["div_contabil"]),
        "div_gerencial": _penalidade(div_gerencial, p["div_gerencial"]),
        "cobertura_extratos": round((1 - cobertura_extratos) * p["cobertura_extratos"]["peso"], 2),
        # sem PGDAS mas com DRE contábil cobrindo o período dos extratos: a DRE substitui o PGDAS
        "cobertura_pgdas": 0.0 if fonte_declarada.startswith("DRE") else
        round((1 - cobertura_pgdas) * p["cobertura_pgdas"]["peso"], 2),
        "nao_classificado": _penalidade(nao_class, p["nao_classificado"]),
    }
    indice = round(max(0.0, 100 - sum(penalidades.values())), 1)

    nivel: Literal["A", "B", "C"] = "A" if indice >= NIVEL_A_MIN else "B" if indice >= NIVEL_B_MIN else "C"
    if gap_fiscal is None:
        nivel = "C"
        alertas.append("Sem extratos ou PGDAS no mesmo período: receita real não pôde ser triangulada.")
    else:
        if abs(gap_fiscal) > GAP_MAX_NIVEL_A and nivel == "A":
            nivel = "B"
        if abs(gap_fiscal) > GAP_MIN_NIVEL_C:
            nivel = "C"
        if gap_fiscal > 0.05:
            alertas.append(f"Receita em conta {gap_fiscal:.0%} acima da declarada ({fonte_declarada}) "
                           "(possível venda sem nota ou crédito não operacional mal classificado).")
        elif gap_fiscal < -0.05:
            alertas.append(f"Receita declarada ({fonte_declarada}) {-gap_fiscal:.0%} acima da recebida em conta "
                           "(possíveis contas bancárias não informadas ou recebimento em espécie).")

    caixa_12 = _soma(caixa, ultimos_12)
    fiscal_12 = _soma(fiscal, ultimos_12)
    nao_declarada_12 = sum(max(0.0, caixa.get(m, 0.0) - fiscal.get(m, 0.0))
                           for m in ultimos_12 if m in fiscal)
    excede = bool(dados.pgdas) and max(caixa_12, fiscal_12) > LIMITE_SIMPLES  # só faz sentido no Simples
    if excede:
        valor_12 = f"{max(caixa_12, fiscal_12):,.0f}".replace(",", ".")
        alertas.append(f"Receita consolidada dos últimos 12 meses (R$ {valor_12}) acima "
                       "do limite do Simples: projetar com o regime tributário que o comprador teria.")
    raizes = {"".join(ch for ch in c.cnpj if ch.isdigit())[:8] for c in dados.empresa.cnpjs}
    if len(raizes) > 1:
        alertas.append(f"Grupo econômico com {len(raizes)} empresas ({len(dados.empresa.cnpjs)} estabelecimentos): "
                       "análise consolidada.")
    elif len(dados.empresa.cnpjs) > 1:
        alertas.append(f"Empresa com {len(dados.empresa.cnpjs)} estabelecimentos (matriz e filiais): análise "
                       "consolidada.")
    if cobertura_extratos < 1:
        alertas.append(f"Extratos cobrem {cobertura_extratos:.0%} dos meses do período.")
    if nao_class > 0.05:
        alertas.append(f"{nao_class:.0%} do valor creditado ainda não classificado (enviar à IA/analista).")

    return ResultadoGCI(
        indice=indice,
        nivel=nivel,
        metricas={
            "gap_fiscal": None if gap_fiscal is None else round(gap_fiscal, 4),
            "div_contabil": None if div_contabil is None else round(div_contabil, 4),
            "div_gerencial": None if div_gerencial is None else round(div_gerencial, 4),
            "cobertura_extratos": round(cobertura_extratos, 4),
            "cobertura_pgdas": round(cobertura_pgdas, 4),
            "nao_classificado": round(nao_class, 4),
        },
        penalidades=penalidades,
        receita_caixa_12m=round(caixa_12, 2),
        receita_fiscal_12m=round(fiscal_12, 2),
        receita_nao_declarada_12m=round(nao_declarada_12, 2),
        excede_limite_simples=excede,
        alertas=alertas,
    )
