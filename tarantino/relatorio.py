"""F8 no tarantino_agent: textos pelo redator (agente) + números e gráficos pelo código → relatorio.html / .pdf.

Trava (decisão de 07/11/2026): só gera com a revisão (F7) feita e sem alerta grave sem decisão.
    f8_entrada.md / f8_saida.json / f8_saida_bruta.txt   pacote e resposta do redator
    textos.json        textos validados (+ impressão digital do pacote e números citados não conferidos)
    relatorio.html / relatorio.pdf
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import date
from pathlib import Path

from engine.finalidade import ler_finalidade
from julgamento.esquemas import TextosRelatorio
from julgamento.executor import ErroJulgamento, executar_claude_code, extrair_json
from relatorio.render import html_para_pdf, montar_html
from tarantino.case import DadosCase, ler_estado
from tarantino.inventario import PASTA_SAIDA
from tarantino.revisao import pendentes_graves

RAIZ = Path(__file__).resolve().parents[1]
INSTRUCOES = RAIZ / "agents" / "f8_redator.md"
MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro",
         "novembro", "dezembro"]


class RelatorioBloqueado(RuntimeError):
    pass


SETORES = {"industria": "Indústria", "comercio": "Comércio", "servicos": "Serviços"}


def _juro_real() -> float:
    from market_data.bcb import carregar_parametros

    return carregar_parametros().get("ipca_mais", {}).get("juro_real", 0.06)


def nome_curto(razao: str) -> str:
    """'XY - INDUSTRIA E COMERCIO DE PLASTICOS LTDA' → 'XY'; 'POUSADA SOL NASCENTE EIRELI' → 'Pousada Sol Nascente'."""
    nome = razao.split(" - ")[0] if " - " in razao and len(razao.split(" - ")[0]) >= 2 else razao
    nome = re.sub(r"\b(LTDA|EIRELI|ME|EPP|S/?A|LIMITADA)\.?$", "", nome.strip(), flags=re.I).strip(" -.,")
    return nome if len(nome) <= 4 else nome.title()


def _ler(arq: Path, limite: int | None = None) -> str | None:
    if not arq.exists():
        return None
    t = arq.read_text(encoding="utf-8")
    return t[:limite] + "\n… (cortado)" if limite and len(t) > limite else t


def verificar_trava(saida: Path) -> None:
    if not (saida / "valuation.json").exists():
        raise RelatorioBloqueado("valuation não encontrado: rode 'avaliar'.")
    if not (saida / "revisao.json").exists():
        raise RelatorioBloqueado("revisão (F7) não feita: rode 'revisar' antes do relatório.")
    graves = pendentes_graves(saida)
    if graves:
        raise RelatorioBloqueado(f"{len(graves)} alerta(s) grave(s) da revisão sem decisão: {', '.join(graves)} — "
                                 f"decida em {PASTA_SAIDA}/revisao_decisoes.json.")


def _r(v: float | None) -> str:
    return "—" if v is None else (f"−R$ {abs(v):,.0f}" if v < 0 else f"R$ {v:,.0f}").replace(",", ".")


def fatos_compactos(pasta: Path) -> str:
    """Ficha enxuta para o redator (corte de tokens, 07/11/2026): fatos da F5, números-chave e alertas decididos —
    em vez dos resumos inteiros (normalização, valuation, revisão)."""
    saida = pasta / PASTA_SAIDA
    q = json.loads(_ler(saida / "qualitativo.json") or "{}")
    v = json.loads((saida / "valuation.json").read_text(encoding="utf-8"))
    fin = ler_finalidade(saida)
    linhas = ["## Números-chave (use exatamente estes)",
              f"- Preço recomendado (venda a mercado): {_r(v['preco_recomendado'])}"]
    fv = v.get("faixa_venda") or {}
    if fv:
        linhas.append(f"- Venda forçada {_r(fv.get('forcada'))} · potencial máximo {_r(fv.get('maximo'))}")
    linhas += [f"- Valor de referência (teto para ofertar na rede): {_r(v.get('valor_oferta'))} ({v.get('valor_oferta_origem')})",
               f"- Receita {v['periodo_base']}: {_r(v['receita_base'])} · EBITDA econômico {_r(v['ebitda_base'])} · "
               f"caixa sustentável {_r(v['fluxo_base'])}/ano",
               f"- Taxa de desconto {v['risco']['taxa_desconto'] * 100:.1f}% (Selic de referência "
               f"{v['risco']['selic'] * 100:.2f}% + prêmio) · horizonte {v['risco']['horizonte_anos']} anos",
               f"- Dívida bruta {_r(v.get('divida_bruta'))} · caixa {_r(v.get('caixa'))}"
               + (f" · payback do preço {v['payback_preco']} anos (régua da casa: até 3)" if v.get("payback_preco") else ""),
               f"- Finalidade: {fin.descricao}" + (f" · pedido do vendedor {_r(fin.pedido_vendedor)}" if fin.pedido_vendedor else "")]
    for c in v.get("contingencias", []):
        linhas.append(f"- Contingência {c['classificacao']}: {c['descricao']} ({_r(c['valor_bruto'])})")
    for nome, val in v.get("ponte_dono") or []:
        if nome.startswith("="):
            linhas.append(f"- Sobra para o dono no teto: {_r(val)}")
    linhas += ["", "## Fatos da análise qualitativa (F5)", f"- Resumo: {q.get('resumo', '—')}",
               f"- Modelo de negócio: {q.get('modelo_negocio', '—')}",
               f"- Fosso: {(q.get('fosso') or {}).get('forca', '—')} — {(q.get('fosso') or {}).get('justificativa', '')}",
               f"- Gestão: {(q.get('gestao') or {}).get('avaliacao', '—')}"]
    linhas += [f"- Ponto forte: {x}" for x in q.get("pontos_fortes", [])[:6]]
    linhas += [f"- Risco [{r['severidade']}]: {r['descricao']}" for r in q.get("riscos", [])[:6]]
    linhas += [f"- Função do dono sem substituto ({f['eixo']}): {f['descricao']}" for f in q.get("funcoes_do_dono", [])]
    perfil = q.get("perfil") or {}
    if any(perfil.values()):
        linhas.append("- Perfil: " + " · ".join(f"{k} {val}" for k, val in perfil.items() if val))
    rev = json.loads(_ler(saida / "revisao.json") or "{}").get("revisao") or {}
    dec = json.loads(_ler(saida / "revisao_decisoes.json") or "{}")
    if rev:
        linhas += ["", f"## Revisão (F7): parecer {rev.get('parecer')}"]
        for a in rev.get("alertas", []):
            st = (dec.get(a["id"]) or {}).get("status")
            if st == "descartado":
                continue
            linhas.append(f"- [{a['severidade']}] {a['achado'][:220]}" + (f" (analista: {st})" if st else ""))
    return "\n".join(linhas)


def montar_entrada(pasta: Path) -> str:
    saida = pasta / PASTA_SAIDA
    estado = ler_estado(pasta)
    esquema = json.dumps(TextosRelatorio.model_json_schema(), ensure_ascii=False, separators=(",", ":"))
    p = [INSTRUCOES.read_text(encoding="utf-8"), "", "---", "", f"# Case {estado.id} — {estado.empresa}", "",
         fatos_compactos(pasta), "", "---", "", "# Formato da resposta",
         "Responda **somente** com um objeto JSON válido (sem texto antes ou depois) conforme o esquema abaixo.",
         f'Use "case_id": "{estado.id}". No modo manual, grave o JSON em `{PASTA_SAIDA}/f8_saida.json`.', "",
         "```json", esquema, "```"]
    return "\n".join(p)


def numeros_nao_conferidos(textos: TextosRelatorio, pacote: str) -> list[str]:
    """Valores 'R$ 1.234.567' citados no texto que não aparecem (em dígitos) no material entregue ao redator."""
    digitos_pacote = set(re.findall(r"\d{4,}", re.sub(r"(?<=\d)[.\s](?=\d{3}\b)", "", pacote)))
    corpo = json.dumps(textos.model_dump(), ensure_ascii=False)
    fora = []
    for m in re.finditer(r"R\$\s?(\d{1,3}(?:\.\d{3})+|\d{4,})(?!,\d{2}\s?mi)", corpo):
        if m.group(1).replace(".", "") not in digitos_pacote:
            fora.append(m.group(0))
    return sorted(set(fora))


def _textos(pasta: Path, modo: str, modelo: str | None, executor, forcar: bool) -> tuple[TextosRelatorio | Path, list[str]]:
    saida = pasta / PASTA_SAIDA
    texto = montar_entrada(pasta)
    (saida / "f8_entrada.md").write_text(texto, encoding="utf-8")
    h = hashlib.sha256(texto.encode("utf-8")).hexdigest()
    anterior = json.loads(_ler(saida / "textos.json") or "{}")
    if not forcar and anterior.get("hash_entrada") == h and anterior.get("textos"):
        return TextosRelatorio.model_validate(anterior["textos"]), anterior.get("numeros_nao_conferidos", [])
    if modo == "manual" and not (saida / "f8_saida.json").exists():
        return saida / "f8_entrada.md", []
    if modo == "claude-code":
        resposta = executor(texto, modelo=modelo)
        (saida / "f8_saida_bruta.txt").write_text(resposta, encoding="utf-8")
        (saida / "f8_saida.json").write_text(json.dumps(extrair_json(resposta), indent=2, ensure_ascii=False),
                                             encoding="utf-8")
    elif modo == "api":
        raise ErroJulgamento("modo 'api' ainda não implementado — use claude-code ou manual.")
    estado = ler_estado(pasta)
    t = TextosRelatorio.model_validate({**json.loads((saida / "f8_saida.json").read_text(encoding="utf-8")),
                                        "case_id": estado.id})
    fora = numeros_nao_conferidos(t, texto)
    (saida / "textos.json").write_text(json.dumps({"hash_entrada": h, "numeros_nao_conferidos": fora,
                                                   "textos": t.model_dump()}, indent=2, ensure_ascii=False),
                                       encoding="utf-8")
    return t, fora


def _contexto(pasta: Path, textos: TextosRelatorio) -> dict:
    from tarantino.mercado import selic_por_horizonte

    saida = pasta / PASTA_SAIDA
    estado = ler_estado(pasta)
    v = json.loads((saida / "valuation.json").read_text(encoding="utf-8"))
    dres = json.loads((saida / "dre_economica.json").read_text(encoding="utf-8"))
    dados = DadosCase.model_validate_json((saida / "dados_brutos.json").read_text(encoding="utf-8"))
    qual = json.loads(_ler(saida / "qualitativo.json") or "{}")
    foto = json.loads(_ler(saida / "mercado.json") or "{}")
    fin = ler_finalidade(saida)
    hoje = date.today()

    def valor(d, conta):
        return sum(l["valor"] for l in d["linhas"] if l["conta"] == conta)

    ordenados = sorted(dres, key=lambda d: d["periodo"])[-3:]
    contas = ["Receita bruta", "Tributos sobre a receita", "Custo das vendas", "Despesas com pessoal",
              "Despesas administrativas e comerciais"]
    linhas = [(cta, [f"{valor(d, cta):,.0f}".replace(",", ".") for d in ordenados], False) for cta in contas]
    linhas.append(("Ajustes aprovados", [f"{sum(a['valor'] for a in d['ajustes'] if a['status'] in ('aplicado', 'aprovado')):,.0f}"
                                         .replace(",", ".") for d in ordenados], False))
    linhas.append(("EBITDA econômico", [f"{d['ebitda']:,.0f}".replace(",", ".") for d in ordenados], True))
    linhas.append(("Margem EBITDA", [f"{d['ebitda'] / valor(d, 'Receita bruta') * 100:.1f}%".replace(".", ",")
                                     if valor(d, "Receita bruta") else "—" for d in ordenados], False))

    rot = {"provavel": ("alta", "desconta do preço"), "possivel": ("média", "retenção no fechamento"),
           "remota": ("baixa", "não afeta o preço")}
    riscos = [{"descricao": c["descricao"], "severidade": rot[c["classificacao"]][0],
               "tratamento": f"{rot[c['classificacao']][1]} (R$ {c['valor_bruto']:,.0f})".replace(",", ".")}
              for c in v.get("contingencias", [])]
    riscos += [{"descricao": r["descricao"], "severidade": r["severidade"], "tratamento": "risco do negócio (na taxa)"}
               for r in (qual.get("riscos") or [])[:6]]

    nomes = {"confiabilidade_informacao": "Confiabilidade da informação", "dependencia_dono": "Dependência do dono",
             "concentracao_clientes": "Concentração de clientes", "recorrencia_receita": "Recorrência de receita",
             "historico_mercado": "Histórico e tempo de mercado", "estabilidade_resultados": "Estabilidade de resultados",
             "endividamento_liquidez": "Endividamento e liquidez", "contingencias": "Contingências",
             "setor_posicao_competitiva": "Setor e posição competitiva"}
    notas = [(nomes[k], n["nota"], n.get("pendente", False)) for k, n in v["notas"].items()]

    macro, selic_fonte = [], "informada"
    sgs, focus = foto.get("sgs", {}), foto.get("focus", {})
    if foto:
        try:
            _, fontes = selic_por_horizonte(foto)
            selic_fonte = fontes[v["risco"]["horizonte_anos"]]
        except Exception:  # noqa: BLE001 — fotografia incompleta: só a taxa informada
            pass
        if "selic_meta" in sgs:
            macro.append(("Selic meta", f"{sgs['selic_meta']['valor']:.2f}% a.a.".replace(".", ","), f"BCB, {sgs['selic_meta']['data']}"))
        macro.append(("Selic de referência (média esperada no horizonte)",
                      f"{v['risco']['selic'] * 100:.2f}% a.a.".replace(".", ","), "Focus/BCB"))
        if "ipca_12m" in sgs:
            macro.append(("IPCA em 12 meses", f"{sgs['ipca_12m']['valor']:.2f}%".replace(".", ","), f"BCB, {sgs['ipca_12m']['data']}"))
        prox = str(hoje.year + 1)
        for nome, rot_, suf in (("ipca", "IPCA esperado", "%"), ("pib", "PIB esperado", "%"), ("cambio", "Dólar esperado", "")):
            med = (focus.get(nome) or {}).get("medianas", {})
            if prox in med:
                txt = f"{med[prox]:.2f}{suf}".replace(".", ",") if suf else f"R$ {med[prox]:.2f}".replace(".", ",")
                macro.append((f"{rot_} {prox}", txt, f"Focus, {focus[nome]['data']}"))
        if "credito_pj_capital_giro" in sgs:
            macro.append(("Juros de capital de giro para empresas", f"{sgs['credito_pj_capital_giro']['valor']:.2f}% a.a."
                          .replace(".", ","), f"BCB, {sgs['credito_pj_capital_giro']['data']}"))

    base = next((d for d in dres if d["periodo"] == v["periodo_base"]), dres[0])
    ficha = [("Atividade", base.get("atividade", "—")), ("CNPJs no grupo", len(dados.empresa.cnpjs)),
             ("Período analisado", f"{estado.periodo_inicio} a {estado.periodo_fim}"),
             ("Receita no período base", f"R$ {valor(base, 'Receita bruta'):,.0f}".replace(",", ".")),
             ("Fonte da receita", base.get("receita_fonte", "—")), ("Regime do comprador", base.get("regime_comprador", "—"))]
    ipca = (sgs.get("ipca_12m") or {}).get("valor")
    focus_selic = (focus.get("selic") or {}).get("medianas") or {}
    focus_ipca = (focus.get("ipca") or {}).get("medianas") or {}
    return {"empresa": estado.empresa, "empresa_curto": nome_curto(estado.empresa),
            "setor": SETORES.get(base.get("atividade"), base.get("atividade")), "ipca_12m": ipca,
            "qual": qual, "ano": hoje.year, "focus_selic": focus_selic, "focus_ipca": focus_ipca,
            "juro_real": _juro_real(), "sgs": sgs, "focus": focus, "cnpjs": len(dados.empresa.cnpjs),
            "regime": base.get("regime_comprador", "").split(" (")[0],
            "case_id": estado.id, "data": f"{MESES[hoje.month - 1]} de {hoje.year}",
            "finalidade": fin.descricao, "pedido_vendedor": fin.pedido_vendedor, "textos": textos.model_dump(),
            "valuation": v, "ficha": ficha, "macro": macro, "selic_fonte": selic_fonte,
            "dre": {"periodos": [d["periodo"] for d in ordenados], "linhas": linhas},
            "grafico_dre": [(d["periodo"], valor(d, "Receita bruta"), d["ebitda"]) for d in ordenados],
            "riscos": riscos, "notas": notas, "leitura_finalidade": v.get("leitura_finalidade") or []}


def gerar_relatorio(pasta_empresa: str | Path, modo: str = "claude-code", modelo: str | None = None,
                    executor=executar_claude_code, forcar_textos: bool = False, pdf: bool = True) -> dict:
    """→ {"pdf"|"html"|"entrada": caminho, "numeros_nao_conferidos": [...]}. Levanta RelatorioBloqueado pela trava."""
    pasta = Path(pasta_empresa)
    saida = pasta / PASTA_SAIDA
    verificar_trava(saida)
    textos, fora = _textos(pasta, modo, modelo, executor, forcar_textos)
    if isinstance(textos, Path):
        return {"entrada": textos, "numeros_nao_conferidos": []}
    html = saida / "relatorio.html"
    html.write_text(montar_html(_contexto(pasta, textos)), encoding="utf-8")
    out = {"html": html, "numeros_nao_conferidos": fora}
    if pdf:
        destino = saida / "relatorio.pdf"
        html_para_pdf(html, destino)
        out["pdf"] = destino
    estado = ler_estado(pasta)
    estado.registrar("F8", "relatorio", f"relatório gerado ({'PDF' if pdf else 'HTML'})"
                     + (f"; {len(fora)} valor(es) citado(s) não conferido(s)" if fora else ""))
    (saida / "state.json").write_text(estado.model_dump_json(indent=2), encoding="utf-8")
    return out
