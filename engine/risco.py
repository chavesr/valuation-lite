"""Score de Risco do Negócio → taxa de desconto (Selic + prêmio) e horizonte do DCF.

Metodologia da boutique: taxa total entre 20% e 35% a.a. (metodologia/parametros_valuation.json);
horizonte de 3 a 5 anos.
Notas por dimensão na escala da ND: 5 = melhor (risco mínimo) ... 1 = pior (risco máximo).
O Score continua sendo de risco: 0 = menor risco, 100 = maior risco.
"""

from __future__ import annotations

from pydantic import BaseModel

PESOS = {
    "confiabilidade_informacao": 15,
    "dependencia_dono": 15,
    "concentracao_clientes": 10,
    "recorrencia_receita": 10,
    "historico_mercado": 10,
    "estabilidade_resultados": 10,
    "endividamento_liquidez": 10,
    "contingencias": 10,
    "setor_posicao_competitiva": 10,
}
assert sum(PESOS.values()) == 100

def _faixa_taxa() -> tuple[float, float, float]:
    import json
    from pathlib import Path

    arq = Path(__file__).resolve().parents[1] / "metodologia" / "parametros_valuation.json"
    try:
        t = json.loads(arq.read_text(encoding="utf-8"))["taxa_desconto"]
        return t["minima"], t["maxima"], t["premio_minimo_sobre_selic"]
    except (OSError, KeyError, ValueError):
        return 0.20, 0.35, 0.05


TAXA_MIN, TAXA_MAX, _PREMIO_MIN = _faixa_taxa()
PREMIO_MINIMO_SOBRE_SELIC = _PREMIO_MIN
SCORE_MAX_PERPETUIDADE = 30


class ResultadoRisco(BaseModel):
    score: float
    pontos_por_dimensao: dict[str, float]
    taxa_desconto: float
    selic: float
    premio_implicito: float
    horizonte_anos: int
    perpetuidade_permitida_pelo_score: bool


NOTA_MAXIMA_POR_NIVEL = {"A": 5, "B": 3, "C": 2}


def nota_gci(indice_gci: float, nivel: str | None = None) -> int:
    """Converte o GCI (índice 0–100, maior = melhor) em nota 1–5 (5 = melhor).

    O nível impõe uma nota máxima: uma empresa rebaixada a C por informalidade (ex.: 40% da
    receita sem nota) não pode ter nota boa só porque as demais fontes batem entre si.
    """
    nota = 1
    for limite, n in ((85, 5), (75, 4), (60, 3), (50, 2)):
        if indice_gci >= limite:
            nota = n
            break
    return min(nota, NOTA_MAXIMA_POR_NIVEL.get(nivel, 5))


def calcular_score(notas: dict[str, int]) -> tuple[float, dict[str, float]]:
    faltantes = set(PESOS) - set(notas)
    if faltantes:
        raise ValueError(f"notas ausentes: {sorted(faltantes)}")
    pontos = {}
    for dimensao, nota in notas.items():
        if dimensao not in PESOS:
            raise ValueError(f"dimensão desconhecida: {dimensao}")
        if not 1 <= nota <= 5:
            raise ValueError(f"nota fora de 1–5 em {dimensao}: {nota}")
        pontos[dimensao] = PESOS[dimensao] * (5 - nota) / 4
    return round(sum(pontos.values()), 2), pontos


def taxa_desconto(score: float, selic: float) -> tuple[float, float]:
    """Retorna (taxa total, prêmio implícito sobre a Selic)."""
    taxa = TAXA_MIN + (TAXA_MAX - TAXA_MIN) * score / 100
    taxa = max(taxa, selic + PREMIO_MINIMO_SOBRE_SELIC)
    return round(taxa, 4), round(taxa - selic, 4)


def horizonte(score: float) -> int:
    if score <= 35:
        return 5
    if score <= 65:
        return 4
    return 3


def fator_anuidade(taxa: float, anos: int) -> float:
    """Valor presente de 1 por ano durante `anos` — usado na checagem de sanidade do múltiplo."""
    return (1 - (1 + taxa) ** -anos) / taxa


def avaliar_risco(notas: dict[str, int], selic: float) -> ResultadoRisco:
    score, pontos = calcular_score(notas)
    taxa, premio = taxa_desconto(score, selic)
    return ResultadoRisco(
        score=score,
        pontos_por_dimensao=pontos,
        taxa_desconto=taxa,
        selic=selic,
        premio_implicito=premio,
        horizonte_anos=horizonte(score),
        perpetuidade_permitida_pelo_score=score <= SCORE_MAX_PERPETUIDADE,
    )
