"""HTML do relatório (até ~10 páginas A4) e PDF pelo Edge/Chrome em modo headless (já instalados no Windows).

Capítulos (definidos pela ND em 07/11/2026): 1 Visão geral · 2 Sobre a empresa · 3 Análise de mercado e setor ·
4 Análise financeira e riscos do negócio · 5 Valuation · 6 Estrutura da transação.
Visual: o do relatório de investimento da ND (A4, branco, Helvetica), em versão reduzida e mais visual, sóbrio
(07/11/2026): preto e tons de cinza claro, blocos arredondados; laranja #FF9900 só nos destaques dos gráficos. Gráficos, ícones, tabelas e fluxogramas são desenhados pelo código (zero tokens); o redator
só escreve frases curtas. Cada capítulo é uma função própria, ajustada um a um com a ND.
"""

from __future__ import annotations

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
        @bottom-left { content: "NOVA DIREÇÃO  ·  Relatório de valuation  ·  confidencial"; font: 7pt Helvetica, Arial,
                       sans-serif; color: #8C8C8C; letter-spacing: .04em; }
        @bottom-right { content: "Pág. " counter(page); font: 7pt Helvetica, Arial, sans-serif; color: #8C8C8C; } }
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
td.base { background: var(--laranja-claro); font-weight: 700; outline: 1.5px solid var(--laranja); }
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


def _ul(itens: list[str], classe: str = "marcador") -> str:
    return f"<ul class='{classe}'>" + "".join(f"<li>{escape(i)}</li>" for i in itens) + "</ul>"


def _cab(n: int, titulo: str, c: dict) -> str:
    return (f'<div class="cab"><h2>{n:02d}. {escape(titulo)} | {escape(c["empresa_curto"])}</h2>'
            f'<div class="sub">Setor: {escape(c.get("setor") or "—")} | {escape(c["data"])} | '
            f'{escape(c["finalidade"])}</div></div>')


def _secao(titulo: str, ic: str, corpo: str) -> str:
    """Tópico sem moldura: só o título com ícone e o conteúdo (gráficos, colunas, tabelas)."""
    return f'<div class="secao"><h3>{icone(ic, cor="#1A1A1A")}{escape(titulo)}</h3>{corpo}</div>'


def _quadro(titulo: str, ic: str, corpo: str, classe: str = "") -> str:
    return f'<div class="quadro {classe}"><h3>{icone(ic, cor="#1A1A1A")}{escape(titulo)}</h3>{corpo}</div>'


def _evolucao_inv(c: dict) -> dict | None:
    """Quanto vira o investimento: mesmo desembolso (preço + dívida líquida + prováveis) na empresa, na Selic e no IPCA+."""
    v = c["valuation"]
    divida_liq = (v.get("divida_bruta") or 0) - (v.get("caixa") or 0)
    descontos = divida_liq + sum(x["valor_bruto"] for x in v.get("contingencias", []) if x["classificacao"] == "provavel")
    desembolso = v["preco_recomendado"] + descontos
    base_c = next((x for x in v["cenarios"] if x["nome"] == "base"), None)
    if not (base_c and base_c["fluxos"] and desembolso > 0 and v["fluxo_base"] > 0):
        return None
    terminal = base_c["valor_terminal"]
    if v.get("patrimonio_mercado") is not None:  # o comprador continua dono dos ativos: o fim nunca vale menos que eles
        terminal = max(terminal, v["patrimonio_mercado"] + descontos)
    ev = evolucao(desembolso, base_c["fluxos"], terminal, v["risco"]["taxa_desconto"], c["ano"],
                  c.get("focus_selic") or {}, c.get("focus_ipca") or {}, c.get("juro_real", 0.06))
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
    kpis = [("receita", f"Receita {v['periodo_base']}", g.brl_compacto(v["receita_base"]),
             f"crescimento {pct(v['crescimento_historico'])} a.a." if v.get("crescimento_historico") is not None else ""),
            ("ebitda", "EBITDA econômico", g.brl_compacto(v["ebitda_base"]), f"margem de {pct(margem)}"),
            ("faixa", "Faixa de valor", g.faixa_compacta(*faixa), "do conservador ao otimista"),
            ("relogio", "Payback do preço", f"{str(v['payback_preco']).replace('.', ',')} anos" if v.get("payback_preco")
             else "—", "régua da casa: até 3 anos"),
            ("divida", "Dívida líquida", g.brl_compacto(divida_liq),
             f"{divida_liq / v['ebitda_base']:.1f}× o EBITDA".replace(".", ",") if v["ebitda_base"] > 0 else "")]
    kpi_html = "".join(f'<div class="kpi"><div class="rot">{icone(ic, cor="#6B6B6B", tam=11)}{escape(rot)}</div>'
                       f'<div class="val">{escape(val)}</div><div class="obs">{escape(obs)}</div></div>'
                       for ic, rot, val, obs in kpis)
    fv = v.get("faixa_venda") or {"forcada": faixa[0], "mercado": v["preco_recomendado"], "maximo": faixa[1]}
    valores = [("Venda forçada", fv["forcada"], "cenário conservador · 0 a 6 meses", False),
               ("Venda a mercado", fv["mercado"], "preço recomendado · 6 a 18 meses", True),
               ("Potencial máximo", fv["maximo"], "cenário otimista · estratégico", False)]
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
                    + f'</table><div class="nota">Desembolso do comprador: {g.brl_compacto(ev["desembolso"])} (preço '
                    'recomendado + dívida assumida). A diferença para a renda fixa é o prêmio pelo risco. Ano a ano no '
                    'capítulo 5.</div>')
    else:
        bloco_ev = '<div class="nota">Sem caixa positivo projetado: comparação com a renda fixa não se aplica.</div>'
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
               + '<div class="legenda-graf">Risco por área (5 = mais sólido)</div>' + g.radar(notas_radar)),
        '</div><div class="duas">',
        _secao("Quanto vale", "valor", g.barras_valor(valores)
               + '<div class="nota">Valores para 100% das cotas, já descontadas dívidas e contingências prováveis.</div>'),
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
        mix = q.get("mix_receita") or []
        extra = ('<div class="legenda-graf">Participação na receita (declarada)</div>'
                 + g.barras_percentual([(x["item"], x["percentual"]) for x in mix])) if mix else ""
        h.append(_secao("Modelo de negócio", "receita", f'<div class="tres">{colunas}</div>{extra}'))
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
                                  (c["empresa_curto"], pos["preco"], pos["especializacao"]) if pos else None)
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
                        '<table><tr><th>Concorrente</th><th>Perfil</th><th>Como a empresa se compara</th></tr>'
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
    if not cl or not cl.get("ranking"):
        return _nd_nota("os 20 maiores clientes dos últimos 3 anos, com faturamento no ano e setor de atuação "
                        "(planilha da ND) ou a curva ABC das notas fiscais.")
    tem_setor = any(r.get("setor") for r in cl["ranking"])
    linhas = "".join(f"<tr><td>{i}</td><td>{escape(r['cliente'])}</td>"
                     + (f"<td>{escape(r.get('setor') or ND)}</td>" if tem_setor else "")
                     + f"<td class='n'>{_mil(r['valor'])}</td><td class='n'>{_pct_frac(r['participacao'])}</td></tr>"
                     for i, r in enumerate(cl["ranking"][:10], 1))
    ano = f" em {cl['ano']}" if cl.get("ano") else ""
    cards = [(cl.get("rotulo_qtd") or "Clientes", str(cl.get("clientes_pj") or ND), ano.strip() or "no período"),
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
        bloco_ano += ' Fonte: DRE contábil.</div>'
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
    h += ['<div class="duas">', _secao("Análise de receita", "receita", bloco_ano),
          _secao("Linhas de receita", "faixa", bloco_linhas), '</div>',
          _secao("Sazonalidade", "calendario", bloco_mes)]

    # custos
    cu, dre = f.get("custos"), f["dre"]
    if cu:
        idx = [dre["colunas"].index(a) for a in cu["anos"]]
        margens = [(nome, [vals[i] for i in idx]) for nome, vals in dre["margens"]]
        series = [(nome.replace('Margem ', '').capitalize().replace('Ebitda', 'EBITDA'), vals, cor)
                  for (nome, vals), cor in zip(margens, (g.CINZA, g.LARANJA, g.TINTA))
                  if all(x is not None for x in vals)]
        h += ['<div class="duas">',
              _secao("Análise de custos", "divida",
                     '<div class="legenda-graf">Para onde vai cada R$ 100 de receita bruta</div>'
                     + g.empilhadas_100(cu["anos"], cu["segmentos"])),
              _secao("Margens", "ebitda", '<div class="legenda-graf">Margens sobre a receita bruta (%)</div>'
                     + g.linhas_rentabilidade(cu["anos"], series)), '</div>']
    else:
        h.append(_secao("Análise de custos", "divida", _nd_nota("a DRE com custo das vendas e despesas abertas.")))

    # DRE simplificado
    if dre["colunas"]:
        cab = "".join(f"<th class='n'>{escape(p)}</th>" for p in dre["colunas"])
        corpo = "".join(f"<tr class='{cls}'><td>{escape(rot)}</td>" + "".join(f"<td class='n'>{_mil(x)}</td>" for x in vals)
                        + "</tr>" for rot, vals, cls in dre["linhas"])
        corpo += "".join(f"<tr class='margem'><td>{escape(rot)}</td>" + "".join(f"<td class='n'>{_pct1(x)}</td>" for x in vals)
                         + "</tr>" for rot, vals in dre["margens"])
        nota = ("Valores da DRE contábil, como reportados (R$ mil; negativos entre parênteses). "
                + ("" if dre["detalhada"] else "A empresa não abre custos e despesas: mostramos receita, lucro "
                   "operacional e lucro líquido. ") + "n/d = não disponível.")
        h.append(_secao("DRE simplificado", "valor", f'<table class="dre compacta"><tr><th>R$ mil</th>{cab}</tr>{corpo}</table>'
                        f'<div class="nota">{nota}</div>'))
    else:
        h.append(_secao("DRE simplificado", "valor", _nd_nota("as DREs anuais dos últimos 3 anos.")))

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


def cap5_valuation(c: dict) -> str:
    t, v = c["textos"], c["valuation"]
    r = v["risco"]
    cen = {x["nome"]: x for x in v["cenarios"]}
    base = cen.get("base")
    div_liq = (v.get("divida_bruta") or 0) - (v.get("caixa") or 0)
    h = ['<section class="capitulo">', _cab(5, "Valuation", c),
         _quadro("Leitura do valuation", "valor", _p(t["leitura_valuation"]), "destaque")]

    # premissas
    perp = ("com perpetuidade" if v.get("perpetuidade")
            else "sem perpetuidade" + (f" (score {r['score']:.0f})" if r.get("score") is not None else ""))
    cards = [("relogio", "Taxa de desconto", pct(r["taxa_desconto"]) + " a.a.",
              f"Selic {pct(r['selic'], 2)} + prêmio de risco {_pp(r['premio_implicito'])}"),
             ("divida", "Caixa sustentável", g.brl_compacto(v["fluxo_base"]) + "/ano",
              "média do lucro do dono" + (f" ({v['periodo_base']} e anterior)" if v.get("periodo_base") else "")),
             ("ebitda", "Crescimento (base)", pct(base["crescimento"]) + " a.a." if base else ND,
              f"histórico de {pct(v['crescimento_historico'])} a.a." if v.get("crescimento_historico") is not None else ""),
             ("calendario", "Horizonte", f"{r['horizonte_anos']} anos", perp),
             ("faixa", "Dívida líquida", g.brl_compacto(div_liq), "dívida − caixa no último balanço")]
    kpis = "".join(f'<div class="kpi"><div class="rot">{icone(ic, cor="#6B6B6B", tam=11)}{escape(rot)}</div>'
                   f'<div class="val pequeno">{escape(val)}</div><div class="obs">{escape(obs)}</div></div>'
                   for ic, rot, val, obs in cards)
    h.append(_secao("Premissas", "valor", f'<div class="kpis">{kpis}</div>'))

    # projeção de DRE e caixa (cenário base) + cenários
    sem_caixa = (v.get("fluxo_base") or 0) <= 0
    pj = (c.get("financeiro") or {}).get("projecao")
    nomes = {"conservador": "Conservador", "base": "Base", "otimista": "Otimista"}
    if sem_caixa:
        h.append(_secao("Projeção e cenários", "ebitda", '<div class="nota nd">A empresa não gera caixa '
                        'sustentável positivo: o fluxo descontado não sustenta valor, e o preço parte do patrimônio '
                        '(ativos a mercado menos dívidas).</div>'))
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
        nota_pj = (f"Cenário base: cada linha cresce {pct(pj['crescimento'])} a.a. sobre o período-base, com margens "
                   f"constantes; desconto a {pct(pj['taxa'])} a.a. ")
        if pj["tem_acerto"]:
            nota_pj += ("O caixa do valuation é a média dos períodos analisados (nunca acima do mais recente), "
                        "por isso o ajuste à média. ")
        if pj.get("multiplo_terminal"):
            nota_pj += (f"Valor ao fim = valor da empresa no último ano ({pj['multiplo_terminal']:.1f}× o caixa, "
                        "ou o valor dos ativos, o que for maior).").replace(".", ",", 1)
        h.append(_secao("Projeção da DRE e do caixa (cenário base)", "ebitda",
                        tab_pj + f'<div class="nota">{escape(nota_pj)}</div>'))
    else:
        h.append(_secao("Projeção da DRE e do caixa (cenário base)", "ebitda",
                        _nd_nota("a DRE econômica do período-base.")))
    barras = g.barras_valor([(nomes.get(x["nome"], x["nome"]), x["valor_patrimonio"],
                              f"taxa {pct(x['taxa'])} · cresc. {pct(x['crescimento'])}", x["nome"] == "base")
                             for x in v["cenarios"]])
    tab = ('<table class="compacta"><tr><th></th>' + "".join(f"<th class='n'>{nomes.get(x['nome'], x['nome'])}</th>"
                                                           for x in v["cenarios"]) + "</tr>"
           + "".join(f"<tr><td>{rot}</td>" + "".join(f"<td class='n'>{fn(x)}</td>" for x in v["cenarios"]) + "</tr>"
                     for rot, fn in (("Valor da empresa", lambda x: _mil(x["valor_empresa"])),
                                     ("(−) Dívida e contingências", lambda x: _mil(x["valor_patrimonio"] - x["valor_empresa"])),
                                     ("Valor para o sócio", lambda x: f"<b>{_mil(x['valor_patrimonio'])}</b>"),
                                     ("Múltiplo do caixa", lambda x: _vezes(x["multiplo_do_fluxo"]))))
           + "</table>")
    bloco_cen = ('<div class="legenda-graf">Valor para o sócio por cenário</div>' + barras + tab
                 + '<div class="nota">R$ mil. Valor para o sócio = valor da empresa − dívida líquida − '
                   'contingências prováveis.</div>')

    # football field
    faixas = []
    if v.get("piso_patrimonial") is not None and v.get("patrimonio_mercado") is not None:
        faixas.append(("Patrimônio", min(v["piso_patrimonial"], v["patrimonio_mercado"]),
                       max(v["piso_patrimonial"], v["patrimonio_mercado"]), "venda forçada a mercado"))
    rp = v.get("regua_payback") or {}
    if rp.get("forcada") and rp.get("maximo"):
        faixas.append(("Régua da casa", rp["forcada"]["valor_patrimonio"], rp["maximo"]["valor_patrimonio"],
                       f"{str(rp['forcada']['anos']).replace('.', ',')} a {str(rp['maximo']['anos']).replace('.', ',')} anos de caixa"))
    if len(v["cenarios"]) >= 2 and not sem_caixa:
        vals = [x["valor_patrimonio"] for x in v["cenarios"]]
        faixas.append(("Fluxo de caixa descontado", min(vals), max(vals), "conservador a otimista"))
    if v.get("epv") is not None:
        faixas.append(("Lucro perpétuo (EPV)", v["epv"], v["epv"], "caixa atual sem crescimento"))
    me = v.get("multiplo_ebitda") or {}
    if me.get("min") is not None:
        faixas.append(("Múltiplo de EBITDA (ref.)", me["min"], me["max"], "mercado; não entra no preço", True))
    marcadores = [("Preço recomendado", v["preco_recomendado"], True)]
    if c.get("pedido_vendedor"):
        marcadores.append(("Pedido do vendedor", c["pedido_vendedor"], False))
    nota_ff = ("Todos os métodos em valor para o sócio (já descontadas dívida líquida e contingências prováveis). "
               "O preço recomendado parte do fluxo descontado com margem de segurança e nunca fica abaixo do patrimônio. "
               "O múltiplo de EBITDA (tracejado) é só referência de mercado: vale para empresas maiores e com menos "
               "risco, e não entra no preço.")
    ff = _secao("Faixas de valor por método", "faixa", g.football_field(faixas, marcadores)
                + f'<div class="nota">{escape(nota_ff)}</div>')

    # sensibilidade + do valor ao preço
    sens = v.get("sensibilidade") or {}
    bloco_sens = ""
    if sens and not sem_caixa:
        taxas = list(sens)
        cres = list(next(iter(sens.values())))
        tb, cb = f"{base['taxa']:.0%}" if base else None, f"{base['crescimento']:.0%}" if base else None
        linhas = "".join(f"<tr><td><b>{escape(tx)}</b></td>" + "".join(
            f"<td class='n{' base' if tx == tb and g_ == cb else ''}'>{_mil(sens[tx][g_])}</td>" for g_ in cres)
            + "</tr>" for tx in taxas)
        bloco_sens = ('<table class="compacta sens"><tr><th>Taxa \\ cresc.</th>'
                      + "".join(f"<th class='n'>{escape(g_)}</th>" for g_ in cres) + f"</tr>{linhas}</table>"
                      '<div class="nota">Valor para o sócio (R$ mil). Em destaque, o cenário base.</div>')
    preco = v["preco_recomendado"]
    ponte = []
    if sem_caixa and v.get("piso_patrimonial") is not None:
        ponte.append(("Patrimônio (piso do preço)", _mil(max(v["piso_patrimonial"], v.get("patrimonio_mercado") or 0)
                                                         if v.get("piso_usado") == "mercado" else v["piso_patrimonial"]), ""))
    elif base:
        ponte.append(("Valor para o sócio (cenário base)", _mil(base["valor_patrimonio"]), ""))
        if base["valor_patrimonio"] > 0 and preco < base["valor_patrimonio"]:
            ponte.append(("(−) Margem de segurança", _mil(preco - base["valor_patrimonio"]),
                          f"{(1 - preco / base['valor_patrimonio']) * 100:.0f}%"))
    ponte.append(("= Preço recomendado", f"<b>{_mil(preco)}</b>", "total"))
    if v.get("payback_preco"):
        ponte.append(("Payback do preço", f'{v["payback_preco"]:.2f}'.replace(".", ",") + "&nbsp;anos",
                      f"régua da casa: até {str(rp['maximo']['anos']).replace('.', ',')} anos" if rp.get("maximo") else ""))
    tab_preco = ('<table class="compacta">' + "".join(
        f"<tr class='{'total' if obs == 'total' else ''}'><td>{escape(rot)}</td><td class='n'>{val}</td>"
        f"<td class='obs-cel'>{escape('' if obs == 'total' else obs)}</td></tr>" for rot, val, obs in ponte)
        + '</table><div class="nota">R$ mil. A margem de segurança protege o comprador contra o que os números '
          'ainda não comprovam.</div>')
    bloco_sens = bloco_sens or '<div class="nota nd">Não se aplica: sem caixa sustentável positivo.</div>'
    if sem_caixa:
        h += [ff, '<div class="duas">', _secao("Sensibilidade", "relogio", bloco_sens),
              _secao("Do valor ao preço", "valor", tab_preco), '</div>']
    else:
        h += ['<div class="duas">', _secao("Cenários", "faixa", bloco_cen),
              '<div>' + _secao("Do valor ao preço", "valor", tab_preco) + _secao("Sensibilidade", "relogio", bloco_sens)
              + '</div>', '</div>', ff]

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
        nota_ev = (f"Desembolso do comprador: {g.brl_compacto(ev['desembolso'])} (preço recomendado + dívida assumida). "
                   "Empresa = caixa gerado, reinvestido na Selic, + valor da empresa pelo nosso DCF (ou os ativos a mercado, se valerem mais); o retorno da "
                   "empresa é a TIR do negócio. A renda fixa é garantida, o caixa da empresa não: a diferença é o "
                   f"prêmio pelo risco. IPCA+ com juro real de {pct(c.get('juro_real', 0.06))} a.a.; Selic e IPCA "
                   "esperados pela Focus/BCB. Entre parênteses, o ganho acumulado.")
        h.append(_secao("Quanto vira o investimento", "retorno",
                        '<div class="duas"><div><div class="legenda-graf">Valor acumulado do mesmo desembolso (R$)</div>'
                        + g.linhas_evolucao(ev["anos"], series) + f'</div><div>{tab_ev}</div></div>'
                        + f'<div class="nota">{escape(nota_ev)}</div>'))
    h.append('</section>')
    return "".join(h)


def _linha_tab(rot: str, vals: list[str], cls: str = "", destaque: int | None = None) -> str:
    return (f"<tr class='{cls}'><td>{rot}</td>"
            + "".join(f"<td class='n{' col' if i == destaque else ''}'>{x}</td>" for i, x in enumerate(vals)) + "</tr>")


def cap6_transacao(c: dict) -> str:
    t, v = c["textos"], c["valuation"]
    tr = (c.get("financeiro") or {}).get("transacao") or {}
    h = ['<section class="capitulo">', _cab(6, "Ida a mercado", c)]
    leitura = _p(t["estrutura_transacao"])
    if c.get("leitura_finalidade"):
        leitura += _ul([x.replace("**", "") for x in c["leitura_finalidade"][1:]])
    h.append(_quadro("Leitura da transação", "valor", leitura, "destaque"))

    cen = tr.get("cenarios") or []
    merc = next((x for x in cen if x["chave"] == "mercado"), None)
    me = tr.get("metodos") or {}
    # valor de ida a mercado × métodos  |  cenários de ida a mercado
    if merc:
        itens = [("Ida a mercado", merc["bruto"], "cotas + dívidas assumidas", True)]
        if me.get("dcf") is not None:
            itens.append(("Fluxo de caixa (DCF)", me["dcf"], "base, sem margem" + (" · vale" if me["vale"] == "DCF" else ""), False))
        if me.get("patrimonio") is not None:
            itens.append(("Patrimônio", me["patrimonio"], "ativos a mercado" + (" · vale" if me["vale"] == "Patrimônio" else ""), False))
        if me.get("estoque"):
            itens.append(("Estoque" + ("*" if "DEFIS" in (me.get("estoque_fonte") or "") else ""), me["estoque"],
                          f"a {me['haircut_estoque']:.0%} do valor contábil", False))
        nota_m = ("Valores brutos, antes de dívida e comissão. Conta o maior entre o fluxo de caixa e o patrimônio, "
                  "nunca a soma: o caixa da empresa só existe porque o estoque e os ativos estão operando. "
                  "O valor de ida a mercado é o preço recomendado das cotas mais as dívidas que o comprador "
                  "assume.")
        if me.get("estoque") and "DEFIS" in (me.get("estoque_fonte") or ""):
            nota_m += f" *Estoque da {me['estoque_fonte']} (o balanço não traz)."
        bloco_m = g.barras_valor(itens) + f'<div class="nota">{escape(nota_m)}</div>'
        bloco_c = g.barras_valor([(x["nome"], x["bruto"], x["obs"].split(" · ")[0], x["chave"] == "mercado") for x in cen]) + (
            '<div class="nota">Valor bruto de ida a mercado em cada cenário. Mínimo = venda forçada em 0 a 6 meses (cenário '
            'conservador); a mercado = preço recomendado, em 6 a 18 meses; máximo = cenário otimista, para um '
            'comprador estratégico.</div>')
        h += ['<div class="duas">', _secao("Valor de ida a mercado × métodos", "faixa", bloco_m),
              _secao("Cenários de ida a mercado", "valor", bloco_c), '</div>']

        # quanto sobra para o dono
        dm = [i for i, x in enumerate(cen) if x["chave"] == "mercado"][0]
        cols = "".join(f"<th class='n'>{escape(x['nome'])}</th>" for x in cen)
        rot_div = ("(−) Dívida bancária" + ("¹" if any(not x["divida_bruta"] for x in cen) else "")
                   if any(x["divida_bruta"] for x in cen) else "(−) Dívida bancária, líquida do caixa")
        linhas = [_linha_tab("Valor de ida a mercado (bruto)", [_mil(x["bruto"]) for x in cen], "sub", dm),
                  _linha_tab("(−) Comissão ND", [_mil(-x["comissao"]) + f" <small>({x['comissao'] / x['bruto'] * 100:.0f}%)</small>"
                                                if x["bruto"] else "—" for x in cen], "", dm),
                  _linha_tab(rot_div, [_mil(-x["divida"]) for x in cen], "", dm)]
        if any(x["passivos"] for x in cen):
            linhas.append(_linha_tab("(−) Fornecedores e obrigações", [_mil(-x["passivos"]) for x in cen], "", dm))
        linhas.append(_linha_tab("(−) Contingências prováveis (jurídico)",
                                 [_mil(-x["provaveis"]) if x["provaveis"] else "—" for x in cen], "", dm))
        linhas.append(_linha_tab("= Recebe pelas cotas, já sem a comissão", [_mil(x["preco_cotas"] - x["comissao"]) for x in cen],
                                 "sub", dm))
        linhas.append(_linha_tab("(−) IR sobre o ganho de capital" + ("" if cen[0]["custo_informado"] else "*"),
                                 [_mil(-x["ir"]) for x in cen], "", dm))
        linhas.append(_linha_tab("= Sobra para o dono", [f"<b>{_mil(x['sobra'])}</b>" for x in cen], "total", dm))
        linhas.append(_linha_tab("Sobra sobre o valor bruto", [_pct1(x["sobra"] / x["bruto"] * 100) if x["bruto"] else ND
                                                               for x in cen], "margem", dm))
        if any(x["retencao"] for x in cen):
            linhas.append(_linha_tab("(dos quais retidos em escrow)", [_mil(x["retencao"]) for x in cen], "margem", dm))
        pc = tr.get("parametros") or {}
        nota_s = (f"R$ mil. Comissão ND = maior entre {pc.get('comissao_percentual', 0.1):.0%} e "
                  f"{g.brl_compacto(pc.get('comissao_minima', 150000))} do valor bruto de ida a mercado, paga na entrada. "
                  "IR do sócio pessoa física sobre o ganho de capital, com alíquotas de 15% a 22,5%.")
        if not cen[0]["custo_informado"]:
            nota_s += (" *Custo de aquisição das cotas não informado: considerado zero, então o IR real tende a "
                       "ser menor (pedir a declaração de IR do sócio).")
        if any(x["passivos"] for x in cen):
            nota_s += (" Quando o valor vem dos ativos, o bruto são os ativos a mercado (com o caixa) e saem fornecedores "
                       "e a dívida bruta; quando vem do fluxo, os fornecedores já estão na operação.")
        if any(x["divida_bruta"] for x in cen) and any(not x["divida_bruta"] for x in cen):
            nota_s += " ¹Líquida do caixa nos cenários que partem do fluxo."
        aviso = ""
        pesados = [x for x in cen if x["preco_cotas"] <= 0 or x["comissao"] / x["preco_cotas"] > 0.3]
        if pesados:
            x = pesados[-1]
            aviso = (f"No cenário {x['nome'].lower()}, a comissão de {g.brl_compacto(x['comissao'])} "
                     + ("é maior que o valor das cotas" if x["sobra"] < 0 or x["preco_cotas"] <= 0
                        else f"consome {x['comissao'] / x['preco_cotas']:.0%} do valor das cotas")
                     + ": avaliar com o sócio se a ida a mercado compensa, ou outra forma de remuneração da ND.")
            aviso = f'<div class="aviso">{escape(aviso)}</div>'
        h.append(_secao("Quanto sobra para o dono", "divida",
                        f'<table class="compacta"><tr><th>R$ mil</th>{cols}</tr>{"".join(linhas)}</table>'
                        f'<div class="nota">{escape(nota_s)}</div>' + aviso))

    # estrutura de pagamento
    pg = tr.get("pagamento")
    if pg:
        es = pg["estruturas"]
        sug = es[-1]
        cab = "".join(f"<th class='n'>{escape(x['nome'])}<br><small>{escape(x['rotulo'])}</small></th>" for x in es)
        cab = cab.replace("<th class='n'>Sugerida", "<th class='n col'>Sugerida")
        ds = len(es) - 1

        def parc(x):
            return f"{x['n']}× {_mil(x['parcela'])}" if x["n"] else "—"

        linhas = [
            _linha_tab("Entrada", [f"{_mil(x['entrada'])} <small>({x['entrada_pct']:.0%})</small>" for x in es], "", ds),
            _linha_tab("Parcelas mensais (corrigidas pelo CDI)", [parc(x) for x in es], "", ds),
            _linha_tab("Escrow (contingências possíveis)", [_mil(x["escrow"]) if x["escrow"] else "—" for x in es], "", ds),
            "<tr class='sub'><td colspan='4'>Sócio</td></tr>",
            _linha_tab("Na assinatura (entrada − comissão − escrow)", [_mil(x["no_fechamento"]) for x in es], "", ds),
            _linha_tab("+ Nas parcelas, em valor de hoje", [_mil(x["parcelas_hoje"]) if x["n"] else "—" for x in es], "", ds),
        ] + ([_linha_tab("+ Escrow, liberado depois", [_mil(x["escrow"]) for x in es], "", ds)] if any(x["escrow"] for x in es)
             else []) + [
            _linha_tab("= Total em valor de hoje (o mesmo nas três)", [f"<b>{_mil(x['liquido_hoje'])}</b>" for x in es], "sub", ds),
            _linha_tab("Total em reais no prazo (parcelas com CDI)", [_mil(x["liquido_nominal"]) for x in es], "margem", ds),
            _linha_tab("+ Earn-out, se o lucro se confirmar", [f"até {_mil(x['earnout'])}" if x["earnout"] else "—" for x in es],
                       "margem", ds),
            "<tr class='sub'><td colspan='4'>Investidor</td></tr>",
            _linha_tab("Desembolso no fechamento (entrada + dívida assumida)", [_mil(x["desembolso"]) for x in es], "", ds),
            _linha_tab("Parcela ÷ caixa mensal da empresa", [_pct1(x["parcela_caixa"] * 100) if x["parcela_caixa"] else "—"
                                                           for x in es], "", ds),
            _linha_tab("Retorno a.a. no cenário base (TIR)", [pct(x["tir"]) if x["tir"] is not None else ND for x in es],
                       "total", ds)]
        nota_p = (f"R$ mil. Premissa: {pg['origem']} ({pg['entrada_aceita']:.0%} de entrada e {pg['prazo']} parcelas). "
                  f"Sugerida = menor entrada, a partir da premissa, com parcela até {pg['limite']:.0%} do caixa mensal "
                  f"projetado ({g.brl_compacto(pg['caixa_mes'])}): a empresa paga a própria compra com folga. Parcelas "
                  "corrigidas pelo CDI: o sócio recebe menos na assinatura, mas o resto chega corrigido, e em valor de hoje o total é o "
                  "mesmo do preço à vista (a negociação não muda, muda só quando o dinheiro chega).")
        if sug["earnout"]:
            nota_p += (f" Earn-out até {g.brl_compacto(sug['earnout'])}: a diferença entre o valor sem margem de "
                       "segurança e o preço; o investidor só paga se o caixa vier acima do cenário base, e paga com esse "
                       "excedente (por isso a TIR não muda).")
        if es[1]["falta_na_entrada"]:
            nota_p += (f" Com {pg['entrada_aceita']:.0%} de entrada, a comissão e o escrow passam da entrada em "
                       f"{g.brl_compacto(es[1]['falta_na_entrada'])}: o restante sai das primeiras parcelas; a "
                       "sugerida já sobe a entrada para cobrir os dois.")
        if sug["parcela_caixa"] and pg["entrada_aceita"] < sug["entrada_pct"]:
            nota_p += (f" Com {pg['entrada_aceita']:.0%} de entrada a parcela tomaria "
                       f"{_pct1(es[1]['parcela_caixa'] * 100)} do caixa mensal: acima do limite.")
        sec_tabela = _secao("Comparação das formas de pagamento", "relogio",
                            f'<table class="compacta pagamento"><tr><th></th>{cab}</tr>{"".join(linhas)}</table>'
                            f'<div class="nota">{escape(nota_p)}</div>')
        # como a operação fecha, em linguagem simples (texto por código, com os números do case)
        em = c.get("empresa_curto") or "a empresa"
        div = (merc or {}).get("divida", 0.0) + (merc or {}).get("provaveis", 0.0)
        bc = g.brl_compacto
        passos = [f"<b>No dia da assinatura</b>, o comprador paga {bc(sug['entrada'])} "
                  f"({sug['entrada_pct']:.0%} do preço). Desse valor sai a comissão da Nova Direção "
                  f"({bc(sug['comissao'])})" + (f" e {bc(sug['escrow'])} vão para a reserva de riscos (passo 4)"
                                                if sug["escrow"] else "")
                  + f", e o sócio fica com {bc(sug['no_fechamento'])}."
                  + (f" O comprador também assume as dívidas da empresa ({bc(div)})." if div > 0 else "")]
        if sug["n"]:
            passos.append(
                f"<b>Nos {sug['n']} meses seguintes</b>, o comprador paga {sug['n']} parcelas de cerca de "
                f"{bc(sug['parcela'])}. Elas são corrigidas pelo CDI, o mesmo rendimento de uma aplicação de renda "
                "fixa: assim o sócio não perde dinheiro por receber depois."
                + (f" Cada parcela equivale a {sug['parcela_caixa']:.0%} do caixa que a própria empresa gera por mês "
                   f"({bc(pg['caixa_mes'])}): o comprador consegue pagar com o resultado do negócio."
                   if sug["parcela_caixa"] else ""))
            passos.append("<b>Até a última parcela</b>, as cotas ficam em garantia para o sócio: se o comprador "
                          "deixar de pagar, a empresa volta para ele.")
        if sug["escrow"]:
            passos.append(f"<b>Reserva de riscos (escrow):</b> {bc(sug['escrow'])} ficam numa conta bancária "
                          "vinculada, que nenhum dos dois pode movimentar sozinho. Se os riscos mapeados (dívidas "
                          "fiscais ou trabalhistas antigas) não aparecerem até prescrever, o dinheiro é liberado ao "
                          "sócio; se aparecerem, ele paga a conta.")
        if sug["earnout"]:
            meta = pg.get("earnout_meta")
            passos.append(
                f"<b>Bônus por resultado (earn-out), no mês 24:</b> o sócio pode receber até {bc(sug['earnout'])} a "
                "mais se o lucro se confirmar"
                + (f": o valor é proporcional ao caixa anual entre {bc(pg['earnout_base'])} (o que os documentos "
                   f"comprovam hoje) e {bc(meta)} (o que o sócio declara)." if meta else ".")
                + " Se o lucro não vier, o comprador não paga o bônus; se vier, ele paga com esse lucro extra.")
        resumo = (f"<b>Em resumo:</b> o sócio recebe {bc(sug['liquido_hoje'])} líquidos em valor de hoje (o mesmo que "
                  "receberia à vista)" + (f", mais até {bc(sug['earnout'])} se o lucro se confirmar" if sug["earnout"] else "")
                  + f". O comprador coloca {bc(sug['desembolso'])} no dia da assinatura (entrada + dívidas assumidas)"
                  + (f" e tem retorno estimado de {pct(sug['tir'])} ao ano no cenário base." if sug["tir"] is not None else "."))
        texto = (f'<p>Na estrutura sugerida, o comprador paga <b>{bc(v["preco_recomendado"])}</b> pelas cotas da '
                 f'{escape(em)}, em etapas:</p><ol class="passos">' + "".join(f"<li>{x}</li>" for x in passos)
                 + f"</ol><p>{resumo}</p>")
        etapas = [("Dia 1 · assinatura", bc(sug["entrada"]), f"o sócio fica com {bc(sug['no_fechamento'])}", True)]
        if sug["n"]:
            etapas.append((f"Meses 1 a {sug['n']}", f"{sug['n']} × {bc(sug['parcela'])}", "parcelas corrigidas pelo CDI",
                           False))
        if sug["escrow"]:
            etapas.append(("Reserva de riscos", bc(sug["escrow"]), "liberada ao sócio se os riscos não aparecerem", False))
        if sug["earnout"]:
            etapas.append(("Mês 24 · bônus", f"até {bc(sug['earnout'])}", "só se o lucro se confirmar", False))
        h.append(_secao("Como a operação fecha, passo a passo", "calendario", texto + g.fluxograma(etapas)))
        h.append(sec_tabela)
        crono = (g.cronograma_pagamento(sug["n"], sug["parcela"], pg["caixa_mes"], pg["limite"], sug["entrada"])
                 if sug["n"] else "")
        if crono:
            leitura_g = [f"Barra cinza: o caixa que a empresa gera por mês no cenário base ({bc(pg['caixa_mes'])}).",
                         f"Barra laranja: a parcela paga ao sócio ({bc(sug['parcela'])}).",
                         f"Linha tracejada: o limite da casa, {pg['limite']:.0%} do caixa. Abaixo dela, a empresa paga "
                         "a própria compra e ainda sobra dinheiro para o dia a dia."]
            h.append('<div class="duas"><div><div class="legenda-graf">A empresa consegue pagar as parcelas?</div>'
                     + crono + '</div><div>' + _secao("Como ler o gráfico", "positivo", _ul(leitura_g)) + '</div></div>')
    h += ['<div class="disclaimer">Relatório preparado pela Nova Direção com base em documentos e informações fornecidos '
          'pela empresa e por seus sócios, não auditados. Os valores são estimativas para orientar a negociação e não '
          'constituem garantia de preço. A estrutura de pagamento é uma simulação, não uma oferta; o IR do sócio é '
          'estimativa e deve ser confirmado com o contador. Documento confidencial.</div>', '</section>']
    return "".join(h)


CAPITULOS = {1: cap1_visao_geral, 2: cap2_empresa, 3: cap3_mercado, 4: cap4_financeiro, 5: cap5_valuation,
             6: cap6_transacao}


def montar_html(c: dict, capitulos: list[int] | None = None) -> str:
    """`c` é o contexto montado por tarantino.relatorio; `capitulos` permite gerar só alguns (prévia)."""
    corpo = "".join(CAPITULOS[n](c) for n in (capitulos or sorted(CAPITULOS)))
    return ("<!doctype html><html lang='pt-BR'><head><meta charset='utf-8'><title>Valuation — "
            f"{escape(c['empresa'])}</title><style>{CSS}</style></head><body>{corpo}</body></html>")


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
