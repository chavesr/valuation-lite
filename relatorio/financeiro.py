"""Números do capítulo 4 (análise financeira): DRE contábil simplificada, composição de custos, receita anual e
mensal, ponte do EBITDA contábil ao econômico, capital de giro e dívida, e as 8 verticais de risco do relatório.

Só código, a partir do que o motor já leu (dados brutos, DRE econômica, valuation, F5). Valor que falta = None;
o render mostra "n/d" na célula ou troca o módulo inteiro por uma nota "Não informado".
"""

from __future__ import annotations

from engine.normalizacao import _dre_do_ano, _receita_declarada_mensal, _receita_gerencial_mensal

ND = None  # valor não disponível


def _f(x) -> float:
    return x or 0.0


# --------------------------------------------------------------------------- DRE contábil


def _parciais(dados) -> list:
    """DRE parcial mais recente (ano corrente), se for de um ano depois do último exercício completo."""
    completos = [d.exercicio for d in dados.dres if d.meses == 12]
    ult = max(completos, default=0)
    parc = [d for d in dados.dres if d.meses < 12 and d.exercicio > ult]
    if not parc:
        return []
    ano = max(d.exercicio for d in parc)
    cand = [d for d in parc if d.exercicio == ano]
    return [max(cand, key=lambda d: d.meses)] if len({d.cnpj for d in cand}) == 1 else []


def _abrir(d) -> dict:
    """Quebra uma DREAnual nas linhas do DRE simplificado. Despesas operacionais sem D&A e sem financeiras."""
    rb, ded = d.receita_bruta, d.deducoes
    rl = d.receita_liquida if d.receita_liquida is not None else (rb + _f(ded) if rb is not None else None)
    cmv = d.custo_vendas
    lb = rl + cmv if rl is not None and cmv is not None else None
    da = _f(d.depreciacao_amortizacao)
    fin_op = _f(d.financeiras_nas_operacionais)
    if d.despesas_operacionais_total is not None:
        desp_total = d.despesas_operacionais_total
    elif d.despesas_administrativas is not None or d.despesas_comerciais is not None:
        desp_total = _f(d.despesas_administrativas) + _f(d.despesas_comerciais) - fin_op
    else:
        desp_total = None
    desp = desp_total - da if desp_total is not None else None
    outras = _f(d.outras_receitas_despesas)
    ebitda = lb + desp + outras if lb is not None and desp is not None else None
    fin = (d.resultado_financeiro + fin_op) if d.resultado_financeiro is not None else (fin_op or None)
    ir = d.ir_csll
    ll = d.lucro_liquido
    calc = ebitda + da + _f(fin) + _f(ir) if ebitda is not None else None
    if ll is None:
        ll = calc
    ajuste = (ll - calc) if ll is not None and calc is not None and abs(ll - calc) >= 1000 else None
    ebit = ebitda + da if ebitda is not None else None
    if ebit is None and ll is not None:  # sem detalhe: lucro operacional = lucro líquido antes do financeiro e IR
        ebit = ll - _f(fin) - _f(ir)
    pessoal = _f(d.despesas_pessoal) + _f(d.pro_labore)
    outras_desp = (desp - pessoal) if desp is not None else None
    if outras_desp is not None and outras_desp > 0:  # pessoal lançado fora do grupo de despesas: não dá para abrir
        outras_desp, pessoal = desp, 0.0
    return {"rb": rb, "ded": ded, "rl": rl, "cmv": cmv, "lb": lb, "desp": desp, "outras": outras or None,
            "ebitda": ebitda, "da": da if da else (0.0 if ebitda is not None else None), "ebit": ebit, "fin": fin,
            "ir": ir, "ajuste": ajuste, "ll": ll, "pessoal": pessoal, "prolab": _f(d.pro_labore), "outras_desp": outras_desp,
            "detalhada": ebitda is not None}


def dre_contabil(dados, anos: int = 3) -> dict:
    """{"colunas": [rótulo], "abertas": [dict], "parcial": bool} — últimos `anos` exercícios completos + parcial."""
    completos = sorted({d.exercicio for d in dados.dres if d.meses == 12})[-anos:]
    cols, abertas = [], []
    for ano in completos:
        d = _dre_do_ano(dados, ano)
        if d is not None:
            cols.append(str(ano))
            abertas.append(_abrir(d) | {"ano": ano, "meses": 12})
    for d in _parciais(dados):
        cols.append(f"{d.exercicio} ({d.meses}m)")
        abertas.append(_abrir(d) | {"ano": d.exercicio, "meses": d.meses})
    return {"colunas": cols, "abertas": abertas}


