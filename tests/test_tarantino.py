import json
import shutil

import openpyxl
import pytest

from captacao.planilha_nd import gerar_modelo
from tarantino import case as case_mod
from tarantino.__main__ import main
from tarantino.case import abrir_case, ler_estado
from tarantino.inventario import Tipo
from tests.ficticio import gerar_case
from tests.ficticio_questionario import TESTE_REAL, escrever_respostas


@pytest.fixture(autouse=True)
def registro_temporario(tmp_path, monkeypatch):
    monkeypatch.setattr(case_mod, "REGISTRO", tmp_path / "registro.json")


def _pasta_charlie(base):
    """Pasta no padrão do Drive: extratos OFX, Planilha ND, questionário, PGDAS/DRE digitados, PDF e duplicata."""
    pasta = base / "Charlie Alimentos"
    dados = gerar_case(pasta, "charlie")  # cria 03_Bancario/*.ofx

    (pasta / "04_Gerencial").mkdir()
    nd = gerar_modelo(pasta / "04_Gerencial" / "Planilha_ND.xlsx", fim="2025-12", meses=24)
    wb = openpyxl.load_workbook(nd)
    g = wb["1_Grupo"]
    for i, emp in enumerate(dados.empresa.cnpjs, start=5):
        g.cell(row=i, column=1, value=emp.cnpj)
        g.cell(row=i, column=2, value=emp.razao_social)
        g.cell(row=i, column=4, value="Simples Nacional")
    s = wb["2_Socios"]
    s["A5"], s["B5"] = dados.empresa.socios[0].nome, 1.0
    f = wb["4_Faturamento"]
    f["B4"] = dados.empresa.cnpjs[0].cnpj
    for i, gm in enumerate(dados.gerencial, start=5):
        f.cell(row=i, column=2, value=gm.receita)
    wb.save(nd)

    (pasta / "00_recebidos").mkdir()
    escrever_respostas(pasta / "00_recebidos" / "respostas.csv",
                       [dict(TESTE_REAL, ID1="Charlie Alimentos", ID2=dados.empresa.cnpjs[0].cnpj)])
    (pasta / "00_recebidos" / "extrato_maio.pdf").write_bytes(b"%PDF-1.4 fake")
    ofx = next((pasta / "03_Bancario").glob("*.ofx"))
    shutil.copy(ofx, pasta / "00_recebidos" / ("copia " + ofx.name))  # cliente reenviou o mesmo arquivo

    (pasta / "_valuation").mkdir()
    manual = {"pgdas": [p.model_dump(mode="json") for p in dados.pgdas],
              "dres": [d.model_dump(mode="json") for d in dados.dres]}
    (pasta / "_valuation" / "entrada_manual.json").write_text(json.dumps(manual), encoding="utf-8")
    return pasta, dados


def test_abrir_case_charlie_ponta_a_ponta(tmp_path):
    pasta, original = _pasta_charlie(tmp_path)
    r = abrir_case(pasta)

    # F1 — inventário
    tipos = {a.caminho: (a.tipo, a.status) for a in r.inventario}
    assert tipos["04_Gerencial/Planilha_ND.xlsx"] == (Tipo.PLANILHA_ND, "lido")
    assert tipos["00_recebidos/respostas.csv"] == (Tipo.QUESTIONARIO, "lido")
    assert tipos["00_recebidos/extrato_maio.pdf"] == (Tipo.PDF, "não lido")
    assert sum(1 for a in r.inventario if a.status == "duplicado") == 1

    # F2 — captação
    d = r.dados
    assert d.empresa.nome == "Charlie Alimentos" and len(d.empresa.cnpjs) == 2
    assert (d.periodo_inicio, d.periodo_fim) == ("2024-01", "2025-12")
    assert len(d.extratos) == 2 and len(d.pgdas) == len(original.pgdas) and len(d.dres) == 4
    assert len(d.gerencial) == 24 and d.questionario.valor("Q01") == 1998
    assert all(t.categoria for e in d.extratos for t in e.transacoes)

    # F3 — Charlie declara 60% da receita: GCI nível C
    assert r.gci.nivel == "C" and r.gci.receita_nao_declarada_12m > 2_000_000
    assert r.estado.estado == "gci_definido" and r.estado.id.startswith("ND-")
    assert [e.fase for e in r.estado.historico] == ["abertura", "F1", "F2", "F3"]

    # saídas
    saida = pasta / "_valuation"
    for nome in ("state.json", "inventario.json", "dados_brutos.json", "gci.json", "pendencias.md"):
        assert (saida / nome).exists()
    md = (saida / "pendencias.md").read_text(encoding="utf-8")
    assert "nível **C**" in md and "extrato_maio.pdf" in md and "Q06 · Quantas horas" in md
    assert "Planilha ND de Captação preenchida" not in md  # foi recebida
    assert "duplicado" in md


def test_reabrir_mantem_id_e_historico(tmp_path):
    pasta, _ = _pasta_charlie(tmp_path)
    id1 = abrir_case(pasta).estado.id
    r = abrir_case(pasta)
    assert r.estado.id == id1
    assert [e.fase for e in r.estado.historico] == ["abertura", "F1", "F2", "F3", "F1", "F2", "F3"]


def test_pasta_so_com_pdfs_gera_pedido_completo(tmp_path):
    pasta = tmp_path / "Empresa PDF"
    (pasta / "00_recebidos").mkdir(parents=True)
    (pasta / "00_recebidos" / "Extrato Jan.pdf").write_bytes(b"%PDF a")
    (pasta / "00_recebidos" / "2025.zip").write_bytes(b"PK")
    r = abrir_case(pasta, fim="2026-08")
    assert r.gci is None and r.estado.estado == "extraido"
    pedidos = " | ".join(r.pendencias.pedir_ao_cliente)
    for trecho in ("OFX de todas as contas", "PGDAS-D", "DRE e Balanço", "Planilha ND", "Questionário",
                   "1 PDF(s) na pasta"):
        assert trecho in pedidos
    assert len(r.pendencias.arquivos_nao_lidos) == 2


def test_cli(tmp_path, capsys):
    pasta, _ = _pasta_charlie(tmp_path)
    main(["abrir", str(pasta)])
    saida = capsys.readouterr().out
    assert "Charlie Alimentos" in saida and "nível C" in saida
    main(["status", str(pasta)])
    assert "gci_definido" in capsys.readouterr().out
    assert ler_estado(pasta).estado == "gci_definido"
