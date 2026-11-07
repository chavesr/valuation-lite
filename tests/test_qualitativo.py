"""F5 — pacote de entrada, execução (executor falso), validação e efeito das notas no Score."""

import json

import pytest
from pydantic import ValidationError

from julgamento.executor import ErroJulgamento, extrair_json
from tarantino import case as case_mod
from tarantino.__main__ import main
from tarantino.avaliar import avaliar_case
from tarantino.case import abrir_case, ler_estado
from tarantino.normalizar import normalizar_case
from tarantino.qualitativo import importar_f5, montar_entrada, rodar_f5
from tests.test_tarantino import _pasta_charlie


@pytest.fixture(autouse=True)
def registro_temporario(tmp_path, monkeypatch):
    monkeypatch.setattr(case_mod, "REGISTRO", tmp_path / "registro.json")


def _resposta(notas=None) -> dict:
    notas = notas or {"dependencia_dono": 2, "recorrencia_receita": 4, "contingencias": 3, "setor_posicao_competitiva": 4}
    return {
        "case_id": "qualquer", "playbook": "comercio",
        "resumo": "Distribuidora regional com base de clientes pulverizada. Dono concentra o comercial.",
        "modelo_negocio": "Revenda de alimentos para pequenos varejistas.",
        "fosso": {"forca": "estreito", "fontes": ["localização"], "justificativa": "Logística regional própria."},
        "gestao": {"avaliacao": "Informação organizada, contas separadas.", "pontos_atencao": ["sem gerente"]},
        "notas_score": [{"dimensao": d, "nota": n, "justificativa": f"justificativa da nota de {d}",
                         "evidencias": ["fato do pacote"], "confianca": "media"} for d, n in notas.items()],
        "riscos": [{"descricao": "Sucessão", "severidade": "alta", "evidencia": "Q08"}],
        "pontos_fortes": ["clientes pulverizados"],
        "perguntas_entrevista": ["Quem atende os 10 maiores clientes?"],
        "lacunas_informacao": ["contratos com fornecedores"],
    }


def _case_normalizado(tmp_path):
    pasta, _ = _pasta_charlie(tmp_path)
    abrir_case(pasta)
    normalizar_case(pasta)
    return pasta


def test_pacote_tem_instrucoes_playbook_fatos_e_esquema(tmp_path):
    pasta = _case_normalizado(tmp_path)
    texto, playbook = montar_entrada(pasta)
    assert playbook in ("industria", "comercio", "servicos")
    assert "analista fundamentalista" in texto and "Playbook geral" in texto
    assert "## DRE econômica" in texto and "## Score de Risco" in texto
    assert "Questionário do empreendedor" in texto and '"notas_score"' in texto
    assert ler_estado(pasta).id in texto


def test_claude_code_com_executor_falso_importa_e_alimenta_score(tmp_path):
    pasta = _case_normalizado(tmp_path)
    recebido = {}

    def falso(prompt, modelo=None):
        recebido["prompt"] = prompt
        return "Segue a análise:\n```json\n" + json.dumps(_resposta()) + "\n```\n"

    q = rodar_f5(pasta, executor=falso)
    saida = pasta / "_valuation"
    assert "Formato da resposta" in recebido["prompt"]
    assert q.case_id == ler_estado(pasta).id  # o código impõe o id do case
    assert (saida / "f5_saida_bruta.txt").exists() and (saida / "qualitativo.md").exists()
    assert ler_estado(pasta).historico[-1].fase == "F5"

    r = avaliar_case(pasta, selic=0.1375)
    assert r.notas["setor_posicao_competitiva"].nota == 4
    assert r.notas["setor_posicao_competitiva"].origem == "F5 (proposta)"
    assert r.notas["dependencia_dono"].pendente  # ainda aguarda o analista


def test_analista_prevalece_sobre_f5(tmp_path):
    pasta = _case_normalizado(tmp_path)
    rodar_f5(pasta, executor=lambda p, modelo=None: json.dumps(_resposta()))
    avaliar_case(pasta, selic=0.1375)
    arq = pasta / "_valuation" / "score_notas.json"
    notas = json.loads(arq.read_text(encoding="utf-8"))
    notas["dependencia_dono"].update(nota=1, origem="analista", evidencia="entrevista: dono é o único vendedor")
    arq.write_text(json.dumps(notas), encoding="utf-8")
    r = avaliar_case(pasta, selic=0.1375)
    assert r.notas["dependencia_dono"].nota == 1 and not r.notas["dependencia_dono"].pendente


def test_modo_manual_e_importar_pela_cli(tmp_path, capsys):
    pasta = _case_normalizado(tmp_path)
    main(["qualitativo", str(pasta), "--modo", "manual"])
    assert (pasta / "_valuation" / "f5_entrada.md").exists()
    assert "f5_saida.json" in capsys.readouterr().out
    (pasta / "_valuation" / "f5_saida.json").write_text(json.dumps(_resposta()), encoding="utf-8")
    main(["qualitativo", str(pasta), "--importar"])
    assert "fosso estreito" in capsys.readouterr().out


def test_resposta_incompleta_e_rejeitada(tmp_path):
    pasta = _case_normalizado(tmp_path)
    ruim = _resposta()
    ruim["notas_score"] = ruim["notas_score"][:3]  # falta uma dimensão
    (pasta / "_valuation" / "f5_saida.json").write_text(json.dumps(ruim), encoding="utf-8")
    with pytest.raises(ValidationError, match="sem as dimensões"):
        importar_f5(pasta)
    ruim = _resposta({"dependencia_dono": 7, "recorrencia_receita": 2, "contingencias": 3,
                      "setor_posicao_competitiva": 2})
    (pasta / "_valuation" / "f5_saida.json").write_text(json.dumps(ruim), encoding="utf-8")
    with pytest.raises(ValidationError):
        importar_f5(pasta)


def test_extrair_json():
    assert extrair_json('texto {"a": 1} mais texto') == {"a": 1}
    assert extrair_json('```json\n{"a": {"b": 2}}\n```') == {"a": {"b": 2}}
    with pytest.raises(ErroJulgamento):
        extrair_json("sem json aqui")


def test_casos_referencia_entram_no_pacote_e_excluem_o_proprio_case(tmp_path):
    from tarantino.qualitativo import casos_referencia

    todos, sem_r1 = casos_referencia(), casos_referencia("R1")
    assert "## R1 " in todos and "## R1 " not in sem_r1 and "## R2 " in sem_r1
    pasta = _case_normalizado(tmp_path)
    texto, _ = montar_entrada(pasta, excluir_referencia="R3")
    assert "## R2 " in texto and "## R3 " not in texto
    assert "5 = melhor" in texto


def test_comparar_concordancia():
    from julgamento.calibracao import carregar_gabarito, comparar

    gab = carregar_gabarito()
    assert set(gab) == {"R1", "R2", "R3", "R4", "R5"}
    prop = {"R1": {**gab["R1"], "contingencias": gab["R1"]["contingencias"] + 2}}
    r = comparar(gab, prop)
    assert (r["notas"], r["exatas"], r["ate_1_ponto"], r["vies_medio"]) == (4, 3, 3, 0.5)
