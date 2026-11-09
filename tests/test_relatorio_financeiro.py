"""Capítulo 4: DRE contábil simplificada, ponte contábil → econômico e verticais de risco."""

from types import SimpleNamespace

from relatorio import financeiro as f


def _dre(**kw):
    base = dict(receita_bruta=1000.0, deducoes=-100.0, receita_liquida=None, custo_vendas=-400.0,
                despesas_pessoal=-150.0, pro_labore=-20.0, despesas_administrativas=None, despesas_comerciais=None,
                despesas_operacionais_total=-300.0, depreciacao_amortizacao=-50.0, outras_receitas_despesas=0.0,
                resultado_financeiro=-30.0, financeiras_nas_operacionais=None, ir_csll=-10.0, lucro_liquido=160.0)
    return SimpleNamespace(**(base | kw))


def test_abre_dre_ate_lucro_liquido():
    a = f._abrir(_dre())
    assert a["rl"] == 900 and a["lb"] == 500
    assert a["desp"] == -250  # despesas sem D&A
    assert a["ebitda"] == 250 and a["da"] == -50
    assert a["ajuste"] is None  # 250 − 50 − 30 − 10 = 160 fecha com o lucro reportado
    assert a["outras_desp"] == -80  # 250 − pessoal 150 − pró-labore 20


def test_sem_detalhe_usa_versao_resumida():
    d = _dre(custo_vendas=None, despesas_operacionais_total=None)
    dre = {"colunas": ["2025"], "abertas": [f._abrir(d) | {"ano": 2025, "meses": 12}]}
    t = f.tabela_dre(dre)
    assert not t["detalhada"]
    assert [r for r, _, _ in t["linhas"]] == ["Receita bruta", "Lucro operacional", "Lucro líquido"]


def test_ponte_fecha_no_ebitda_economico():
    k = 1000.0  # a ponte só mostra itens a partir de R$ 1 mil
    d = _dre(**{c: getattr(_dre(), c) * k for c in vars(_dre()) if getattr(_dre(), c)})
    dre = {"colunas": ["2025"], "abertas": [f._abrir(d) | {"ano": 2025, "meses": 12}]}
    linhas = [("Receita bruta", 1000), ("Tributos sobre a receita", -110), ("Custo das vendas", -400),
              ("Despesas com pessoal", -150), ("Despesas administrativas e comerciais", -80)]
    econ = [{"periodo": "2025", "ebitda": 116 * k, "linhas": [{"conta": c, "valor": v * k} for c, v in linhas],
             "ajustes": [{"id": "pro_labore_mercado", "status": "aplicado", "valor": -144 * k, "descricao": "x"},
                         {"id": "substituicao_tecnico", "status": "proposto", "valor": -50 * k, "descricao": "y"}]}]
    p = f.ponte_economica(dre, econ, "2025")
    itens = dict(p["itens"])
    assert p["itens"][0] == ("EBITDA contábil", 250 * k)
    assert itens["Tributos no regime do comprador"] == -10 * k
    assert itens["Pró-labore atual (sai da despesa)"] == 20 * k
    assert itens["Pró-labore de mercado"] == -144 * k
    assert sum(v for r, v in p["itens"][1:-1]) == p["itens"][-1][1] - 250 * k  # fecha sem resíduo escondido
    assert p["pendentes"] == 1 and p["pendentes_valor"] == -50 * k


def test_verticais_sem_nota_ficam_nd():
    v = {"notas": {"dependencia_dono": {"nota": 2, "pendente": True}, "contingencias": {"nota": 4}}}
    out = {x["vertical"]: x for x in f.verticais_risco(v, {"fosso": {"forca": "amplo"}})}
    assert len(out) == 8
    assert out["Gestão e dependência do dono"]["nota"] == 2 and out["Gestão e dependência do dono"]["pendente"]
    assert out["Diferencial e intangíveis"]["nota"] == 5
    assert out["Operação e ativos físicos"]["nota"] is None


def _planilha(abas, faturamento=None):
    total = faturamento or {}
    return SimpleNamespace(abas=abas, faturamento_mensal_total=lambda: total)


def test_clientes_da_planilha_com_setor_e_participacao_na_receita():
    dre = {"abertas": [{"ano": 2025, "meses": 12, "rb": 1_000_000.0}]}
    linhas = [{"ano": 2025, "cliente": "A", "setor_do_cliente": "Saúde", "faturamento_no_ano_r": 300_000.0},
              {"ano": 2025, "cliente": "B", "setor_do_cliente": "Saúde", "faturamento_no_ano_r": 100_000.0},
              {"ano": 2025, "cliente": "C", "faturamento_no_ano_r": 200_000.0},
              {"ano": 2024, "cliente": "A", "faturamento_no_ano_r": 900_000.0}]
    cl = f.clientes_planilha(SimpleNamespace(planilha_nd=_planilha({"5_Clientes": linhas})), dre)
    assert cl["ano"] == 2025 and [r["cliente"] for r in cl["ranking"]] == ["A", "C", "B"]
    assert cl["maior"] == 0.3 and round(cl["top5"], 2) == 0.6 and cl["base_receita"]
    assert cl["por_setor"] == [("Saúde", 40.0)]


