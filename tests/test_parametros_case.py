import json

from engine.normalizacao import carregar_parametros
from tarantino.normalizar import parametros_do_case


def test_sem_arquivo_usa_metodologia(tmp_path):
    assert parametros_do_case(tmp_path) == carregar_parametros()


def test_premissas_do_case_sobrepoem_e_fixam_atividade(tmp_path):
    (tmp_path / "parametros_case.json").write_text(json.dumps({
        "_motivo": "equiparação hospitalar",
        "atividade": "servicos",
        "lucro_presumido": {"irpj_csll_sobre_receita": {"servicos": 0.0308}},
    }), encoding="utf-8")
    p, base = parametros_do_case(tmp_path), carregar_parametros()
    assert p["atividade_case"] == "servicos"
    assert p["lucro_presumido"]["irpj_csll_sobre_receita"]["servicos"] == 0.0308
    # o resto do bloco continua o da metodologia
    assert p["lucro_presumido"]["irpj_csll_sobre_receita"]["industria"] == base["lucro_presumido"]["irpj_csll_sobre_receita"]["industria"]
    assert p["lucro_presumido"]["pis_cofins_cumulativo"] == base["lucro_presumido"]["pis_cofins_cumulativo"]
    assert "_motivo" not in p
