"""F4 — Normalização: da informação captada à DRE ECONÔMICA (o resultado que um comprador teria).

Regras (ver metodologia/parametros_normalizacao.json):
  1. Períodos: últimos exercícios com DRE de 12 meses e os últimos 12 meses (LTM) com receita mensal.
  2. Receita econômica: declarada (PGDAS/SPED/DRE) → gerencial, se o caixa a confirma → caixa, se os extratos
     cobrem o período e mostram receita acima da declarada. Gerencial sem confirmação vira sensibilidade.
  3. Custos: DRE gerencial (quando é a fonte da receita) ou DRE contábil com CMV proporcional à receita
     econômica e despesas fixas pelo valor contábil; sem DRE, o caixa (confiança baixa).
  4. Tributos recalculados no regime que o comprador teria (Simples até o limite, senão Lucro Presumido).
  5. Ajustes: de metodologia entram sozinhos (tributos, pró-labore de mercado); de julgamento ficam
     "propostos" até o analista aprovar em _valuation/ajustes_decisoes.json (Checkpoint 2).
Zero tokens.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from captacao.schemas import Categoria, DadosBrutos, DREAnual
from captacao.util import brl, meses_entre, normalizar_texto

PARAMETROS = Path(__file__).resolve().parents[1] / "metodologia" / "parametros_normalizacao.json"
Atividade = Literal["industria", "comercio", "servicos"]


def carregar_parametros(caminho: str | Path = PARAMETROS) -> dict:
    return json.loads(Path(caminho).read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- modelos


class Ajuste(BaseModel):
    id: str
    descricao: str
    valor: float  # efeito anual no resultado (+ aumenta o lucro, − reduz)
    tipo: Literal["metodologia", "julgamento"]
    fonte: str
    confianca: Literal["alta", "media", "baixa"] = "media"
    status: Literal["aplicado", "proposto", "aprovado", "rejeitado"] = "proposto"
    nota: str | None = None


class Linha(BaseModel):
    conta: str
    valor: float
    fonte: str


class DREEconomica(BaseModel):
    periodo: str  # "2025" ou "LTM 2025-10 a 2026-09"
    meses: int
    atividade: Atividade
    regime_comprador: str
    receita_fonte: str
    receitas_por_fonte: dict[str, float | None]
    linhas: list[Linha] = Field(default_factory=list)
    ajustes: list[Ajuste] = Field(default_factory=list)
    ebitda: float = 0.0
    ebit: float = 0.0
    lucro_economico: float = 0.0
    capex_manutencao: float | None = None
    capex_fonte: str | None = None
    owner_earnings: float | None = None
    confianca: Literal["alta", "media", "baixa"] = "media"
    alertas: list[str] = Field(default_factory=list)

    def valor(self, conta: str) -> float:
        return sum(l.valor for l in self.linhas if l.conta == conta)

    @property
    def margem_ebitda(self) -> float | None:
        r = self.valor("Receita bruta")
        return round(self.ebitda / r, 4) if r else None


# --------------------------------------------------------------------------- insumos


def atividade_principal(dados) -> Atividade:
    return atividade_evidenciada(dados) or "comercio"


def atividade_evidenciada(dados) -> Atividade | None:
    """Atividade principal quando há evidência (questionário, PGDAS, SPED); None se não houver."""
    q = getattr(dados, "questionario", None)
    if q:
        pcts = {"industria": q.valor("P01a") or 0, "comercio": q.valor("P01b") or 0, "servicos": q.valor("P01c") or 0}
        if any(pcts.values()):
            return max(pcts, key=pcts.get)
    simples = getattr(dados, "simples", None) or {}
    texto = normalizar_texto(" ".join((simples.get("atividades") or {}).keys()))
    if "INDUSTRIALIZADAS" in texto:
        return "industria"
    if "SERVICO" in texto and "MERCADORIA" not in texto:
        return "servicos"
    efd = getattr(dados, "efd", None) or []
    prod = sum(v for e in efd for c, v in e.por_cfop.items() if c[1:] in {"101", "107", "401"})
    revenda = sum(v for e in efd for c, v in e.por_cfop.items() if c[1:] in {"102", "106", "108", "403", "405"})
    if prod or revenda:
        return "industria" if prod >= revenda else "comercio"
    return None


def _receita_declarada_mensal(dados) -> tuple[dict[str, float], str | None]:
    if dados.pgdas:
        out: dict[str, float] = {}
        for p in dados.pgdas:
            out[p.competencia] = out.get(p.competencia, 0.0) + p.receita_bruta
        return out, "PGDAS-D"
    fiscal = getattr(dados, "fiscal_mensal", None) or []
    if fiscal:
        out = {}
        for f in fiscal:
            out[f.competencia] = out.get(f.competencia, 0.0) + f.receita_bruta - f.devolucoes
        return out, fiscal[0].fonte
    return {}, None


def _receita_gerencial_mensal(dados) -> dict[str, float]:
    out: dict[str, float] = {}
    for g in getattr(dados, "gerenciais", None) or []:
        for c, v in g.receita_mensal().items():
            out.setdefault(c, v)
    if not out:
        for g in dados.gerencial:
            if g.cliente is None:
                out[g.competencia] = out.get(g.competencia, 0.0) + g.receita
    return out


def _caixa_mensal(dados) -> tuple[dict[str, float], set[str]]:
    receita: dict[str, float] = {}
    cobertos: set[str] = set()
    for e in dados.extratos:
        for t in e.transacoes:
            m = f"{t.data:%Y-%m}"
            cobertos.add(m)
            if t.categoria == Categoria.RECEITA_OPERACIONAL:
                receita[m] = receita.get(m, 0.0) + t.valor
    return receita, cobertos


def _pro_labore_mercado(receita_anual: float, p: dict) -> float:
    for faixa in p["pro_labore_mercado"]["faixas_receita_anual"]:
        if faixa["ate"] is None or receita_anual <= faixa["ate"]:
            mensal = faixa["mensal"]
            break
    cfg = p["pro_labore_mercado"]
    return round(mensal * cfg["meses_por_ano"] * (1 + cfg["encargos"]), 2)


def _carga_comprador(receita: float, atividade: Atividade, dados, p: dict) -> tuple[str, float, float]:
    """→ (regime, tributos sobre a receita, IR/CS)."""
    if receita <= p["simples"]["limite_receita"]:
        aliq = (getattr(dados, "simples", None) or {}).get("aliquota_efetiva") or \
            p["simples"]["aliquota_efetiva_padrao"][atividade]
        return f"Simples (alíquota efetiva {aliq:.1%})", round(receita * aliq, 2), 0.0
    lp = p["lucro_presumido"]
    return ("Lucro Presumido", round(receita * (lp["pis_cofins_cumulativo"] + lp["icms_iss_sobre_receita"][atividade]), 2),
            round(receita * lp["irpj_csll_sobre_receita"][atividade], 2))


def _lucro_real(receita: float, custo_vendas: float, outras_despesas: float, resultado_antes_tributos: float,
                atividade: Atividade, p: dict) -> tuple[float, float]:
    """Tributos no Lucro Real (valores anuais; custos e despesas negativos). → (tributos sobre a receita, IR/CS).
    resultado_antes_tributos = receita + custos + despesas + D&A (antes de tributos sobre a receita)."""
    lr, lp = p["lucro_real"], p["lucro_presumido"]
    creditos = (abs(custo_vendas) * lr["creditos_pis_cofins_sobre"]["custo_vendas"]
                + abs(outras_despesas) * lr["creditos_pis_cofins_sobre"]["outras_despesas"])
    pis_cofins = max(0.0, (receita - creditos) * lr["pis_cofins_nao_cumulativo"])
    trib = pis_cofins + receita * lp["icms_iss_sobre_receita"][atividade]
    lucro = resultado_antes_tributos - trib
    if lucro <= 0:
        return round(trib, 2), 0.0
    irpj = lucro * lr["irpj"] + max(0.0, lucro - lr["limite_adicional_anual"]) * lr["adicional_irpj"]
    return round(trib, 2), round(irpj + lucro * lr["csll"], 2)


def _dre_do_ano(dados, ano: int, gerencial: bool = False) -> DREAnual | None:
    """DRE de 12 meses do ano; com mais de um CNPJ, soma as empresas do grupo (consolidação simples)."""
    fonte = getattr(dados, "dres_gerenciais", []) if gerencial else dados.dres
    cand = [d for d in fonte if d.exercicio == ano and d.meses == 12]
    if len(cand) <= 1:
        return cand[0] if cand else None
    campos = [k for k, v in DREAnual.model_fields.items() if v.annotation in (float | None, float)]
    soma = {k: (sum(getattr(d, k) or 0 for d in cand) if any(getattr(d, k) is not None for d in cand) else None)
            for k in campos}
    return DREAnual(cnpj="+".join(d.cnpj for d in cand), exercicio=ano, meses=12,
                    proveniencia=cand[0].proveniencia.model_copy(update={"localizacao": f"soma de {len(cand)} DREs"}),
                    **soma)


# --------------------------------------------------------------------------- períodos


def periodos(dados) -> list[tuple[str, list[str]]]:
    """[(nome, meses)] — LTM (se houver 12 meses de receita mensal) e os 2 últimos exercícios com DRE de 12 meses."""
    saida = []
    mensal = {**_receita_gerencial_mensal(dados), **_receita_declarada_mensal(dados)[0]}
    if mensal:
        fim = max(mensal)
        ano, m = map(int, fim.split("-"))
        total = ano * 12 + m - 12
        inicio = f"{total // 12:04d}-{total % 12 + 1:02d}"
        meses = meses_entre(inicio, fim)
        if sum(1 for x in meses if x in mensal) >= 12:
            saida.append((f"LTM {inicio} a {fim}", meses))
    anos = sorted({d.exercicio for d in dados.dres if d.meses == 12} |
                  {d.exercicio for d in getattr(dados, "dres_gerenciais", []) if d.meses == 12}, reverse=True)[:2]
    for a in anos:
        saida.append((str(a), meses_entre(f"{a}-01", f"{a}-12")))
    return saida


# --------------------------------------------------------------------------- normalização


def normalizar_periodo(dados, nome: str, meses: list[str], decisoes: dict, p: dict) -> DREEconomica:
    atividade = atividade_principal(dados)
    fator = 12 / len(meses)
    declarada_m, fonte_decl = _receita_declarada_mensal(dados)
    gerencial_m = _receita_gerencial_mensal(dados)
    caixa_m, cobertos = _caixa_mensal(dados)
    ano = int(nome) if nome.isdigit() else None
    contabil = _dre_do_ano(dados, ano) if ano else None
    ger_pdf = _dre_do_ano(dados, ano, gerencial=True) if ano else None

    def soma(serie):  # só se cobrir o período inteiro
        return round(sum(serie[m] for m in meses), 2) if all(m in serie for m in meses) else None

    receitas = {
        "declarada": soma(declarada_m) if declarada_m else None,
        "contabil": contabil.receita_bruta if contabil else None,
        "gerencial": soma(gerencial_m) if gerencial_m else (ger_pdf.receita_bruta if ger_pdf else None),
        "caixa": round(sum(caixa_m.get(m, 0.0) for m in meses), 2)
        if sum(1 for m in meses if m in cobertos) >= p["receita"]["cobertura_minima_caixa"] * len(meses) else None,
    }
    alertas: list[str] = []
    base = receitas["declarada"] or receitas["contabil"]
    fonte_receita = (fonte_decl if receitas["declarada"] else "DRE contábil") if base else None
    receita = base
    rel = p["receita"]["acima_da_declarada_relevante"]
    ger, caixa = receitas["gerencial"], receitas["caixa"]
    if ger and base and ger > base * (1 + rel):
        if caixa and caixa >= p["receita"]["confirmacao_gerencial_pelo_caixa"] * ger:
            receita, fonte_receita = ger, "gerencial confirmada pelo caixa"
        else:
            alertas.append(f"Receita gerencial R$ {brl(ger, 0)} acima da declarada R$ {brl(base, 0)} sem confirmação "
                           "pelo caixa: mantida a declarada (a gerencial fica como sensibilidade).")
    if caixa and base and caixa > (receita or 0) * (1 + rel) and fonte_receita != "gerencial confirmada pelo caixa":
        receita, fonte_receita = caixa, "caixa (receita acima da declarada comprovada nos extratos)"
    if receita is None and caixa:
        receita, fonte_receita = caixa, "caixa (sem receita declarada)"
    if receita is None and ger:
        receita, fonte_receita = ger, "gerencial (sem receita declarada nem caixa para confirmar)"
    if receita is None:
        raise ValueError(f"{nome}: sem receita em nenhuma fonte")
    receita_anual = receita * fator

    d = DREEconomica(periodo=nome, meses=len(meses), atividade=atividade, regime_comprador="",
                     receita_fonte=fonte_receita, receitas_por_fonte=receitas, alertas=alertas)

    def linha(conta, valor, fonte):
        if valor:
            d.linhas.append(Linha(conta=conta, valor=round(valor, 2), fonte=fonte))

    linha("Receita bruta", receita, fonte_receita)
    regime, trib, ircs = _carga_comprador(receita_anual, atividade, dados, p)  # Presumido é revisto no fim

    # ---- custos e despesas
    # custos da MESMA fonte da receita quando ela é gerencial (misturar receita gerencial com custo contábil infla
    # a margem); senão a DRE contábil do período, ou a mais recente para o LTM
    estrutura = None
    gerenciais = getattr(dados, "gerenciais", None) or []
    gerencial_cobre = bool(gerenciais) and all(any(m in g.competencias for g in gerenciais) for m in meses)
    usar_gerencial = fonte_receita.startswith("gerencial")
    if usar_gerencial and ger_pdf:
        estrutura, nome_estr = ger_pdf, "DRE gerencial"
    elif usar_gerencial and gerencial_cobre:
        pass  # usa as categorias da planilha gerencial abaixo
    elif contabil:
        estrutura, nome_estr = contabil, "DRE contábil"
    elif ano is None and dados.dres:
        ultimo = max((x for x in dados.dres if x.receita_bruta), key=lambda x: (x.exercicio, x.meses), default=None)
        if ultimo:
            estrutura, nome_estr = ultimo, f"DRE contábil {ultimo.exercicio} ({ultimo.meses} meses)"
    if estrutura is None and gerenciais:
        cats: dict[str, float] = {}
        for g in gerenciais:
            for cat, serie in g.por_categoria().items():
                cats[cat] = cats.get(cat, 0.0) + sum(serie.get(m, 0.0) for m in meses)
        linha("Custo das vendas", cats.get("custo_variavel"), "DRE gerencial (planilha)")
        linha("Despesas com pessoal", cats.get("despesa_pessoal"), "DRE gerencial (planilha)")
        linha("Despesas administrativas e comerciais",
              cats.get("despesa_administrativa", 0) + cats.get("despesa_comercial", 0), "DRE gerencial (planilha)")
        pro_lab_atual = -cats.get("pro_labore", 0.0) * fator
        da = 0.0
    elif estrutura is not None:
        escala = len(meses) / estrutura.meses
        base_estr = estrutura.receita_bruta or 0
        if not estrutura.custo_vendas and atividade in ("industria", "comercio"):
            d.alertas.append(f"{nome_estr} sem linha de CMV numa empresa de {atividade}: o custo das vendas pode estar "
                             "nas despesas ou faltar — o EBITDA pode estar superestimado; pedir a DRE com CMV.")
            d.confianca = "baixa"
        if estrutura.custo_vendas and base_estr:
            linha("Custo das vendas", estrutura.custo_vendas / base_estr * receita,
                  f"{nome_estr}: CMV de {abs(estrutura.custo_vendas) / base_estr:.1%} da receita aplicado à receita econômica")
        pessoal = (estrutura.despesas_pessoal or 0) * escala
        linha("Despesas com pessoal", pessoal, nome_estr)
        conhecidas = sum(x or 0 for x in (estrutura.despesas_pessoal, estrutura.pro_labore,
                                           estrutura.depreciacao_amortizacao, estrutura.financeiras_nas_operacionais))
        outras = ((estrutura.despesas_administrativas or 0) + (estrutura.despesas_comerciais or 0) - conhecidas) * escala
        linha("Despesas administrativas e comerciais", outras,
              f"{nome_estr} (sem pessoal, pró-labore, depreciação e juros/IOF)")
        pro_lab_atual = -(estrutura.pro_labore or 0) / estrutura.meses * 12
        da = (estrutura.depreciacao_amortizacao or 0) * escala
        if estrutura is not contabil and ano is None:
            d.alertas.append(f"Estrutura de custos do LTM estimada pela {nome_estr}.")
    else:
        desp: dict[str, float] = {}
        for e in dados.extratos:
            for t in e.transacoes:
                if f"{t.data:%Y-%m}" in meses and t.valor < 0:
                    desp[t.categoria.value] = desp.get(t.categoria.value, 0.0) + t.valor
        linha("Custos e despesas operacionais (caixa)", desp.get("despesa_operacional"), "extratos (caixa)")
        linha("Despesas com pessoal", desp.get("folha", 0) + desp.get("encargos_folha", 0), "extratos (caixa)")
        pro_lab_atual, da = 0.0, 0.0
        d.confianca = "baixa"
        d.alertas.append("Sem DRE: custos e despesas pelo caixa (inclui compras de estoque e pagamentos fora de "
                         "competência) — confiança baixa.")

    folha = getattr(dados, "folha", None) or []
    if not pro_lab_atual and folha:
        pro_lab_atual = sum(f.pro_labore for f in folha) / len({f.competencia for f in folha}) * 12
    if not pro_lab_atual and getattr(dados, "defis", None):
        pro_lab_atual = max(dados.defis, key=lambda x: x.ano).pro_labore_socios

    # ---- ajustes
    mercado = _pro_labore_mercado(receita_anual, p)
    if not pro_lab_atual:
        d.alertas.append("Pró-labore atual não aparece separado na fonte de custos: se a retirada dos sócios já estiver "
                         "dentro de 'pessoal', o pró-labore de mercado está sendo descontado em dobro — conferir.")
    d.ajustes.append(Ajuste(id="pro_labore_mercado", tipo="metodologia", status="aplicado", confianca="media",
                            descricao=f"Pró-labore de mercado (gestor contratado) R$ {brl(mercado, 0)}/ano no lugar do "
                                      f"pró-labore atual R$ {brl(pro_lab_atual, 0)}/ano",
                            valor=round(-mercado / fator, 2),  # o pró-labore atual já ficou fora das linhas
                            fonte="metodologia/parametros_normalizacao.json"))
    q = getattr(dados, "questionario", None)
    if q and q.valor("Q25a") == "Sim" and isinstance(q.valor("Q25b"), (int, float)):
        d.ajustes.append(Ajuste(id="despesas_pessoais", tipo="julgamento", confianca="baixa",
                                descricao=f"Despesas pessoais dos sócios pagas pela empresa (R$ {brl(q.valor('Q25b'), 0)}/mês, "
                                          "informado no questionário)", valor=round(q.valor("Q25b") * 12 / fator, 2),
                                fonte="questionário Q25"))
    planilha = getattr(dados, "planilha_nd", None)
    for i, aj in enumerate((planilha.abas.get("9_Ajustes", []) if planilha else []), start=1):
        if not aj.get("valor_r"):
            continue
        anual = aj["valor_r"] * (12 if (aj.get("periodicidade") or "").startswith("Mensal") else 1)
        sinal = -1 if "Receita" in (aj.get("tipo") or "") else 1  # receita que não se repete sai; despesa volta
        d.ajustes.append(Ajuste(id=f"planilha_ajuste_{i}", tipo="julgamento", confianca="baixa",
                                descricao=f"{aj.get('tipo') or 'Ajuste'}: {aj.get('descricao') or ''}".strip(),
                                valor=round(sinal * anual / fator, 2), fonte="Planilha ND, aba 9_Ajustes"))
    erp = getattr(dados, "erp", None) or {}
    pj_total = erp.get("pj_total_mensal")
    if pj_total:
        enc = p["encargos_pj_para_clt"]["percentual"]
        d.ajustes.append(Ajuste(id="encargos_pj", tipo="julgamento", confianca="baixa",
                                descricao=f"Encargos se os PJ (R$ {brl(pj_total, 0)}/mês) forem registrados como CLT ({enc:.0%})",
                                valor=round(-pj_total * 12 * enc / fator, 2), fonte="planilha de colaboradores PJ"))
    for k, dec in sorted(decisoes.items()):  # D1: funções do dono sem substituto, propostas pela F5
        if k.startswith("substituicao_") and dec.get("valor_proposto") is not None:
            d.ajustes.append(Ajuste(id=k, tipo="julgamento", confianca="media", descricao=dec["descricao"],
                                    valor=round(dec["valor_proposto"] / fator, 2),
                                    fonte=f"F5 — {dec.get('evidencia') or 'funções do dono'}"))
    for a in d.ajustes:  # decisões do analista (Checkpoint 2)
        dec = decisoes.get(a.id)
        if dec and dec.get("aprovado") is not None:  # null = ainda pendente: continua "proposto"
            a.status = "aprovado" if dec.get("aprovado") else "rejeitado"
            if dec.get("valor") is not None:
                a.valor = float(dec["valor"])
            a.nota = dec.get("nota")

    # ---- tributos do comprador: acima do limite do Simples, o menor entre Presumido e Real
    antes = sum(l.valor for l in d.linhas if l.conta != "Receita bruta") + \
        sum(a.valor for a in d.ajustes if a.status in ("aplicado", "aprovado")) + da
    if regime == "Lucro Presumido":
        cmv = d.valor("Custo das vendas")
        outras = sum(l.valor for l in d.linhas if l.conta not in ("Receita bruta", "Custo das vendas"))
        real_trib, real_ircs = _lucro_real(receita_anual, cmv * fator, outras * fator, (receita + antes) * fator,
                                           atividade, p)
        presumido_total, real_total = trib + ircs, real_trib + real_ircs
        d.alertas.append(f"Regime do comprador: Lucro Presumido R$ {brl(presumido_total, 0)}/ano × Lucro Real "
                         f"R$ {brl(real_total, 0)}/ano em tributos — usado o "
                         f"{'Real' if real_total < presumido_total else 'Presumido'} (aproximação; confirmar com o contador).")
        if real_total < presumido_total:
            regime, trib, ircs = "Lucro Real", real_trib, real_ircs
    d.regime_comprador = regime
    d.linhas.insert(1, Linha(conta="Tributos sobre a receita", valor=round(-trib / fator, 2),
                             fonte=f"recalculado no regime do comprador ({regime})"))

    # ---- resultado
    operacional = sum(l.valor for l in d.linhas)
    aplicados = sum(a.valor for a in d.ajustes if a.status in ("aplicado", "aprovado"))
    d.ebitda = round(operacional + aplicados, 2)
    d.ebit = round(d.ebitda + da, 2)
    if da:
        d.linhas.append(Linha(conta="Depreciação e amortização", valor=round(da, 2), fonte="DRE contábil"))
    d.lucro_economico = round(d.ebit - ircs / fator, 2)
    if ircs:
        d.linhas.append(Linha(conta="IRPJ/CSLL (regime do comprador)", valor=round(-ircs / fator, 2), fonte=regime))

    capex, fonte_capex = None, None
    if q and isinstance(q.valor("Q28"), (int, float)):
        capex, fonte_capex = q.valor("Q28") / fator, "questionário Q28 (capex de manutenção informado)"
    elif da:
        capex, fonte_capex = -da, "depreciação da DRE contábil"
    else:  # período sem DRE própria (LTM gerencial/caixa): depreciação anual da DRE contábil mais recente
        ultima = max((x for x in dados.dres if x.depreciacao_amortizacao), key=lambda x: (x.exercicio, x.meses), default=None)
        if ultima:
            capex = -ultima.depreciacao_amortizacao / ultima.meses * len(meses)
            fonte_capex = f"depreciação da DRE contábil {ultima.exercicio} ({ultima.meses} meses)"
    if capex is not None:
        d.capex_manutencao, d.capex_fonte = round(capex, 2), fonte_capex
        d.owner_earnings = round(d.lucro_economico - da - capex, 2)  # lucro + D&A − capex (da é negativo)
    else:
        d.owner_earnings = d.lucro_economico  # sem depreciação conhecida: capex de manutenção não estimado

    if any(a.status == "proposto" for a in d.ajustes):
        d.alertas.append(f"{sum(a.status == 'proposto' for a in d.ajustes)} ajuste(s) de julgamento aguardando o "
                         "analista (Checkpoint 2): não entram no resultado até serem aprovados.")
    if "caixa" in fonte_receita and receitas["declarada"]:
        d.alertas.append(f"Receita econômica acima da declarada em R$ {brl(receita - receitas['declarada'], 0)}: tratar "
                         "o passivo fiscal da receita não declarada como contingência no valuation.")
    if fonte_receita.startswith(("caixa", "gerencial (sem")) or (estrutura is None and not gerenciais):
        d.confianca = "baixa"
    return d


def normalizar(dados, decisoes: dict | None = None, parametros: dict | None = None) -> list[DREEconomica]:
    p = parametros or carregar_parametros()
    saida = []
    for nome, meses in periodos(dados):
        try:
            saida.append(normalizar_periodo(dados, nome, meses, decisoes or {}, p))
        except ValueError:
            continue
    return saida