LINHAS_DRE = [("Receita bruta", "rb", "total"), ("(−) Deduções e tributos", "ded", ""),
              ("Receita líquida", "rl", "sub"), ("(−) Custo das vendas", "cmv", ""), ("Lucro bruto", "lb", "sub"),
              ("(−) Despesas operacionais", "desp", ""), ("Outras receitas e despesas", "outras", ""),
              ("EBITDA contábil", "ebitda", "total"), ("(−) Depreciação e amortização", "da", ""),
              ("Resultado financeiro", "fin", ""), ("(−) IR/CSLL", "ir", ""),
              ("Outros (fechamento contábil)", "ajuste", ""), ("Lucro líquido", "ll", "total")]
LINHAS_DRE_RESUMIDA = [("Receita bruta", "rb", "total"), ("Lucro operacional", "ebit", "sub"),
                       ("Lucro líquido", "ll", "total")]


def tabela_dre(dre: dict) -> dict:
    """Linhas (rótulo, [valor|None], classe) + margens. Se nenhum ano abre até o EBITDA, usa a versão resumida."""
    ab = dre["abertas"]
    detalhada = any(a["detalhada"] for a in ab)
    modelo = LINHAS_DRE if detalhada else LINHAS_DRE_RESUMIDA
    linhas = []
    for rot, k, cls in modelo:
        vals = [a.get(k) for a in ab]
        if k in ("outras", "ajuste", "ir") and not any(v for v in vals):
            continue
        linhas.append((rot, vals, cls))
    def marg(k):
        return [a[k] / a["rb"] * 100 if a.get(k) is not None and a.get("rb") else None for a in ab]
    margens = ([("Margem bruta", marg("lb")), ("Margem EBITDA", marg("ebitda")), ("Margem líquida", marg("ll"))]
               if detalhada else [("Margem operacional", marg("ebit")), ("Margem líquida", marg("ll"))])
    return {"colunas": dre["colunas"], "linhas": linhas, "margens": margens, "detalhada": detalhada}


def composicao_custos(dre: dict) -> dict | None:
    """Cada exercício completo como 100% da receita bruta: tributos, custo, pessoal, outras despesas e EBITDA."""
    anos, seg = [], {k: [] for k in ("Tributos", "Custo das vendas", "Pessoal", "Outras despesas", "EBITDA")}
    for a in dre["abertas"]:
        if a["meses"] != 12 or not a["detalhada"] or not a.get("rb"):
            continue
        rb = a["rb"]
        anos.append(str(a["ano"]))
        seg["Tributos"].append(-_f(a["ded"]) / rb * 100)
        seg["Custo das vendas"].append(-_f(a["cmv"]) / rb * 100)
        seg["Pessoal"].append(-_f(a["pessoal"]) / rb * 100)
        seg["Outras despesas"].append(-(_f(a["outras_desp"]) + _f(a["outras"])) / rb * 100)
        seg["EBITDA"].append(a["ebitda"] / rb * 100)
    if not anos:
        return None
    valores = {k: [] for k in ("Custo das vendas", "Pessoal", "Outras despesas")}
    for a in dre["abertas"]:
        if a["meses"] == 12 and a["detalhada"] and a.get("rb"):
            valores["Custo das vendas"].append(-_f(a["cmv"]))
            valores["Pessoal"].append(-_f(a["pessoal"]))
            valores["Outras despesas"].append(-(_f(a["outras_desp"]) + _f(a["outras"])))
    return {"anos": anos, "segmentos": seg, "valores": valores}


# --------------------------------------------------------------------------- receita


def receita_anual(dre: dict) -> list[tuple[str, float, float | None]]:
    """[(ano, receita bruta, crescimento % sobre o ano anterior)] dos exercícios completos."""
    out, ant = [], None
    for a in dre["abertas"]:
        if a["meses"] == 12 and a.get("rb"):
            out.append((str(a["ano"]), a["rb"], (a["rb"] / ant - 1) * 100 if ant else None))
            ant = a["rb"]
    return out


