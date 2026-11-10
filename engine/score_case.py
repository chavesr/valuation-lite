"""Notas do Score de Risco (escala da ND: 5 = melhor/risco mínimo … 1 = pior/risco máximo) a partir dos dados do case.

Dimensões objetivas são calculadas por código. Dimensões de julgamento usam o questionário quando houver
resposta; sem informação, recebem nota NEUTRA (3) marcada como pendente — "não sei" não é "ruim"; a taxa
fica provisória, com a faixa possível mostrada no relatório (Checkpoint: o analista — e, mais
tarde, o agente da F5 — decide em _valuation/score_notas.json).
"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel

from engine.gci import ResultadoGCI
from engine.normalizacao import DREEconomica
from engine.risco import PESOS, nota_gci


class NotaDimensao(BaseModel):
    dimensao: str
    nota: int
    origem: str  # "código", "questionário", "padrão conservador", "analista"
    evidencia: str
    pendente: bool = False


def _faixa(valor: float, limites: list[float]) -> int:
    """limites crescentes → nível 1..5 (valor ≤ limites[i] → nível i+1). Nível alto = valor alto, não nota."""
    for i, lim in enumerate(limites):
        if valor <= lim:
            return i + 1
    return 5


def _ultimo_balanco(dados):
    return max((b for b in dados.balancos if b.data_base), key=lambda b: b.data_base, default=None)


def excluir_haveres_socios(dados, decisoes: dict | None) -> float:
    """Decisão do analista (valuation_decisoes.json → haveres_socios_fora_da_divida.ativo): dívida da empresa com sócio
    ou ex-sócio (dividendos a pagar, haveres, mútuo) que é lançamento contábil e não dívida da operação. Zera
    `mutuos_socios` no último balanço, em memória, para o Score, a ponte e a liquidação (10/11/2026, Vedis: caminho B).
    → valor excluído (0 se a decisão não está ativa)."""
    d = (decisoes or {}).get("haveres_socios_fora_da_divida") or {}
    bp = _ultimo_balanco(dados)
    if not d.get("ativo") or not bp or not bp.mutuos_socios:
        return 0.0
    valor, bp.mutuos_socios = bp.mutuos_socios, 0.0
    return round(valor, 2)


def divida_liquida(dados) -> tuple[float, float, str]:
    """→ (dívida bruta, caixa, fonte). Dívida dos extratos bancários quando houver (mais atual), senão do Balanço."""
    bp = _ultimo_balanco(dados)
    caixa = (bp.caixa_aplicacoes or 0.0) if bp else 0.0
    if not bp and getattr(dados, "defis", None):
        caixa = max(dados.defis, key=lambda d: d.ano).caixa_final or 0.0
    if getattr(dados, "dividas", None):
        bruta = sum(d.saldo_devedor for d in dados.dividas)
        fonte = f"{len(dados.dividas)} contrato(s) bancário(s)"
        if bp:
            bruta += (bp.parcelamentos_fiscais or 0) + (bp.mutuos_socios or 0)
        return round(bruta, 2), round(caixa, 2), fonte
    if bp:
        bruta = sum(x or 0 for x in (bp.emprestimos_cp, bp.emprestimos_lp, bp.parcelamentos_fiscais, bp.mutuos_socios))
        return round(bruta, 2), round(caixa, 2), f"Balanço de {bp.data_base:%d/%m/%Y}"
    return 0.0, round(caixa, 2), "sem Balanço nem extrato de dívidas"


def propor_notas(dados, gci: ResultadoGCI | None, dres: list[DREEconomica], base: DREEconomica | None) -> dict[str, NotaDimensao]:
    q = getattr(dados, "questionario", None)
    notas: dict[str, NotaDimensao] = {}

    def put(dim, nota, origem, evid, pendente=False):
        notas[dim] = NotaDimensao(dimensao=dim, nota=nota, origem=origem, evidencia=evid, pendente=pendente)

    # 1. confiabilidade da informação
    if gci:
        put("confiabilidade_informacao", nota_gci(gci.indice, gci.nivel), "código", f"GCI {gci.indice:.1f}, nível {gci.nivel}")
    else:
        put("confiabilidade_informacao", 2, "sem informação", "GCI não calculado (sem extratos nem fonte fiscal)", True)

    # 2. dependência do dono
    q08 = q.valor("Q08") if q else None
    mapa = {"Funcionaria normalmente": 5, "Funcionaria com perda pequena": 4, "Perderia vendas relevantes": 2, "Pararia": 1}
    if q08 in mapa:
        n = mapa[q08] + (1 if q and q.valor("Q09a") == "Sim" and mapa[q08] < 5 else 0)
        put("dependencia_dono", n, "questionário", f"Q08 '{q08}'; gerente com autonomia: {q.valor('Q09a') or '?'}", True)
    else:
        put("dependencia_dono", 3, "sem informação (neutra)", "sem resposta do questionário (Q08/Q09) nem entrevista", True)

    # 3. concentração de clientes
    conc = getattr(dados, "concentracao_clientes", None) or {}
    rank = ((getattr(dados, "erp", None) or {}).get("ranking_clientes") or {})
    if conc.get("total_vendas"):
        maior, fonte = conc["maior"], "SPED Fiscal (clientes empresa)"
    elif rank:
        maior, fonte = rank["maior"], "ranking de clientes do ERP"
    elif q and isinstance(q.valor("Q12a"), (int, float)):
        maior, fonte = q.valor("Q12a") / 100, "questionário Q12"
    else:
        maior, fonte = None, None
    if maior is not None:
        put("concentracao_clientes", 6 - _faixa(maior, [0.05, 0.10, 0.20, 0.35]), "código", f"maior cliente {maior:.1%} ({fonte})")
    else:
        put("concentracao_clientes", 3, "sem informação (neutra)", "sem dado de clientes", True)

    # 4. recorrência
    q13 = q.valor("Q13") if q else None
    if isinstance(q13, (int, float)):
        put("recorrencia_receita", _faixa(q13 / 100, [0.10, 0.30, 0.50, 0.70]) if q13 < 100 else 5, "questionário",
            f"{q13:.0f}% da receita recorrente (Q13)", True)
    else:
        put("recorrencia_receita", 3, "sem informação (neutra)", "sem informação de contratos/recorrência", True)

    # 5. histórico e tempo de mercado
    inicio = None
    if q and isinstance(q.valor("Q01"), (int, float)):
        inicio = int(q.valor("Q01"))
    abertura = (getattr(dados, "simples", None) or {}).get("abertura")
    if inicio is None and abertura:
        inicio = date.fromisoformat(str(abertura)).year
    if inicio:
        anos = date.today().year - inicio
        put("historico_mercado", _faixa(anos, [3, 5, 10, 20]) if anos < 21 else 5, "código", f"{anos} anos de operação")
    else:
        put("historico_mercado", 3, "sem informação (neutra)", "data de início não informada", True)

    # 6. estabilidade de resultados
    margens = [d.margem_ebitda for d in dres if d.margem_ebitda is not None and d.confianca != "baixa"] or \
        [d.margem_ebitda for d in dres if d.margem_ebitda is not None]
    if len(margens) >= 2:
        amplitude = max(margens) - min(margens)
        n = 6 - _faixa(amplitude, [0.03, 0.06, 0.10, 0.15])
        if min(margens) < 0:
            n = min(n, 2)
        put("estabilidade_resultados", n, "código", f"margem EBITDA entre {min(margens):.1%} e {max(margens):.1%}")
    else:
        put("estabilidade_resultados", 3, "sem informação (neutra)", "menos de 2 períodos comparáveis", True)

    # 7. endividamento e liquidez
    bruta, caixa, fonte = divida_liquida(dados)
    ebitda = base.ebitda if base else 0.0
    if ebitda > 0:
        alav = (bruta - caixa) / ebitda
        put("endividamento_liquidez", 6 - _faixa(alav, [0.5, 1.5, 2.5, 3.5]), "código",
            f"dívida líquida/EBITDA {alav:.1f}× (dívida R$ {bruta:,.0f}, caixa R$ {caixa:,.0f}; {fonte})".replace(",", "."))
    else:
        put("endividamento_liquidez", 1, "código", "EBITDA econômico ≤ 0")

    # 8. contingências (proposta por código; julgamento final do analista)
    sinais = []
    alertas_case = getattr(dados, "alertas", None) or []
    texto = " ".join(alertas_case)
    if base and base.receita_fonte.startswith("caixa"):  # não casar "gerencial (sem ... nem caixa para confirmar)"
        sinais.append("receita acima da declarada")
    if any("indício de venda sem nota" in a or "valores redondos" in a for a in alertas_case):
        sinais.append("DRE gerencial divergente")
    if ((getattr(dados, "erp", None) or {}).get("contas_pagar") or {}).get("passivo_fiscal_pago"):
        sinais.append("parcelamento/dívida ativa")
    if (getattr(dados, "erp", None) or {}).get("pj_total_mensal"):
        sinais.append("PJ em função de empregado")
    if "reapresentada" in texto:
        sinais.append("contabilidade reapresentada")
    if "Empréstimos contratados até" in texto:
        sinais.append("dívida fora do Balanço")
    if q and q.valor("Q24") == "Não, parte é recebida sem nota":
        sinais.append("venda sem nota (declarada no questionário)")
    put("contingencias", max(1, 5 - len(sinais)), "código", "; ".join(sinais) or "nenhum sinal nos documentos", True)

    # 9. setor e posição competitiva — julgamento (F5)
    put("setor_posicao_competitiva", 3, "sem informação (neutra)", "aguarda análise qualitativa (F5) / analista", True)

    assert set(notas) == set(PESOS)
    return notas


def aplicar_qualitativo(notas: dict[str, NotaDimensao], notas_f5: list[dict]) -> None:
    """Notas propostas pela F5 (qualitativo.json) substituem as de questionário/padrão nas dimensões de julgamento.
    Continuam pendentes (taxa provisória) até o analista aprovar com origem "analista" em score_notas.json."""
    for n in notas_f5:
        dim = n["dimensao"]
        if dim not in notas:
            continue
        atual = notas[dim]
        evid = f"{n['justificativa']} [{n['confianca']}]"
        if atual.origem == "código":
            evid += f" · código: {atual.evidencia}"
        notas[dim] = NotaDimensao(dimensao=dim, nota=int(n["nota"]), origem="F5 (proposta)", evidencia=evid,
                                  pendente=True)
