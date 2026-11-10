"""Quanto vira o investimento recomendado: empresa × Selic × IPCA+, a partir do mesmo desembolso (decisão de 07/11/2026).

- Desembolso do comprador = valor de ida a mercado (parte do sócio + dívidas e obrigações assumidas). O caixa que
  vem com a empresa volta para ele no fechamento: entra como caixa inicial (10/11/2026).
- Empresa, no ano t = caixa gerado até t, reinvestido na Selic esperada, + valor da empresa em t pelo nosso DCF
  (valor presente, à taxa de desconto, do caixa que falta + valor terminal); no último ano, o valor terminal.
- Selic e IPCA+ = o desembolso rendendo as expectativas Focus de cada ano (IPCA+ com o juro real dos parâmetros).
- TIR do negócio = taxa que zera: −desembolso + caixas anuais + valor terminal no fim.
"""

from __future__ import annotations


def _taxa_ano(med: dict, ano: int) -> float:
    if not med:
        return 0.0
    return (med.get(str(ano), med[max(med)]) or 0.0) / 100


def tir(desembolso: float, fluxos: list[float], terminal: float) -> float | None:
    """Taxa interna de retorno por bisseção (None se não houver troca de sinal)."""
    def vpl(r: float) -> float:
        return -desembolso + sum(f / (1 + r) ** t for t, f in enumerate(fluxos, 1)) + terminal / (1 + r) ** len(fluxos)

    lo, hi = -0.99, 10.0
    if vpl(lo) * vpl(hi) > 0:
        return None
    for _ in range(200):
        meio = (lo + hi) / 2
        if vpl(lo) * vpl(meio) <= 0:
            hi = meio
        else:
            lo = meio
    return round((lo + hi) / 2, 4)


def evolucao(desembolso: float, fluxos: list[float], terminal: float, taxa: float, ano0: int,
             focus_selic: dict, focus_ipca: dict, juro_real: float, caixa_inicial: float = 0.0) -> dict:
    """→ {"anos", "empresa", "selic", "ipca_mais", "tir"} com valores em R$ para hoje e cada ano do horizonte."""
    n = len(fluxos)
    anos = [ano0 + i for i in range(n + 1)]
    empresa, selic, ipca = [desembolso], [desembolso], [desembolso]
    caixa = caixa_inicial
    for t in range(1, n + 1):
        s, i = _taxa_ano(focus_selic, anos[t]), _taxa_ano(focus_ipca, anos[t])
        caixa = caixa * (1 + s) + fluxos[t - 1]
        restante = sum(f / (1 + taxa) ** (k - t) for k, f in enumerate(fluxos, 1) if k > t)
        valor_empresa = restante + terminal / (1 + taxa) ** (n - t)
        empresa.append(round(caixa + valor_empresa, 2))
        selic.append(round(selic[-1] * (1 + s), 2))
        ipca.append(round(ipca[-1] * (1 + i) * (1 + juro_real), 2))
    return {"anos": anos, "empresa": empresa, "selic": selic, "ipca_mais": ipca,
            "tir": tir(desembolso - caixa_inicial, fluxos, terminal)}