def receita_mensal(dados, meses: int = 24) -> dict | None:
    """Faturamento mês a mês (PGDAS/EFD ou gerencial), últimos `meses`. None se não houver série."""
    serie, fonte = _receita_declarada_mensal(dados)
    if not serie:
        serie, fonte = _receita_gerencial_mensal(dados), "gerencial"
    serie = {k: v for k, v in serie.items() if v}
    if len(serie) < 6:
        return None
    chaves = sorted(serie)[-meses:]
    nomes = {"PGDAS-D": "declarações do Simples Nacional", "gerencial": FONTE_EMPRESA}
    return {"meses": chaves, "valores": [serie[k] for k in chaves], "fonte": nomes.get(fonte, "documentos fiscais")}


# --------------------------------------------------------------------------- ponte contábil → econômico


def ponte_economica(dre: dict, dres_econ: list[dict], periodo_base: str) -> dict | None:
    """Do EBITDA contábil do período base ao EBITDA econômico, item a item. None se faltar a DRE contábil do ano."""
    econ = next((d for d in dres_econ if d["periodo"] == periodo_base), None)
    cont = next((a for a in dre["abertas"] if str(a["ano"]) == periodo_base and a["meses"] == 12), None)
    if econ is None or cont is None or not cont["detalhada"]:
        return None
    val = lambda conta: sum(l["valor"] for l in econ["linhas"] if l["conta"] == conta)  # noqa: E731
    itens: list[tuple[str, float]] = [("EBITDA contábil", cont["ebitda"])]
    soma = cont["ebitda"]

    def add(rot, v):
        nonlocal soma
        if abs(v) >= 1000:
            itens.append((rot, v))
            soma += v

    add("Receita econômica (vs. contábil)", val("Receita bruta") - _f(cont["rb"]))
    add("Tributos no regime do comprador", val("Tributos sobre a receita") - _f(cont["ded"]))
    add("Custo das vendas na receita econômica", val("Custo das vendas") - _f(cont["cmv"]))
    desp_econ = val("Despesas com pessoal") + val("Despesas administrativas e comerciais")
    desp_cont = _f(cont["desp"]) + _f(cont["outras"])
    # o pró-labore atual sai da despesa contábil e volta como pró-labore de mercado (ajuste da metodologia)
    add("Pró-labore atual (sai da despesa)", -_f(cont["prolab"]))
    add("Despesas fora do recorrente", desp_econ - desp_cont + _f(cont["prolab"]))
    for a in econ["ajustes"]:
        if a["status"] in ("aplicado", "aprovado"):
            add(_rotulo_ajuste(a), a["valor"])
    residuo = econ["ebitda"] - soma
    add("Outros acertos", residuo)
    itens.append(("= EBITDA econômico", econ["ebitda"]))
    pendentes = [a for a in econ["ajustes"] if a["status"] == "proposto"]
    return {"periodo": periodo_base, "itens": itens, "pendentes": len(pendentes),
            "pendentes_valor": sum(a["valor"] for a in pendentes)}


def _rotulo_ajuste(a: dict) -> str:
    rot = {"pro_labore_mercado": "Pró-labore de mercado", "substituicao_financeiro": "Substituir o dono: financeiro",
           "substituicao_tecnico": "Substituir o dono: técnico", "substituicao_comercial": "Substituir o dono: comercial",
           "substituicao_gestao": "Substituir o dono: gestão"}
    return rot.get(a["id"]) or a["descricao"].split(":")[0].split("(")[0].strip()[:42]


# --------------------------------------------------------------------------- capital de giro e dívida