def test_operacional_so_com_um_volume_e_um_preco_por_ano():
    V, P = f.VOLUME, f.PRECO
    regs = [{"ano": 2024, "tipo": V, "valor_no_ano": 100.0, "indicador": "Milheiros", "unidade": "mil"},
            {"ano": 2024, "tipo": P, "valor_no_ano": 10.0, "indicador": "Preço", "unidade": "R$"},
            {"ano": 2025, "tipo": V, "valor_no_ano": 120.0, "indicador": "Milheiros", "unidade": "mil"},
            {"ano": 2025, "tipo": P, "valor_no_ano": 11.0, "indicador": "Preço", "unidade": "R$"},
            {"ano": 2023, "tipo": V, "valor_no_ano": 90.0}]  # sem preço: fica de fora
    op = f.operacional_planilha(SimpleNamespace(planilha_nd=_planilha({"11_Indicadores": regs})))
    assert op["anos"] == ["2024", "2025"] and op["receita"] == [1000.0, 1320.0]
    assert op["volume"]["nome"] == "Milheiros" and op["preco"]["unidade"] == "R$"


def test_linhas_de_receita_ordenadas_pelo_ultimo_ano():
    regs = [{"ano": 2024, "linha_de_receita": "Serviço", "receita_no_ano_r": 50.0},
            {"ano": 2025, "linha_de_receita": "Serviço", "receita_no_ano_r": 40.0},
            {"ano": 2025, "linha_de_receita": "Produto", "receita_no_ano_r": 200.0}]
    lr = f.linhas_receita_planilha(SimpleNamespace(planilha_nd=_planilha({"10_Linhas_Receita": regs})))
    assert lr["anos"] == ["2024", "2025"]
    assert lr["linhas"] == [("Produto", [None, 200.0]), ("Serviço", [50.0, 40.0])]


def test_sem_planilha_nada_quebra():
    d = SimpleNamespace(planilha_nd=None)
    assert f.clientes_planilha(d, {"abertas": []}) is None
    assert f.linhas_receita_planilha(d) is None and f.operacional_planilha(d) is None


def test_f5_preenche_quando_a_planilha_nao_traz():
    qual = {"operacional": {"volume": {"nome": "Milheiros", "unidade": "milheiros",
                                       "valores": [{"ano": 2024, "valor": 100}, {"ano": 2025, "valor": 120}]},
                            "preco": {"nome": "Preço", "unidade": "R$", "valores": [{"ano": 2025, "valor": 10}]},
                            "fonte": "dono, entrevista A"},
            "linhas_receita": [{"nome": "Serviço", "valores": [{"ano": 2025, "valor": 40}]},
                               {"nome": "Produto", "valores": [{"ano": 2025, "valor": 200}]}],
            "clientes_principais": [{"cliente": "A", "setor": "Saúde", "receita_anual": 250_000},
                                    {"cliente": "B", "percentual": 30}, {"cliente": "C"}],
            "leitura_verticais": [{"vertical": "Contingências", "leitura": "x", "tratamento": "retenção"}]}
    op = f.operacional_f5(qual)
    assert op["anos"] == ["2025"] and op["receita"] == [1200] and op["fonte"] == "declaração dos sócios"
    assert [n for n, _ in f.linhas_receita_f5(qual)["linhas"]] == ["Produto", "Serviço"]
    dre = {"abertas": [{"ano": 2025, "meses": 12, "rb": 1_000_000.0}]}
    cl = f.clientes_f5(qual, dre, SimpleNamespace(planilha_nd=None))
    assert [r["cliente"] for r in cl["ranking"]] == ["B", "A", "C"]  # C sem valor vai no fim
    assert cl["maior"] == 0.3 and cl["ranking"][1]["participacao"] == 0.25 and cl["ranking"][0]["valor"] == 300_000
    assert cl["ranking"][2]["cliente"] == "C" and cl["ranking"][2]["valor"] is None and cl["top5"] is None
    assert f.leituras_verticais(qual)["Contingências"]["tratamento"] == "retenção"
    assert f.operacional_f5({}) is None and f.linhas_receita_f5({}) is None and f.clientes_f5({}, dre, None) is None
    mensal = f.operacional_f5({**qual, "operacional": {**qual["operacional"], "preco_mensal": True}})
    assert mensal["receita"] == [14_400] and mensal["mensal"]


def test_esquema_f5_aceita_saida_antiga_e_recusa_vertical_repetida():
    import pytest
    from julgamento.esquemas import Qualitativo
    base = {"case_id": "x", "playbook": "geral", "resumo": "r", "modelo_negocio": "m",
            "fosso": {"forca": "estreito", "justificativa": "j"}, "gestao": {"avaliacao": "a"},
            "notas_score": [{"dimensao": d, "nota": 3, "justificativa": "sem informação", "evidencias": ["e"],
                             "confianca": "baixa"} for d in ("dependencia_dono", "recorrencia_receita",
                                                             "contingencias", "setor_posicao_competitiva")]}
    q = Qualitativo.model_validate(base)  # saída anterior aos campos do capítulo 4
    assert q.operacional is None and q.leitura_verticais == []
    dup = [{"vertical": "Contingências", "leitura": "a", "tratamento": "b"}] * 2
    with pytest.raises(ValueError):
        Qualitativo.model_validate(base | {"leitura_verticais": dup})
