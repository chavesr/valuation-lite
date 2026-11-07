import pytest

from captacao.carregador import carregar_extratos
from captacao.classificacao import Classificador
from captacao.schemas import DadosBrutos
from engine.gci import calcular_gci
from engine.risco import PESOS, avaliar_risco, fator_anuidade, nota_gci, taxa_desconto
from tests.ficticio import gerar_case


def _montar(tmp_path, chave):
    dados = gerar_case(tmp_path, chave)
    extratos, _ = carregar_extratos(tmp_path / "03_Bancario")
    dados.extratos = Classificador(dados.empresa).classificar(extratos)
    return dados


def test_gci_empresa_formal_nivel_a(tmp_path):
    r = calcular_gci(_montar(tmp_path, "alfa"))
    assert r.nivel == "A", r
    assert abs(r.metricas["gap_fiscal"]) < 0.03
    assert not r.excede_limite_simples


def test_gci_empresa_informal_nivel_c(tmp_path):
    r = calcular_gci(_montar(tmp_path, "charlie"))
    assert r.nivel == "C", r
    assert r.metricas["gap_fiscal"] == pytest.approx(0.40, abs=0.02)
    assert r.excede_limite_simples
    # receita não declarada ≈ 40% de ~R$7,2 mi/ano; transferências, empréstimo e aporte NÃO entram como receita
    assert 2_500_000 < r.receita_nao_declarada_12m < 3_300_000
    assert any("Grupo econômico com 2 empresas" in a for a in r.alertas)


def test_dados_brutos_serializa_em_json(tmp_path):
    dados = _montar(tmp_path, "charlie")
    texto = dados.model_dump_json()
    assert DadosBrutos.model_validate_json(texto) == dados


@pytest.mark.parametrize("score,selic,taxa,premio", [
    (0, 0.1094, 0.20, 0.0906),     # 10,94% + 5 p.p. = 15,9% → piso da casa 20%
    (57.5, 0.1094, 0.2457, 0.1363),  # JB: 10,94% + 13,6 p.p. ≈ 24,4% (ND usou 24,44%)
    (100, 0.1094, 0.3094, 0.20),
    (100, 0.18, 0.35, 0.17),       # teto da casa 35%
])
def test_taxa_desconto(score, selic, taxa, premio):
    assert taxa_desconto(score, selic) == (pytest.approx(taxa), pytest.approx(premio))


def test_score_horizonte_e_perpetuidade():
    baixo = avaliar_risco({d: 5 for d in PESOS}, selic=0.15)  # 5 = melhor nota → menor risco
    alto = avaliar_risco({d: 1 for d in PESOS}, selic=0.15)
    assert (baixo.score, baixo.horizonte_anos, baixo.perpetuidade_permitida_pelo_score) == (0, 5, True)
    assert (alto.score, alto.horizonte_anos, alto.perpetuidade_permitida_pelo_score) == (100, 3, False)
    with pytest.raises(ValueError):
        avaliar_risco({d: 3 for d in list(PESOS)[:-1]}, selic=0.15)


def test_sanidade_multiplo_e_nota_gci():
    assert fator_anuidade(0.20, 5) == pytest.approx(2.99, abs=0.01)
    assert fator_anuidade(0.35, 3) == pytest.approx(1.70, abs=0.01)
    assert (nota_gci(90), nota_gci(70), nota_gci(40)) == (5, 3, 1)
    assert nota_gci(68.9, "C") == 2  # caso Charlie: nível C impõe nota máxima
    assert nota_gci(80, "B") == 3


def test_selic_por_horizonte_escolhe_a_media_do_horizonte_do_score():
    ref = {3: 0.1125, 4: 0.1094, 5: 0.1075}
    alto = avaliar_risco({d: 1 for d in PESOS}, selic=ref)   # Score 100 → 3 anos
    baixo = avaliar_risco({d: 5 for d in PESOS}, selic=ref)  # Score 0 → 5 anos
    assert (alto.horizonte_anos, alto.selic) == (3, 0.1125) and (baixo.horizonte_anos, baixo.selic) == (5, 0.1075)
    assert alto.taxa_desconto == pytest.approx(0.1125 + 0.20)
