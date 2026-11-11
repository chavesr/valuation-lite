"""F8 — relatório: trava pela revisão, textos validados, números conferidos e HTML com os 6 capítulos."""

import json

import pytest
from pydantic import ValidationError

from tarantino import case as case_mod
from tarantino.avaliar import avaliar_case
from tarantino.case import abrir_case
from tarantino.normalizar import normalizar_case
from tarantino.relatorio import RelatorioBloqueado, gerar_relatorio
from tarantino.revisao import rodar_f7
from tests.test_tarantino import _pasta_charlie


@pytest.fixture(autouse=True)
def registro_temporario(tmp_path, monkeypatch):
    monkeypatch.setattr(case_mod, "REGISTRO", tmp_path / "registro.json")


TEXTOS = {"case_id": "x", "tese": "Indústria de alimentos com 28 anos de mercado; o valor depende de confirmar custos.",
          "por_que_olhar": ["Marca regional consolidada.", "Base de clientes pulverizada."],
          "o_que_pesa_contra": ["Custos não comprovados: pedir DRE com CMV.", "Venda sem nota declarada."],
          "sobre_empresa": "Fabrica alimentos e presta serviços de manutenção a clientes regionais há quase três décadas.",
          "gestao_pessoas": "O fundador concentra as vendas; não há gerente com autonomia.",
          "mercado_setor": "Setor pulverizado e de preço competitivo; o diferencial é a logística regional própria.",
          "leitura_financeira": "A receita comprovada nos extratos supera a declarada; a margem calculada não é crível.",
          "leitura_riscos": "Informalidade e dependência do dono são os riscos centrais; ambos têm caminho de solução.",
          "leitura_valuation": "Descontamos o caixa sustentável pela taxa da casa e conferimos pela régua de payback.",
          "estrutura_transacao": "Venda total, com retenção de parte do preço para as contingências possíveis."}


def _revisao(graves):
    alertas = [{"id": "custos_ausentes", "fase": "normalizacao", "severidade": "alta" if graves else "media",
                "achado": "Margem sem custo de produção lançado.", "evidencia": "normalizacao.md",
                "sugestao": "Pedir DRE com CMV."}]
    return {"case_id": "x", "parecer": "aprovado_com_ressalvas", "resumo": "Valor depende dos custos.",
            "alertas": alertas, "perguntas_ao_dono": []}


def _case(tmp_path, graves=False):
    pasta, _ = _pasta_charlie(tmp_path)
    abrir_case(pasta)
    normalizar_case(pasta)
    avaliar_case(pasta, selic=0.1094)
    return pasta


def _registrar_leitura(pasta):
    from tarantino.leitura import documentos
    (pasta / "_valuation" / "leitura.json").write_text(json.dumps(
        {"arquivos": {d: {"resumo": "lido no teste"} for d in documentos(pasta)}}), encoding="utf-8")


def test_sem_leitura_integral_bloqueia(tmp_path):
    pasta = _case(tmp_path)
    rodar_f7(pasta, executor=lambda p, modelo=None: json.dumps(_revisao(graves=False)))
    with pytest.raises(RelatorioBloqueado, match="sem leitura registrada"):
        gerar_relatorio(pasta, executor=lambda p, modelo=None: json.dumps(TEXTOS), pdf=False)


def test_sem_revisao_ou_com_grave_pendente_bloqueia(tmp_path):
    pasta = _case(tmp_path)
    with pytest.raises(RelatorioBloqueado, match="revisar"):
        gerar_relatorio(pasta, executor=lambda p, modelo=None: json.dumps(TEXTOS), pdf=False)
    rodar_f7(pasta, executor=lambda p, modelo=None: json.dumps(_revisao(graves=True)))
    with pytest.raises(RelatorioBloqueado, match="custos_ausentes"):
        gerar_relatorio(pasta, executor=lambda p, modelo=None: json.dumps(TEXTOS), pdf=False)


