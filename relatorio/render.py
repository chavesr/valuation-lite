"""HTML do relatório (até ~10 páginas A4) e PDF pelo Edge/Chrome em modo headless (já instalados no Windows).

Capítulos (definidos pela ND em 07/11/2026): 1 Visão geral · 2 Sobre a empresa · 3 Análise de mercado e setor ·
4 Análise financeira e riscos do negócio · 5 Valuation · 6 Estrutura da transação.
Visual: o do relatório de investimento da ND (A4, branco, Helvetica), em versão reduzida e mais visual, sóbrio
(07/11/2026): preto e tons de cinza claro, blocos arredondados; laranja #FF9900 só nos destaques dos gráficos. Gráficos, ícones, tabelas e fluxogramas são desenhados pelo código (zero tokens); o redator
só escreve frases curtas. Cada capítulo é uma função própria, ajustada um a um com a ND.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from html import escape
from pathlib import Path

from relatorio import graficos as g
from relatorio.evolucao import evolucao
from relatorio.icones import icone

CSS = """
@page { size: A4; margin: 15mm 14mm 16mm 14mm;
        @top-right { content: __LOGO__; vertical-align: bottom; padding-bottom: 3mm; }
        @bottom-left { content: "NOVA DIREÇÃO  ·  Relatório de valuation  ·  confidencial"; font: 7pt Helvetica, Arial,
                       sans-serif; color: #8C8C8C; letter-spacing: .04em; }
        @bottom-right { content: "Pág. " counter(page); font: 7pt Helvetica, Arial, sans-serif; color: #8C8C8C; } }
@page capa { margin: 0; @top-right { content: none; } @bottom-left { content: none; } @bottom-right { content: none; } }
.capa { page: capa; position: relative; height: 296.5mm; overflow: hidden; background: #111111; color: #FFFFFF; }
.capa .logo { position: absolute; top: 22mm; left: 20mm; width: 62mm; }
.capa .meio { position: absolute; left: 20mm; right: 20mm; top: 108mm; }
.capa .rotulo { font-size: 9pt; letter-spacing: .28em; color: var(--laranja); font-weight: 700; }
.capa h1 { color: #FFFFFF; font-size: 34pt; line-height: 1.08; margin: 5mm 0 4mm; font-weight: 700; }
.capa .razao { font-size: 10pt; color: #BFBFBF; }
.capa .traco { width: 24mm; height: 1.4mm; background: var(--laranja); margin: 9mm 0 7mm; }
.capa .dados { display: grid; grid-template-columns: 34mm 1fr; gap: 2.4mm 4mm; font-size: 9.5pt; }
.capa .dados b { color: #8C8C8C; font-weight: 400; }
.capa .rodape { position: absolute; left: 20mm; right: 20mm; bottom: 18mm; font-size: 7.6pt; color: #8C8C8C;
                border-top: 1px solid #333333; padding-top: 4mm; line-height: 1.5; }
:root { --laranja:#FF9900; --laranja-claro:#FFF4E3; --cinza-quadro:#F2F2F2; --ink:#000000; --ink2:#1A1A1A;
        --gray:#6B6B6B; --gray2:#8C8C8C; --line:#E6E6E6; }
* { box-sizing: border-box; }
html, body { background: #FFFFFF; }
body { margin: 0; color: var(--ink2); font-family: Helvetica, Arial, sans-serif; font-size: 8.6pt; line-height: 1.42;
       -webkit-print-color-adjust: exact; print-color-adjust: exact; }
h1, h2, h3 { margin: 0; color: var(--ink); }
p { margin: 0 0 1.8mm; }
p, ul.marcador li, ul li { text-align: justify; hyphens: auto; -webkit-hyphens: auto; }
.capitulo { break-before: page; }
.cab { border-bottom: 1px solid var(--line); padding-bottom: 2.2mm; margin-bottom: 4mm; }
.cab h2 { font-size: 15pt; font-weight: 700; }
.cab .sub { color: var(--gray); font-size: 7.8pt; margin-top: .8mm; }
.quadro { border: 1px solid var(--line); border-radius: 3mm; padding: 3mm 3.4mm 2.6mm; margin-bottom: 3mm; break-inside: avoid; }
.quadro.destaque { background: var(--cinza-quadro); border-color: var(--cinza-quadro); }
.quadro h3 { display: flex; align-items: center; gap: 1.6mm; font-size: 9pt; font-weight: 700; color: var(--ink);
             margin-bottom: 1.6mm; }
.duas { display: grid; grid-template-columns: 1fr 1fr; gap: 3mm; }
.duas .quadro { margin-bottom: 0; }
.linha-quadros { margin-bottom: 3mm; }
.kpis { display: grid; grid-template-columns: repeat(5, 1fr); gap: 2mm; margin-bottom: 3.4mm; }
.kpi { background: var(--cinza-quadro); border-radius: 3mm; padding: 2.4mm 2.8mm; }
.kpi .rot { display: flex; align-items: center; gap: 1.2mm; font-size: 7pt; color: var(--gray); line-height: 1.2; min-height: 6mm; }
.kpi .val { font-size: 12.5pt; font-weight: 700; color: var(--ink); margin-top: 1mm; white-space: nowrap; }
.kpi .obs { font-size: 6.8pt; color: var(--gray2); line-height: 1.25; margin-top: .6mm; }
ul.marcador { list-style: none; padding: 0; margin: 0 0 2mm; }
ol.passos { margin: 1.5mm 0 2mm; padding-left: 5mm; }
ol.passos li { margin-bottom: 1.4mm; text-align: justify; }
ul.marcador li { position: relative; padding-left: 3.2mm; margin-bottom: 1.1mm; }
ul.marcador li::before { content: ""; position: absolute; left: 0; top: 1.5mm; width: 1.5mm; height: 1.5mm;
                         background: var(--ink2); border-radius: 50%; }
.legenda-graf { font-size: 7.2pt; color: var(--gray); margin: 1mm 0 .5mm; }
.nota { font-size: 6.8pt; color: var(--gray2); }
.kpi .val.pequeno { font-size: 10pt; white-space: normal; line-height: 1.2; }
.tres { display: grid; grid-template-columns: repeat(3, 1fr); gap: 2.4mm; margin-bottom: 1.5mm; }
.coluna-modelo { background: var(--cinza-quadro); border-radius: 3mm; padding: 2.2mm 2.6mm; }
.coluna-modelo .tit { display: flex; align-items: center; gap: 1.2mm; font-weight: 700; color: var(--ink);
                      margin-bottom: 1.4mm; }
.coluna-modelo ul.marcador { margin: 0; }
.coluna-modelo ul.marcador li { text-align: left; hyphens: manual; }
.grafico-org { margin: 1mm 0 2mm; }
.secao { margin: 0 0 2.6mm; break-inside: avoid; }
.kpis3 { display: grid; grid-template-columns: repeat(3, 1fr); gap: 1.6mm; margin-bottom: 2mm; }
.kpi.mini { padding: 1.6mm 2mm; } .kpi.mini .val { font-size: 10.5pt; } .kpi.mini .rot { min-height: 0; }
p.fosso { margin-top: 1.5mm; }
.secao h3 { display: flex; align-items: center; gap: 1.6mm; font-size: 9pt; font-weight: 700; color: var(--ink);
            margin-bottom: 2mm; padding-bottom: 1.2mm; border-bottom: 1px solid var(--line); }
h3.sec { font-size: 9pt; color: var(--ink); margin: 4mm 0 1.6mm; }
table { width: 100%; border-collapse: collapse; font-size: 7.8pt; margin: 1mm 0 3mm; }
th { text-align: left; background: var(--ink2); color: #FFFFFF; font-weight: 700; padding: 1.3mm 1.8mm; }
td { border-bottom: 1px solid var(--line); padding: 1.2mm 1.8mm; }
td.n, th.n { text-align: right; font-variant-numeric: tabular-nums; }
tr.total td { font-weight: 700; background: var(--cinza-quadro); }
.ficha { display: grid; grid-template-columns: repeat(3, 1fr); gap: 2mm 5mm; background: var(--cinza-quadro);
         padding: 2.5mm 3mm; margin-bottom: 3mm; border-radius: 3mm; }
.ficha b { display: block; font-size: 6.8pt; color: var(--gray); font-weight: 400; }
.perfil { display: grid; grid-template-columns: 1fr 1fr; gap: 0 6mm; background: var(--cinza-quadro);
          border-radius: 3mm; padding: 2.2mm 3.4mm; margin-bottom: 3.4mm; }
.perfil .lin { display: grid; grid-template-columns: 23mm 1fr; align-items: baseline; padding: .9mm 0; }
.perfil .rot { display: flex; align-items: center; gap: 1.4mm; font-size: 8pt; color: var(--gray); }
.perfil .rot svg { position: relative; top: .3mm; }
.perfil .val { font-size: 8pt; color: var(--ink); line-height: 1.3; }
.perfil .val small { font-size: 6.8pt; color: var(--gray2); }
.bloco-junto { break-inside: avoid; }
.formula { background: var(--cinza-quadro); border-radius: 2mm; padding: 1.6mm 3mm; margin: 1mm 0 1.4mm; font-size: 8.4pt; }
td.col, th.col { background: var(--laranja-claro); }
th.col { color: var(--ink); }
td.obs-cel { color: var(--gray); font-size: 7pt; }
.kpis4 { display: grid; grid-template-columns: repeat(4, 1fr); gap: 1.6mm; margin-bottom: 2mm; }
.nota.nd { color: var(--gray); font-style: italic; }
table.dre tr.sub td { font-weight: 700; }
table.dre tr.margem td { color: var(--gray); font-style: italic; }
table.verticais-larga td:nth-child(1) { width: 24%; } table.verticais-larga td:nth-child(2) { width: 6%; }
table.verticais-larga td:nth-child(3) { width: 42%; } table.verticais-larga td:nth-child(4) { width: 28%; }
table.compacta td, table.compacta th { padding: .55mm 1.8mm; line-height: 1.25; }
small { font-size: 6.8pt; color: var(--gray2); }
.aviso { background: var(--cinza-quadro); padding: 2mm 3mm; margin: 2mm 0; border-radius: 3mm; }
.disclaimer { font-size: 6.8pt; color: var(--gray2); margin-top: 6mm; border-top: 1px solid var(--line); padding-top: 2mm; }
table.ativos td:nth-child(1) { width: 27%; white-space: nowrap; } table.ativos td:nth-child(2), table.ativos td:nth-child(3) { width: 9%; }
table.riscos td:nth-child(1) { width: 62%; } table.riscos td:nth-child(2) { width: 9%; }
table.riscos td:nth-child(3) { width: 29%; }
"""


def brl(v: float | None) -> str:
    if v is None:
        return "—"
    s = f"{abs(v):,.0f}".replace(",", ".")
    return f"−R$ {s}" if v < 0 else f"R$ {s}"


def pct(v: float | None, casas: int = 1) -> str:
    return "—" if v is None else f"{v * 100:.{casas}f}%".replace(".", ",")


def _p(texto: str) -> str:
    return "".join(f"<p>{escape(par.strip())}</p>" for par in texto.split("\n") if par.strip())



def _card_divida(c: dict, v: dict) -> tuple[str, str, str] | None:
    """Dívida da empresa com o próprio sócio (credito_vendedor): o card mostra a dívida com terceiros e o caixa
    líquido — os haveres são quitados ao sócio na venda (10/11/2026, Vedis)."""
    cred = max(((x.get("credito_vendedor") or 0.0) for x in (_ida(c) or {}).values()), default=0.0)
    if cred <= 0:
        if v.get("haveres_fora_da_divida") and (v.get("divida_bruta") or 0) < 1:  # caminho B: endividamento zero
            return "Dívida", "Zero", f"caixa líquido de {g.brl_compacto(v.get('caixa') or 0)}"
        return None
    terceiros = max((v.get("divida_bruta") or 0) - cred, 0.0)
    liq = terceiros - (v.get("caixa") or 0)
    val = "Zero" if terceiros < 1 else g.brl_compacto(terceiros)
    obs = (f"caixa líquido de {g.brl_compacto(-liq)}" if liq < 0 else f"dívida líquida de {g.brl_compacto(liq)}")         + f"; {g.brl_compacto(cred)} de haveres do sócio quitados na venda"
    return "Dívida com terceiros", val, obs

def _ul(itens: list[str], classe: str = "marcador") -> str:
    return f"<ul class='{classe}'>" + "".join(f"<li>{escape(i)}</li>" for i in itens) + "</ul>"


ASSETS = Path(__file__).resolve().parent / "assets"


def _logo_b64(branco: bool = False) -> str:
    import base64
    arq = ASSETS / ("logo_nd_branco.png" if branco else "logo_nd.png")
    return base64.b64encode(arq.read_bytes()).decode() if arq.exists() else ""


def _logo_cabecalho() -> str:
    """Logo da ND para o cabeçalho das páginas: SVG com tamanho fixo (a margem da página não aceita CSS de largura)."""
    import base64
    b64 = _logo_b64()
    if not b64:
        return "none"
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="96" height="13" '
           f'viewBox="0 0 740 100"><image width="740" height="100" xlink:href="data:image/png;base64,{b64}"/></svg>')
    return f"url(data:image/svg+xml;base64,{base64.b64encode(svg.encode()).decode()})"


def capa(c: dict) -> str:
    perfil = (c.get("qual") or {}).get("perfil") or {}
    razao = (c.get("empresas_grupo") or [("", "")])[0][0] or c["empresa"]
    dados = [("Setor", c.get("setor") or "—"), ("Sede", perfil.get("cidade_uf") or "—"),
             ("Finalidade", c.get("finalidade") or "—"), ("Data", c["data"])]
    b64 = _logo_b64(branco=True)
    logo = f'<img class="logo" src="data:image/png;base64,{b64}" alt="Nova Direção">' if b64 else ""
    return (f'<section class="capa">{logo}<div class="meio"><div class="rotulo">RELATÓRIO DE VALUATION</div>'
            f'<h1>{escape(c["empresa_curto"])}</h1><div class="razao">{escape(razao)}</div><div class="traco"></div>'
            '<div class="dados">' + "".join(f"<b>{escape(k)}</b><span>{escape(v)}</span>" for k, v in dados)
            + '</div></div><div class="rodape">Preparado pela Nova Direção com base em documentos e informações '
            'fornecidos pela empresa e por seus sócios, não auditados. Documento confidencial: não compartilhe sem '
            'autorização.</div></section>')


def _cab(n: int, titulo: str, c: dict) -> str:
    return (f'<div class="cab"><h2>{n:02d}. {escape(titulo)} | {escape(c["empresa_curto"])}</h2>'
            f'<div class="sub">Setor: {escape(c.get("setor") or "—")} | {escape(c["data"])} | '
            f'{escape(c["finalidade"])}</div></div>')


def _secao(titulo: str, ic: str, corpo: str) -> str:
    """Tópico sem moldura: só o título com ícone e o conteúdo (gráficos, colunas, tabelas)."""
    return f'<div class="secao"><h3>{icone(ic, cor="#1A1A1A")}{escape(titulo)}</h3>{corpo}</div>'


def _quadro(titulo: str, ic: str, corpo: str, classe: str = "") -> str:
    return f'<div class="quadro {classe}"><h3>{icone(ic, cor="#1A1A1A")}{escape(titulo)}</h3>{corpo}</div>'


def _ida(c: dict) -> dict:
    """Cenários de ida a mercado do capítulo 6 por chave (forcada | mercado | maximo). Desde 10/11/2026 é o número
    que o relatório mostra; o preço das cotas só aparece como "parte do sócio" no capítulo 6."""
    return {x["chave"]: x for x in ((c.get("financeiro") or {}).get("transacao") or {}).get("cenarios") or []}


def _payback_ida(c: dict) -> float | None:
    """Anos de caixa para o comprador recuperar o valor de ida a mercado (líquido do caixa que vem com a empresa)."""
    merc, fluxo = _ida(c).get("mercado"), c["valuation"].get("fluxo_base") or 0
    return round(merc["liquido_caixa"] / fluxo, 2) if merc and fluxo > 0 else None


def _offsets(c: dict) -> tuple[float, float]:
    """Do valor para o sócio ao valor de ida a mercado, com o caixa da empresa dentro: + dívida bruta + prováveis,
    igual em todos os métodos (base única, 10/11/2026). Mantém o par (fluxo, ativos) para os chamadores."""
    v = c["valuation"]
    prov = sum(x["valor_bruto"] for x in v.get("contingencias", []) if x["classificacao"] == "provavel")
    off = (v.get("divida_bruta") or 0.0) + prov + sum((v.get("passivos_desconto") or {}).values())
    return off, off


def _evolucao_inv(c: dict) -> dict | None:
    """Quanto vira o investimento: mesmo desembolso (valor de ida a mercado líquido do caixa) na empresa, na Selic e
    no IPCA+."""
    v = c["valuation"]
    divida_liq = (v.get("divida_bruta") or 0) - (v.get("caixa") or 0)
    descontos = divida_liq + sum(x["valor_bruto"] for x in v.get("contingencias", []) if x["classificacao"] == "provavel")
    merc = _ida(c).get("mercado")
    caixa_emp = v.get("caixa") or 0.0
    desembolso = merc["bruto"] if merc else v["preco_recomendado"] + descontos + caixa_emp
    base_c = next((x for x in v["cenarios"] if x["nome"] == "base"), None)
    if not (base_c and base_c["fluxos"] and desembolso > 0 and v["fluxo_base"] > 0):
        return None
    terminal = base_c["valor_terminal"]  # o motor já usa a liquidação dos ativos como piso do valor terminal
    ev = evolucao(desembolso, base_c["fluxos"], terminal, v["risco"]["taxa_desconto"], c["ano"],
                  c.get("focus_selic") or {}, c.get("focus_ipca") or {}, c.get("juro_real", 0.06), caixa_emp)
    ev["caixa_empresa"] = caixa_emp
    n = len(ev["anos"]) - 1
    ev["ret_selic"] = (ev["selic"][-1] / ev["selic"][0]) ** (1 / n) - 1
    ev["ret_ipca"] = (ev["ipca_mais"][-1] / ev["ipca_mais"][0]) ** (1 / n) - 1
    ev["desembolso"] = desembolso
    return ev


def cap1_visao_geral(c: dict) -> str:
    t, v = c["textos"], c["valuation"]
    cen = {x["nome"]: x for x in v["cenarios"]}
    faixa = (cen["conservador"]["valor_patrimonio"], cen["otimista"]["valor_patrimonio"])
    divida_liq = (v.get("divida_bruta") or 0) - (v.get("caixa") or 0)
    margem = v["ebitda_base"] / v["receita_base"] if v.get("receita_base") else None
    ida = _ida(c)
    pb = _payback_ida(c) if ida else v.get("payback_preco")
    if ida.get("mercado"):
        k_valor = ("faixa", "Valor de ida a mercado",
                   g.faixa_compacta(min(x["bruto"] for x in ida.values()), max(x["bruto"] for x in ida.values())),
                   "da venda forçada ao potencial máximo")
    else:
        k_valor = ("faixa", "Faixa de valor", g.faixa_compacta(*faixa), "da venda forçada ao potencial máximo")
    kpis = [("receita", f"Receita {v['periodo_base']}", g.brl_compacto(v["receita_base"]),
             f"crescimento {pct(v['crescimento_historico'])} a.a." if v.get("crescimento_historico") is not None else ""),
            ("ebitda", "EBITDA econômico", g.brl_compacto(v["ebitda_base"]), f"margem de {pct(margem)}"),
            k_valor,
            ("relogio", "Payback", f"{str(pb).replace('.', ',')} anos" if pb else "—",
             "anos de caixa · régua da casa: até 3"),
            ("divida", "Dívida líquida", g.brl_compacto(divida_liq),
             f"{divida_liq / v['ebitda_base']:.1f}× o EBITDA".replace(".", ",") if v["ebitda_base"] > 0 else "")]
    if (cd := _card_divida(c, v)):
        kpis[-1] = ("divida",) + cd
    kpi_html = "".join(f'<div class="kpi"><div class="rot">{icone(ic, cor="#6B6B6B", tam=11)}{escape(rot)}</div>'
                       f'<div class="val">{escape(val)}</div><div class="obs">{escape(obs)}</div></div>'
                       for ic, rot, val, obs in kpis)
    if ida:
        valores = [(x["nome"], x["bruto"], x["obs"], False) for x in ida.values()]  # sem destaque: não recomendamos valor
        nota_vale = ("Valor de ida a mercado: o total que o comprador paga pela empresa, somando o que vai ao sócio e "
                     "as dívidas e obrigações da empresa que ele assume. Antes da comissão da ND.")
    else:
        fv = v.get("faixa_venda") or {"forcada": faixa[0], "mercado": v["preco_recomendado"], "maximo": faixa[1]}
        valores = [("Venda forçada", fv["forcada"], "0 a 6 meses", False),
                   ("Venda a mercado", fv["mercado"], "6 a 18 meses", False),
                   ("Potencial máximo", fv["maximo"], "comprador estratégico", False)]
        nota_vale = "Valores para 100% das cotas, já descontadas dívidas e contingências prováveis."
    if c.get("pedido_vendedor"):
        valores.append(("Expectativa do dono", c["pedido_vendedor"], "pedido informado", False))
    ev = _evolucao_inv(c)
    if ev:
        bloco_ev = ('<table class="compacta"><tr><th>Mesmo desembolso em</th>'
                    f'<th class="n">Vira em {ev["anos"][-1]}</th><th class="n">Retorno a.a.</th></tr>'
                    + "".join(f'<tr class="{"total" if dest else ""}"><td>{rot}</td><td class="n">{g.brl_compacto(serie[-1])}</td>'
                              f'<td class="n">{pct(ret) if ret is not None else ND}</td></tr>'
                              for rot, serie, ret, dest in (("A empresa", ev["empresa"], ev["tir"], True),
                                                            ("Selic", ev["selic"], ev["ret_selic"], False),
                                                            ("IPCA+", ev["ipca_mais"], ev["ret_ipca"], False)))
                    + f'</table><div class="nota">Desembolso do comprador: {g.brl_compacto(ev["desembolso"])}, o '
                    'valor de ida a mercado no cenário venda a mercado (parte do sócio + dívidas assumidas)'
                    + (f'; o caixa de {g.brl_compacto(ev["caixa_empresa"])} que vem com a empresa entra no retorno'
                       if ev.get("caixa_empresa") else '')
                    + '. A diferença para a renda fixa é o prêmio pelo risco. Ano a ano no capítulo 5.</div>')
    else:
        bloco_ev = '<div class="nota">Sem caixa positivo projetado: comparação com a renda fixa não se aplica.</div>'
    vt = (c.get("financeiro") or {}).get("verticais") or []
    notas_radar = [(nome.split(" e ")[0].replace("Confiabilidade da informação", "Informação")
                    .replace("Setor", "Setor/fosso"), nota) for nome, nota, _ in c["notas"]]
    return "".join([
        _cab(1, "Visão geral", c),
        _quadro("A empresa", "empresa", f"<p>{escape(t['tese'])}</p>", "destaque"),
        f'<div class="kpis">{kpi_html}</div>',
        '<div class="duas">',
        _secao("Por que olhar", "positivo", _ul(t["por_que_olhar"])
               + '<div class="legenda-graf">Receita e EBITDA econômico (R$)</div>' + g.colunas_mini(c["grafico_dre"])),
        _secao("O que pesa contra", "alerta", _ul(t["o_que_pesa_contra"])
               + (f'<div class="legenda-graf">Risco por vertical (5 = mais sólido)</div>'
                  + g.radar_verticais([(x["vertical"], x["nota"]) for x in vt]) if vt else
                  '<div class="legenda-graf">Risco por área (5 = mais sólido)</div>' + g.radar(notas_radar))),
        '</div><div class="duas">',
        _secao("Quanto vale", "valor", g.barras_valor(valores) + f'<div class="nota">{escape(nota_vale)}</div>'),
        _secao("Quanto vira o investimento", "retorno", bloco_ev),
        '</div>'])


def _cnpj(cnpj: str) -> str:
    d = "".join(ch for ch in cnpj or "" if ch.isdigit())
    return f"{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}" if len(d) == 14 else (cnpj or "—")


def cap2_empresa(c: dict) -> str:
    t, q = c["textos"], c.get("qual") or {}
    perfil = q.get("perfil") or {}
    fund = perfil.get("fundacao") or min((e["ano"] for e in q.get("linha_do_tempo") or []), default=None)
    anos = c["ano"] - fund if fund else None
    grupo = c.get("empresas_grupo") or []
    razao, cnpj = grupo[0] if grupo else (c.get("empresa") or "—", "")
    extra_cnpj = f"+{len(grupo) - 1} no grupo" if len(grupo) > 1 else ""
    func = perfil.get("funcionarios")
    esquerda = [("cartao", "Razão social", razao, ""),
                ("documento", "CNPJ", _cnpj(cnpj), extra_cnpj),
                ("local", "Sede", perfil.get("cidade_uf") or "—", "")]
    direita = [("etiqueta", "Setor", (perfil.get("setor") or c.get("setor") or "—")[:70], ""),
               ("pessoas", "Funcionários", str(func) if func else "—", "declarado" if func else ""),
               ("calendario", "Fundação", str(fund) if fund else "—", f"{anos} anos de mercado" if anos else "")]
    coluna = lambda itens: "<div>" + "".join(  # noqa: E731
        f'<div class="lin"><div class="rot">{icone(ic, cor="#6B6B6B", tam=11)}{escape(rot)}</div>'
        f'<div class="val">{escape(val)}{f" <small>· {escape(obs)}</small>" if obs else ""}</div></div>'
        for ic, rot, val, obs in itens) + "</div>"
    cards = coluna(esquerda) + coluna(direita)
    h = ['<section class="capitulo">' + _cab(2, "Sobre a empresa", c),
         f'<div class="perfil">{cards}</div>',
         _quadro("O negócio", "empresa", _p(t["sobre_empresa"]), "destaque")]
    eventos = [(e["ano"], e["evento"]) for e in q.get("linha_do_tempo") or []]
    if eventos:
        h.append(_secao("Linha do tempo", "calendario", g.linha_do_tempo(eventos)))
    m = q.get("modelo") or {}
    if any(m.get(k) for k in ("operacao", "venda", "receita")):
        colunas = "".join(f'<div class="coluna-modelo"><div class="tit">{icone(ic, cor="#1A1A1A", tam=12)}'
                          f'{escape(tit)}</div>{_ul(m.get(k) or ["—"])}</div>'
                          for k, tit, ic in (("operacao", "Operação", "empresa"), ("venda", "Como vende", "pessoas"),
                                             ("receita", "Como ganha dinheiro", "divida")))
        h.append(_secao("Modelo de negócio", "receita", f'<div class="tres">{colunas}</div>'))
    org = q.get("organograma") or []
    decide = q.get("quem_decide") or []
    corpo = ""
    if org:
        corpo += f'<div class="grafico-org">{g.organograma(org)}</div>'
    if decide:
        corpo += ('<table><tr><th>Decisão</th><th>Quem decide</th><th>Como</th></tr>'
                  + "".join(f"<tr><td>{escape(d['decisao'])}</td><td>{escape(d['quem'])}</td><td>{escape(d['como'])}</td></tr>"
                            for d in decide) + '</table>')
    h += [_quadro("Gestão e pessoas", "pessoas", _p(t["gestao_pessoas"]), "destaque"),
          _secao("Organograma e quem decide", "pessoas", corpo) if corpo else "",
          '<div class="nota">Perfil, histórico, operação e organograma com base no que o empreendedor declarou e nos '
          'documentos recebidos.</div>', '</section>']
    return "".join(h)


def _num(v: float | None, casas: int = 2, suf: str = "%") -> str:
    return "—" if v is None else f"{v:.{casas}f}{suf}".replace(".", ",")


def cap3_mercado(c: dict) -> str:
    t, q, v = c["textos"], c.get("qual") or {}, c["valuation"]
    fosso = q.get("fosso") or {}
    texto = _p(t["mercado_setor"])
    if fosso:
        fontes = ", ".join(fosso.get("fontes") or []) or "—"
        texto += (f'<p class="fosso"><b>Fosso competitivo: {escape(fosso.get("forca", "—"))}</b> · fontes: '
                  f'{escape(fontes)}</p>')
    h = ['<section class="capitulo">' + _cab(3, "Análise de mercado e setor", c),
         _quadro("O setor", "empresa", texto, "destaque")]
    if q.get("cadeia_valor"):
        h.append(_secao("Cadeia de valor", "faixa", g.cadeia_valor(q["cadeia_valor"])
                        + '<div class="nota">Em preto, as etapas em que a empresa atua.</div>'))
    pos = q.get("posicao_empresa")
    mapa = (g.mapa_posicionamento(q.get("concorrentes") or [],
                                  (re.sub(r"\s*\(.*\)$", "", c["empresa_curto"]), pos["preco"], pos["especializacao"]) if pos else None)
            if (q.get("concorrentes") or pos) else '<div class="nota">Sem concorrentes informados.</div>')
    sgs, focus, prox = c.get("sgs") or {}, c.get("focus") or {}, str(c["ano"] + 1)
    med = lambda k: ((focus.get(k) or {}).get("medianas") or {}).get(prox)  # noqa: E731
    cards = [("Selic hoje", _num((sgs.get("selic_meta") or {}).get("valor")), "meta do Copom"),
             ("Selic esperada", _num(v["risco"]["selic"] * 100), f"média no horizonte"),
             ("IPCA 12 meses", _num((sgs.get("ipca_12m") or {}).get("valor")), "inflação acumulada"),
             (f"PIB {prox}", _num(med("pib"), 1), "crescimento esperado"),
             (f"Dólar {prox}", _num(med("cambio"), 2, "").join(["R$ ", ""]) if med("cambio") else "—", "esperado"),
             ("Capital de giro", _num((sgs.get("credito_pj_capital_giro") or {}).get("valor"), 1), "juros a.a. para empresas")]
    cards_html = "".join(f'<div class="kpi mini"><div class="rot">{escape(r)}</div><div class="val">{escape(x)}</div>'
                         f'<div class="obs">{escape(o)}</div></div>' for r, x, o in cards)
    anos = [c["ano"] + i for i in range(0, 5)]
    serie = lambda k: [((focus.get(k) or {}).get("medianas") or {}).get(str(a)) for a in anos]  # noqa: E731
    traj = g.linhas_rentabilidade(anos, [("Selic", serie("selic"), g.LARANJA), ("IPCA", serie("ipca"), "#9A9A9A")])
    h += ['<div class="duas">',
          _secao("Posicionamento competitivo", "faixa", mapa
                 + '<div class="nota">Notas de 1 a 5 a partir do que o empreendedor e os documentos informam.</div>'),
          _secao("Cenário econômico", "receita", f'<div class="kpis3">{cards_html}</div>'
                 '<div class="legenda-graf">Trajetória esperada (Focus/BCB, % a.a.)</div>' + traj),
          '</div>']
    conc = q.get("concorrentes") or []
    if conc:
        h.append(_secao("Concorrentes", "pessoas",
                        '<table class="compacta"><tr><th>Concorrente</th><th>Perfil</th><th>Como a empresa se compara</th></tr>'
                        + "".join(f"<tr><td>{escape(k['nome'])}</td><td>{escape(k.get('perfil', ''))}</td>"
                                  f"<td>{escape(k.get('comparacao', ''))}</td></tr>" for k in conc) + '</table>'))
    h.append('</section>')
    return "".join(h)


ND = "n/d"


def _nd_nota(o_que: str) -> str:
    return f'<div class="nota nd">Não informado. Pedir ao vendedor: {escape(o_que)}</div>'


def _mil(v: float | None) -> str:
    """R$ mil sem casas, negativo entre parênteses; n/d quando falta."""
    if v is None:
        return ND
    s = f"{abs(v) / 1000:,.0f}".replace(",", ".")
    return f"({s})" if v < 0 else s


def _dias(v: float | None) -> str:
    return ND if v is None else f"{v:.0f}"


def _vezes(v: float | None) -> str:
    return ND if v is None else f"{v:.1f}x".replace(".", ",")


def _pct1(v: float | None) -> str:
    return ND if v is None else f"{v:.1f}%".replace(".", ",")


def _pct_frac(v: float | None) -> str:
    return ND if v is None else _pct1(v * 100)


def _mes(comp: str) -> str:
    meses = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]
    a, m = comp.split("-")
    return f"{meses[int(m) - 1]}/{a[2:]}"


def _bloco_clientes(cl: dict | None) -> str:
    if cl and cl.get("b2c"):  # 11/11/2026 (IBRATE): clientes pessoa física, pulverizados — sem ranking de clientes
        cards_html = "".join(f'<div class="kpi mini"><div class="rot">{escape(c["rotulo"])}</div><div class="val">'
                             f'{escape(c["valor"])}</div><div class="obs">{escape(c.get("obs") or "")}</div></div>'
                             for c in cl["cards"])
        return (f'<div class="kpis4">{cards_html}</div>'
                f'<div class="nota">{escape(cl.get("texto") or "")} Fonte: {escape(cl.get("fonte") or ND)}.</div>')
    if not cl or not cl.get("ranking"):
        return _nd_nota("os 20 maiores clientes dos últimos 3 anos, com faturamento no ano e setor de atuação "
                        "(planilha da ND) ou a curva ABC das notas fiscais.")
    tem_setor = any(r.get("setor") for r in cl["ranking"])
    linhas = "".join(f"<tr><td>{i}</td><td>{escape(r['cliente'])}</td>"
                     + (f"<td>{escape(r.get('setor') or ND)}</td>" if tem_setor else "")
                     + f"<td class='n'>{_mil(r['valor'])}</td><td class='n'>{_pct_frac(r['participacao'])}</td></tr>"
                     for i, r in enumerate(cl["ranking"][:10], 1))
    ano = f" em {cl['ano']}" if cl.get("ano") else ""
    cards = [(cl.get("rotulo_qtd") or "Clientes", str(cl.get("clientes_pj") or ND),
              cl.get("obs_qtd") or ano.strip() or "no período"),
             ("Maior cliente", _pct_frac(cl.get("maior")), "da receita"),
             ("5 maiores", _pct_frac(cl.get("top5")), "da receita"),
             ("10 maiores", _pct_frac(cl.get("top10")), "da receita")]
    cards_html = "".join(f'<div class="kpi mini"><div class="rot">{escape(r)}</div><div class="val">{escape(x)}</div>'
                         f'<div class="obs">{escape(o)}</div></div>' for r, x, o in cards)
    tabela = (f'<table class="compacta"><tr><th>#</th><th>Cliente</th>' + ("<th>Setor</th>" if tem_setor else "")
              + f'<th class="n">Receita{escape(ano)} (R$ mil)</th><th class="n">Part.</th></tr>{linhas}</table>')
    setores = cl.get("por_setor") or []
    lado = (('<div class="legenda-graf">Receita dos clientes listados por setor (% da receita)</div>'
             + g.barras_percentual(setores)) if setores else "")
    corpo = (f'<div class="duas"><div>{tabela}</div><div>{lado}</div></div>' if lado else tabela)
    obs = f"Fonte: {escape(cl.get('fonte') or ND)}."
    if not cl.get("base_receita", True):
        obs += " Sem a receita do ano: participação sobre a soma dos clientes listados (superestima a concentração)."
    return f'<div class="kpis4">{cards_html}</div>{corpo}<div class="nota">{obs}</div>'


def _bloco_operacional(op: dict) -> str:
    vol, pre = op["volume"], op["preco"]
    ult = len(op["anos"]) - 1

    def graf(serie, titulo):
        itens = [(a, v, "") for a, v in zip(op["anos"], serie["valores"])]
        un = f" ({escape(serie['unidade'])})" if serie["unidade"] else ""
        return (f'<div class="legenda-graf">{escape(serie["nome"])}{un}</div>'
                + g.colunas_serie(itens, {ult}, titulo=titulo))

    num = lambda v: f"{v:,.0f}".replace(",", ".") if v >= 100 or float(v).is_integer() else f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")  # noqa: E731
    conta = (f'<div class="formula"><b>{escape(op["anos"][-1])}:</b> {num(vol["valores"][-1])} {escape(vol["unidade"])} '
             f'× {num(pre["valores"][-1])} {escape(pre["unidade"])}' + (" × 12 meses" if op.get("mensal") else "")
             + f' = <b>{escape(g.brl_compacto(op["receita"][-1]))}</b> de receita no ano</div>')
    return (f'<div class="duas"><div>{graf(vol, "Volume por ano")}</div><div>{graf(pre, "Preço médio por ano")}</div></div>'
            + conta + f'<div class="nota">Fonte: {escape(op.get("fonte") or ND)}. Volume × preço explica a receita; '
            'diferença para a DRE vem de outras linhas, devoluções e descontos.</div>')


def cap4_financeiro(c: dict) -> str:
    t, v, f = c["textos"], c["valuation"], c["financeiro"]
    q = c.get("qual") or {}
    h = ['<section class="capitulo">', _cab(4, "Análise financeira e riscos do negócio", c),
         _quadro("Leitura financeira", "receita", _p(t["leitura_financeira"]), "destaque")]

    # análise operacional (x · y = receita) e base de clientes
    op = f.get("operacional")
    if op:
        h.append(_secao("Análise operacional", "ebitda", _bloco_operacional(op)))
    elif f.get("operacional_resumo"):  # 12/11/2026 (Emunah): só o retrato atual, sem série ano a ano
        h.append(_secao("Análise operacional", "ebitda", f'<p>{escape(f["operacional_resumo"])}</p>'
                        '<div class="nota">Série ano a ano de volume e preço não informada: pedir ao vendedor.</div>'))
    else:
        h.append(_secao("Análise operacional", "ebitda", _nd_nota(
            "os dois indicadores que explicam a receita, ano a ano (ex.: volume vendido e preço médio; "
            "clientes ativos e ticket médio).")))
    h.append(_secao("Base de clientes", "pessoas", _bloco_clientes(f.get("clientes"))))

    # receita: anual + sazonalidade + linhas
    ra = f["receita_anual"]
    if ra:
        itens = [(a, rb, "" if cr is None else f"{'+' if cr >= 0 else ''}{cr:.0f}%") for a, rb, cr in ra]
        bloco_ano = ('<div class="legenda-graf">Receita bruta por ano (R$) e crescimento</div>'
                     + g.colunas_serie(itens, {len(itens) - 1}, titulo="Receita bruta por ano"))
        if len(ra) >= 3 and ra[0][1]:
            cagr = ((ra[-1][1] / ra[0][1]) ** (1 / (len(ra) - 1)) - 1) * 100
            bloco_ano += f'<div class="nota">Crescimento médio de {_pct1(cagr)} a.a. entre {ra[0][0]} e {ra[-1][0]}.'
        else:
            bloco_ano += '<div class="nota">'
        if f.get("parcial"):
            bloco_ano += f' {escape(f["parcial"]["rotulo"])}: {escape(g.brl_compacto(f["parcial"]["rb"]))} até agora.'
        bloco_ano += f' Fonte: {escape(f.get("receita_anual_fonte") or "DRE contábil")}.</div>'
    else:
        bloco_ano = _nd_nota("as DREs anuais dos últimos 3 anos.")
    m = f.get("mensal")
    if m:
        top = sorted(range(len(m["valores"])), key=lambda i: -m["valores"][i])[:3]
        itens = [(_mes(k), val, "") for k, val in zip(m["meses"], m["valores"])]
        bloco_mes = ('<div class="legenda-graf">Faturamento mensal (R$) · em laranja, os 3 maiores meses</div>'
                     + g.colunas_serie(itens, set(top), altura=110, largura=660, titulo="Faturamento mensal")
                     + f'<div class="nota">{_mes(m["meses"][0])} a {_mes(m["meses"][-1])} · fonte: {escape(m["fonte"] or ND)}.</div>')
    else:
        bloco_mes = _nd_nota("o faturamento mês a mês dos últimos 24 meses (declarações do Simples ou planilha da ND).")
    linhas_rec = f.get("linhas_receita")
    mix = q.get("mix_receita") or []
    if linhas_rec:
        bloco_linhas = ('<div class="legenda-graf">Receita por linha (R$) e participação no último ano</div>'
                        + g.linhas_empilhadas(linhas_rec["anos"], linhas_rec["linhas"])
                        + f'<div class="nota">Fonte: {escape(linhas_rec["fonte"])}.</div>')
    elif mix:
        bloco_linhas = ('<div class="legenda-graf">Participação na receita (declarada, último ano)</div>'
                        + g.barras_percentual([(x["item"], x["percentual"]) for x in mix]))
    else:
        bloco_linhas = _nd_nota("a receita de cada linha de produto ou serviço nos últimos 3 anos.")
    if not m and not linhas_rec and not mix:  # os dois sem dado: a nota da sazonalidade vai na coluna da direita
        h += ['<div class="duas">', _secao("Análise de receita", "receita", bloco_ano),
              '<div>' + _secao("Linhas de receita", "faixa", bloco_linhas)
              + _secao("Sazonalidade", "calendario", bloco_mes) + '</div>', '</div>']
    else:
        h += ['<div class="duas">', _secao("Análise de receita", "receita", bloco_ano),
              _secao("Linhas de receita", "faixa", bloco_linhas), '</div>',
              _secao("Sazonalidade", "calendario", bloco_mes)]

    # custos
    cu, dre = f.get("custos"), f["dre"]
    if cu and cu.get("margens"):  # 11/11/2026: composição montada pelo analista a partir do gerencial
        series = [(nome, vals, cor) for (nome, vals), cor in zip(cu["margens"], (g.LARANJA, g.TINTA, g.CINZA))]
    elif cu:
        idx = [dre["colunas"].index(a) for a in cu["anos"]]
        margens = [(nome, [vals[i] for i in idx]) for nome, vals in dre["margens"]]
        series = [(nome.replace('Margem ', '').capitalize().replace('Ebitda', 'EBITDA'), vals, cor)
                  for (nome, vals), cor in zip(margens, (g.CINZA, g.LARANJA, g.TINTA))
                  if all(x is not None for x in vals)]
    if cu:
        h += ['<div class="duas">',
              _secao("Análise de custos", "divida",
                     '<div class="legenda-graf">Para onde vai cada R$ 100 de receita bruta</div>'
                     + g.empilhadas_100(cu["anos"], cu["segmentos"])),
              _secao("Margens", "ebitda", '<div class="legenda-graf">Margens sobre a receita bruta (%)</div>'
                     + g.linhas_rentabilidade(cu["anos"], series)), '</div>']
        if cu.get("nota"):
            h.append(f'<div class="nota">{escape(cu["nota"])}</div>')
    else:
        h.append(_secao("Análise de custos", "divida", _nd_nota("a DRE com custo das vendas e despesas abertas.")))

    # DRE simplificado
    def tabela(dre_t):
        cab = "".join(f"<th class='n'>{escape(p)}</th>" for p in dre_t["colunas"])
        corpo = "".join(f"<tr class='{cls}'><td>{escape(rot)}</td>" + "".join(f"<td class='n'>{_mil(x)}</td>" for x in vals)
                        + "</tr>" for rot, vals, cls in dre_t["linhas"])
        corpo += "".join(f"<tr class='margem'><td>{escape(rot)}</td>" + "".join(f"<td class='n'>{_pct1(x)}</td>" for x in vals)
                         + "</tr>" for rot, vals in dre_t["margens"])
        return f'<table class="dre compacta"><tr><th>R$ mil</th>{cab}</tr>{corpo}</table>'

    if dre["colunas"]:
        nota = dre.get("nota") or (
            "Valores da DRE contábil, como reportados (R$ mil; negativos entre parênteses). "
            + ("" if dre["detalhada"] else "A empresa não abre custos e despesas: mostramos receita, lucro "
               "operacional e lucro líquido. ") + "n/d = não disponível.")
        h.append(_secao(dre.get("titulo") or "DRE simplificado", "valor", tabela(dre) + f'<div class="nota">{escape(nota)}</div>'))
        dc_ref = f.get("dre_contabil")  # 12/11/2026 (Emunah): a contábil continua no relatório, como referência
        if dc_ref:
            h.append(_secao("DRE contábil (como reportada, só referência)", "valor", tabela(dc_ref)
                            + '<div class="nota">Valores da DRE contábil assinada pelo contador (R$ mil; negativos entre '
                              'parênteses). Não é a base do valuation: ver a DRE gerencial acima e a conciliação abaixo. '
                              'n/d = não disponível.</div>'))
    else:
        h.append(_secao("DRE simplificado", "valor", _nd_nota("as DREs anuais dos últimos 3 anos.")))

    # 12/11/2026 (Emunah): receita e lucro como a empresa declarou (briefing), ao lado do contábil, com a conciliação
    dc = f.get("declarado")
    if dc and dc.get("linhas"):
        cab = "".join(f"<th{'' if i == 0 else ' class=\"n\"'}>{escape(x)}</th>" for i, x in enumerate(dc["colunas"]))
        corpo = "".join("<tr>" + "".join(f"<td{'' if i == 0 else ' class=\"n\"'}>"
                                         f"{escape(x) if isinstance(x, str) else _mil(x)}</td>" for i, x in enumerate(r))
                        + "</tr>" for r in dc["linhas"])
        h.append(_secao(dc.get("titulo") or "Números declarados pela empresa", "receita",
                        f'<table class="compacta">{"<tr>" + cab + "</tr>"}{corpo}</table>'
                        + (f'<div class="nota">{escape(dc["nota"])}</div>' if dc.get("nota") else "")))

    # ponte contábil → econômico
    p = f.get("ponte")
    if p:
        nota = (f"Período {escape(p['periodo'])}. O EBITDA econômico é o que um comprador teria com a empresa "
                "rodando sem o dono atual e com os tributos do seu regime.")
        if p["pendentes"]:
            nota += (f" {p['pendentes']} ajuste(s) de julgamento ainda em aprovação "
                     f"({escape(g.brl_compacto(p['pendentes_valor']))}) não entram aqui.")
        h.append(_secao("Do resultado contábil ao econômico", "faixa", g.cascata_ponte(p["itens"])
                        + f'<div class="nota">{nota}</div>'))

    # capital de giro e dívida
    gd = f.get("giro") or []
    if gd:
        anos = "".join(f"<th class='n'>{x['ano']}</th>" for x in gd)
        lin = [("Prazo de recebimento (dias)", [_dias(x["pmr"]) for x in gd]),
               ("Prazo de estoque (dias)", [_dias(x["pme"]) + ("*" if x["estoque_fonte"] == "DEFIS" and x["pme"] else "")
                                            for x in gd]),
               ("Prazo de pagamento (dias)", [_dias(x["pmp"]) for x in gd]),
               ("Ciclo de caixa (dias)", [_dias(x["ciclo"]) for x in gd]),
               ("Dívida bruta (R$ mil)", [_mil(x["divida_bruta"]) for x in gd]),
               ("Caixa (R$ mil)", [_mil(x["caixa"]) for x in gd]),
               ("Dívida líquida / EBITDA", [_vezes(x["alavancagem"]) for x in gd])]
        tabela = (f'<table class="compacta"><tr><th></th>{anos}</tr>'
                  + "".join(f"<tr class='{'total' if 'Ciclo' in r else ''}'><td>{escape(r)}</td>"
                            + "".join(f"<td class='n'>{escape(x)}</td>" for x in vals) + "</tr>" for r, vals in lin)
                  + '</table>')
        obs = "Prazos sobre receita bruta e custo das vendas do ano; ciclo = recebimento + estoque − pagamento."
        if any(x["estoque_fonte"] == "DEFIS" for x in gd):
            obs += " *Estoque da DEFIS (o balanço não traz)."
        itens = [(str(x["ano"]), x["divida_liquida"], "" if x["alavancagem"] is None else _vezes(x["alavancagem"]) + " EBITDA")
                 for x in gd if x["divida_liquida"] is not None]
        graf = ('<div class="legenda-graf">Dívida líquida (R$) e múltiplo do EBITDA</div>'
                + g.colunas_serie(itens, {len(itens) - 1}, titulo="Dívida líquida por ano")) if itens else ""
        h += ['<div class="duas">', _secao("Capital de giro e dívida", "divida", tabela + f'<div class="nota">{obs}</div>'),
              _secao("Endividamento", "alerta", graf or _nd_nota("os contratos de empréstimo e saldos devedores.")),
              '</div>']
    else:
        h.append(_secao("Capital de giro e dívida", "divida", _nd_nota("os balanços dos últimos 3 anos.")))

    # mapa de riscos (8 verticais)
    vt = f["verticais"]
    tab_v = ('<table class="verticais compacta"><tr><th>Vertical</th><th class="n">Nota</th></tr>'
             + "".join(f"<tr><td>{escape(x['vertical'])}{' <small>(proposta)</small>' if x['pendente'] else ''}</td>"
                       f"<td class='n'><b>{ND if x['nota'] is None else str(x['nota']).replace('.0', '').replace('.', ',')}</b></td></tr>"
                       for x in vt) + '</table>')
    lt = f.get("leituras") or {}
    # com a leitura por vertical, os riscos do negócio já estão nela: a tabela fica só com as contingências em R$
    lista = [r for r in c["riscos"] if r.get("contingencia")] if lt else c["riscos"]
    riscos = "".join(f"<tr><td>{escape(r['descricao'])}</td><td>{escape(r['severidade'])}</td>"
                     f"<td>{escape(r['tratamento'])}</td></tr>" for r in lista)
    nota_score = (f'<div class="nota">Score de risco {v["risco"]["score"]:.0f}/100 (0 = menor risco), que define a '
                  'taxa de desconto. "Proposta" = nota ainda não confirmada pelo analista.</div>')
    radar = _secao("Risco por vertical", "alerta", g.radar_verticais([(x["vertical"], x["nota"]) for x in vt]))
    if lt:  # F5 escreveu a leitura de cada vertical: tabela larga com nota, leitura e tratamento
        fmt = lambda n: ND if n is None else str(n).replace(".0", "").replace(".", ",")  # noqa: E731
        linhas = "".join(
            f"<tr><td><b>{escape(x['vertical'])}</b>{' <small>(proposta)</small>' if x['pendente'] else ''}</td>"
            f"<td class='n'><b>{fmt(x['nota'])}</b></td><td>{escape((lt.get(x['vertical']) or {}).get('leitura') or ND)}</td>"
            f"<td>{escape((lt.get(x['vertical']) or {}).get('tratamento') or ND)}</td></tr>" for x in vt)
        h += ['<div class="bloco-junto"><div class="duas">', radar,
              _quadro("Mapa de riscos", "alerta", _p(t["leitura_riscos"]), "destaque"), '</div></div>',
              _secao("Leitura por vertical (5 = mais sólido)", "valor",
                     f'<table class="verticais-larga compacta"><tr><th>Vertical</th><th class="n">Nota</th>'
                     f'<th>Principal ponto</th><th>Tratamento</th></tr>{linhas}</table>' + nota_score)]
    else:
        h += ['<div class="bloco-junto">', _quadro("Mapa de riscos", "alerta", _p(t["leitura_riscos"]), "destaque"),
              '<div class="duas">', radar, _secao("Notas (5 = mais sólido)", "valor", tab_v + nota_score),
              '</div></div>']
    if lista:
        titulo = "Contingências e tratamento no preço" if lt else "Principais riscos e tratamento"
        h.append(_secao(titulo, "positivo", f'<table class="riscos"><tr><th>Risco</th><th>Peso</th>'
                        f'<th>Tratamento no valor</th></tr>{riscos}</table>'))
    h.append('</section>')
    return "".join(h)


def _pp(v: float) -> str:
    return f"{v * 100:.1f} p.p.".replace(".", ",", 1)


NOTA_MAX = 200  # 12/11/2026: notas de ativos, projeção e "do fluxo ao valor" em 1 linha (cabem na mesma página)


def _checa_nota(secao: str, nota: str) -> None:
    if len(nota) > NOTA_MAX:
        import sys
        print(f"aviso: nota de '{secao}' com {len(nota)} caracteres (máx. {NOTA_MAX}): pode empurrar a página",
              file=sys.stderr)


def _bloco_ativos(at: dict | None, piso_mercado: bool = False) -> str:
    """Ativo | Valor (venda a mercado de cada bem), decisão de 11/11/2026; o piso de liquidação só na nota.
    `piso_mercado` (12/11/2026, Emunah): o analista escolheu os ativos a mercado como piso da venda a mercado."""
    if not at:
        return _nd_nota("o balanço e a relação de bens (imóveis, veículos, máquinas, móveis).")
    # 12/11/2026 (usuário): sem as linhas de ativo sem dado (n/d) e nota de 1 linha — ativos, premissas, projeção e
    # "do fluxo ao valor" cabem na mesma página
    linhas = [r for r in at["linhas"] if r["valor"] is not None]
    corpo = "".join(f"<tr><td>{escape(r['nome'])}{' <small>(fora da venda)</small>' if r['fora'] else ''}</td>"
                    f"<td class='n'>{_mil(r['valor'])}</td></tr>" for r in linhas)
    corpo += f"<tr class='total'><td>= Total a mercado</td><td class='n'>{_mil(at['total'])}</td></tr>"
    nota = "R$ mil. Valor de venda a mercado de cada bem (sem laudo, o contábil)."
    if any(r["fora"] for r in linhas):
        nota += " Bens fora da venda não somam."
    if piso_mercado:
        nota += " Menos dívidas e obrigações, é o piso do valor (decisão do analista)."
    elif at.get("piso") is not None:
        nota += f" Numa liquidação ordenada, o patrimônio vale {g.brl_compacto(at['piso'])}: é o piso do valor."
    _checa_nota("Ativos da empresa", nota)
    return ('<table class="compacta ativos"><tr><th>Ativo</th><th class="n">Valor</th></tr>' + corpo + '</table>'
            f'<div class="nota">{escape(nota)}</div>')


def _bloco_parte_socios(c: dict) -> str | None:
    """Valuation independente (12/11/2026, Emunah): sem o capítulo 6, o capítulo 5 mostra quanto fica para os sócios
    em cada cenário — valor da empresa menos dívidas e obrigações. Sem comissão, IR nem forma de pagamento (não há venda)."""
    ida = _ida(c)
    cen = [ida[k] for k in ("forcada", "mercado", "maximo") if k in ida]
    if not cen:
        return None
    comp = lambda x, k: (x.get("divida_componentes") or {}).get(k) or 0.0  # noqa: E731
    traco = lambda v: "—" if abs(v) < 1 else _mil(-v)  # noqa: E731
    cred = [x.get("credito_vendedor") or 0.0 for x in cen]
    linhas = [("Valor da empresa", [_mil(x["bruto"]) for x in cen], "sub"),
              ("(−) Fornecedores (vencidos ou renegociados)", [traco(x.get("fornecedores_vencidos") or 0.0) for x in cen], ""),
              ("(−) Passivos bancários", [traco(comp(x, "bancarios")) for x in cen], ""),
              ("(−) Passivos tributários (parcelamentos)", [traco(comp(x, "tributarios")) for x in cen], ""),
              ("(−) Passivos trabalhistas (processos)", [traco(x.get("provaveis_trabalhistas") or 0.0) for x in cen], ""),
              ("(−) Rescisão dos funcionários (até a data-base)", [traco(x.get("rescisao") or 0.0) for x in cen], "")]
    if any(comp(x, "socios") - c >= 1 for x, c in zip(cen, cred)):
        linhas.append(("(−) Dívidas com sócios", [traco(comp(x, "socios") - c) for x, c in zip(cen, cred)], ""))
    if any(x["provaveis"] - (x.get("provaveis_trabalhistas") or 0.0) >= 1 for x in cen):
        linhas.append(("(−) Contingências prováveis (tributárias e cíveis)",
                       [traco(x["provaveis"] - (x.get("provaveis_trabalhistas") or 0.0)) for x in cen], ""))
    linhas.append(("= Parte dos sócios", [_mil(x['preco_cotas'] + c) for x, c in zip(cen, cred)], "sub"))
    ir = [x.get("ir_sem_comissao", x.get("ir")) or 0.0 for x in cen]
    linhas.append(("(−) IR sobre o ganho de capital" + ("" if cen[0].get("custo_informado") else "*"),
                   [traco(v) for v in ir], ""))
    linhas.append(("= Líquido para os sócios, após impostos",
                   [f"<b>{_mil(x['preco_cotas'] + c - v)}</b>" for x, c, v in zip(cen, cred, ir)], "total"))
    cab = "".join(f"<th class='n'>{escape(x['nome'])}</th>" for x in cen)
    corpo = "".join(f"<tr class='{cls}'><td>{escape(rot)}</td>" + "".join(f"<td class='n'>{v}</td>" for v in vals)
                    + "</tr>" for rot, vals, cls in linhas)
    nota = ("R$ mil. Valuation independente, sem decisão de venda: o que fica para os sócios é o valor da empresa menos "
            "as dívidas e as obrigações que a empresa carrega. Não há comissão nem forma de pagamento, que só existem "
            "numa venda.")
    nota += (" IR do sócio pessoa física sobre o ganho de capital, com alíquotas de 15% a 22,5%, calculado como se as cotas "
             "fossem vendidas por esse valor.")
    if not cen[0].get("custo_informado"):
        nota += (" *Custo de aquisição das cotas não informado: considerado zero, então o IR real tende a ser menor "
                 "(pedir a declaração de IR dos sócios).")
    rb = next((x.get("rescisao_base") for x in cen if x.get("rescisao")), None)
    if rb:
        nota += f" Rescisão: {rb}."
    return _secao("Quanto fica para os sócios", "pessoas",
                  f'<table class="compacta"><tr><th>R$ mil</th>{cab}</tr>{corpo}</table>'
                  f'<div class="nota">{escape(nota)}</div>')


def cap5_valuation(c: dict) -> str:
    t, v = c["textos"], c["valuation"]
    r = v["risco"]
    cen = {x["nome"]: x for x in v["cenarios"]}
    base = cen.get("base")
    div_liq = (v.get("divida_bruta") or 0) - (v.get("caixa") or 0)
    piso_merc = v.get("piso_usado") == "mercado" and v.get("patrimonio_mercado") is not None  # 12/11/2026 (Emunah)
    h = ['<section class="capitulo">', _cab(5, "Valuation", c)]

    # premissas
    perp = ("com perpetuidade" if v.get("perpetuidade")
            else "sem perpetuidade" + (f" (score {r['score']:.0f})" if r.get("score") is not None else ""))
    cards = [("relogio", "Taxa de desconto", pct(r["taxa_desconto"]) + " a.a.",
              f"Selic {pct(r['selic'], 2)} + prêmio de risco {_pp(r['premio_implicito'])}"),
             ("divida", "Caixa sustentável", g.brl_compacto(v["fluxo_base"]) + "/ano",
              (f"lucro do dono de {v['periodo_base']}" if v.get("periodo_base") and "," not in (v.get("fluxo_fonte") or "")
               else "média do lucro do dono" + (f" ({v['periodo_base']} e anterior)" if v.get("periodo_base") else ""))),
             ("ebitda", "Crescimento (base)", pct(base["crescimento"]) + " a.a." if base else ND,
              f"histórico de {pct(v['crescimento_historico'])} a.a." if v.get("crescimento_historico") is not None else ""),
             ("calendario", "Horizonte", f"{r['horizonte_anos']} anos", perp),
             ("faixa", "Dívida líquida", g.brl_compacto(div_liq), "dívida − caixa no último balanço")]
    if (cd := _card_divida(c, v)):
        cards[-1] = ("faixa",) + cd
    kpis = "".join(f'<div class="kpi"><div class="rot">{icone(ic, cor="#6B6B6B", tam=11)}{escape(rot)}</div>'
                   f'<div class="val pequeno">{escape(val)}</div><div class="obs">{escape(obs)}</div></div>'
                   for ic, rot, val, obs in cards)
    # ordem do capítulo (12/11/2026, usuário): ativos da empresa → premissas → projeção → do fluxo ao valor →
    # quanto sobra para o dono (os três cenários de ida a mercado) → faixas por método → quanto vira o investimento.
    # Sem "Cenários" (DCF por cenário), sem "Leitura do valuation" e sem capítulo 6.
    h.append(_secao("Ativos da empresa", "empresa", _bloco_ativos((c.get("financeiro") or {}).get("ativos"), piso_merc)))
    h.append(_secao("Premissas", "valor", f'<div class="kpis">{kpis}</div>'))

    # projeção de DRE e caixa (cenário base) + cenários
    sem_caixa = (v.get("fluxo_base") or 0) <= 0
    pj = (c.get("financeiro") or {}).get("projecao")
    nomes = {"conservador": "Venda forçada", "base": "Venda a mercado", "otimista": "Potencial máximo"}
    if sem_caixa and not pj:
        h.append(_secao("Projeção e cenários", "ebitda", '<div class="nota nd">A empresa não gera caixa '
                        'sustentável positivo: o fluxo descontado não sustenta valor, e o preço parte do patrimônio '
                        + ('(ativos a mercado menos dívidas).' if v.get('piso_usado') == 'mercado' else
                           '(liquidação ordenada dos ativos menos passivos; ver Ativos da empresa).') + '</div>'))
    elif pj:
        ncol = len(pj["colunas"])

        def cel(x, margem=False):
            if x is None:
                return "<td class='n'></td>"
            return f"<td class='n'>{_pct1(x) if margem else _mil(x)}</td>"

        corpo = "".join(f"<tr class='{cls}'><td>{escape(rot)}</td>" + "".join(cel(x, cls == "margem") for x in vals)
                        + "</tr>" for rot, vals, cls in pj["linhas"])
        corpo += ("<tr class='total'><td>= Caixa considerado no valuation</td>"
                  + "".join(cel(x) for x in pj["caixa"]) + "</tr>")
        corpo += ("<tr class='margem'><td>Fator de desconto</td>" + "".join(
            "<td class='n'></td>" if f is None else f"<td class='n'>{f:.3f}".replace(".", ",") + "</td>"
            for f in pj["fator"]) + "</tr>")
        corpo += "<tr class='sub'><td>Valor presente (VP)</td>" + "".join(cel(x) for x in pj["vp"]) + "</tr>"
        corpo += ("<tr class='total'><td>= Valor da empresa (soma dos VP)</td>" + "<td class='n'></td>" * (ncol - 1)
                  + f"<td class='n'>{_mil(pj['soma_vp'])}</td></tr>")
        tab_pj = ('<table class="dre compacta projecao"><tr><th>R$ mil</th>'
                  + "".join(f"<th class='n'>{escape(x)}</th>" for x in pj["colunas"]) + f"</tr>{corpo}</table>")
        # 12/11/2026 (usuário): nota de 1 linha, sem repetir as Premissas (taxa de desconto, crescimento, horizonte)
        rec = v.get("recuperacao_margem")
        if rec:
            mg = rec["margens"]
            nota_pj = (f"R$ mil. A margem do caixa do dono sai de {pct(mg['partida'])} e chega a {pct(mg['base'])} em "
                       f"{rec['anos']} anos (a de {rec['alvo']} foi {pct(mg['meta'])}), com corte de pessoal e despesas "
                       "administrativas.")
        else:
            nota_pj = "R$ mil. Margens constantes sobre o período-base."
            if pj["tem_acerto"]:
                nota_pj += " Caixa = média dos períodos analisados."
        if sem_caixa:
            nota_pj += " Caixa negativo: o valor vem dos ativos."
        _checa_nota("Projeção", nota_pj)
        h.append(_secao("Projeção da DRE e caixa", "ebitda",
                        tab_pj + f'<div class="nota">{escape(nota_pj)}</div>'))
    else:
        h.append(_secao("Projeção da DRE e caixa", "ebitda",
                        _nd_nota("a DRE econômica do período-base.")))
    off_fluxo, off_ativos = _offsets(c)
    merc = _ida(c).get("mercado")
    caixa_emp = v.get("caixa") or 0.0
    # 12/11/2026 (Emunah, usuário): os cenários mostram SÓ o fluxo de caixa — os ativos não entram aqui, só na ida a
    # mercado; sem as linhas "Valor pelo fluxo" e "Crescimento"
    linhas_cen = [("Valor da operação", lambda x: _mil(x["valor_empresa"]), ""),
                  ("(+) Caixa da empresa", lambda x: _mil(caixa_emp), ""),
                  ("= Valor da empresa", lambda x: f"<b>{_mil(x['valor_empresa'] + caixa_emp)}</b>", "total"),
                  ("Taxa de desconto", lambda x: pct(x["taxa"]), "margem"),
                  ("Múltiplo do caixa (operação)", lambda x: _vezes(x["multiplo_do_fluxo"]), "")]
    tab = ('<table class="compacta"><tr><th></th>' + "".join(f"<th class='n'>{nomes.get(x['nome'], x['nome'])}</th>"
                                                           for x in v["cenarios"]) + "</tr>"
           + "".join(f"<tr class='{cls}'><td>{rot}</td>" + "".join(f"<td class='n'>{fn(x)}</td>" for x in v["cenarios"])
                     + "</tr>" for rot, fn, cls in linhas_cen)
           + "</table>")
    if v.get("forcada_origem") == "ativos":  # 12/11/2026 (Emunah): forçada vem dos ativos, não de taxa implícita
        nota_cen = ("R$ mil. Só o fluxo de caixa, sem os ativos (eles entram como piso, na tabela acima). Valor da operação = caixa projetado "
                    "trazido a valor presente; somado ao caixa de hoje, dá o valor da empresa. Venda forçada: valor da "
                    "operação = 60% do da venda a mercado, e a taxa é a que leva o mesmo fluxo a esse valor (o retorno "
                    "de quem compra nesse preço). Potencial máximo: taxa menor, margem de volta ao melhor ano. Os três "
                    "são cenários possíveis, sem recomendação.")
    else:
        nota_cen = ("R$ mil. Valor da operação = caixa projetado trazido a valor presente; somado ao caixa que a empresa "
                    "tem hoje, dá o valor da empresa. Venda forçada: 60% da venda a mercado; a taxa é a que leva o mesmo "
                    "fluxo da venda a mercado a esse valor (o retorno de quem compra nesse preço). Potencial máximo: taxa "
                    "menor, crescimento histórico. Os três são cenários possíveis, sem recomendação.")
    bloco_cen = tab + f'<div class="nota">{escape(nota_cen)}</div>'

    # football field — tudo em valor de ida a mercado (10/11/2026): métodos do fluxo somam a dívida líquida e os
    # prováveis; os do patrimônio somam dívida bruta, fornecedores e prováveis (ativos a mercado, com o caixa)
    faixas = []
    if len(v["cenarios"]) >= 2 and not sem_caixa:
        vals = [x["valor_empresa"] + caixa_emp for x in v["cenarios"]]
        faixas.append(("Fluxo de caixa descontado", min(vals), max(vals), "venda forçada a potencial máximo"))
    rp = v.get("regua_payback") or {}
    if rp.get("forcada") and rp.get("maximo"):
        faixas.append(("Régua da casa", rp["forcada"]["valor_empresa"] + caixa_emp, rp["maximo"]["valor_empresa"] + caixa_emp,
                       f"{str(rp['forcada']['anos']).replace('.', ',')} a {str(rp['maximo']['anos']).replace('.', ',')} anos de caixa"))
    if v.get("piso_patrimonial") is not None:
        liq = v["piso_patrimonial"] + off_ativos
        faixas.append(("Liquidação dos ativos", liq, liq,
                       "venda rápida dos bens; não entra no valor" if piso_merc else "piso da venda a mercado")
                      + ((True,) if piso_merc else ()))
    if v.get("epv") is not None:
        faixas.append(("Lucro perpétuo (EPV)", v["epv"] + off_fluxo, v["epv"] + off_fluxo, "caixa atual sem crescimento"))
    me = v.get("multiplo_ebitda") or {}
    if me.get("min") is not None:
        faixas.append(("Múltiplo de EBITDA (ref.)", me["min"] + off_fluxo, me["max"] + off_fluxo,
                       "mercado; não entra no valor", True))
    if v.get("patrimonio_mercado") is not None:
        am = v["patrimonio_mercado"] + off_ativos
        if piso_merc:
            faixas.append(("Ativos a mercado", am, am, "piso da venda a mercado (decisão do analista)"))
        else:
            faixas.append(("Ativos a mercado (ref.)", am, am, "argumento de negociação; não entra no valor", True))
    # 11/11/2026: a linha da venda a mercado continua no gráfico, só sem o rótulo de "recomendada"
    marcadores = [("Venda a mercado", merc["bruto"] if merc else v["preco_recomendado"] + off_fluxo, True)]
    if c.get("pedido_vendedor"):
        marcadores.append(("Pedido do vendedor", c["pedido_vendedor"], False))
    nota_ff = ("Todos os métodos em valor de ida a mercado, com o caixa da empresa dentro. Os cenários vêm do fluxo "
               "de caixa (a venda forçada é 60% da venda a mercado); a liquidação dos ativos é o piso da venda a mercado. Tracejados, só referência: o múltiplo de "
               "EBITDA vale para empresas maiores, e os ativos a mercado só se realizam se a operação for encerrada.")
    if piso_merc:
        nota_ff = ("Todos os métodos em valor de ida a mercado, com o caixa da empresa dentro. Os cenários vêm do fluxo "
                   "de caixa (a venda forçada é 60% da venda a mercado); por decisão do analista, o piso da venda a "
                   "mercado são os ativos a mercado (bens avaliados por laudo, menos dívidas e obrigações). Tracejados, "
                   "só referência: a liquidação (venda rápida dos bens) e o múltiplo de EBITDA, que vale para empresas "
                   "maiores.")
    ff = _secao("Faixas de valor por método", "faixa", g.football_field(faixas, marcadores)
                + f'<div class="nota">{escape(nota_ff)}</div>')

    # do valor à ida a mercado (11/11/2026: sem a sensibilidade e sem valor recomendado — os três cenários com o
    # mesmo peso; a ND mostra os cenários possíveis e não recomenda valor de ida a mercado)
    ponte = []
    if base and not sem_caixa:
        ponte.append(("Valor presente da operação", _mil(base["valor_empresa"]), ""))
        ponte.append(("(+) Caixa da empresa", _mil(caixa_emp), ""))
        ponte.append(("= DCF", _mil(base["valor_empresa"] + caixa_emp), "sub"))
    if piso_merc:
        ponte.append(("Piso: ativos a mercado", _mil(v["patrimonio_mercado"] + off_ativos), ""))
    elif v.get("piso_patrimonial") is not None:
        ponte.append(("Piso: liquidação dos ativos", _mil(v["piso_patrimonial"] + off_ativos), ""))
    ida_c = _ida(c)
    if ida_c.get("mercado"):  # 11/11/2026: só a venda a mercado; os outros cenários estão em Cenários
        ponte.append(("= Ida a mercado", f"<b>{_mil(ida_c['mercado']['bruto'])}</b>", "total"))
    else:
        ponte.append(("Ida a mercado", _mil(v["preco_recomendado"] + off_fluxo), ""))
    pb = _payback_ida(c) if merc else v.get("payback_preco")
    if pb:
        ponte.append(("Payback", f'{pb:.2f}'.replace(".", ",") + "&nbsp;anos", ""))
    tab_preco = ('<table class="compacta">' + "".join(
        f"<tr class='{cls}'><td>{escape(rot)}</td><td class='n'>{val}</td></tr>" for rot, val, cls in ponte)
        + '</table><div class="nota">R$ mil. Vale o maior entre o valor pelo fluxo e o piso '
        + ('de ativos a mercado.' if piso_merc else 'de liquidação dos ativos.') + '</div>')
    h.append(_secao("Do valor à ida a mercado", "valor", tab_preco))
    h.append(_venda(_secao_sobra_dono(c)))
    h.append(ff)

    # quanto vira o investimento, ano a ano
    ev = _evolucao_inv(c)
    if ev:
        series = [("empresa", ev["empresa"], g.LARANJA), ("Selic", ev["selic"], g.TINTA),
                  ("IPCA+", ev["ipca_mais"], "#9A9A9A")]
        linhas_ev = "".join(
            f"<tr><td>{'Hoje' if i == 0 else ano}</td>" + "".join(
                f"<td class='n'>{_mil(serie[i])}"
                + (f" <small>({(serie[i] / serie[0] - 1) * 100:+.0f}%)</small>" if i else "") + "</td>"
                for serie in (ev["empresa"], ev["selic"], ev["ipca_mais"])) + "</tr>"
            for i, ano in enumerate(ev["anos"]))
        linhas_ev += ("<tr class='total'><td>Retorno a.a.</td>" + "".join(
            f"<td class='n'>{pct(x) if x is not None else ND}</td>" for x in (ev["tir"], ev["ret_selic"], ev["ret_ipca"]))
            + "</tr>")
        tab_ev = ('<table class="compacta"><tr><th>R$ mil</th><th class="n">Empresa</th><th class="n">Selic</th>'
                  f'<th class="n">IPCA+</th></tr>{linhas_ev}</table>')
        nota_ev = (f"Desembolso do comprador: {g.brl_compacto(ev['desembolso'])}, o valor de ida a mercado"
                   + (f"; o caixa de {g.brl_compacto(ev['caixa_empresa'])} que vem com a empresa é reinvestido na "
                      "Selic desde o primeiro dia" if ev.get("caixa_empresa") else "") + ". "
                   "Empresa = caixa gerado, reinvestido na Selic, + valor da empresa pelo DCF; o retorno é a TIR do "
                   f"negócio, e a diferença para a renda fixa é o prêmio pelo risco. IPCA+ com juro real de "
                   f"{pct(c.get('juro_real', 0.06))} a.a.; Selic e IPCA pela Focus/BCB.")
        h.append(_secao("Quanto vira o investimento", "retorno",
                        '<div class="duas"><div><div class="legenda-graf">Valor acumulado do mesmo desembolso (R$)</div>'
                        + g.linhas_evolucao(ev["anos"], series) + f'</div><div>{tab_ev}</div></div>'
                        + f'<div class="nota">{escape(nota_ev)}</div>'))
    h += [DISCLAIMER, '</section>']
    return "".join(h)


def _linha_tab(rot: str, vals: list[str], cls: str = "", destaque: int | None = None) -> str:
    return (f"<tr class='{cls}'><td>{rot}</td>"
            + "".join(f"<td class='n{' col' if i == destaque else ''}'>{x}</td>" for i, x in enumerate(vals)) + "</tr>")


def _venda(html: str) -> str:
    """Bloco com linguagem de venda (ida a mercado, comissão): o valuation independente não o reescreve."""
    return f"<!--venda-->{html}<!--/venda-->" if html else ""


def _secao_sobra_dono(c: dict) -> str:
    """Quanto sobra para o dono em cada cenário de ida a mercado (veio do antigo capítulo 6 em 12/11/2026)."""
    tr = (c.get("financeiro") or {}).get("transacao") or {}
    cen = tr.get("cenarios") or []
    if not cen:
        return ""
    # quanto sobra para o dono
    dm = None  # sem coluna destacada (11/11/2026): os três cenários com o mesmo peso
    cols = "".join(f"<th class='n'>{escape(x['nome'])}</th>" for x in cen)
    # descontos antes da parte do sócio (11/11/2026): comissão, fornecedores vencidos, bancários, tributários,
    # trabalhistas (processos de funcionários) e rescisão até a data da venda; sócios e outras prováveis se houver
    traco = lambda x: _mil(-x) if abs(x) >= 1 else "—"  # noqa: E731
    comp = lambda x, k: (x.get("divida_componentes") or {}).get(k, 0.0)  # noqa: E731
    cred = [x.get("credito_vendedor") or 0.0 for x in cen]
    linhas = [_linha_tab("Valor de ida a mercado (bruto)", [_mil(x["bruto"]) for x in cen], "sub", dm),
              _linha_tab("(−) Comissão ND", [_mil(-x["comissao"]) + f" <small>({x['comissao'] / x['bruto'] * 100:.0f}%)</small>"
                                            if x["bruto"] else "—" for x in cen], "", dm),
              _linha_tab("(−) Fornecedores (vencidos ou renegociados)",
                         [traco(x.get("fornecedores_vencidos") or 0.0) for x in cen], "", dm),
              _linha_tab("(−) Passivos bancários", [traco(comp(x, "bancarios")) for x in cen], "", dm),
              _linha_tab("(−) Passivos tributários (parcelamentos)", [traco(comp(x, "tributarios")) for x in cen], "", dm),
              _linha_tab("(−) Passivos trabalhistas (processos)",
                         [traco(x.get("provaveis_trabalhistas") or 0.0) for x in cen], "", dm),
              _linha_tab("(−) Rescisão dos funcionários (até a venda)",
                         [traco(x.get("rescisao") or 0.0) for x in cen], "", dm)]
    if any(comp(x, "socios") - c >= 1 for x, c in zip(cen, cred)):
        linhas.append(_linha_tab("(−) Dívidas com sócios", [traco(comp(x, "socios") - c) for x, c in zip(cen, cred)], "", dm))
    if any(x["passivos"] for x in cen):
        linhas.append(_linha_tab("(−) Fornecedores e obrigações", [_mil(-x["passivos"]) for x in cen], "", dm))
    if any(x["provaveis"] - (x.get("provaveis_trabalhistas") or 0.0) >= 1 for x in cen):
        linhas.append(_linha_tab("(−) Contingências prováveis (tributárias e cíveis)",
                                 [traco(x["provaveis"] - (x.get("provaveis_trabalhistas") or 0.0)) for x in cen],
                                 "", dm))
    linhas.append(_linha_tab("= Parte do sócio, já sem a comissão",
                             [_mil(x["preco_cotas"] - x["comissao"] + c) for x, c in zip(cen, cred)], "sub", dm))
    linhas.append(_linha_tab("(−) IR sobre o ganho de capital",
                             [_mil(-x["ir"]) for x in cen], "", dm))
    linhas.append(_linha_tab("= Sobra para o dono", [f"<b>{_mil(x['sobra'])}</b>" for x in cen], "total", dm))
    if any(x["retencao"] for x in cen):
        linhas.append(_linha_tab("(dos quais retidos em escrow)", [_mil(x["retencao"]) for x in cen], "margem", dm))
    pc = tr.get("parametros") or {}
    nota_s = (f"R$ mil. Comissão ND = maior entre {pc.get('comissao_percentual', 0.1):.0%} e "
              f"{g.brl_compacto(pc.get('comissao_minima', 150000))} do valor bruto de ida a mercado, paga na entrada. "
              "IR do sócio pessoa física sobre o ganho de capital, com alíquotas de 15% a 22,5%.")
    if any(cred):
        nota_s += (f" As dívidas da empresa com o próprio sócio ({g.brl_compacto(max(cred))}: dividendos a pagar e "
                   "haveres) não entram como desconto: a empresa as quita com ele na venda, sem IR de ganho de capital.")
    nota_s += (" Passivos trabalhistas: processos de funcionários julgados, em acordo ou com perda provável (os de "
               "perda possível vão para a retenção).")
    if cen[0].get("rescisao"):
        nota_s += (" Rescisão: o comprador só responde pelo tempo de casa a partir da compra, então a rescisão "
                   "acumulada até a venda (férias, 13º, multa do FGTS e aviso prévio) fica com o vendedor; já inclui "
                   "as férias, o 13º e os encargos provisionados no balanço"
                   + (f" ({cen[0]['rescisao_base']})" if cen[0].get("rescisao_base") else "") + ".")
    nota_s += " O valor bruto já inclui o caixa da empresa, que fica com o comprador."
    # 12/11/2026 (usuário): sem o aviso "avaliar com o sócio se a ida a mercado compensa"
    return (_secao("Quanto sobra para o dono", "divida",
                    f'<table class="compacta"><tr><th>R$ mil</th>{cols}</tr>{"".join(linhas)}</table>'
                    f'<div class="nota">{escape(nota_s)}</div>'))


DISCLAIMER = ('<div class="disclaimer">Relatório preparado pela Nova Direção com base em documentos e informações '
              'fornecidos pela empresa e por seus sócios, não auditados. Os valores são estimativas para orientar a '
              'negociação e não constituem garantia de preço. O IR do sócio é estimativa e deve ser confirmado com o '
              'contador. Documento confidencial.</div>')


CAPITULOS = {1: cap1_visao_geral, 2: cap2_empresa, 3: cap3_mercado, 4: cap4_financeiro, 5: cap5_valuation}


AVALIACAO = [("Valor de ida a mercado", "Valor da empresa"), ("valor de ida a mercado", "valor da empresa"),
             ("Ida a mercado recomendada", "Valor da empresa recomendado"),
             ("ida a mercado recomendada", "valor da empresa recomendado"),
             ("Do valor à ida a mercado", "Do fluxo ao valor da empresa"), ("Ida a mercado", "Valor da empresa"),
             ("ida a mercado", "valor da empresa"), ("Desembolso do comprador", "Valor investido"),
             (" Antes da comissão da ND.", ""), ("o total que o comprador paga pela empresa, somando o que vai ao sócio "
              "e as dívidas e obrigações da empresa que ele assume", "o valor das cotas somado às dívidas e obrigações "
              "da empresa (valor da firma)")]


def sem_linguagem_de_venda(html: str) -> str:
    """Valuation independente: o número é o valor da empresa, não um preço de ida a mercado com comissão."""
    partes = re.split(r"(<!--venda-->.*?<!--/venda-->)", html, flags=re.S)
    for i, p in enumerate(partes):
        if not p.startswith("<!--venda-->"):
            for velho, novo in AVALIACAO:
                p = p.replace(velho, novo)
            partes[i] = p
    return "".join(partes)


def montar_html(c: dict, capitulos: list[int] | None = None) -> str:
    """`c` é o contexto montado por tarantino.relatorio; `capitulos` permite gerar só alguns (prévia)."""
    caps = capitulos or sorted(CAPITULOS)
    # valuation independente: o relatório fala em "valor da empresa", menos os blocos de ida a mercado do capítulo 5
    # (quanto sobra para o dono, cenários de ida a mercado), marcados com _venda (12/11/2026)
    aval = c.get("tipo_finalidade") == "avaliacao"
    ajusta = (lambda html: sem_linguagem_de_venda(html)) if aval else (lambda html: html)  # noqa: E731
    corpo = ((ajusta(capa(c)) if capitulos is None else "")
             + "".join(ajusta(CAPITULOS[n](c)) for n in caps))
    css = CSS.replace("__LOGO__", _logo_cabecalho())
    return ("<!doctype html><html lang='pt-BR'><head><meta charset='utf-8'><title>Valuation — "
            f"{escape(c['empresa'])}</title><style>{css}</style></head><body>{corpo}</body></html>")


def navegador() -> str | None:
    for c in (r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
              r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
              r"C:\Program Files\Google\Chrome\Application\chrome.exe"):
        if Path(c).exists():
            return c
    return shutil.which("msedge") or shutil.which("chrome") or shutil.which("google-chrome")


def html_para_pdf(html: Path, pdf: Path, timeout: int = 120) -> None:
    exe = navegador()
    if not exe:
        raise RuntimeError("Edge/Chrome não encontrado: abra o relatorio.html e imprima como PDF.")
    with tempfile.TemporaryDirectory(prefix="tarantino_pdf_") as perfil:
        cmd = [exe, "--headless=new", "--disable-gpu", "--no-pdf-header-footer", f"--user-data-dir={perfil}",
               "--virtual-time-budget=4000", f"--print-to-pdf={pdf}", html.resolve().as_uri()]
        subprocess.run(cmd, capture_output=True, timeout=timeout)
    if not pdf.exists() or pdf.stat().st_size < 1000:
        raise RuntimeError("o navegador não gerou o PDF; abra o relatorio.html e imprima como PDF.")
