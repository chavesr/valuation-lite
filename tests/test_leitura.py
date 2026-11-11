import json

from tarantino.leitura import nao_lidos


def _reg(pasta, conteudo):
    (pasta / "_valuation").mkdir(exist_ok=True)
    (pasta / "_valuation" / "leitura.json").write_text(json.dumps(conteudo), encoding="utf-8")


def test_sem_registro_tudo_falta(tmp_path):
    (tmp_path / "sub").mkdir()
    (tmp_path / "a.pdf").write_text("x")
    (tmp_path / "sub" / "b.xlsx").write_text("x")
    (tmp_path / "_valuation").mkdir()
    (tmp_path / "_valuation" / "dados_brutos.json").write_text("{}")
    assert nao_lidos(tmp_path) == ["a.pdf", "sub/b.xlsx"]


def test_resumo_duplicata_e_vazio(tmp_path):
    for n in ("a.pdf", "a (1).pdf", "c.jpg", "d.pdf"):
        (tmp_path / n).write_text("x")
    _reg(tmp_path, {"arquivos": {"a.pdf": {"resumo": "DRE 2025"}, "a (1).pdf": {"duplicata_de": "a.pdf"},
                                 "c.jpg": {"sem_conteudo": "foto da fachada"}, "d.pdf": {"resumo": "  "}}})
    assert nao_lidos(tmp_path) == ["d.pdf"]


def test_pasta_de_origem_entra_na_conta(tmp_path):
    case, origem = tmp_path / "case", tmp_path / "Empresa"
    case.mkdir(), origem.mkdir()
    (origem / "laudo.pdf").write_text("x")
    _reg(case, {"pasta_origem": str(origem), "arquivos": {}})
    assert nao_lidos(case) == ["Empresa/laudo.pdf"]
    _reg(case, {"pasta_origem": str(origem), "arquivos": {"laudo.pdf": {"resumo": "laudo 2020, R$ 3,0 mi"}}})
    assert nao_lidos(case) == []
