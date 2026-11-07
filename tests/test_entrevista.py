"""Entrevistas/briefings: reconhecimento pelo nome, leitura de DOCX/TXT e chegada ao pacote da F5."""

import zipfile

import pytest

from captacao.parsers.entrevista import EntrevistaNaoLida, eh_entrevista, extrair_texto
from tarantino.inventario import Tipo, identificar


def _docx(caminho, paragrafos):
    w = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    corpo = "".join(f"<w:p><w:r><w:t>{p}</w:t></w:r></w:p>" for p in paragrafos)
    xml = f'<?xml version="1.0"?><w:document xmlns:w="{w}"><w:body>{corpo}</w:body></w:document>'
    with zipfile.ZipFile(caminho, "w") as z:
        z.writestr("word/document.xml", xml)
    return caminho


@pytest.mark.parametrize("nome,esperado", [
    ("26.07.xx - Briefing - Fulana - Empresa X.docx", True),
    ("Kick-off Empresa X - Anotações do Gemini.pdf", True),
    ("kickoff_empresa.txt", True),
    ("Entrevista com o dono.docx", True),
    ("Reunião inicial 2026-08-01.pdf", True),
    ("Empresa-X-Consolidado-Gravacoes-out2026.pdf", True),
    ("Visita ao empreendedor com investidor.docx", True),
    ("Empresa X - Apresentação de Valuation - Anotações do Gemini.pdf", False),
    ("26.09.24 - Valuation - Fulano - Empresa.docx", False),
    ("Dossiê e Avaliação Empresa - Consultoria.docx", False),
    ("relatorio_completo_empresa.pdf", False),
])
def test_reconhece_entrada_e_exclui_saida_da_nd(nome, esperado):
    assert eh_entrevista(nome) is esperado


def test_le_docx_e_classifica(tmp_path):
    arq = _docx(tmp_path / "Briefing - Empresa.docx",
                ["O dono atende pessoalmente os 10 maiores clientes.", "Não há gerente; a esposa cuida do financeiro."])
    assert identificar(arq) == Tipo.ENTREVISTA
    texto = extrair_texto(arq)
    assert "10 maiores clientes" in texto and "esposa cuida do financeiro" in texto
    vazio = _docx(tmp_path / "Briefing vazio.docx", [""])
    with pytest.raises(EntrevistaNaoLida):
        extrair_texto(vazio)


def test_atalho_google_nao_trava_o_inventario(tmp_path):
    from tarantino.inventario import inventariar

    (tmp_path / "Briefing - Empresa.gdoc").write_text('{"doc_id": "x"}', encoding="utf-8")
    itens = inventariar(tmp_path)
    assert itens[0].tipo == Tipo.GOOGLE and itens[0].status == "não lido" and "baixe" in itens[0].detalhe


def test_entrevista_chega_ao_pacote_da_f5(tmp_path, monkeypatch):
    from tarantino import case as case_mod
    from tarantino.case import abrir_case
    from tarantino.normalizar import normalizar_case
    from tarantino.qualitativo import montar_entrada
    from tests.test_tarantino import _pasta_charlie

    monkeypatch.setattr(case_mod, "REGISTRO", tmp_path / "registro.json")
    pasta, _ = _pasta_charlie(tmp_path)
    (pasta / "03_fundamentos").mkdir()
    _docx(pasta / "03_fundamentos" / "Kick-off - Charlie.docx", ["O fundador ainda faz todas as vendas da linha industrial."])
    r = abrir_case(pasta)
    assert any(e.arquivo.endswith("Kick-off - Charlie.docx") for e in r.dados.entrevistas)
    normalizar_case(pasta)
    texto, _ = montar_entrada(pasta)
    assert "## Entrevistas e briefings" in texto and "faz todas as vendas da linha industrial" in texto


def test_planilha_com_extensao_pdf_e_detectada(tmp_path):
    import openpyxl

    from tarantino.inventario import formato_real, inventariar

    wb = openpyxl.Workbook()
    wb.active["A1"] = "DRE GERENCIAL 2025"
    wb.save(tmp_path / "dre_2025.pdf")
    assert formato_real(tmp_path / "dre_2025.pdf") == "zip"
    item = inventariar(tmp_path)[0]
    assert item.tipo == Tipo.EXTENSAO_ERRADA and "renomeie para .xlsx" in item.detalhe


def test_planilhas_avulsas_viram_trecho_e_dados_pessoais_ficam_de_fora(tmp_path, monkeypatch):
    import openpyxl

    from tarantino import case as case_mod
    from tarantino.case import abrir_case
    from tests.test_tarantino import _pasta_charlie

    monkeypatch.setattr(case_mod, "REGISTRO", tmp_path / "registro.json")
    pasta, _ = _pasta_charlie(tmp_path)
    (pasta / "03_fundamentos").mkdir()
    for nome, linhas in (("curva_abc_clientes.xlsx", [["Cliente", "% faturamento"], ["Transportadora Alfa", 0.06],
                                                       ["Indústria Beta", 0.05]]),
                         ("Relação de funcionários.xlsx", [["Nome", "CPF", "Salário"], ["Fulano", "000", 3000]])):
        wb = openpyxl.Workbook()
        for l in linhas:
            wb.active.append(l)
        wb.save(pasta / "03_fundamentos" / nome)
    r = abrir_case(pasta)
    nomes = [t.arquivo for t in r.dados.outros_documentos]
    assert any(n.endswith("curva_abc_clientes.xlsx") for n in nomes)
    assert not any("funcion" in n.lower() for n in nomes)
    assert "Transportadora Alfa" in next(t.texto for t in r.dados.outros_documentos if "curva" in t.arquivo)


def test_atividade_sem_evidencia_e_none():
    from types import SimpleNamespace

    from engine.normalizacao import atividade_evidenciada, atividade_principal

    vazio = SimpleNamespace(questionario=None, simples=None, efd=[])
    assert atividade_evidenciada(vazio) is None and atividade_principal(vazio) == "comercio"