def giro_divida(dados, dre: dict, dres_econ: list[dict], v: dict) -> list[dict]:
    """Por balanço anual: prazos (dias), ciclo de caixa, dívida bruta, caixa e dívida líquida / EBITDA."""
    por_ano: dict[int, dict] = {}
    for b in dados.balancos:
        if b.data_base and (b.data_base.month, b.data_base.day) != (12, 31):
            continue
        x = por_ano.setdefault(b.exercicio, {})
        for k in ("caixa_aplicacoes", "contas_receber", "estoques", "fornecedores", "emprestimos_cp", "emprestimos_lp",
                  "parcelamentos_fiscais"):
            if getattr(b, k) is not None:
                x[k] = x.get(k, 0.0) + getattr(b, k)
    defis = {d.ano: d for d in getattr(dados, "defis", None) or []}
    abertas = {a["ano"]: a for a in dre["abertas"] if a["meses"] == 12}
    econ = {d["periodo"]: d for d in dres_econ}
    out = []
    for ano in sorted(por_ano)[-3:]:
        b, a = por_ano[ano], abertas.get(ano) or {}
        rb, cmv = a.get("rb"), -_f(a.get("cmv")) or None
        est, est_fonte = b.get("estoques"), "balanço"
        if est is None and ano in defis and getattr(defis[ano], "estoque_final", None) is not None:
            est, est_fonte = defis[ano].estoque_final, "DEFIS"
        pmr = b["contas_receber"] / rb * 360 if rb and "contas_receber" in b else None
        pme = est / cmv * 360 if cmv and est is not None else None
        pmp = b["fornecedores"] / cmv * 360 if cmv and "fornecedores" in b else None
        ciclo = pmr + _f(pme) - pmp if pmr is not None and pmp is not None else None
        tem_div = any(k in b for k in ("emprestimos_cp", "emprestimos_lp", "parcelamentos_fiscais"))
        bruta = sum(b.get(k, 0.0) for k in ("emprestimos_cp", "emprestimos_lp", "parcelamentos_fiscais")) if tem_div else None
        caixa = b.get("caixa_aplicacoes")
        liquida = bruta - _f(caixa) if bruta is not None else None
        eb = (econ.get(str(ano)) or {}).get("ebitda") or a.get("ebitda")
        out.append({"ano": ano, "pmr": pmr, "pme": pme, "pmp": pmp, "ciclo": ciclo, "estoque_fonte": est_fonte,
                    "divida_bruta": bruta, "caixa": caixa, "divida_liquida": liquida,
                    "alavancagem": liquida / eb if liquida is not None and eb and eb > 0 else None,
                    "ebitda_tipo": "econômico" if str(ano) in econ else "contábil"})
    return out


# --------------------------------------------------------------------------- 8 verticais de risco

VERTICAIS = [("Receita e clientes", ["concentracao_clientes", "recorrencia_receita"]),
             ("Mercado e concorrência", ["setor_posicao_competitiva", "historico_mercado"]),
             ("Diferencial e intangíveis", ["@fosso"]),
             ("Gestão e dependência do dono", ["dependencia_dono"]),
             ("Governança e informação", ["confiabilidade_informacao"]),
             ("Saúde financeira", ["endividamento_liquidez", "estabilidade_resultados"]),
             ("Operação e ativos físicos", ["@operacao"]),
             ("Contingências", ["contingencias"])]
NOTA_FOSSO = {"nenhum": 1, "estreito": 3, "amplo": 5}


def verticais_risco(v: dict, qual: dict) -> list[dict]:
    """[{vertical, nota (média 1–5, 1 casa) | None, origem, pendente}] — a taxa continua nas 9 dimensões do score."""
    out = []
    for nome, fontes in VERTICAIS:
        notas, pend, origem = [], False, []
        for f in fontes:
            if f == "@fosso":
                forca = (qual.get("fosso") or {}).get("forca")
                if forca in NOTA_FOSSO:
                    notas.append(NOTA_FOSSO[forca])
                    origem.append(f"fosso {forca}")
            elif f == "@operacao":
                n = (qual.get("operacao_ativos") or {}).get("nota")
                if n:
                    notas.append(n)
                    origem.append("F5")
            elif f in (v.get("notas") or {}):
                n = v["notas"][f]
                notas.append(n["nota"])
                pend = pend or bool(n.get("pendente"))
                origem.append("score")
        out.append({"vertical": nome, "nota": round(sum(notas) / len(notas), 1) if notas else None,
                    "origem": ", ".join(origem), "pendente": pend})
    return out


# --------------------------------------------------------------------------- planilha ND (abas 5, 10 e 11)
# Mesmo formato vale para o F5 (fase seguinte): o relatório não sabe de onde veio, só a "fonte" no rodapé.

VOLUME, PRECO = "Volume (quanto foi vendido)", "Preço médio / ticket"
# fontes no relatório: curtas, sem aba, arquivo ou minuto de gravação (o detalhe fica nos arquivos do case)
FONTE_EMPRESA = "informações enviadas pela empresa"


def _receita_do_ano(dre: dict, dados, ano: int) -> float | None:
    a = next((x for x in dre["abertas"] if x["ano"] == ano and x["meses"] == 12), None)
    if a and a.get("rb"):
        return a["rb"]
    p = getattr(dados, "planilha_nd", None)
    if p is not None:
        meses = {c: v for c, v in p.faturamento_mensal_total().items() if c.startswith(f"{ano}-")}
        if len(meses) == 12:
            return sum(meses.values())
    return None


