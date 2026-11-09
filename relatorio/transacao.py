"""Capítulo 6 — ida a mercado (código, zero tokens). Regras validadas com a ND em 09/11/2026:

- Valor de ida a mercado (bruto) de cada cenário = valor para o sócio do cenário + o que sai depois (dívida, prováveis);
  "a mercado" = preço recomendado; mínimo = venda forçada; máximo = otimista (faixa_venda do motor).
- Métodos comparados: DCF base, patrimônio (ativos a mercado) e estoque (balanço; sem ele, DEFIS). Vale o maior entre
  DCF e patrimônio, nunca a soma (o caixa da empresa já pressupõe o estoque e os ativos operando).
- Comissão ND = maior entre 10% e R$ 150 mil do valor bruto de ida a mercado, paga inteira na entrada.
- IR do sócio sobre o ganho de capital (alíquotas progressivas), ganho = preço das cotas − comissão − custo das cotas
  (sem o custo informado, considerado zero: o IR real tende a ser menor).
- Pagamento: premissa ND = 25% de entrada + 24 parcelas mensais corrigidas pelo CDI (o sócio não perde para a renda
  fixa); o que o sócio aceita (reuniões) vem da finalidade. Estrutura sugerida = menor entrada que o sócio aceita com
  parcela ≤ 70% do caixa mensal + earn-out até o valor sem margem de segurança + escrow das contingências possíveis.
"""

from __future__ import annotations

import math
from datetime import date

from relatorio.evolucao import tir

PADRAO = {"comissao_percentual": 0.10, "comissao_minima": 150_000.0, "entrada_padrao": 0.25, "prazo_padrao_meses": 24,
          "parcela_max_caixa": 0.70,
          "ir_ganho_capital": [[5_000_000, 0.15], [10_000_000, 0.175], [30_000_000, 0.20], [None, 0.225]]}


def comissao(bruto: float, p: dict) -> float:
    return round(max(bruto * p["comissao_percentual"], p["comissao_minima"]), 2) if bruto > 0 else 0.0


def ir_ganho_capital(ganho: float, faixas: list) -> float:
    """Alíquotas progressivas por faixa do ganho (Lei 13.259/2016)."""
    if ganho <= 0:
        return 0.0
    ir, ant = 0.0, 0.0
    for teto, aliq in faixas:
        topo = ganho if teto is None else min(ganho, teto)
        if topo > ant:
            ir += (topo - ant) * aliq
        if teto is None or ganho <= teto:
            break
        ant = teto
    return round(ir, 2)


def _estoque(dados) -> tuple[float | None, str | None]:
    bp = max((b for b in dados.balancos if b.data_base), key=lambda b: b.data_base, default=None)
    if bp and bp.estoques:
        return bp.estoques, "balanço"
    defis = [d for d in getattr(dados, "defis", []) or [] if getattr(d, "estoque_final", None)]
    if defis:
        ano = max(d.ano for d in defis)
        return sum(d.estoque_final for d in defis if d.ano == ano), f"DEFIS {ano}"
    return None, None


def _passivos_op(dados) -> float:
    bp = max((b for b in dados.balancos if b.data_base), key=lambda b: b.data_base, default=None)
    return sum(x or 0 for x in (bp.fornecedores, bp.obrigacoes_trabalhistas, bp.obrigacoes_fiscais)) if bp else 0.0


def metodos(dados, v: dict, pv: dict) -> dict:
    """Valores brutos (antes de dívida e comissão) por método, para comparar com o valor de ida a mercado."""
    base = next((x for x in v["cenarios"] if x["nome"] == "base"), None)
    dcf = base["valor_empresa"] if base and (v.get("fluxo_base") or 0) > 0 else None
    est, fonte = _estoque(dados)
    est_merc = est * pv["patrimonio_mercado"]["estoques"] if est else None
    pat = v.get("ativos_mercado")
    vale = max([("DCF", dcf), ("Patrimônio", pat)], key=lambda x: x[1] if x[1] is not None else float("-inf"))[0]
    return {"dcf": dcf, "patrimonio": pat, "estoque": est_merc, "estoque_fonte": fonte, "vale": vale,
            "haircut_estoque": pv["patrimonio_mercado"]["estoques"]}


