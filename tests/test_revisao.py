"""F7 — revisor: pacote, validação, decisões, reaproveitamento quando nada muda e bloqueio de graves."""

import json

import pytest
from pydantic import ValidationError

from tarantino import case as case_mod
from tarantino.avaliar import avaliar_case
from tarantino.case import abrir_case, ler_estado
from tarantino.normalizar import normalizar_case
from tarantino.revisao import importar_f7, montar_entrada, pendentes_graves, rodar_f7
from tests.test_tarantino import _pasta_charlie


@pytest.fixture(autouse=True)
def registro_temporario(tmp_path, monkeypatch):
    monkeypatch.setattr(case_mod, "REGISTRO", tmp_path / "registro.json")


def _case_avaliado(tmp_path):
    pasta, _ = _pasta_charlie(tmp_path)
    abrir_case(pasta)
    normalizar_case(pasta)
    avaliar_case(pasta, selic=0.1094)
    return pasta


def _resposta(alertas=None):
    return {"case_id": "x", "parecer": "aprovado_com_ressalvas",
            "resumo": "A margem de 83% não é crível para indústria; o valor depende de confirmar custos.",
            "alertas": alertas if alertas is not None else [
                {"id": "margem_incoerente", "fase": "normalizacao", "severidade": "alta",
                 "achado": "Margem EBITDA de 83% sem custo de produção lançado.",
                 "evidencia": "normalizacao.md: custo das vendas zero", "sugestao": "Pedir DRE com CMV ao contador."},
                {"id": "pedido_acima", "fase": "finalidade", "severidade": "baixa",
                 "achado": "Pedido do vendedor não informado.", "evidencia": "finalidade.json",
                 "sugestao": "Registrar o pedido com tarantino finalidade."}],
            "perguntas_ao_dono": ["Qual é o custo mensal de matéria-prima?"]}


def test_pacote_traz_resumos_e_decisoes_abertas(tmp_path):
    pasta = _case_avaliado(tmp_path)
    texto = montar_entrada(pasta)
    assert "revisor cético" in texto and "## Valuation (F6)" in texto and "## Normalização" in texto
    assert "## Decisões ainda abertas do analista" in texto and "Nota do Score pendente" in texto
    assert ler_estado(pasta).id in texto and '"parecer"' in texto


def test_revisao_importa_bloqueia_graves_e_reaproveita_quando_nada_muda(tmp_path):
    pasta = _case_avaliado(tmp_path)
    saida = pasta / "_valuation"
    chamadas = []

    def falso(prompt, modelo=None):
        chamadas.append(1)
        return "```json\n" + json.dumps(_resposta()) + "\n```"

    r, reaproveitada = rodar_f7(pasta, executor=falso)
    assert not reaproveitada and r.parecer == "aprovado_com_ressalvas" and len(chamadas) == 1
    assert (saida / "revisao.md").exists() and ler_estado(pasta).historico[-1].fase == "F7"
    assert pendentes_graves(saida) == ["margem_incoerente"]

    r, reaproveitada = rodar_f7(pasta, executor=falso)  # pacote igual: não chama o agente
    assert reaproveitada and len(chamadas) == 1

    dec = json.loads((saida / "revisao_decisoes.json").read_text(encoding="utf-8"))
    dec["margem_incoerente"].update(status="aceito_risco", nota="contador confirma custos no próximo balancete")
    (saida / "revisao_decisoes.json").write_text(json.dumps(dec), encoding="utf-8")
    assert pendentes_graves(saida) == []
    importar_f7(pasta)  # reimportar mantém a decisão do analista
    assert json.loads((saida / "revisao_decisoes.json").read_text(encoding="utf-8"))["margem_incoerente"]["status"] \
        == "aceito_risco"

    rodar_f7(pasta, executor=falso, forcar=True)
    assert len(chamadas) == 2


def test_resposta_invalida_e_rejeitada(tmp_path):
    pasta = _case_avaliado(tmp_path)
    ruim = _resposta([{"id": "Com Espaço", "fase": "valuation", "severidade": "alta", "achado": "achado longo o bastante",
                       "evidencia": "evid.", "sugestao": "fazer algo"}])
    (pasta / "_valuation" / "f7_saida.json").write_text(json.dumps(ruim), encoding="utf-8")
    with pytest.raises(ValidationError):
        importar_f7(pasta)


def test_sem_valuation_pede_avaliar(tmp_path):
    pasta, _ = _pasta_charlie(tmp_path)
    abrir_case(pasta)
    with pytest.raises(FileNotFoundError, match="avaliar"):
        montar_entrada(pasta)