def test_gera_html_com_os_seis_capitulos_e_reaproveita_textos(tmp_path):
    pasta = _case(tmp_path)
    rodar_f7(pasta, executor=lambda p, modelo=None: json.dumps(_revisao(graves=False)))
    _registrar_leitura(pasta)
    chamadas = []

    def redator(prompt, modelo=None):
        chamadas.append(1)
        return json.dumps({**TEXTOS, "leitura_valuation": TEXTOS["leitura_valuation"] + " Valor de R$ 9.999.999."})

    r = gerar_relatorio(pasta, executor=redator, pdf=False)
    html = r["html"].read_text(encoding="utf-8")
    for cap in ("Visão geral", "Sobre a empresa", "Análise de mercado e setor",
                "Análise financeira e riscos do negócio", "Valuation", "Ida a mercado"):
        assert cap in html
    assert "Quanto vale" in html and "<svg" in html and "Marca regional consolidada." in html
    assert r["numeros_nao_conferidos"] == ["R$ 9.999.999"]  # número que não está no material
    gerar_relatorio(pasta, executor=redator, pdf=False)
    assert len(chamadas) == 1  # nada mudou: textos reaproveitados


def test_textos_fora_do_formato_sao_rejeitados(tmp_path):
    pasta = _case(tmp_path)
    rodar_f7(pasta, executor=lambda p, modelo=None: json.dumps(_revisao(graves=False)))
    _registrar_leitura(pasta)
    with pytest.raises(ValidationError):
        gerar_relatorio(pasta, executor=lambda p, modelo=None: json.dumps({**TEXTOS, "por_que_olhar": []}), pdf=False)


def test_graficos_do_capitulo_2():
    from relatorio import graficos as g

    org = g.organograma([{"id": "dono", "cargo": "Sócio-administrador", "nome": "Fulano", "superior": None},
                         {"id": "ger", "cargo": "Gerente de produção", "nome": None, "superior": "dono"},
                         {"id": "fin", "cargo": "Financeiro", "nome": "esposa", "superior": "dono"},
                         {"id": "op", "cargo": "Operadores", "nome": "equipe de 6", "superior": "ger"}])
    assert org.startswith("<svg") and "Sócio-administrador" in org and "equipe de 6" in org
    tl = g.linha_do_tempo([(2010, "Mudança para sede própria"), (1996, "Fundação em São Paulo")])
    assert tl.index("1996") < tl.index("2010")  # ordem cronológica
    assert "%" in g.barras_percentual([("Etiquetas", 90), ("Ribbons", 10)])


def test_evolucao_do_investimento_e_tir():
    from relatorio.evolucao import evolucao, tir

    # paga 100, recebe 30/ano por 3 anos e a empresa vale 100 no fim → TIR de 30%
    assert tir(100, [30, 30, 30], 100) == pytest.approx(0.30, abs=1e-3)
    e = evolucao(100, [30, 30, 30], 100, 0.30, 2026, {"2027": 10, "2028": 10, "2029": 10}, {"2027": 4}, 0.06)
    assert e["anos"] == [2026, 2027, 2028, 2029] and e["empresa"][0] == e["selic"][0] == e["ipca_mais"][0] == 100
    assert e["selic"][-1] == pytest.approx(100 * 1.1 ** 3, abs=0.01)
    assert e["ipca_mais"][-1] == pytest.approx(100 * (1.04 * 1.06) ** 3, abs=0.01)
    caixa = (30 * 1.1 + 30) * 1.1 + 30  # caixa reinvestido na Selic
    assert e["empresa"][-1] == pytest.approx(caixa + 100, abs=0.01)  # + valor terminal no último ano


def test_ativos_so_ativo_e_valor_de_mercado():
    """11/11/2026: a tabela de ativos tem só Ativo | Valor (venda a mercado); bem fora da venda não soma."""
    from relatorio.render import _bloco_ativos
    at = {"linhas": [{"nome": "Imóveis", "valor": 2_000_000.0, "fora": True},
                     {"nome": "Veículos", "valor": 40_000.0, "fora": False},
                     {"nome": "Máquinas e equipamentos", "valor": None, "fora": False}],
          "total": 40_000.0, "piso": 1_600_000.0, "fonte": None}
    html = _bloco_ativos(at)
    assert "<th>Ativo</th><th class=\"n\">Valor</th></tr>" in html
    assert "Contábil" not in html and "Realização" not in html
    assert "(fora da venda)" in html and "n/d" in html.lower()
