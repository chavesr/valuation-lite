"""F6 — Score do case e valuation com dados sintéticos."""

import pytest

from engine.normalizacao import normalizar
from engine.risco import avaliar_risco
from engine.score_case import propor_notas
from engine.valuation import _dcf, avaliar, carregar_parametros, lucro_sustentavel
from captacao.schemas import BalancoAnual
from tests.test_normalizacao import PROV, _dados


def test_dcf_horizonte_finito_e_perpetuidade():
    fluxos, vt, ev = _dcf(100.0, 0.30, 0.0, 4, 0.0, False, 0.03)
    assert fluxos == [100.0] * 4 and vt == 0
    assert ev == pytest.approx(100 * (1 - 1.3 ** -4) / 0.30, abs=0.01)  # fator de anuidade 2,17×
    _, vt, ev_p = _dcf(100.0, 0.30, 0.0, 4, 0.0, True, 0.03)
    assert vt == pytest.approx(100 * 1.03 / 0.27, abs=0.01) and ev_p > ev


def test_lucro_sustentavel_media_nunca_acima_do_recente():
    p = carregar_parametros()
    dres = normalizar(_dados())
    dres[0].owner_earnings, dres[1].owner_earnings = 100_000, 300_000
    _, fluxo, regra = lucro_sustentavel(dres, p)
    assert fluxo == 100_000 and "mais recente" in regra  # média 200 mil, mas o recente é 100 mil
    dres[0].owner_earnings = 400_000
    _, fluxo, regra = lucro_sustentavel(dres, p)
    assert fluxo == 350_000 and regra.startswith("owner earnings — média")


def test_valuation_ponta_a_ponta_com_divida_e_piso():
    dados = _dados()
    dados.balancos = [BalancoAnual(cnpj="1", exercicio=2025, data_base=__import__("datetime").date(2025, 12, 31),
                                   caixa_aplicacoes=100_000, contas_receber=200_000, estoques=300_000,
                                   imobilizado_liquido=100_000, fornecedores=150_000, emprestimos_lp=400_000,
                                   proveniencia=PROV)]
    dres = normalizar(dados)
    base = dres[0]
    notas = propor_notas(dados, None, dres, base)
    assert notas["confiabilidade_informacao"].nota == 2 and notas["confiabilidade_informacao"].pendente
    assert notas["setor_posicao_competitiva"].pendente
    risco = avaliar_risco({k: v.nota for k, v in notas.items()}, selic=0.1375)
    r = avaliar(dados, dres, None, risco, notas)
    assert not r.perpetuidade and "Score" in r.perpetuidade_motivo
    assert r.divida_bruta == 400_000 and r.caixa == 100_000
    # piso = 100 + 0,8×200 + 0,5×300 + 0,4×100 − 150 − 400 = −100 mil
    assert r.piso_patrimonial == pytest.approx(-100_000)
    cons, base_c, otim = r.cenarios
    liquidacao_op = 0.8 * 200_000 + 0.5 * 300_000 + 0.4 * 100_000 - 150_000
    f_base = r.fluxo_base * (1 + base_c.crescimento) ** base_c.anos
    assert base_c.valor_terminal == pytest.approx(max(2.5 * f_base, liquidacao_op), abs=0.01)
    assert cons.valor_terminal == pytest.approx(max(1.5 * r.fluxo_base, liquidacao_op), abs=0.01)
    assert cons.valor_patrimonio <= base_c.valor_patrimonio <= otim.valor_patrimonio
    assert base_c.valor_patrimonio == pytest.approx(base_c.valor_empresa - 300_000)  # − dívida líquida
    assert r.preco_recomendado == pytest.approx(max(base_c.valor_patrimonio * 0.75, 0.0))
    assert any("aguardando o analista" in a for a in r.alertas)


def _avaliar_com(dec):
    dados = _dados()
    dres = normalizar(dados)
    notas = propor_notas(dados, None, dres, dres[0])
    risco = avaliar_risco({k: v.nota for k, v in notas.items()}, selic=0.1375)
    return avaliar(dados, dres, None, risco, notas, None, dec)


def test_d2_provavel_desconta_possivel_retem_remota_ignora():
    sem = _avaliar_com({})
    com = _avaliar_com({
        "divida_fiscal": {"descricao": "Débito fiscal estimado", "valor_bruto": 50_000, "classificacao": "provavel"},
        "trabalhista": {"descricao": "Reclamação trabalhista", "valor_bruto": 70_000, "classificacao": "possivel"},
        "ambiental": {"descricao": "Licença vencida", "valor_bruto": 10_000, "classificacao": "remota"},
        "_leia": "ignorado"})
    assert com.base.valor_patrimonio == pytest.approx(sem.base.valor_patrimonio - 50_000)
    assert com.retencao_sugerida == 70_000
    assert any("Retenção sugerida" in a for a in com.alertas)
    assert {c.id: c.classificacao for c in com.contingencias} == {
        "divida_fiscal": "provavel", "trabalhista": "possivel", "ambiental": "remota"}


def test_d2_bloqueante_quando_contingencias_passam_do_faturamento():
    receita = _avaliar_com({}).receita_base
    r = _avaliar_com({"iss": {"descricao": "Auto de ISS sem parecer", "valor_bruto": receita * 1.5,
                              "classificacao": "possivel"}})
    assert any(a.startswith("BLOQUEANTE") for a in r.alertas)


