"""DRE gerencial em Excel — planilhas sintéticas no formato das PMEs (sem dados de clientes)."""

from datetime import date

import openpyxl
from openpyxl.styles import Font

from captacao.parsers.gerencial_xlsx import Categoria, eh_gerencial, ler_gerencial, salvar_mapa
from captacao.schemas import DREAnual, Metodo, Proveniencia
from tarantino.case import _comparar_contabil

MESES = ["JANEIRO", "FEVEREIRO", "MARÇO", "ABRIL", "MAIO", "JUNHO", "JULHO", "AGOSTO", "SETEMBRO",
         "OUTUBRO", "NOVEMBRO", "DEZEMBRO"]


def _largo(caminho, meses_com_dados=12, emprestimo_no_grupo=False, conta_estranha=None):
    """Modelo 'DRE GERENCIAL 2025': contas na coluna B, meses em C..N, acumulado em P."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "DRE"
    ws["B2"] = "DRE GERENCIAL 2025"
    for j, m in enumerate(MESES, start=3):
        ws.cell(row=4, column=j, value=m)
    ws.cell(row=4, column=16, value="ACUMUL.")
    ws.cell(row=4, column=17, value="MÉDIA")

    linhas = [  # (rótulo, negrito, valor mensal)
        ("Entradas Totais", True, 100_000), ("Saídas Totais", True, 80_000), ("Resultado Líquido", True, 20_000),
        None,
        ("Receita Operacional Bruta", True, 100_000), ("Venda de Peças", False, 30_000), ("Novos", False, 70_000),
        None,
        ("Deduções", True, 6_000), ("Tributos", False, 6_000),
        None,
        ("Receita Operacional Líquida", True, 94_000),
        None,
        ("Despesas Variáveis", True, 40_000), ("Produção", False, 38_000), ("Frete", False, 2_000),
        None,
        ("Despesas Fixas", True, 30_000), ("Pessoal", False, 25_000), ("Administrativas", False, 5_000),
        None,
        ("Resultado Operacional", True, 24_000), ("% Resultado Operacional", True, 0.24),
        None,
        ("Outras Entradas", True, 0), ("Empréstimo", False, 0),
        None,
        ("Outras Saídas", True, 4_000), ("Juros de Empréstimos", False, 3_000), ("Investimento", False, 1_000),
    ]
    if conta_estranha:
        linhas.insert(4, (conta_estranha, False, 500))
    r = 6
    for item in linhas:
        if item is None:
            r += 1
            continue
        rotulo, negrito, valor = item
        ws.cell(row=r, column=2, value=rotulo).font = Font(bold=negrito)
        for j in range(3, 15):
            mes = j - 2
            v = valor if mes <= meses_com_dados else 0
            if rotulo == "Empréstimo" and mes == 6:
                v = 500_000
            if rotulo == "Outras Entradas" and mes == 6 and emprestimo_no_grupo:
                v = 500_000
            ws.cell(row=r, column=j, value=v)
        total = sum(ws.cell(row=r, column=j).value for j in range(3, 15))
        if rotulo == "Resultado Líquido":
            total += 500_000  # erro típico: o acumulado soma o empréstimo como resultado
        ws.cell(row=r, column=16, value=total)
        ws.cell(row=r, column=17, value=total / 12)
        r += 1
    wb.save(caminho)
    return caminho


def test_dre_gerencial_largo_classifica_e_separa_operacao(tmp_path):
    d = ler_gerencial(_largo(tmp_path / "DRE 2025.xlsx"))
    assert d.competencias[0] == "2025-01" and d.competencias[-1] == "2025-12"
    cat = {l.rotulo: (l.categoria, l.origem) for l in d.linhas}
    assert cat["Novos"] == (Categoria.RECEITA_OPERACIONAL, "grupo")  # herda do grupo
    assert cat["Produção"][0] == Categoria.CUSTO_VARIAVEL
    assert cat["Empréstimo"][0] == Categoria.EMPRESTIMO_RECEBIDO
    assert cat["Juros de Empréstimos"][0] == Categoria.DESPESA_FINANCEIRA
    assert cat["Investimento"][0] == Categoria.INVESTIMENTO
    assert cat["Receita Operacional Líquida"][0] == Categoria.SUBTOTAL
    assert cat["% Resultado Operacional"][0] == Categoria.IGNORAR
    assert d.pendentes() == []

    ano = d.resumo_anual()[2025]
    assert ano["receita_operacional"] == 1_200_000 and ano["deducoes"] == -72_000
    assert ano["custo_variavel"] == -480_000 and ano["despesa_pessoal"] == -300_000
    assert ano["resultado_operacional"] == 288_000  # sem juros, investimento nem empréstimo
    assert ano["emprestimo_recebido"] == 500_000 and ano["investimento"] == -12_000
    assert len(d.gerencial_mensal()) == 12 and d.gerencial_mensal()[0].receita == 100_000

    texto = " | ".join(d.alertas)
    assert "'Outras Entradas': o valor do grupo não bate com a soma das contas em 1 mês(es) (2025-06)" in texto
    assert "'Resultado Líquido' (subtotal): total do ano na planilha R$ 740.000,00" in texto


def test_meses_futuros_zerados_nao_contam(tmp_path):
    d = ler_gerencial(_largo(tmp_path / "DRE 2026.xlsx", meses_com_dados=9, emprestimo_no_grupo=True))
    assert d.receita_mensal() and max(d.receita_mensal()) == "2025-09"


def test_conta_desconhecida_fica_pendente_e_mapa_resolve(tmp_path):
    arq = _largo(tmp_path / "DRE.xlsx", conta_estranha="Xpto Diversos")
    d = ler_gerencial(arq)
    assert d.pendentes() == ["Xpto Diversos"]
    assert any("1 conta(s) sem categoria: Xpto Diversos" in a for a in d.alertas)

    mapa = tmp_path / "mapa_gerencial.json"
    salvar_mapa(mapa, {"Xpto Diversos": "despesa_administrativa"})
    import json
    d2 = ler_gerencial(arq, json.loads(mapa.read_text(encoding="utf-8")))
    linha = next(l for l in d2.linhas if l.rotulo == "Xpto Diversos")
    assert (linha.categoria, linha.origem) == (Categoria.DESPESA_ADMINISTRATIVA, "mapa") and d2.pendentes() == []


def test_formato_longo_com_blocos(tmp_path):
    """Planilha improvisada: datas descendo na coluna A, contas no cabeçalho de cada bloco."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws["A1"], ws["A2"], ws["B2"], ws["C2"] = "Faturamento", "Mês", "Peças", "Novos"
    for i in range(12):
        ws.cell(row=3 + i, column=1, value=date(2023, i + 1, 1 + i))  # dias variados, como no original
        ws.cell(row=3 + i, column=2, value=10_000)
        ws.cell(row=3 + i, column=3, value=50_000)
    ws["A17"], ws["A18"], ws["B18"], ws["C18"] = "Custos/Despesas", "Mês", "Matéria Prima", "Pessoal"
    for i in range(12):
        ws.cell(row=19 + i, column=1, value=date(2023, i + 1, 1))
        ws.cell(row=19 + i, column=2, value=25_000)
        ws.cell(row=19 + i, column=3, value=15_000)
    arq = tmp_path / "DRE 2023.xlsx"
    wb.save(arq)

    assert eh_gerencial(arq)
    d = ler_gerencial(arq)
    assert d.alertas == []  # títulos de bloco não são conferidos como grupo
    ano = d.resumo_anual()[2023]
    assert ano["receita_operacional"] == 720_000  # Peças e Novos herdam "Faturamento"
    assert ano["custo_variavel"] == -300_000 and ano["despesa_pessoal"] == -180_000
    assert ano["resultado_operacional"] == 240_000


def test_gerencial_acima_do_contabil_gera_alerta():
    receita = {f"2025-{m:02d}": 1_000_000.0 for m in range(1, 13)}
    dre = DREAnual(cnpj="1", exercicio=2025, receita_bruta=9_000_000,
                   proveniencia=Proveniencia(arquivo="DRE.pdf", metodo=Metodo.PARSER))
    (alerta,) = _comparar_contabil(receita, [dre])
    assert "gerencial R$ 12.000.000 × contábil R$ 9.000.000 (+33%)" in alerta and "sem nota" in alerta