def clientes_planilha(dados, dre: dict) -> dict | None:
    """Maiores clientes do último ano da aba 5_Clientes, com setor e participação na receita do ano."""
    p = getattr(dados, "planilha_nd", None)
    linhas = [l for l in (p.abas.get("5_Clientes", []) if p else [])
              if l.get("ano") and l.get("cliente") and l.get("faturamento_no_ano_r")]
    if not linhas:
        return None
    ano = int(max(l["ano"] for l in linhas))
    doano = sorted((l for l in linhas if int(l["ano"]) == ano), key=lambda l: -l["faturamento_no_ano_r"])
    receita = _receita_do_ano(dre, dados, ano)
    base = receita or sum(l["faturamento_no_ano_r"] for l in doano)
    part = [l["faturamento_no_ano_r"] / base for l in doano]
    setores: dict[str, float] = {}
    for l in doano:
        if l.get("setor_do_cliente"):
            setores[l["setor_do_cliente"]] = setores.get(l["setor_do_cliente"], 0.0) + l["faturamento_no_ano_r"]
    return {"ano": ano, "fonte": FONTE_EMPRESA, "base_receita": receita is not None,
            "clientes_pj": len(doano), "rotulo_qtd": "Clientes listados",
            "maior": part[0], "top5": sum(part[:5]), "top10": sum(part[:10]),
            "ranking": [{"cliente": l["cliente"], "valor": l["faturamento_no_ano_r"], "participacao": x,
                         "setor": l.get("setor_do_cliente")} for l, x in zip(doano[:10], part)],
            "por_setor": sorted(((s, v / base * 100) for s, v in setores.items()), key=lambda x: -x[1])}


def linhas_receita_planilha(dados) -> dict | None:
    """{"anos": [..], "linhas": [(nome, [valor|None por ano])]} da aba 10_Linhas_Receita (últimos 3 anos)."""
    p = getattr(dados, "planilha_nd", None)
    regs = [l for l in (p.abas.get("10_Linhas_Receita", []) if p else [])
            if l.get("ano") and l.get("linha_de_receita") and l.get("receita_no_ano_r") is not None]
    if not regs:
        return None
    anos = sorted({int(l["ano"]) for l in regs})[-3:]
    tab: dict[str, dict[int, float]] = {}
    for l in regs:
        if int(l["ano"]) in anos:
            d = tab.setdefault(l["linha_de_receita"].strip(), {})
            d[int(l["ano"])] = d.get(int(l["ano"]), 0.0) + l["receita_no_ano_r"]
    ordem = sorted(tab, key=lambda n: -tab[n].get(anos[-1], 0.0))
    return {"anos": [str(a) for a in anos], "linhas": [(n, [tab[n].get(a) for a in anos]) for n in ordem],
            "fonte": FONTE_EMPRESA}


def operacional_planilha(dados) -> dict | None:
    """Volume e preço médio por ano (aba 11_Indicadores); só anos com um volume e um preço."""
    p = getattr(dados, "planilha_nd", None)
    regs = [l for l in (p.abas.get("11_Indicadores", []) if p else [])
            if l.get("ano") and l.get("tipo") in (VOLUME, PRECO) and l.get("valor_no_ano") is not None]
    por_ano: dict[int, dict[str, list[dict]]] = {}
    for l in regs:
        por_ano.setdefault(int(l["ano"]), {}).setdefault(l["tipo"], []).append(l)
    anos = sorted(a for a, t in por_ano.items() if len(t.get(VOLUME, [])) == 1 and len(t.get(PRECO, [])) == 1)[-3:]
    if not anos:
        return None
    ult = por_ano[anos[-1]]

    def serie(tipo):
        ref = ult[tipo][0]
        return {"nome": ref.get("indicador") or tipo, "unidade": ref.get("unidade") or "",
                "valores": [por_ano[a][tipo][0]["valor_no_ano"] for a in anos]}

    vol, pre = serie(VOLUME), serie(PRECO)
    return {"anos": [str(a) for a in anos], "volume": vol, "preco": pre,
            "receita": [v * x for v, x in zip(vol["valores"], pre["valores"])],
            "fonte": FONTE_EMPRESA}


