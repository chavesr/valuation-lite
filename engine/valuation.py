"""F6 — Valuation (código, zero tokens). Metodologia da boutique (ARQUITETURA.md §7):

  * fluxo base = owner earnings sustentável (Graham: média dos períodos normalizados, nunca acima do mais recente)
  * DCF de horizonte finito (3–5 anos pelo Score); valor terminal de empresa em funcionamento = múltiplo do fluxo
    do último ano (1,5× / 2,5× / 3,0×), nunca abaixo da liquidação dos ativos operacionais
  * perpetuidade só com Score ≤ 30 e teste de perpetuidade aprovado
  * EPV (sem crescimento, perpetuidade) apenas como referência; múltiplo de EBITDA como checagem
  * valor da empresa − dívida líquida − contingências = valor do patrimônio; recomendado = cenário base (opção A,
    10/11/2026: sem margem de segurança à parte — o conservador e a régua já protegem o comprador)
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


def parametros_do_case(dados, decisoes: dict | None, p: dict | None = None) -> dict:
    """Decisão do analista (valuation_decisoes.json → imobilizado_laudo: {liquidacao, mercado, fonte}, 11/11/2026,
    Emunah): imobilizado pelo laudo em vez dos % padrão. 'liquidacao' (liquidez forçada do laudo) entra no piso;
    'mercado' (valor de mercado do laudo) nos ativos a mercado. Vira o % do imobilizado líquido do último balanço."""
    import copy

    p = copy.deepcopy(p or carregar_parametros())
    laudo = (decisoes or {}).get("imobilizado_laudo") or {}
    bp = max((b for b in dados.balancos if b.data_base), key=lambda b: b.data_base, default=None)
    imob = bp.imobilizado_liquido if bp else None
    if laudo and imob:
        for chave, criterio in (("liquidacao", "piso_patrimonial"), ("mercado", "patrimonio_mercado")):
            if laudo.get(chave) is not None:
                p[criterio]["imobilizado"] = laudo[chave] / imob
    return p


Classificacao = Literal["provavel", "possivel", "remota"]


class Contingencia(BaseModel):
    """Regra da casa: provável desconta do preço; possível vira retenção (escrow); remota não afeta o preço."""

    id: str
    descricao: str
    valor_bruto: float
    classificacao: Classificacao
    fonte: str
    nota: str | None = None
    # natureza (11/11/2026): "trabalhista" (processos de funcionários) | "tributaria" | "civel" — o quadro do dono
    # mostra as trabalhistas na linha "Passivos trabalhistas (processos)" e as demais em "Contingências prováveis"
    natureza: str | None = None

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
    crescimento_fonte: str | None = None  # None = calculado das DREs normalizadas
    haveres_fora_da_divida: float | None = None  # haveres de sócio excluídos da dívida por decisão do analista
    # 11/11/2026: abertura da dívida bruta (bancários, tributários, sócios) e passivos que descontam da parte do sócio
    # sem ser dívida (fornecedores vencidos/renegociados, trabalhista acumulado) — o quadro do dono mostra um a um
    divida_componentes: dict[str, float] = Field(default_factory=dict)
    passivos_desconto: dict[str, float] = Field(default_factory=dict)
    rescisao_base: str | None = None  # como a rescisão até a data da venda foi calculada (valuation_decisoes.json)
    risco: ResultadoRisco
    notas: dict[str, NotaDimensao]
    perpetuidade: bool
    perpetuidade_motivo: str
    divida_bruta: float
    caixa: float
    divida_fonte: str
    contingencias: list[Contingencia] = Field(default_factory=list)
    retencao_sugerida: float = 0.0  # contingências possíveis: ficam retidas no fechamento, não descontam o preço
    aviso_mercado: str | None = None  # Selic mudou desde a fotografia do case (o analista decide se atualiza)
    regua_payback: dict[str, dict[str, float]] = Field(default_factory=dict)  # régua da casa (conferência)
    faixa_venda: dict[str, float] = Field(default_factory=dict)  # forçada ≤ mercado ≤ máximo (cenários do DCF)
    payback_preco: float | None = None  # anos de fluxo para pagar o preço recomendado + dívida + prováveis
    piso_patrimonial: float | None = None  # ativos em liquidação ordenada − passivos (venda forçada)
    patrimonio_mercado: float | None = None  # ativos a valor de mercado − passivos (critério da ND)
    piso_usado: str = "liquidacao"  # qual dos dois serve de piso do preço (escolha do analista por case)
    # 12/11/2026 (Emunah): "fluxo" = venda forçada pela taxa implícita no fluxo; "ativos" = a venda a mercado vem do
    # piso de ativos e a forçada é 60% dela — sem taxa implícita (daria taxa abaixo da Selic e valor acima do fluxo)
    forcada_origem: str = "fluxo"
    ativos_mercado: float | None = None  # ativos brutos a mercado, sem descontar passivos (critério da ND)
    valor_oferta: float | None = None  # maior entre valor da empresa (DCF base) e ativos a mercado
    valor_oferta_origem: str | None = None  # "fluxo (DCF)" ou "ativos a mercado"
    ponte_dono: list[tuple[str, float]] = Field(default_factory=list)  # do valor de oferta ao que sobra ao dono
    finalidade: str | None = None  # D7: venda total / parcial / entrada de sócio
    leitura_finalidade: list[str] = Field(default_factory=list)
    epv: float | None = None
    multiplo_ebitda: dict[str, float] = Field(default_factory=dict)
    cenarios: list[Cenario] = Field(default_factory=list)
    sensibilidade: dict[str, dict[str, float]] = Field(default_factory=dict)  # taxa → crescimento → patrimônio
    recuperacao_margem: dict | None = None  # cenários de recuperação de margem (margens_recuperacao)
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


def _trabalhista(bp, rescisao: float | None) -> float:
    """Passivo com os funcionários até a data da venda (11/11/2026): a rescisão calculada, quando informada, já inclui
    as férias, o 13º e os encargos provisionados no balanço — substitui as obrigações trabalhistas, sem somar as duas."""
    return rescisao if rescisao is not None else (bp.obrigacoes_trabalhistas or 0) if bp else 0.0


def liquidacao(dados, p: dict, criterio: str = "piso_patrimonial",
               rescisao: float | None = None) -> tuple[float | None, float | None]:
    """→ (piso patrimonial, valor de liquidação dos ativos operacionais).
    Piso = ativos a valor de realização − todos os passivos conhecidos (valor mínimo para o sócio hoje).
    Operacional = recebíveis + estoque + imobilizado a valor de realização − fornecedores e obrigações (sem caixa nem
    dívida, que entram à parte): é o valor terminal do DCF no cenário base."""
    bp = max((b for b in dados.balancos if b.data_base), key=lambda b: b.data_base, default=None)
    if not bp:
        return None, None
    h = p[criterio]
    operacionais = ((bp.contas_receber or 0) * h["contas_receber"] + (bp.estoques or 0) * h["estoques"]
                    + (bp.imobilizado_liquido or 0) * h["imobilizado"])
    passivos_op = sum(x or 0 for x in (bp.fornecedores, bp.obrigacoes_fiscais)) + _trabalhista(bp, rescisao)
    dividas = sum(x or 0 for x in (bp.parcelamentos_fiscais, bp.emprestimos_cp, bp.emprestimos_lp, bp.mutuos_socios))
    piso = (bp.caixa_aplicacoes or 0) * h["caixa"] + operacionais - passivos_op - dividas
    # o operacional (valor terminal do fluxo, no fim do horizonte) fica com o trabalhista do balanço: a rescisão de hoje
    # é do vendedor e já sai da parte do sócio — levá-la ao terminal descontaria duas vezes
    passivos_bp = sum(x or 0 for x in (bp.fornecedores, bp.obrigacoes_fiscais)) + _trabalhista(bp, None)
    return round(piso, 2), round(max(operacionais - passivos_bp, 0.0), 2)


def criterio_piso(piso_usado: str) -> str:
    return "patrimonio_mercado" if piso_usado == "mercado" else "piso_patrimonial"


def ativos_brutos(dados, p: dict, criterio: str = "patrimonio_mercado") -> float | None:
    """Caixa + recebíveis + estoque + imobilizado a valor de mercado, SEM descontar passivos (critério da ND)."""
    bp = max((b for b in dados.balancos if b.data_base), key=lambda b: b.data_base, default=None)
    if not bp:
        return None
    h = p[criterio]
    return round((bp.caixa_aplicacoes or 0) * h["caixa"] + (bp.contas_receber or 0) * h["contas_receber"]
                 + (bp.estoques or 0) * h["estoques"] + (bp.imobilizado_liquido or 0) * h["imobilizado"], 2)


def passivos_operacionais(dados, rescisao: float | None = None) -> float:
    bp = max((b for b in dados.balancos if b.data_base), key=lambda b: b.data_base, default=None)
    return sum(x or 0 for x in (bp.fornecedores, bp.obrigacoes_fiscais)) + _trabalhista(bp, rescisao) if bp else 0.0


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
                                fonte=f"receita econômica × declarada; {fonte_aliq}", natureza="tributaria"))
    pj = (getattr(dados, "erp", None) or {}).get("pj_total_mensal")
    if pj:
        r = c["pj"]
        out.append(Contingencia(id="pj", descricao=f"Vínculo de emprego dos PJ ({r['anos']} anos de encargos)",
                                valor_bruto=round(pj * 12 * 0.5 * r["anos"], 2), classificacao=r["classificacao"],
                                fonte="planilha de colaboradores PJ", natureza="trabalhista"))
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
            if dec.get("natureza"):
                atual.natureza = dec["natureza"]
        elif dec.get("descricao") and dec.get("valor_bruto") is not None and dec.get("classificacao"):
            out.append(Contingencia(id=k, descricao=dec["descricao"], valor_bruto=float(dec["valor_bruto"]),
                                    classificacao=dec["classificacao"], fonte=dec.get("fonte") or "analista",
                                    nota=dec.get("nota"), natureza=dec.get("natureza")))
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


def margens_recuperacao(dres: list[DREEconomica], decisao: dict | None, p: dict) -> dict | None:
    """Cenarização de recuperação de margem (11/11/2026, Emunah). valuation_decisoes.json → recuperacao_margem:
    {"de": período de partida (o realizado mais recente), "alvo": período cuja margem é a meta (o melhor ano
    recente), "fracao_base": quanto do caminho o cenário base recupera, "anos": em quantos anos}.
    Margem = caixa do dono ÷ receita bruta. Conservador fica na margem de partida, otimista chega à meta.
    → {"de", "alvo", "anos", "margens": {conservador, base, otimista, partida, meta}} ou None."""
    if not decisao or not decisao.get("de") or not decisao.get("alvo"):
        return None
    por_nome = {d.periodo: d for d in dres}
    ini, fim = por_nome.get(decisao["de"]), por_nome.get(decisao["alvo"])
    if not ini or not fim:
        raise ValueError(f"recuperacao_margem: períodos {decisao['de']} / {decisao['alvo']} não existem na "
                         f"normalização ({', '.join(por_nome)})")

    def margem(d):
        rb = d.valor("Receita bruta")
        oe = d.owner_earnings if d.owner_earnings is not None else d.lucro_economico
        return oe / rb if rb else 0.0

    pr = p.get("recuperacao_margem", {})
    frac = decisao.get("fracao_base", pr.get("fracao_base", 0.5))
    m0, m1 = margem(ini), margem(fim)
    return {"de": decisao["de"], "alvo": decisao["alvo"], "anos": int(decisao.get("anos", pr.get("anos", 3))),
            "margens": {"partida": round(m0, 4), "meta": round(m1, 4), "conservador": round(m0, 4),
                        "base": round(m0 + frac * (m1 - m0), 4), "otimista": round(m1, 4)}}


def fluxos_recuperacao(receita: float, g: float, anos: int, m0: float, alvo: float, anos_rec: int) -> list[float]:
    """Caixa de cada ano: receita crescendo a g × margem que sai de m0 e chega ao alvo em linha reta em anos_rec."""
    return [round(receita * (1 + g) ** t * (m0 + (alvo - m0) * min(t / max(anos_rec, 1), 1.0)), 2)
            for t in range(1, anos + 1)]


def _dcf(fluxo: float, taxa: float, g: float, anos: int, terminal: float, perpetuidade: bool, g_perp: float,
         fluxos: list[float] | None = None) -> tuple[list[float], float, float]:
    fluxos = fluxos or [round(fluxo * (1 + g) ** t, 2) for t in range(1, anos + 1)]
    vp = sum(f / (1 + taxa) ** t for t, f in enumerate(fluxos, start=1))
    if perpetuidade and taxa > g_perp:
        terminal = fluxos[-1] * (1 + g_perp) / (taxa - g_perp)
    vp_terminal = terminal / (1 + taxa) ** anos
    return fluxos, round(terminal, 2), round(vp + vp_terminal, 2)


def avaliar(dados, dres: list[DREEconomica], gci, risco: ResultadoRisco, notas: dict[str, NotaDimensao],
            p: dict | None = None, decisoes_contingencias: dict | None = None,
            piso_escolhido: str = "liquidacao", crescimento_informado: dict | None = None,
            fornecedores_vencidos: float | None = None, recuperacao: dict | None = None,
            rescisao: dict | None = None) -> ResultadoValuation:
    """`recuperacao`: saída de margens_recuperacao (cenários com a margem voltando ao melhor ano recente).
    `rescisao`: {valor, base} — rescisão de todos os funcionários na data da venda (o comprador só responde pelo
    tempo de casa a partir da compra); substitui as obrigações trabalhistas do balanço."""
    p = p or carregar_parametros()
    base, fluxo, fonte = lucro_sustentavel(dres, p)
    hist = crescimento_historico(dres)
    hist_fonte = None
    if hist is None and crescimento_informado and crescimento_informado.get("valor") is not None:
        # 10/11/2026 (GSD): sem 2 exercícios normalizados, o analista informa o crescimento da receita (ex.: faturamento
        # declarado dos últimos anos) em valuation_decisoes.json; os tetos de cenário continuam valendo
        hist = float(crescimento_informado["valor"])
        hist_fonte = crescimento_informado.get("fonte") or "informado pelo analista"
    perp, motivo = teste_perpetuidade(dados, notas, risco, gci, p)
    bruta, caixa, fonte_div = divida_liquida(dados)
    conts = contingencias(dados, base, p, decisoes_contingencias)
    resc = (rescisao or {}).get("valor")
    resc = float(resc) if resc is not None else None
    piso_liq, liquidacao_operacional = liquidacao(dados, p, rescisao=resc)
    piso_merc, _ = liquidacao(dados, p, "patrimonio_mercado", rescisao=resc)
    piso = piso_merc if piso_escolhido == "mercado" and piso_merc is not None else piso_liq
    bp_ult = max((b for b in dados.balancos if b.data_base), key=lambda b: b.data_base, default=None)
    componentes = {"bancarios": round(bruta - sum(x or 0 for x in (bp_ult.parcelamentos_fiscais, bp_ult.mutuos_socios)), 2)
                   if bp_ult else bruta,
                   "tributarios": (bp_ult.parcelamentos_fiscais or 0.0) if bp_ult else 0.0,
                   "socios": (bp_ult.mutuos_socios or 0.0) if bp_ult else 0.0}
    # passivos que não são dívida mas saem da parte do sócio (11/11/2026): fornecedores vencidos ou renegociados
    # (informados pelo analista; contas a pagar no prazo ficam no giro) e a rescisão dos funcionários até a data da
    # venda (o comprador só responde a partir da compra). As férias, o 13º e os encargos provisionados no balanço já
    # estão dentro da rescisão e não descontam à parte; processos trabalhistas são contingências (natureza trabalhista)
    pdesc = {"fornecedores": round(fornecedores_vencidos or 0.0, 2), "rescisao": round(resc or 0.0, 2)}
    pd_total = sum(pdesc.values())
    ajuste_patrimonio = -(bruta - caixa) - sum(c.valor for c in conts) - pd_total
    cr = p["crescimento"]
    g_base = min(max(hist or 0.0, 0.0) * cr["base_fracao_do_historico"], cr["base_teto"])
    g_otim = min(max(hist or 0.0, 0.0), cr["otimista_teto"])
    t = p["cenarios_taxa"]

    r = ResultadoValuation(periodo_base=base.periodo, fluxo_base=fluxo, fluxo_fonte=fonte, ebitda_base=base.ebitda,
                           receita_base=base.valor("Receita bruta"), crescimento_historico=hist, crescimento_fonte=hist_fonte, risco=risco, notas=notas,
                           perpetuidade=perp, perpetuidade_motivo=motivo, divida_bruta=bruta, caixa=caixa,
                           divida_fonte=fonte_div, contingencias=conts, piso_patrimonial=piso_liq,
                           patrimonio_mercado=piso_merc,
                           piso_usado="mercado" if piso is not None and piso == piso_merc and piso_escolhido == "mercado"
                           else "liquidacao",
                           retencao_sugerida=round(sum(c.retencao for c in conts), 2),
                           divida_componentes=componentes, passivos_desconto=pdesc, recuperacao_margem=recuperacao,
                           rescisao_base=(rescisao or {}).get("base") if resc else None)
    ativos_liquidos = liquidacao_operacional or 0.0  # valor terminal (firma) no cenário base/otimista
    mult_vt = p["valor_terminal"]["multiplo_do_fluxo"]
    sinal = 1 if fluxo > 0 else -1  # com fluxo negativo, taxa maior daria valor menos negativo: inverte
    for nome, dtaxa, g in (("conservador", sinal * t["conservador"], cr["conservador"]),
                           ("base", 0.0, g_base), ("otimista", sinal * t["otimista"], g_otim)):
        taxa = round(min(max(risco.taxa_desconto + dtaxa, TAXA_MIN), TAXA_MAX), 4)
        proj = None
        if recuperacao:  # a margem sai do realizado e volta em direção ao melhor ano (11/11/2026)
            mg = recuperacao["margens"]
            proj = fluxos_recuperacao(base.valor("Receita bruta"), g, risco.horizonte_anos, mg["partida"], mg[nome],
                                      recuperacao["anos"])
            fluxo_final = proj[-1]
        else:
            fluxo_final = fluxo * (1 + g) ** risco.horizonte_anos
        terminal = max(mult_vt[nome] * fluxo_final, ativos_liquidos)  # empresa em funcionamento ou liquidação
        fluxos, vt, ev = _dcf(fluxo, taxa, g, risco.horizonte_anos, terminal, perp and nome != "conservador",
                              cr["perpetuidade"], proj)
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
            proj = None
            if recuperacao:
                mg = recuperacao["margens"]
                proj = fluxos_recuperacao(base.valor("Receita bruta"), g, risco.horizonte_anos, mg["partida"],
                                          mg["base"], recuperacao["anos"])
            final = proj[-1] if proj else fluxo * (1 + g) ** risco.horizonte_anos
            terminal = max(mult_vt["base"] * final, ativos_liquidos)
            _, _, ev = _dcf(fluxo, taxa, g, risco.horizonte_anos, terminal, perp, cr["perpetuidade"], proj)
            r.sensibilidade[f"{taxa:.0%}"][f"{g:.0%}"] = round(ev + ajuste_patrimonio, 2)

    valor_base = max(base_c.valor_patrimonio, piso or float("-inf")) if piso is not None else base_c.valor_patrimonio
    r.preco_recomendado = round(max(valor_base, piso or 0.0, 0.0), 2)

    # valor de ida a mercado (decisão de 10/11/2026): tudo na mesma base de caixa — o que o comprador paga no total
    # (parte do sócio + dívida bruta + prováveis). Vem do fluxo (valor da empresa + caixa, cenário base);
    # o piso é a liquidação ordenada dos ativos. Os ativos a mercado viram só referência para a negociação.
    r.ativos_mercado = ativos_brutos(dados, p)
    provaveis = sum(c.valor for c in conts)
    passivos_op = passivos_operacionais(dados, resc)
    do_piso_liq = piso is not None and r.preco_recomendado > 0 and abs(r.preco_recomendado - max(piso, 0.0)) < 1 \
        and (fluxo <= 0 or piso >= base_c.valor_patrimonio)
    # 10/11/2026 (GSD): com dívida maior que o valor, a parte do sócio é negativa nos dois métodos; a liquidação ainda
    # vence quando entrega mais na base de ida a mercado (vale mais fechada do que operando)
    if not do_piso_liq and piso is not None and fluxo > 0 and base_c.valor_patrimonio < piso < 0:
        do_piso_liq = True
    # base única (10/11/2026): ida a mercado = parte do sócio + dívida bruta + prováveis em todos os métodos (os
    # fornecedores já saem dentro da liquidação e, no fluxo, fazem parte do giro da operação)
    if do_piso_liq:
        r.valor_oferta = round(max(r.preco_recomendado, piso) + bruta + provaveis + pd_total, 2)
        r.valor_oferta_origem = ("liquidação dos ativos (piso)" if r.piso_usado == "liquidacao"
                                 else "ativos a mercado (piso)")
        r.ponte_dono = [("Ativos a valor de realização (inclui o caixa)", max(r.preco_recomendado, piso) + bruta + passivos_op),
                        ("(−) Fornecedores e obrigações", -passivos_op), ("(−) Dívida bruta", -bruta)]
        pd_total_ponte = 0.0  # na liquidação, os passivos (e a rescisão) já saem dentro de fornecedores e obrigações
    else:
        r.valor_oferta = round(base_c.valor_empresa + caixa, 2)
        r.valor_oferta_origem = "fluxo (DCF) + caixa"
        r.ponte_dono = [("Valor da empresa pelo fluxo (DCF base)", base_c.valor_empresa), ("(+) Caixa da empresa", caixa),
                        ("(−) Dívida bruta", -bruta)]
        pd_total_ponte = pd_total
    if pd_total_ponte:
        r.ponte_dono.append(("(−) Fornecedores vencidos e rescisão dos funcionários", -pd_total_ponte))
    if provaveis:
        r.ponte_dono.append(("(−) Contingências prováveis", -provaveis))
    if do_piso_liq and bp_ult and r.valor_oferta:
        peso = (bp_ult.estoques or 0) * p[criterio_piso(r.piso_usado)]["estoques"] / r.valor_oferta
        if peso >= 0.5:
            r.alertas.append(f"Valor de ida a mercado vem dos ativos e o estoque é {peso:.0%} deles: confirmar estoque "
                             "físico e valor de realização antes de ofertar (balanço reapresentado infla estoque).")
    r.ponte_dono.append(("= Sobra para o dono", round(sum(v for _, v in r.ponte_dono), 2)))
    if r.retencao_sugerida:
        r.ponte_dono.append(("(retido no fechamento até a contingência possível prescrever)", -r.retencao_sugerida))

    # venda forçada (decisão de 11/11/2026): sempre uma fração fixa (60%) da ida a mercado da venda a mercado, sem
    # piso de liquidação; a taxa do cenário passa a ser a implícita nesse valor (não mais a do Score + 3 p.p.)
    fr = (p.get("venda_forcada") or {}).get("fracao_do_mercado", 0.6)
    off_ida = bruta + provaveis + pd_total  # da parte do sócio ao valor de ida a mercado (base única)
    ida_forcada = round(fr * r.valor_oferta, 2)
    alvo_ev = ida_forcada - caixa
    if do_piso_liq:
        # 12/11/2026 (Emunah, regra do Guilherme): com a venda a mercado vindo dos ativos, o VALOR DA OPERAÇÃO da venda
        # forçada é SEMPRE 60% do valor da operação da venda a mercado (coluna ao lado), com a taxa implícita nesse
        # valor; o valor da empresa da forçada continua 60% do valor da venda a mercado (ativos)
        r.forcada_origem = "ativos"
        alvo_ev = round(fr * r.base.valor_empresa, 2)
    if fluxo > 0 and alvo_ev > 0:
        # taxa implícita sobre o MESMO fluxo da venda a mercado: o retorno de quem compra a 60% (com recuperação de
        # margem, o fluxo sem crescimento pode nem alcançar os 60%, por isso não se usa o fluxo do conservador)
        c1 = r.base
        proj1 = (fluxos_recuperacao(base.valor("Receita bruta"), c1.crescimento, risco.horizonte_anos,
                                    recuperacao["margens"]["partida"], recuperacao["margens"]["base"],
                                    recuperacao["anos"]) if recuperacao else None)
        final1 = proj1[-1] if proj1 else fluxo * (1 + c1.crescimento) ** risco.horizonte_anos
        terminal1 = max(mult_vt["base"] * final1, ativos_liquidos)
        ev_de = lambda tx: _dcf(fluxo, tx, c1.crescimento, risco.horizonte_anos, terminal1, perp,  # noqa: E731
                                cr["perpetuidade"], proj1)
        lo, hi = 0.0001, 10.0
        for _ in range(200):  # o valor cai com a taxa: bissecção
            mid = (lo + hi) / 2
            lo, hi = (mid, hi) if ev_de(mid)[2] > alvo_ev else (lo, mid)
        taxa_imp = round((lo + hi) / 2, 4)
        fluxos0, vt0, _ = ev_de(taxa_imp)
        r.cenarios[0] = Cenario(nome="conservador", taxa=taxa_imp, crescimento=c1.crescimento, anos=c1.anos,
                                fluxos=fluxos0, valor_terminal=vt0, valor_empresa=round(alvo_ev, 2),
                                valor_patrimonio=round(alvo_ev + ajuste_patrimonio, 2),
                                multiplo_do_fluxo=round(alvo_ev / fluxo, 2))
    otim_v = r.cenarios[2].valor_patrimonio
    r.faixa_venda = {"forcada": round(ida_forcada - off_ida, 2),
                     "mercado": r.preco_recomendado,
                     "maximo": round(max(otim_v, r.preco_recomendado), 2)}

    # régua da casa (payback): valor da empresa = anos × fluxo; patrimônio = empresa − dívida líquida − prováveis
    rp = p["regua_payback"]
    descontos = (bruta - caixa) + sum(c.valor for c in conts) + pd_total
    if fluxo > 0:
        for nome in ("forcada", "mercado", "maximo"):
            ev_regua = round(rp[nome] * fluxo, 2)
            r.regua_payback[nome] = {"anos": rp[nome], "valor_empresa": ev_regua,
                                     "valor_patrimonio": round(ev_regua - descontos, 2)}
        r.payback_preco = round((r.preco_recomendado + descontos) / fluxo, 2)
        if do_piso_liq and r.payback_preco > rp["maximo"]:
            r.alertas.append(f"Valor vem do piso (liquidação dos ativos), não do fluxo: pelo caixa ele se pagaria em "
                             f"{r.payback_preco:.1f} anos — a empresa vale mais fechada do que funcionando; discutir a "
                             "venda dos ativos em vez da empresa (confirmar valor de realização).")
        elif r.payback_preco > rp["maximo"]:
            r.alertas.append(f"Preço recomendado se paga em {r.payback_preco:.2f} anos de fluxo: acima da régua da "
                             f"casa ({rp['maximo']:.1f} anos). Comprador dificilmente aceita.")
        elif r.payback_preco < rp["forcada"] and r.preco_recomendado > 0:
            r.alertas.append(f"Preço recomendado se paga em {r.payback_preco:.1f} anos: abaixo da venda forçada da "
                             f"régua ({rp['forcada']:.1f}); conferir se o DCF não está conservador demais.")

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
        r.alertas.append("Liquidação dos ativos acima do valor pelo fluxo: a empresa vale mais fechada do que "
                         "funcionando — o relatório deve dizer isso e discutir a venda dos ativos (confirmar estoque e "
                         "imobilizado a valor de realização).")
    ref_ativos = r.patrimonio_mercado + bruta + provaveis + pd_total if r.patrimonio_mercado is not None else None
    if ref_ativos is not None and r.valor_oferta and ref_ativos > r.valor_oferta:
        am, vo = f"{ref_ativos:,.0f}".replace(",", "."), f"{r.valor_oferta:,.0f}".replace(",", ".")
        r.alertas.append(f"Ativos a mercado (R$ {am} na base de ida a mercado) acima da ida a mercado recomendada "
                         f"(R$ {vo}): argumento do vendedor na negociação, não valor — os ativos só rendem isso se a "
                         "operação for encerrada.")
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
