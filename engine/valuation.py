"""F6 — Valuation (código, zero tokens). Metodologia da boutique (ARQUITETURA.md §7):

  * fluxo base = owner earnings sustentável (Graham: média dos períodos normalizados, nunca acima do mais recente)
  * DCF de horizonte finito (3–5 anos pelo Score); valor terminal de empresa em funcionamento = múltiplo do fluxo
    do último ano (1,5× / 2,5× / 3,0×), nunca abaixo da liquidação dos ativos operacionais
  * perpetuidade só com Score ≤ 30 e teste de perpetuidade aprovado
  * EPV (sem crescimento, perpetuidade) apenas como referência; múltiplo de EBITDA como checagem
  * valor da empresa − dívida líquida − contingências = valor do patrimônio; preço recomendado com margem de segurança
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from engine.normalizacao import DREEconomica
from engine.risco import TAXA_MAX, TAXA_MIN, ResultadoRisco, avaliar_risco, fator_anuidade
from engine.score_case import NotaDimensao, divida_liquida

PARAMETROS = Path(__file__).resolve().parents[1] / "metodologia" / "parametros_valuation.json"


def carregar_parametros(caminho: str | Path = PARAMETROS) -> dict:
    return json.loads(Path(caminho).read_text(encoding="utf-8"))


Classificacao = Literal["provavel", "possivel", "remota"]


class Contingencia(BaseModel):
    """Regra da casa: provável desconta do preço; possível vira retenção (escrow); remota não afeta o preço."""

    id: str
    descricao: str
    valor_bruto: float
    classificacao: Classificacao
    fonte: str
    nota: str | None = None

    @property
    def valor(self) -> float:  # o que sai do valor do patrimônio
        return round(self.valor_bruto, 2) if self.classificacao == "provavel" else 0.0

    @property
    def retencao(self) -> float:  # o que fica retido no fechamento
        return round(self.valor_bruto, 2) if self.classificacao == "possivel" else 0.0


class Cenario(BaseModel):
    nome: str
    taxa: float
    crescimento: float
    anos: int
    fluxos: list[float]
    valor_terminal: float
    valor_empresa: float
    valor_patrimonio: float
    multiplo_do_fluxo: float


class ResultadoValuation(BaseModel):
    periodo_base: str
    fluxo_base: float  # owner earnings sustentável (anual)
    fluxo_fonte: str
    ebitda_base: float
    receita_base: float
    crescimento_historico: float | None
    risco: ResultadoRisco
    notas: dict[str, NotaDimensao]
    perpetuidade: bool
    perpetuidade_motivo: str
    divida_bruta: float
    caixa: float
    divida_fonte: str
    contingencias: list[Contingencia] = Field(default_factory=list)
    retencao_sugerida: float = 0.0  # contingências possíveis: ficam retidas no fechamento, não descontam o preço
    piso_patrimonial: float | None = None
    epv: float | None = None
    multiplo_ebitda: dict[str, float] = Field(default_factory=dict)
    cenarios: list[Cenario] = Field(default_factory=list)
    sensibilidade: dict[str, dict[str, float]] = Field(default_factory=dict)  # taxa → crescimento → patrimônio
    preco_recomendado: float = 0.0
    taxa_provisoria: dict[str, float] | None = None  # faixa da taxa se as notas pendentes forem 5 (melhor) ou 1 (pior)
    alertas: list[str] = Field(default_factory=list)

    @property
    def base(self) -> Cenario:
        return next(c for c in self.cenarios if c.nome == "base")


def lucro_sustentavel(dres: list[DREEconomica], p: dict) -> tuple[DREEconomica, float, str]:
    """→ (período mais recente usado, owner earnings sustentável, explicação)."""
    validos = [d for d in dres if d.owner_earnings is not None]
    if p["lucro_sustentavel"]["excluir_confianca_baixa_se_houver_outros"] and any(d.confianca != "baixa" for d in validos):
        validos = [d for d in validos if d.confianca != "baixa"]
    if not validos:
        validos = [d for d in dres]
        for d in validos:
            d.owner_earnings = d.lucro_economico if d.owner_earnings is None else d.owner_earnings
    validos = validos[: p["lucro_sustentavel"]["periodos_media"]]
    recente = validos[0]
    media = sum(d.owner_earnings for d in validos) / len(validos)
    fluxo = min(media, recente.owner_earnings)
    nomes = ", ".join(f"{d.periodo} R$ {d.owner_earnings:,.0f}".replace(",", ".") for d in validos)
    regra = "média" if fluxo == media else "mais recente (abaixo da média)"
    return recente, round(fluxo, 2), f"owner earnings — {regra} de: {nomes}"


def crescimento_historico(dres: list[DREEconomica]) -> float | None:
    anuais = sorted((d for d in dres if d.periodo.isdigit()), key=lambda d: d.periodo)
    if len(anuais) < 2:
        return None
    a, b = anuais[0].valor("Receita bruta"), anuais[-1].valor("Receita bruta")
    n = int(anuais[-1].periodo) - int(anuais[0].periodo)
    if a <= 0 or n <= 0:
        return None
    return round((b / a) ** (1 / n) - 1, 4)


def liquidacao(dados, p: dict) -> tuple[float | None, float | None]:
    """→ (piso patrimonial, valor de liquidação dos ativos operacionais).
    Piso = ativos a valor de realização − todos os passivos conhecidos (valor mínimo para o sócio hoje).
    Operacional = recebíveis + estoque + imobilizado a valor de realização − fornecedores e obrigações (sem caixa nem
    dívida, que entram à parte): é o valor terminal do DCF no cenário base."""
    bp = max((b for b in dados.balancos if b.data_base), key=lambda b: b.data_base, default=None)
    if not bp:
        return None, None
    h = p["piso_patrimonial"]
    operacionais = ((bp.contas_receber or 0) * h["contas_receber"] + (bp.estoques or 0) * h["estoques"]
                    + (bp.imobilizado_liquido or 0) * h["imobilizado"])
    passivos_op = sum(x or 0 for x in (bp.fornecedores, bp.obrigacoes_trabalhistas, bp.obrigacoes_fiscais))
    dividas = sum(x or 0 for x in (bp.parcelamentos_fiscais, bp.emprestimos_cp, bp.emprestimos_lp, bp.mutuos_socios))
    piso = (bp.caixa_aplicacoes or 0) * h["caixa"] + operacionais - passivos_op - dividas
    return round(piso, 2), round(max(operacionais - passivos_op, 0.0), 2)


def carga_efetiva_atual(dados, base: DREEconomica) -> tuple[float, str]:
    """Carga tributária sobre a receita que a empresa paga hoje (para o tributo latente da receita fora dos livros)."""
    aliq = (getattr(dados, "simples", None) or {}).get("aliquota_efetiva")
    if aliq:
        return aliq, "alíquota efetiva do PGDAS-D"
    contabeis = [x for x in (getattr(dados, "dres", None) or []) if x.receita_bruta and x.deducoes]
    if contabeis:
        x = max(contabeis, key=lambda x: (x.exercicio, x.meses))
        return abs(x.deducoes) / x.receita_bruta, f"deduções/receita da DRE contábil {x.exercicio}"
    receita = base.valor("Receita bruta")
    return (abs(base.valor("Tributos sobre a receita")) / receita if receita else 0.0,
            "tributos do regime do comprador (aproximação)")


def contingencias(dados, base: DREEconomica, p: dict, decisoes: dict | None = None) -> list[Contingencia]:
    """Contingências calculadas + decisões/acréscimos do analista (_valuation/contingencias_decisoes.json)."""
    c = p["contingencias"]
    out = []
    decl = base.receitas_por_fonte.get("declarada") or base.receitas_por_fonte.get("contabil")
    receita = base.valor("Receita bruta")
    if decl and receita > decl and "caixa" in base.receita_fonte:
        aliq, fonte_aliq = carga_efetiva_atual(dados, base)
        anual = (receita - decl) * 12 / base.meses * aliq
        r = c["receita_nao_declarada"]
        out.append(Contingencia(id="receita_nao_declarada",
                                descricao=f"Tributos sobre receita não declarada ({r['anos']} anos não prescritos, "
                                          f"carga de {aliq:.1%})",
                                valor_bruto=round(anual * r["anos"], 2), classificacao=r["classificacao"],
                                fonte=f"receita econômica × declarada; {fonte_aliq}"))
    pj = (getattr(dados, "erp", None) or {}).get("pj_total_mensal")
    if pj:
        r = c["pj"]
        out.append(Contingencia(id="pj", descricao=f"Vínculo de emprego dos PJ ({r['anos']} anos de encargos)",
                                valor_bruto=round(pj * 12 * 0.5 * r["anos"], 2), classificacao=r["classificacao"],
                                fonte="planilha de colaboradores PJ"))
    for k, dec in (decisoes or {}).items():
        if k.startswith("_"):
            continue
        atual = next((x for x in out if x.id == k), None)
        if atual:  # o analista reclassifica ou corrige o valor
            if dec.get("classificacao"):
                atual.classificacao = dec["classificacao"]
            if dec.get("valor_bruto") is not None:
                atual.valor_bruto = float(dec["valor_bruto"])
            atual.nota = dec.get("nota")
        elif dec.get("descricao") and dec.get("valor_bruto") is not None and dec.get("classificacao"):
            out.append(Contingencia(id=k, descricao=dec["descricao"], valor_bruto=float(dec["valor_bruto"]),
                                    classificacao=dec["classificacao"], fonte=dec.get("fonte") or "analista",
                                    nota=dec.get("nota")))
    return out


def teste_perpetuidade(dados, notas: dict[str, NotaDimensao], risco: ResultadoRisco, gci, p: dict) -> tuple[bool, str]:
    if not risco.perpetuidade_permitida_pelo_score:
        return False, f"Score {risco.score:.0f} > 30"
    t = p["teste_perpetuidade"]
    falhas = []
    if notas["recorrencia_receita"].pendente or notas["recorrencia_receita"].nota < 4:
        falhas.append("recorrência não comprovada")
    if notas["historico_mercado"].nota < 4:
        falhas.append(f"menos de {t['anos_de_mercado_minimo']} anos de mercado")
    if notas["concentracao_clientes"].nota < 3:
        falhas.append("clientes concentrados")
    if not gci or gci.nivel not in t["gci_niveis"]:
        falhas.append("GCI abaixo de B")
    if notas["dependencia_dono"].nota < t["dependencia_dono_nota_minima"]:
        falhas.append("dependência do dono")
    return (not falhas), ("aprovado" if not falhas else "reprovado: " + ", ".join(falhas))


def _dcf(fluxo: float, taxa: float, g: float, anos: int, terminal: float, perpetuidade: bool, g_perp: float) -> tuple[list[float], float, float]:
    fluxos = [round(fluxo * (1 + g) ** t, 2) for t in range(1, anos + 1)]
    vp = sum(f / (1 + taxa) ** t for t, f in enumerate(fluxos, start=1))
    if perpetuidade and taxa > g_perp:
        terminal = fluxos[-1] * (1 + g_perp) / (taxa - g_perp)
    vp_terminal = terminal / (1 + taxa) ** anos
    return fluxos, round(terminal, 2), round(vp + vp_terminal, 2)


def avaliar(dados, dres: list[DREEconomica], gci, risco: ResultadoRisco, notas: dict[str, NotaDimensao],
            p: dict | None = None, decisoes_contingencias: dict | None = None) -> ResultadoValuation:
    p = p or carregar_parametros()
    base, fluxo, fonte = lucro_sustentavel(dres, p)
    hist = crescimento_historico(dres)
    perp, motivo = teste_perpetuidade(dados, notas, risco, gci, p)
    bruta, caixa, fonte_div = divida_liquida(dados)
    conts = contingencias(dados, base, p, decisoes_contingencias)
    piso, liquidacao_operacional = liquidacao(dados, p)
    ajuste_patrimonio = -(bruta - caixa) - sum(c.valor for c in conts)
    cr = p["crescimento"]
    g_base = min(max(hist or 0.0, 0.0) * cr["base_fracao_do_historico"], cr["base_teto"])
    g_otim = min(max(hist or 0.0, 0.0), cr["otimista_teto"])
    t = p["cenarios_taxa"]

    r = ResultadoValuation(periodo_base=base.periodo, fluxo_base=fluxo, fluxo_fonte=fonte, ebitda_base=base.ebitda,
                           receita_base=base.valor("Receita bruta"), crescimento_historico=hist, risco=risco, notas=notas,
                           perpetuidade=perp, perpetuidade_motivo=motivo, divida_bruta=bruta, caixa=caixa,
                           divida_fonte=fonte_div, contingencias=conts, piso_patrimonial=piso,
                           retencao_sugerida=round(sum(c.retencao for c in conts), 2))
    ativos_liquidos = liquidacao_operacional or 0.0  # valor terminal (firma) no cenário base/otimista
    mult_vt = p["valor_terminal"]["multiplo_do_fluxo"]
    for nome, dtaxa, g in (("conservador", t["conservador"], cr["conservador"]),
                           ("base", 0.0, g_base), ("otimista", t["otimista"], g_otim)):
        taxa = round(min(max(risco.taxa_desconto + dtaxa, TAXA_MIN), TAXA_MAX), 4)
        fluxo_final = fluxo * (1 + g) ** risco.horizonte_anos
        terminal = max(mult_vt[nome] * fluxo_final, ativos_liquidos)  # empresa em funcionamento ou liquidação
        fluxos, vt, ev = _dcf(fluxo, taxa, g, risco.horizonte_anos, terminal, perp and nome != "conservador",
                              cr["perpetuidade"])
        r.cenarios.append(Cenario(nome=nome, taxa=taxa, crescimento=g, anos=risco.horizonte_anos, fluxos=fluxos,
                                  valor_terminal=vt, valor_empresa=ev, valor_patrimonio=round(ev + ajuste_patrimonio, 2),
                                  multiplo_do_fluxo=round(ev / fluxo, 2) if fluxo > 0 else 0.0))
    base_c = r.base
    if fluxo > 0:
        r.epv = round(fluxo / risco.taxa_desconto + ajuste_patrimonio, 2)
    m = p["multiplos_referencia_ev_ebitda"]
    if base.ebitda > 0:
        r.multiplo_ebitda = {"min": round(base.ebitda * m["min"] + ajuste_patrimonio, 2),
                             "max": round(base.ebitda * m["max"] + ajuste_patrimonio, 2),
                             "implicito_base": round(base_c.valor_empresa / base.ebitda, 2)}
    for taxa in sorted({round(min(max(risco.taxa_desconto + dt, TAXA_MIN), TAXA_MAX), 4) for dt in (-0.03, 0.0, 0.03)}):
        r.sensibilidade[f"{taxa:.0%}"] = {}
        for g in sorted({0.0, g_base, g_otim}):
            terminal = max(mult_vt["base"] * fluxo * (1 + g) ** risco.horizonte_anos, ativos_liquidos)
            _, _, ev = _dcf(fluxo, taxa, g, risco.horizonte_anos, terminal, perp, cr["perpetuidade"])
            r.sensibilidade[f"{taxa:.0%}"][f"{g:.0%}"] = round(ev + ajuste_patrimonio, 2)

    valor_base = max(base_c.valor_patrimonio, piso or float("-inf")) if piso is not None else base_c.valor_patrimonio
    r.preco_recomendado = round(max(valor_base * (1 - p["margem_de_seguranca"]["percentual"]), piso or 0.0, 0.0), 2)

    # alertas e sanidade
    expostas = sum(c.valor_bruto for c in conts if c.classificacao != "remota")
    receita_anual = base.valor("Receita bruta") * 12 / base.meses if base.meses else 0
    if receita_anual and expostas > receita_anual * p["contingencias"]["bloqueante_fracao_receita"]:
        r.alertas.append(f"BLOQUEANTE: contingências prováveis + possíveis (R$ {expostas:,.0f}) acima do faturamento "
                         f"anual (R$ {receita_anual:,.0f}). Não negociar antes de parecer jurídico.".replace(",", "."))
    if r.retencao_sugerida:
        r.alertas.append(f"Retenção sugerida no fechamento (contingências possíveis): R$ {r.retencao_sugerida:,.0f} — "
                         "não desconta do preço; é liberada ao vendedor se a contingência não se materializar."
                         .replace(",", "."))
    if fluxo <= 0:
        r.alertas.append("Owner earnings sustentável ≤ 0: o valor vem só do patrimônio (piso) — não há fluxo a descontar.")
    elif not perp:
        anuidade = fator_anuidade(risco.taxa_desconto, risco.horizonte_anos)
        if not 1.4 <= anuidade <= 3.0:
            r.alertas.append(f"Fator de anuidade {anuidade:.2f}× fora da faixa 1,4–3,0× da metodologia.")
        if base_c.multiplo_do_fluxo > 5:
            r.alertas.append(f"Valor da empresa = {base_c.multiplo_do_fluxo:.1f}× o fluxo: acima do usual para PME; revisar "
                             "o múltiplo terminal e o crescimento.")
    if piso is not None and piso > 0 and piso > base_c.valor_patrimonio:
        r.alertas.append("Piso patrimonial acima do valor pelo fluxo: a empresa vale mais pelos ativos do que pelo resultado "
                         "(confirmar estoque e imobilizado a valor de realização).")
    if base_c.valor_patrimonio < 0 < base_c.valor_empresa:
        anos_div = (bruta - caixa) / fluxo if fluxo > 0 else float("inf")
        r.alertas.append(f"Valor da empresa positivo (R$ {base_c.valor_empresa:,.0f}) mas patrimônio negativo: a dívida "
                         f"líquida equivale a {anos_div:.1f} anos de fluxo, mais que o horizonte de {risco.horizonte_anos} "
                         "anos. Na prática, o comprador assumiria a dívida e pagaria pouco ou nada pelas quotas."
                         .replace(",", "."))
    pendentes = [n.dimensao for n in notas.values() if n.pendente]
    if pendentes:
        notas_num = {k: v.nota for k, v in notas.items()}
        ref = risco.selic_por_horizonte or risco.selic
        otim = avaliar_risco({**notas_num, **{k: 5 for k in pendentes}}, ref)
        pess = avaliar_risco({**notas_num, **{k: 1 for k in pendentes}}, ref)
        r.taxa_provisoria = {"minima": otim.taxa_desconto, "maxima": pess.taxa_desconto}
    if pendentes:
        r.alertas.append(f"{len(pendentes)} nota(s) do Score com padrão conservador ou aguardando o analista: "
                         f"{', '.join(pendentes)} — o preço muda quando forem decididas.")
    if base.confianca == "baixa":
        r.alertas.append(f"Período base {base.periodo} com confiança baixa: tratar o resultado como indicativo.")
    return r