# --------------------------------------------------------------------------- F5 (declarado), quando a planilha não traz
FONTE_F5 = "declaração dos sócios"


def clientes_f5(qual: dict, dre: dict, dados) -> dict | None:
    regs = qual.get("clientes_principais") or []
    if not regs:
        return None
    completos = [a["ano"] for a in dre["abertas"] if a["meses"] == 12 and a.get("rb")]
    ano = max(completos, default=None)
    receita = _receita_do_ano(dre, dados, ano) if ano else None
    linhas = []
    for c in regs:
        part = (c["percentual"] / 100 if c.get("percentual") is not None
                else (c["receita_anual"] / receita if receita and c.get("receita_anual") is not None else None))
        valor = c.get("receita_anual") if c.get("receita_anual") is not None else (part * receita if receita and part is not None else None)
        linhas.append({"cliente": c["cliente"], "setor": c.get("setor") or None, "valor": valor, "participacao": part})
    com_valor = sorted((r for r in linhas if r["participacao"] is not None), key=lambda r: -r["participacao"])
    linhas = com_valor + [r for r in linhas if r["participacao"] is None]  # citados sem valor vão no fim, com n/d
    soma = lambda n: sum(r["participacao"] for r in com_valor[:n]) if len(com_valor) >= n else None  # noqa: E731
    setores: dict[str, float] = {}
    for r in com_valor:
        if r["setor"]:
            setores[r["setor"]] = setores.get(r["setor"], 0.0) + r["participacao"] * 100
    return {"ano": ano, "fonte": FONTE_F5 + (f"; participação sobre a receita de {ano}" if ano else ""),
            "base_receita": True, "clientes_pj": qual.get("clientes_total") or len(linhas),
            "rotulo_qtd": "Clientes ativos" if qual.get("clientes_total") else "Clientes citados",
            "obs_qtd": "declarado pelos sócios" if qual.get("clientes_total") else None,
            "maior": com_valor[0]["participacao"] if com_valor else None, "top5": soma(5), "top10": soma(10),
            "ranking": linhas[:10],
            "por_setor": sorted(setores.items(), key=lambda x: -x[1])}


ATIVOS = (("imoveis", "Imóveis"), ("veiculos", "Veículos"), ("maquinas_equipamentos", "Máquinas e equipamentos"),
          ("moveis_informatica", "Móveis e informática"), ("estoques", "Estoque"), ("contas_receber", "Contas a receber"))


def ativos_empresa(dados, ativos: dict | None, p: dict) -> dict:
    """Aba 'Ativos da empresa': só Ativo | Valor, o valor de venda a mercado de cada bem (decisão de 11/11/2026).
    Valor = `valor_mercado` do _valuation/ativos.json (relação de bens, preenchida pelo analista); sem ele, o valor
    contábil × o percentual de patrimonio_mercado (imobilizado 100%, estoque 90%, receber 95%); sem nenhum, n/d.
    Estoque e contas a receber vêm do último balanço quando o analista não preenche. `fora_da_venda: true` marca o
    bem que não vai com a empresa (ex.: imóvel dos sócios), fora do total. O piso de liquidação (venda forçada)
    continua no cálculo e só aparece na nota."""
    bp = max((b for b in dados.balancos if b.data_base), key=lambda b: b.data_base, default=None)
    hm = p.get("patrimonio_mercado") or {}
    itens = (ativos or {}).get("itens") or {}
    linhas = []
    for chave, nome in ATIVOS:
        it = itens.get(chave) or {}
        contabil, valor = it.get("valor_contabil"), it.get("valor_mercado")
        if chave in ("estoques", "contas_receber") and bp is not None and contabil is None:
            contabil = getattr(bp, chave)
        if valor is None and contabil is not None:
            valor = contabil * hm.get(chave if chave in ("estoques", "contas_receber") else "imobilizado", 1.0)
        linhas.append({"nome": nome, "valor": valor, "fora": bool(it.get("fora_da_venda"))})
    pt = ponte_liquidacao(bp, p.get("piso_patrimonial") or {})
    return {"linhas": linhas, "total": sum(x["valor"] for x in linhas if x["valor"] is not None and not x["fora"]),
            "fonte": (ativos or {}).get("fonte"), "piso": pt["piso"] if pt else None,
            "data_base": pt["data_base"] if pt else None}


