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
