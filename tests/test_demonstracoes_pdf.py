"""Leitor de DRE/Balanço em PDF: ordem das colunas."""
def test_colunas_ano_atual_primeiro():
    from captacao.parsers.demonstracoes_pdf import colunas_ano_atual_primeiro
    assert colunas_ano_atual_primeiro("BALANÇO PATRIMONIAL\nDescrição 2025 2024\n31/12/2025 31/12/2024")
    assert not colunas_ano_atual_primeiro("Descrição Saldo anterior Saldo atual\nBalanço encerrado em: 31/12/2025")
    assert not colunas_ano_atual_primeiro("Período 2024 2025")


def test_duas_colunas_com_natureza():
    from captacao.parsers.demonstracoes_pdf import _separar
    assert _separar("DISPONIVEL 262.191,14D 307.483,10D") == ("DISPONIVEL", [262191.14, 307483.10], "D")
    assert _separar("LUCROS ACUMULADOS 0,00 335.402,58C")[1] == [0.0, 335402.58]