def ponte_liquidacao(bp, h: dict) -> dict | None:
    """Do balanço ao piso de liquidação (11/11/2026, IBRATE): mesma conta de engine.valuation.liquidacao, linha a
    linha, para a seção 'Ativos da empresa' fechar com o piso usado no preço. Outros ativos do balanço (adiantamentos,
    tributos a recuperar etc., implícitos em PL + passivos − ativos listados) aparecem, mas não entram na liquidação."""
    if bp is None:
        return None
    v = lambda x: x or 0.0  # noqa: E731
    ativos = [("Caixa e aplicações", v(bp.caixa_aplicacoes), h.get("caixa", 1.0)),
              ("Contas a receber", v(bp.contas_receber), h.get("contas_receber", 1.0)),
              ("Estoque", v(bp.estoques), h.get("estoques", 1.0)),
              ("Imobilizado líquido", v(bp.imobilizado_liquido), h.get("imobilizado", 1.0))]
    passivos = [("Fornecedores e adiantamentos", v(bp.fornecedores)),
                ("Obrigações trabalhistas", v(bp.obrigacoes_trabalhistas)),
                ("Obrigações fiscais", v(bp.obrigacoes_fiscais)),
                ("Parcelamentos fiscais", v(bp.parcelamentos_fiscais)),
                ("Empréstimos", v(bp.emprestimos_cp) + v(bp.emprestimos_lp)),
                ("Mútuos com sócios", v(bp.mutuos_socios))]
    linhas = [{"nome": n, "contabil": c, "realizacao": round(c * f, 2), "obs": f"{f:.0%} do contábil"}
              for n, c, f in ativos if c]
    outros = None
    if bp.patrimonio_liquido is not None:
        outros = round(bp.patrimonio_liquido + sum(x for _, x in passivos) - sum(c for _, c, _ in ativos), 2)
        if abs(outros) >= 1:
            linhas.append({"nome": "Outros ativos do balanço", "contabil": outros, "realizacao": 0.0,
                           "obs": "adiantamentos, tributos a recuperar etc.: não entram"})
    total_ativos = round(sum(l["realizacao"] for l in linhas), 2)
    pas = [{"nome": n, "valor": -x} for n, x in passivos if x]
    piso = round(total_ativos + sum(p["valor"] for p in pas), 2)
    return {"data_base": f"{bp.data_base:%d/%m/%Y}" if bp.data_base else None, "ativos": linhas,
            "total_ativos": total_ativos, "passivos": pas, "piso": piso}


def linhas_receita_f5(qual: dict) -> dict | None:
    regs = qual.get("linhas_receita") or []
    anos = sorted({v["ano"] for l in regs for v in l["valores"]})[-3:]
    if not anos:
        return None
    linhas = [(l["nome"], [next((v["valor"] for v in l["valores"] if v["ano"] == a), None) for a in anos]) for l in regs]
    linhas.sort(key=lambda x: -(x[1][-1] or 0))
    return {"anos": [str(a) for a in anos], "linhas": linhas, "fonte": FONTE_F5}


def operacional_f5(qual: dict) -> dict | None:
    op = qual.get("operacional")
    if not op:
        return None
    vol = {v["ano"]: v["valor"] for v in op["volume"]["valores"]}
    pre = {v["ano"]: v["valor"] for v in op["preco"]["valores"]}
    anos = sorted(set(vol) & set(pre))[-3:]
    if not anos:
        return None
    serie = lambda ind, d: {"nome": ind["nome"], "unidade": ind.get("unidade") or "", "valores": [d[a] for a in anos]}  # noqa: E731
    return {"anos": [str(a) for a in anos], "volume": serie(op["volume"], vol), "preco": serie(op["preco"], pre),
            "receita": [vol[a] * pre[a] * (12 if op.get("preco_mensal") else 1) for a in anos],
            "mensal": bool(op.get("preco_mensal")), "fonte": FONTE_F5}


def leituras_verticais(qual: dict) -> dict[str, dict]:
    return {x["vertical"]: x for x in qual.get("leitura_verticais") or []}


# --------------------------------------------------------------------------- capítulo 5: projeção ano a ano


