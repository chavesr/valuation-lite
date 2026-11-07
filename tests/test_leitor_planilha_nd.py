import openpyxl

from captacao.leitor_planilha_nd import ler_planilha_nd
from captacao.planilha_nd import gerar_modelo

A, B = "11.111.111/0001-11", "22.222.222/0001-22"


def _preencher(caminho, *, trocar_cabecalho_b=True, participacao_b=0.5):
    wb = openpyxl.load_workbook(caminho)
    g = wb["1_Grupo"]
    for i, linha in enumerate([[A, "Fábrica Teste Ltda", "Fábrica", "Simples Nacional", "fábrica", 1998],
                               [B, "Peças Teste Ltda", "Peças", "Simples Nacional", "revenda de peças", "2015"]],
                              start=5):
        for j, v in enumerate(linha, start=1):
            g.cell(row=i, column=j, value=v)

    s = wb["2_Socios"]
    for i, linha in enumerate([["Sócio 1", 0.5, "A e B", "Diretor", 50, "15.000,00", 8000, "Não"],
                               ["Sócio 2", participacao_b, "A", "Comercial", "40", 10000, None, "Sim, sem prazo"]],
                              start=5):
        for j, v in enumerate(linha, start=1):
            s.cell(row=i, column=j, value=v)

    d = wb["6_Dividas"]
    for j, v in enumerate([A, "Banco X", "Empréstimo bancário", 500000, 320000, 15000, 2, 24, "aval"], start=1):
        d.cell(row=5, column=j, value=v)

    f = wb["4_Faturamento"]
    f["B4"] = A
    if trocar_cabecalho_b:
        f["C4"] = B
    for i in range(5, 5 + 24):  # 24 meses de 2024-11 a 2026-10
        f.cell(row=i, column=2, value=300_000)
        f.cell(row=i, column=3, value=150_000)
    f.cell(row=10, column=3).value = None  # buraco no meio do período no CNPJ B
    f.cell(row=12, column=7, value="mês da reforma")
    wb.save(caminho)
    return caminho


def test_le_planilha_preenchida(tmp_path):
    arq = _preencher(gerar_modelo(tmp_path / "nd.xlsx", fim="2026-10", meses=24))
    p = ler_planilha_nd(arq)

    assert p.cnpjs_grupo() == ["11111111000111", "22222222000122"]
    assert p.abas["1_Grupo"][1]["ano_de_abertura"] == 2015
    socio = p.abas["2_Socios"][0]
    assert socio["pct_de_participacao"] == 0.5 and socio["pro_labore_mensal_r"] == 15_000
    divida = p.abas["6_Dividas"][0]
    assert divida["taxa_de_juros_pct_ao_mes"] == 0.02  # digitado '2' numa célula de %
    assert divida["saldo_devedor_hoje_r"] == 320_000

    totais = p.faturamento_mensal_total()
    assert len(totais) == 24 and totais["2026-10"] == 450_000 and totais["2025-04"] == 300_000
    assert p.observacoes_faturamento == {"2025-06": "mês da reforma"}
    assert len(p.gerencial()) == 24 and p.gerencial()[0].proveniencia.localizacao == "4_Faturamento"

    texto = " | ".join(p.alertas)
    assert "22222222000122 sem valor em 1 mês" in texto
    assert "possível divisão para ficar no Simples" in texto  # 12 × 450 mil = 5,4 mi em 2 CNPJs do Simples
    assert "participações" not in texto


def test_alertas_de_preenchimento(tmp_path):
    arq = _preencher(gerar_modelo(tmp_path / "nd.xlsx", fim="2026-10", meses=24),
                     trocar_cabecalho_b=False, participacao_b=0.3)
    wb = openpyxl.load_workbook(arq)
    wb["1_Grupo"]["D5"] = "Simples"  # fora da lista
    wb["1_Grupo"]["A5"] = "123"  # CNPJ incompleto
    del wb["9_Ajustes"]
    wb.save(arq)

    texto = " | ".join(ler_planilha_nd(arq).alertas)
    assert "'CNPJ empresa 2' tem valores mas o cabeçalho não foi trocado" in texto
    assert "participações somam 80.0%" in texto
    assert "valor fora da lista ('Simples')" in texto
    assert "documento com 3 dígitos" in texto
    assert "Aba 9_Ajustes não encontrada" in texto
    assert "CNPJ 11111111000111 tem faturamento mas não está na aba 1_Grupo" in texto


def test_modelo_em_branco_nao_quebra(tmp_path):
    p = ler_planilha_nd(gerar_modelo(tmp_path / "nd.xlsx", fim="2026-10"))
    assert p.faturamento == [] and all(v == [] for v in p.abas.values())
    assert p.alertas == ["1_Grupo vazia: o grupo econômico não foi informado."]