def cenarios_dono(v: dict, dados, fin, p: dict) -> list[dict]:
    """Mínimo / a mercado / máximo: do valor bruto de ida a mercado ao que fica com o dono (após comissão e IR)."""
    nomes = {x["nome"]: x["valor_patrimonio"] for x in v.get("cenarios", [])}
    fv = v.get("faixa_venda") or {"forcada": max(min(nomes.get("conservador", 0.0), v["preco_recomendado"]), 0.0),
                                  "mercado": v["preco_recomendado"],
                                  "maximo": max(nomes.get("otimista", 0.0), v["preco_recomendado"])}
    bruta, caixa = v.get("divida_bruta") or 0.0, v.get("caixa") or 0.0
    prov = sum(x["valor_bruto"] for x in v.get("contingencias", []) if x["classificacao"] == "provavel")
    sem_caixa = (v.get("fluxo_base") or 0) <= 0
    pisos = [x for x in (v.get("patrimonio_mercado"), v.get("piso_patrimonial")) if x is not None]
    pct = getattr(fin, "percentual", 1.0) or 1.0
    custo = getattr(fin, "custo_cotas", None)
    out = []
    for chave, nome, obs in (("forcada", "Mínimo", "venda forçada · 0 a 6 meses"),
                             ("mercado", "A mercado", "preço recomendado · 6 a 18 meses"),
                             ("maximo", "Máximo", "cenário otimista · comprador estratégico")):
        socio = fv.get(chave)
        if socio is None:
            continue
        # valor vindo dos ativos (patrimônio a mercado ou liquidação): o bruto são os ativos, o caixa já está dentro e
        # saem fornecedores e a dívida bruta; vindo do fluxo, os fornecedores já estão na operação e sai a dívida líquida
        ativos = sem_caixa or any(abs(socio - x) < 1 for x in pisos if x > 0)
        passivos = _passivos_op(dados) if ativos else 0.0
        divida = bruta if ativos else bruta - caixa
        bruto = socio + divida + prov + passivos
        com = comissao(bruto * pct, p)
        preco_cotas = socio * pct
        ganho = preco_cotas - com - (custo or 0.0)
        ir = ir_ganho_capital(ganho, p["ir_ganho_capital"])
        out.append({"chave": chave, "nome": nome, "obs": obs, "bruto": bruto, "divida": divida, "divida_bruta": ativos,
                    "passivos": passivos, "provaveis": prov, "socio": socio, "percentual": pct, "preco_cotas": preco_cotas,
                    "comissao": com, "ir": ir, "custo_informado": custo is not None,
                    "sobra": preco_cotas - com - ir, "retencao": v.get("retencao_sugerida") or 0.0})
    return out


def _pmt(valor: float, i: float, n: int) -> float:
    return valor / n if i == 0 else valor * i / (1 - (1 + i) ** -n)


def _fator_vp(i: float, n: int) -> float:
    return n if i == 0 else (1 - (1 + i) ** -n) / i