def projecao_dre(dres: list[dict], v: dict, ano0: int) -> dict | None:
    """DRE econômica do período-base projetada no cenário base, até o caixa e o valor presente de cada ano.

    Cada linha cresce à taxa do cenário base (margens constantes). O caixa usado no valuation é a média dos
    períodos (nunca acima do mais recente), não o ano-base puro: a diferença vira a linha "ajuste à média", e o
    caixa considerado fecha com os fluxos do motor. A soma dos VP (com o valor ao fim) = valor da empresa."""
    base_c = next((x for x in v.get("cenarios", []) if x["nome"] == "base"), None)
    fluxo = v.get("fluxo_base") or 0
    d = next((x for x in dres if x["periodo"] == v.get("periodo_base")), None)
    # 11/11/2026: projeção sempre, mesmo com caixa negativo (o preço então vem do piso, mas o leitor vê o porquê)
    if not base_c or not base_c.get("fluxos") or not fluxo or not d:
        return None

    def conta(nome):
        return sum(l["valor"] for l in d["linhas"] if l["conta"] == nome)

    rb, trib, cmv = conta("Receita bruta"), conta("Tributos sobre a receita"), conta("Custo das vendas")
    pes, adm = conta("Despesas com pessoal"), conta("Despesas administrativas e comerciais")
    aj = sum(a["valor"] for a in d.get("ajustes", []) if a["status"] in ("aplicado", "aprovado"))
    ebitda = d["ebitda"]
    outros = ebitda - (rb + trib + cmv + pes + adm + aj)
    capex = -(d.get("capex_manutencao") or 0)
    oe = d["owner_earnings"] if d.get("owner_earnings") is not None else d.get("lucro_economico", 0.0)
    ir = oe - ebitda - capex
    acerto = fluxo - oe
    g, taxa, n = base_c["crescimento"], base_c["taxa"], len(base_c["fluxos"])

    modelo = [("Receita bruta", rb, ""), ("(−) Tributos sobre a receita", trib, ""), ("(−) Custo das vendas", cmv, ""),
              ("= Lucro bruto", rb + trib + cmv, "sub"), ("(−) Despesas com pessoal", pes, ""),
              ("(−) Despesas administrativas e comerciais", adm, ""),
              ("(−) Ajustes de normalização", aj, ""), ("(±) Outros", outros, ""),
              ("= EBITDA econômico", ebitda, "sub"), ("(−) Investimento de manutenção", capex, ""),
              ("(−) Impostos sobre o lucro", ir, ""), ("= Caixa do dono no período", oe, "sub"),
              ("(±) Ajuste à média dos períodos", acerto, "")]
    linhas = []
    for rot, val, cls in modelo:
        if cls == "" and abs(val) < 1000:
            continue
        linhas.append((rot, [val] + [val * (1 + g) ** t for t in range(1, n + 1)] + [None], cls))
        if rot == "= EBITDA econômico":
            linhas.append(("Margem EBITDA", [ebitda / rb * 100 if rb else None] * (n + 1) + [None], "margem"))
    rec = v.get("recuperacao_margem")
    if rec:  # 11/11/2026: a margem volta em direção ao melhor ano — diferença para a margem constante, ano a ano
        constante = [(oe + acerto) * (1 + g) ** t for t in range(1, n + 1)]
        linhas.append((f"(+) Recuperação de margem (rumo a {rec['alvo']})",
                       [0.0] + [f_ - c_ for f_, c_ in zip(base_c["fluxos"], constante)] + [None], ""))
        linhas.append(("Margem do caixa do dono", [rec["margens"]["partida"] * 100]
                       + [f_ / (rb * (1 + g) ** t) * 100 if rb else None
                          for t, f_ in enumerate(base_c["fluxos"], start=1)] + [None], "margem"))
    caixa = [fluxo] + list(base_c["fluxos"]) + [base_c["valor_terminal"]]
    fator = [None] + [1 / (1 + taxa) ** t for t in range(1, n + 1)] + [1 / (1 + taxa) ** n]
    vp = [None] + [c_ * f_ for c_, f_ in zip(caixa[1:], fator[1:])]
    return {"colunas": [f"{d['periodo']} (base)"] + [str(ano0 + t) for t in range(1, n + 1)] + ["Valor ao fim"],
            "linhas": linhas, "caixa": caixa, "fator": fator, "vp": vp, "soma_vp": sum(vp[1:]),
            "valor_empresa": base_c["valor_empresa"], "crescimento": g, "taxa": taxa,
            "multiplo_terminal": base_c["valor_terminal"] / caixa[n] if caixa[n] else None,
            "tem_acerto": abs(acerto) >= 1000}
