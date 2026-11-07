import pytest

from captacao.questionario import carregar_catalogo, ler_respostas, parse_moeda
from tests.ficticio_questionario import TESTE_REAL, cabecalho_forms, escrever_respostas


def test_catalogo_bate_com_formulario():
    cat = carregar_catalogo()
    assert len(cat.perguntas) == 96
    assert len(cat.combos) == 7 and cat.combos["Fabricação + serviços"] == ["I", "S"]
    assert cat.perguntas["Q24"].opcoes == ["Sim", "Não, parte é recebida sem nota"]
    assert cat.perguntas["I08a"].essencial and not cat.perguntas["I03"].essencial
    # mesmo layout da planilha real exportada em 06/11/2026: 271 colunas, 97 títulos distintos
    cab = cabecalho_forms()
    assert len(cab) == 271 and len(set(cab)) == 97


@pytest.mark.parametrize("entrada,esperado", [
    ("4 mi", 4_000_000), ("1,5 mi", 1_500_000), ("2 milhões", 2_000_000), ("R$ 150 mil", 150_000),
    ("150k", 150_000), ("R$ 20.000,00", 20_000), ("20.000", 20_000), ("3,2MM", 3_200_000),
    ("não sei", None), ("", None),
])
def test_parse_moeda(entrada, esperado):
    assert parse_moeda(entrada) == esperado


def test_le_resposta_real_e_junta_colunas_dos_caminhos(tmp_path):
    arq = escrever_respostas(tmp_path / "respostas.csv", [TESTE_REAL])
    r = ler_respostas(arq)
    assert r.empresa.startswith("TESTE") and r.cnpj == "00000000000100"
    assert r.caminho == "Fabricação + serviços" and r.modulos_completos == ["I", "S"]
    assert r.valor("Q01") == 1998 and r.valor("Q12a") == 18
    assert r.valor("Q03a") == 4_000_000 and r.valor("Q28") == 150_000
    assert r.valor("Q24") == "Não, parte é recebida sem nota"
    assert r.valor("I02a") == 12 and r.valor("S01a") == 60 and r.valor("C04") == 45
    assert len(r.valor("P01")) == 3  # as 3 opções, apesar das vírgulas dentro do texto
    assert r.valor("Q02") == ["Aposentadoria"]
    assert r.alertas == []
    pend = r.pendentes()
    assert "I03" in pend and "S02" in pend  # módulos completos do caminho
    assert "C02" in pend and "C03a" not in pend  # comércio < 10%: só as essenciais
    assert "Q01" not in pend


def test_alertas_de_consistencia_e_outro(tmp_path):
    dados = dict(TESTE_REAL, P01b="15", Q02="Aposentadoria, Briga com o banco",
                 P03="Somente fabricação", Q06="muitas")
    r = ler_respostas(escrever_respostas(tmp_path / "r.csv", [dados]))
    texto = " | ".join(r.alertas)
    assert "somam 110%" in texto
    assert "P03 incoerente" in texto and "fabricação + comércio + serviços" in texto
    assert "Q06: número não reconhecido" in texto
    assert r.respostas["Q02"].valor == ["Aposentadoria"] and r.respostas["Q02"].outro == "Briga com o banco"
    assert r.valor("S01a") == 60  # essencial: também é perguntada como atividade secundária
    assert "S02" not in r.pendentes()  # não essencial de serviços: fora do caminho escolhido


def test_varias_respostas_escolhe_por_cnpj(tmp_path):
    outra = dict(TESTE_REAL, ID1="Outra Empresa", ID2="11.111.111/0001-11")
    arq = escrever_respostas(tmp_path / "r.csv", [TESTE_REAL, outra])
    assert ler_respostas(arq, cnpj="00000000000100").empresa.startswith("TESTE")
    r = ler_respostas(arq)
    assert r.empresa == "Outra Empresa" and any("2 respostas" in a for a in r.alertas)
    with pytest.raises(ValueError):
        ler_respostas(arq, cnpj="99")


def test_titulo_alterado_no_forms_vira_alerta(tmp_path):
    arq = escrever_respostas(tmp_path / "r.csv", [TESTE_REAL])
    texto = arq.read_text(encoding="utf-8").replace("Seu nome", "Nome do respondente", 1)
    arq.write_text(texto, encoding="utf-8")
    r = ler_respostas(arq)
    assert any("Nome do respondente" in a for a in r.alertas)