def _estrutura(nome: str, preco: float, entrada_pct: float, n: int, earnout: float, escrow: float, com: float,
               i_cdi: float, i_selic: float, caixa_mes: float, desembolso_extra: float, fluxos: list[float],
               terminal: float, rotulo: str) -> dict:
    entrada = preco * entrada_pct
    financiado = preco - entrada
    parcela = _pmt(financiado, i_cdi, n) if n and financiado > 0 else 0.0
    total = entrada + parcela * n + earnout
    i_sm = (1 + i_selic) ** (1 / 12) - 1
    vp_socio = entrada + parcela * _fator_vp(i_sm, n)  # sem o earn-out, que depende do resultado
    falta = max(com + escrow - entrada, 0.0)  # comissão e escrow acima da entrada saem das primeiras parcelas
    no_fechamento = max(entrada - com - escrow, 0.0)
    # investidor: paga a entrada (+ dívida e prováveis assumidas); parcelas saem do caixa da empresa
    anos = len(fluxos)
    por_ano = [sum(parcela for m in range(1, n + 1) if (m - 1) // 12 == t) for t in range(anos)]
    if anos and n > 12 * anos:
        por_ano[-1] += parcela * (n - 12 * anos)
    # TIR no cenário base: o earn-out só é pago se o caixa vier acima do base, e aí ele se paga com esse excedente
    liquidos = [f - pa for f, pa in zip(fluxos, por_ano)]
    return {"nome": nome, "rotulo": rotulo, "entrada_pct": entrada_pct, "entrada": entrada, "n": n, "parcela": parcela,
            "earnout": earnout, "escrow": escrow, "comissao": com, "no_fechamento": no_fechamento, "total": total,
            "falta_na_entrada": falta, "liquido_hoje": vp_socio - com,
            "parcelas_hoje": vp_socio - com - no_fechamento - escrow, "liquido_nominal": entrada + parcela * n - com,
            "vp_socio": vp_socio, "parcela_caixa": parcela / caixa_mes if caixa_mes > 0 and parcela else None,
            "desembolso": entrada + desembolso_extra,
            "tir": tir(entrada + desembolso_extra, liquidos, terminal) if fluxos else None}


def pagamento(v: dict, fin, p: dict, cen_mercado: dict | None, recente: float | None = None) -> dict | None:
    """À vista × premissa (o que o sócio aceita ou o padrão ND) × estrutura sugerida (com earn-out e escrow)."""
    base = next((x for x in v["cenarios"] if x["nome"] == "base"), None)
    preco = v.get("preco_recomendado") or 0.0
    if not base or not cen_mercado or preco <= 0:
        return None
    selic = v["risco"].get("selic") or 0.11
    i_m = (1 + selic) ** (1 / 12) - 1  # CDI ≈ Selic
    fluxos = base["fluxos"] if (v.get("fluxo_base") or 0) > 0 else []
    caixa_mes = fluxos[0] / 12 if fluxos else 0.0
    extra = cen_mercado["divida"] + cen_mercado["provaveis"]
    com, escrow = cen_mercado["comissao"], cen_mercado["retencao"]
    entrada_socio = getattr(fin, "entrada_aceita", None)
    prazo_socio = getattr(fin, "prazo_aceito_meses", None)
    origem = "o que o sócio aceita (reuniões)" if entrada_socio or prazo_socio else "premissa ND"
    e0 = entrada_socio if entrada_socio is not None else p["entrada_padrao"]
    n0 = int(prazo_socio or p["prazo_padrao_meses"])
    # menor entrada (≥ a aceita) com parcela ≤ 70% do caixa mensal, em degraus de 5%
    if caixa_mes > 0:
        max_fin = p["parcela_max_caixa"] * caixa_mes * _fator_vp(i_m, n0)
        e_min = max(e0, 1 - max_fin / preco)
        e_sug = min(1.0, math.ceil(round(e_min * 100, 6) / 5) * 5 / 100)
    else:
        e_sug = 1.0
    # a entrada da sugerida cobre ao menos a comissão e o escrow (que saem inteiros no fechamento)
    e_sug = min(1.0, max(e_sug, math.ceil(round((com + escrow) / preco * 100, 6) / 5) * 5 / 100))
    # earn-out: até o valor para o sócio sem a margem de segurança (o teto que os números sustentam)
    aceita_eo = getattr(fin, "aceita_earnout", None)
    teto = max(base["valor_patrimonio"], preco)
    earnout = max(teto - preco, 0.0) if aceita_eo is not False and fluxos else 0.0
    terminal = base["valor_terminal"]
    estr = [_estrutura("À vista", preco, 1.0, 0, 0.0, escrow, com, i_m, selic, caixa_mes, extra, fluxos, terminal,
                       "100% no fechamento"),
            _estrutura("Premissa", preco, e0, n0, 0.0, escrow, com, i_m, selic, caixa_mes, extra, fluxos, terminal,
                       f"{e0:.0%} + {n0} meses"),
            _estrutura("Sugerida", preco, e_sug, n0 if e_sug < 1 else 0, earnout, escrow, com, i_m, selic, caixa_mes,
                       extra, fluxos, terminal, " + ".join(x for x, ok in (("entrada", True), ("parcelas", e_sug < 1),
                                                                         ("earn-out", earnout > 0), ("escrow", escrow > 0)) if ok))]
    # meta do earn-out: caixa do período mais recente se acima do considerado; senão o caixa do otimista no ano 2
    otim = next((x for x in v["cenarios"] if x["nome"] == "otimista"), None)
    meta = recente if recente and recente > (v["fluxo_base"] or 0) * 1.05 else (
        otim["fluxos"][min(1, len(otim["fluxos"]) - 1)] if otim and otim["fluxos"] else None)
    return {"estruturas": estr, "selic": selic, "caixa_mes": caixa_mes, "origem": origem, "prazo": n0,
            "entrada_aceita": e0, "earnout_teto": teto, "earnout_meta": meta, "earnout_base": v.get("fluxo_base"),
            "limite": p["parcela_max_caixa"], "escrow": escrow, "comissao": com}


def montar(dados, v: dict, fin, pv: dict, dres: list[dict] | None = None) -> dict:
    p = {**PADRAO, **(pv.get("transacao") or {})}
    cen = cenarios_dono(v, dados, fin, p)
    merc = next((x for x in cen if x["chave"] == "mercado"), None)
    d = next((x for x in dres or [] if x["periodo"] == v.get("periodo_base")), None)
    recente = d.get("owner_earnings") if d else None
    return {"metodos": metodos(dados, v, pv), "cenarios": cen, "pagamento": pagamento(v, fin, p, merc, recente),
            "parametros": {k: p[k] for k in ("comissao_percentual", "comissao_minima")}, "hoje": date.today().isoformat()}
