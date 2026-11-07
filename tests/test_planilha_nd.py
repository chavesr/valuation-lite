import openpyxl

from captacao.planilha_nd import ABAS, gerar_modelo


def test_gera_modelo_com_abas_meses_e_listas(tmp_path):
    caminho = gerar_modelo(tmp_path / "modelo.xlsx", fim="2026-10", meses=36)
    wb = openpyxl.load_workbook(caminho)
    assert [a.nome for a in ABAS] == [n for n in wb.sheetnames if n not in ("Instrucoes", "_listas")]

    fat = wb["4_Faturamento"]
    meses = [fat.cell(row=i, column=1).value for i in range(5, 5 + 36)]
    assert meses[0] == "2023-11" and meses[-1] == "2026-10"
    assert fat["F5"].value == "=SUM(B5:E5)"

    grupo = wb["1_Grupo"]
    assert grupo["A4"].value == "CNPJ"
    assert len(grupo.data_validations.dataValidation) == 1  # lista de regime tributário