def test_d2_tributo_latente_usa_carga_efetiva_da_empresa():
    from types import SimpleNamespace

    from engine.normalizacao import DREEconomica, Linha
    from engine.valuation import carga_efetiva_atual, contingencias

    base = DREEconomica(periodo="2025", meses=12, atividade="comercio", regime_comprador="Simples Nacional",
                        receita_fonte="caixa (extratos)", receitas_por_fonte={"declarada": 600_000.0},
                        linhas=[Linha(conta="Receita bruta", valor=1_000_000, fonte="extratos"),
                                Linha(conta="Tributos sobre a receita", valor=-200_000, fonte="comprador")])
    dados = SimpleNamespace(simples={"aliquota_efetiva": 0.08}, dres=[], erp=None)
    assert carga_efetiva_atual(dados, base) == (0.08, "alíquota efetiva do PGDAS-D")
    (c,) = contingencias(dados, base, carregar_parametros())
    assert c.id == "receita_nao_declarada" and c.classificacao == "possivel"
    assert c.valor_bruto == pytest.approx(400_000 * 0.08 * 5)  # 5 anos não prescritos, carga de 8% (não a do comprador)
    (c,) = contingencias(dados, base, carregar_parametros(), {"receita_nao_declarada": {"classificacao": "provavel"}})
    assert c.valor == c.valor_bruto  # reclassificada pelo analista: passa a descontar


def test_d4_regua_da_casa_e_payback_do_preco():
    r = _avaliar_com({"divida_fiscal": {"descricao": "Débito", "valor_bruto": 20_000, "classificacao": "provavel"}})
    descontos = (r.divida_bruta - r.caixa) + 20_000
    assert set(r.regua_payback) == {"forcada", "mercado", "maximo"}
    m = r.regua_payback["mercado"]
    assert m["anos"] == 2.5 and m["valor_empresa"] == pytest.approx(2.5 * r.fluxo_base, abs=0.01)
    assert m["valor_patrimonio"] == pytest.approx(m["valor_empresa"] - descontos, abs=0.01)
    assert r.payback_preco == pytest.approx((r.preco_recomendado + descontos) / r.fluxo_base, abs=0.01)


def test_d5_patrimonio_a_mercado_e_em_liquidacao():
    import datetime

    dados = _dados()
    dados.balancos = [BalancoAnual(cnpj="1", exercicio=2025, data_base=datetime.date(2025, 12, 31),
                                   caixa_aplicacoes=100_000, contas_receber=200_000, estoques=300_000,
                                   imobilizado_liquido=100_000, fornecedores=150_000, emprestimos_lp=400_000,
                                   proveniencia=PROV)]
    dres = normalizar(dados)
    notas = propor_notas(dados, None, dres, dres[0])
    risco = avaliar_risco({k: v.nota for k, v in notas.items()}, selic=0.1094)
    liq = avaliar(dados, dres, None, risco, notas)
    merc = avaliar(dados, dres, None, risco, notas, None, None, "mercado")
    # mercado: 100 + 0,95×200 + 0,9×300 + 1,0×100 − 150 − 400 = +110 mil; liquidação = −100 mil
    assert liq.patrimonio_mercado == pytest.approx(110_000) and liq.piso_patrimonial == pytest.approx(-100_000)
    assert (liq.piso_usado, merc.piso_usado) == ("liquidacao", "mercado")
    assert merc.preco_recomendado >= 110_000 - 0.01  # o piso a mercado vira o mínimo do preço


def test_d5_valor_de_oferta_pelos_ativos_brutos_e_ponte_para_o_dono():
    import datetime

    dados = _dados()
    dados.balancos = [BalancoAnual(cnpj="1", exercicio=2025, data_base=datetime.date(2025, 12, 31),
                                   caixa_aplicacoes=100_000, contas_receber=200_000, estoques=9_000_000,
                                   imobilizado_liquido=100_000, fornecedores=150_000, emprestimos_lp=400_000,
                                   proveniencia=PROV)]
    dres = normalizar(dados)
    notas = propor_notas(dados, None, dres, dres[0])
    r = avaliar(dados, dres, None, avaliar_risco({k: v.nota for k, v in notas.items()}, selic=0.1094), notas)
    ativos = 100_000 + 0.95 * 200_000 + 0.9 * 9_000_000 + 100_000  # brutos: sem descontar passivos
    assert r.ativos_mercado == pytest.approx(ativos)
    assert r.valor_oferta == pytest.approx(ativos) and r.valor_oferta_origem == "ativos a mercado"
    assert r.ponte_dono[-1] == ("= Sobra para o dono", pytest.approx(ativos - 150_000 - 400_000))


def test_fluxo_negativo_conservador_e_o_pior_cenario():
    dados = _dados()
    dres = normalizar(dados)
    for d in dres:
        d.owner_earnings = -100_000
    notas = propor_notas(dados, None, dres, dres[0])
    r = avaliar(dados, dres, None, avaliar_risco({k: v.nota for k, v in notas.items()}, selic=0.1094), notas)
    cons, base_c, otim = r.cenarios
    assert r.fluxo_base < 0
    assert cons.valor_patrimonio <= base_c.valor_patrimonio <= otim.valor_patrimonio


def test_faixa_de_venda_sempre_progressiva():
    r = _avaliar_com({})
    f = r.faixa_venda
    assert f["forcada"] <= f["mercado"] <= f["maximo"]
    assert f["mercado"] == r.preco_recomendado
    assert f["maximo"] == pytest.approx(max(r.cenarios[2].valor_patrimonio, r.preco_recomendado))
