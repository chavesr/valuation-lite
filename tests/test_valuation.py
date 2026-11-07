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
