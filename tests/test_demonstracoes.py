"""Leitor de DRE/Balanço em PDF — linhas sintéticas que reproduzem os layouts reais (sem dados de clientes).

Cada linha é (x0, y, texto), como sai do pdfplumber: x0 = indentação, y = centro vertical da linha.
"""

import pytest

from captacao.parsers.demonstracoes_pdf import DemonstracaoNaoLida, ler_demonstracao
from captacao.schemas import DREAnual, Metodo, Proveniencia
from tarantino.case import _consolidar

CAB_SPED = [
    (41, 20, "DEMONSTRAÇÃO DE RESULTADO DO EXERCÍCIO"),
    (41, 35, "Entidade: EMPRESA TESTE INDUSTRIA LTDA"),
    (41, 50, "Período da Escrituração: 01/01/2025 a 31/12/2025 CNPJ: 12.345.678/0001-90"),
    (41, 65, "Número de Ordem do Livro: 3"),
    (41, 80, "Período Selecionado: 01 de janeiro de 2025 a 31 de dezembro de 2025"),
    (41, 95, "Descrição Nota Saldo anterior Saldo atual"),
]


def _dre_sped():
    y = iter(range(110, 2000, 16))
    linhas = list(CAB_SPED)

    def conta(x, texto):
        linhas.append((x, next(y), texto))

    conta(54.3, "RECEITA BRUTA R$ 1.000.000,00 R$ 1.200.000,00")
    conta(63.2, "VENDA DE PRODUTOS R$ 1.000.000,00 R$ 1.200.000,00")
    conta(54.3, "(-) DEDUÇÕES R$ (100.000,00) R$ (150.000,00)")
    # descrição quebrada em 3 linhas, com os valores na linha do meio (como no SPED real, a conta
    # ocupa mais altura: a linha de cima fica ~9 pt acima dos valores e ~20 pt abaixo da conta anterior)
    base = next(y) + 13
    next(y)
    linhas += [(63.2, base - 9, "(-) (-) DEVOLUÇÃO DE VENDA DE"),
               (41.0, base, "PRODUTOS FABRICADOS NO R$ (20.000,00) R$ (30.000,00)"),
               (41.0, base + 9, "PERÍODO")]
    # descrição quebrada em 2 linhas, valores numa linha só deles (fora de ordem no PDF)
    base = next(y)
    linhas += [(383.2, base, "R$ (80.000,00) R$ (120.000,00)"),
               (63.2, base - 4, "(-) (-) SIMPLES"), (41.0, base + 5, "NACIONAL")]
    conta(54.3, "RECEITA LÍQUIDA R$ 900.000,00 R$ 1.050.000,00")
    conta(54.3, "(-) CMV R$ (400.000,00) R$ (450.000,00)")
    conta(54.3, "LUCRO BRUTO R$ 500.000,00 R$ 600.000,00")
    conta(54.3, "(-) DESPESAS OPERACIONAIS R$ (300.000,00) R$ (380.000,00)")
    conta(63.2, "(-) DESPESAS ADMINISTRATIVAS R$ (300.000,00) R$ (380.000,00)")
    conta(72.1, "(-) SALÁRIOS E ORDENADOS R$ (150.000,00) R$ (180.000,00)")
    conta(72.1, "(-) PRÓ-LABORE R$ (24.000,00) R$ (36.000,00)")
    conta(72.1, "(-) FGTS R$ (12.000,00) R$ (14.400,00)")
    conta(72.1, "(-) ALUGUÉIS R$ (60.000,00) R$ (60.000,00)")
    conta(72.1, "(-) DEPRECIAÇÃO R$ (10.000,00) R$ (12.000,00)")
    conta(72.1, "(-) JUROS E COMISSÕES BANCÁRIAS R$ (44.000,00) R$ (77.600,00)")
    conta(63.2, "RECEITAS FINANCEIRAS R$ 2.000,00 R$ 3.000,00")
    conta(54.3, "RESULTADO ANTES DO IR E CSL R$ 202.000,00 R$ 223.000,00")
    conta(54.3, "(-) PROVISÕES PARA IR E CSL R$ (0,00) R$ (20.000,00)")
    conta(54.3, "LUCRO LÍQUIDO DO EXERCÍCIO R$ 202.000,00 R$ 203.000,00")
    linhas.append((41, next(y), "Este documento é parte integrante de escrituração cuja autenticação se comprova"))
    linhas.append((41, next(y), "02.55.53.BA.28.F0.E9.BD.AF.0A.2B.A1.73.37.3E.BE.24.9C.65.42-4, nos termos do Decreto"))
    return linhas


def test_dre_sped_com_quebras_e_comparativo():
    d = ler_demonstracao("DRE ECD 2025.pdf", linhas=_dre_sped())
    assert (d.tipo, d.layout, d.cnpj) == ("dre", "sped", "12345678000190")
    assert d.alertas == []  # bruta + deduções = líquida; líquida + CMV = lucro bruto; deduções = soma
    nomes = [c.nome for c in d.contas[1].filhos]
    assert nomes == ["(-) (-) DEVOLUÇÃO DE VENDA DE PRODUTOS FABRICADOS NO PERÍODO", "(-) (-) SIMPLES NACIONAL"]

    atual, anterior = d.dres
    assert (atual.exercicio, atual.proveniencia.localizacao, atual.proveniencia.confianca) == (2025, "saldo atual", "alta")
    assert (anterior.exercicio, anterior.proveniencia.confianca) == (2024, "media")
    assert atual.receita_bruta == 1_200_000 and atual.deducoes == -150_000 and atual.receita_liquida == 1_050_000
    assert atual.custo_vendas == -450_000 and atual.despesas_administrativas == -380_000
    assert atual.despesas_pessoal == -194_400 and atual.pro_labore == -36_000  # salários + FGTS, sem pró-labore
    assert atual.aluguel == -60_000 and atual.depreciacao_amortizacao == -12_000
    assert atual.resultado_financeiro == -74_600  # 3.000 − 77.600
    assert atual.ir_csll == -20_000 and atual.lucro_liquido == 203_000
    assert anterior.lucro_liquido == 202_000 and anterior.receita_bruta == 1_000_000


def _balanco_sistema(pl="912.864,86C"):
    linhas = [(40, 10, "Empresa: COMERCIO TESTE LTDA Folha: 0001"), (40, 20, "C.N.P.J.: 11.222.333/0001-81"),
              (40, 30, "Balanço encerrado em: 31/12/2024"), (40, 40, "BALANÇO PATRIMONIAL"),
              (40, 50, "Descrição Saldo Atual")]
    contas = [
        (47.5, "ATIVO 1.258.628,09D"),
        (54.6, "ATIVO CIRCULANTE 292.890,99D"),
        (61.7, "DISPONÍVEL 126.885,35D"), (68.9, "BANCOS CONTA MOVIMENTO 126.885,35D"),
        (61.7, "CLIENTES 2.916,25D"), (68.9, "DUPLICATAS A RECEBER 2.916,25D"),
        (61.7, "ESTOQUE 163.089,39D"), (68.9, "MERCADORIAS PARA REVENDA 163.089,39D"),
        (54.6, "ATIVO NÃO-CIRCULANTE 965.737,10D"),
        (61.7, "ATIVO REALIZÁVEL A LONGO PRAZO 638.863,83D"), (68.9, "OUTROS CRÉDITOS 638.863,83D"),
        (61.7, "IMOBILIZADO 326.873,27D"),
        (68.9, "MÁQUINAS E EQUIPAMENTOS 340.906,38D"),
        (68.9, "(-) DEPRECIAÇÕES, AMORT. E EXAUS. ACUMUL 14.033,11C"),
        (47.5, "PASSIVO 1.258.628,09C"),
        (54.6, "PASSIVO CIRCULANTE 256.216,56C"),
        (61.7, "EMPRÉSTIMOS E FINANCIAMENTOS 67.160,01C"), (68.9, "EMPRESTIMO SICOOB 67.160,01C"),
        (61.7, "FORNECEDORES 173.908,78C"), (68.9, "FORNECEDORES 173.908,78C"),
        (61.7, "OBRIGAÇÕES TRIBUTÁRIAS 12.357,17C"), (68.9, "SIMPLES NACIONAL A RECOLHER 12.357,17C"),
        (61.7, "OBRIGAÇÕES TRABALHISTA E PREVIDENCIÁRIA 2.790,60C"), (68.9, "FGTS A RECOLHER 2.790,60C"),
        (54.6, "PASSIVO NÃO-CIRCULANTE 89.546,67C"),
        (61.7, "EMPRÉSTIMOS E FINANCIAMENTOS 89.546,67C"), (68.9, "EMPRESTIMO SICOOB 89.546,67C"),
        (54.6, f"PATRIMÔNIO LÍQUIDO {pl}"),  # no layout real o PL fica dentro do PASSIVO
        (61.7, f"LUCROS ACUMULADOS {pl}"),
    ]
    linhas += [(x, 60 + 10.3 * i, t) for i, (x, t) in enumerate(contas)]
    linhas += [(40, 400, "_______________________ _______________________"), (40, 410, "CPF: 000.000.000-00")]
    return linhas


def test_balanco_sistema_debito_credito():
    d = ler_demonstracao("BP 2024.pdf", linhas=_balanco_sistema())
    assert (d.tipo, d.layout, d.data_fim.isoformat()) == ("balanco", "sistema", "2024-12-31")
    assert d.alertas == []  # todos os grupos somam e Ativo = Passivo + PL
    (bp,) = d.balancos
    assert bp.imobilizado_liquido == 326_873.27  # líquido da depreciação (C dentro do ativo = negativo)
    assert bp.caixa_aplicacoes == 126_885.35 and bp.contas_receber == 2_916.25 and bp.estoques == 163_089.39
    assert bp.fornecedores == 173_908.78 and bp.obrigacoes_fiscais == 12_357.17
    assert bp.obrigacoes_trabalhistas == 2_790.60
    assert bp.emprestimos_cp == 67_160.01 and bp.emprestimos_lp == 89_546.67
    assert bp.patrimonio_liquido == 912_864.86
    depreciacao = d.contas[0].filhos[1].filhos[1].filhos[1]
    assert depreciacao.atual == -14_033.11


def test_balanco_que_nao_fecha_gera_alerta():
    d = ler_demonstracao("BP.pdf", linhas=_balanco_sistema(pl="900.000,00C"))
    assert any(a.startswith("Soma não confere — PASSIVO:") for a in d.alertas)


def test_pdf_escaneado_e_documento_estranho():
    with pytest.raises(DemonstracaoNaoLida, match="escaneado"):
        ler_demonstracao("scan.pdf", linhas=[])
    with pytest.raises(DemonstracaoNaoLida, match="não parece"):
        ler_demonstracao("x.pdf", linhas=[(40, 10, "Extrato de conta corrente " * 5)])


def test_consolidar_detecta_contabilidade_reapresentada():
    def dre(lucro, arquivo, onde):
        return DREAnual(cnpj="1", exercicio=2024, lucro_liquido=lucro, receita_bruta=7_800_000.00,
                        proveniencia=Proveniencia(arquivo=arquivo, localizacao=onde, metodo=Metodo.PARSER))

    alertas = []
    saida = _consolidar([dre(20_000.00, "DRE 2025.pdf", "comparativo (saldo anterior)"),
                         dre(3_100_000.00, "DRE 2024.pdf", "saldo atual")], "dre", alertas)
    assert len(saida) == 1 and saida[0].lucro_liquido == 20_000.00  # vale a versão reapresentada (livro mais recente)
    assert len(alertas) == 1 and "reapresentada" in alertas[0] and "3.100.000,00" in alertas[0]


def _linhas(textos, x=50.0):
    return [(x if not isinstance(t, tuple) else t[0], i * 14.0, t if not isinstance(t, tuple) else t[1])
            for i, t in enumerate(textos)]


def test_layout_classificacao_com_dc_e_duas_colunas():
    from captacao.parsers.demonstracoes_pdf import ler_demonstracao

    dre = ler_demonstracao("dre_ficticia.pdf", _linhas([
        "EMPRESA FICTICIA LTDA Página: 1", "CNPJ : 11.222.333/0001-81",
        "Demonstração do Resultado de 01/01/2025 a 31/12/2025", "Código Classificação Nome movimento",
        "1 01 RECEITAS 1.000.000,00C00,,", "2 01.1 RECEITA OPERACIONAL BRUTA 1.000.000,00C",
        "3 01.1.01 Venda de Produtos 1.000.000,00C", "14 02 DEDUÇÕES DAS RECEITAS 100.000,00D",
        "15 02.1 Simples Nacional 100.000,00D", "20 03 RECEITA LÍQUIDA 900.000,00C",
        "30 04 CUSTOS E DESPESAS 600.000,00D", "31 04.1 CUSTO DOS PRODUTOS VENDIDOS 400.000,00D",
        "32 04.2 DESPESAS ADMINISTRATIVAS 200.000,00D", "33 04.2.01 Salários 150.000,00D",
        "34 04.2.02 Aluguel 50.000,00D"]))
    assert dre.layout == "classificacao" and dre.data_fim.year == 2025 and dre.data_inicio.month == 1
    d = dre.dres[0]
    assert (d.receita_bruta, d.deducoes, d.receita_liquida) == (1_000_000, -100_000, 900_000)
    assert d.custo_vendas == -400_000 and d.aluguel == -50_000 and d.despesas_pessoal == -150_000

    bp = ler_demonstracao("bp_ficticio.pdf", _linhas([
        "BALANÇO PATRIMONIAL DE 01/01/2025 A 31/12/2025 Página: 1", "CNPJ:11.222.333/0001-81",
        "Código Classificação Nome Saldo anterior Saldo atual",
        "1 01 ATIVO 500,00D 900,00D", "2 01.1 ATIVO CIRCULANTE 500,00D 900,00D",
        "3 01.1.1 DISPONIBILIDADES 100,00D 300,00D", "4 01.1.2 ESTOQUES 400,00D 600,00D",
        "10 02 PASSIVO 500,00C 900,00C", "11 02.1 PASSIVO CIRCULANTE 200,00C 300,00C",
        "12 02.1.1 FORNECEDORES 200,00C 300,00C", "13 02.3 PATRIMÔNIO LÍQUIDO 300,00C 600,00C",
        "14 02.3.1 CAPITAL 300,00C 600,00C"]))
    atual, anterior = bp.balancos
    assert (atual.exercicio, atual.caixa_aplicacoes, atual.estoques, atual.fornecedores) == (2025, 300, 600, 300)
    assert (anterior.exercicio, anterior.caixa_aplicacoes) == (2024, 100)


def test_dre_com_gastos_impressos_positivos_e_sem_indentacao():
    from captacao.parsers.demonstracoes_pdf import ler_demonstracao

    doc = ler_demonstracao("dre_gerencial.pdf", _linhas([
        "999 - EMPRESA FICTICIA Página: 1", "Contabilidade DRE Data: 01/02/2026",
        "Consolidação: Empresa Grau: 5 Período: 01/2025 a 12/2025",
        "RECEITA OPERACIONAL BRUTA 1.000.000,00", "Venda a Vista de Serviços 1.000.000,00",
        "DEDUÇÕES DA RECEITA BRUTA 60.000,00", "Imposto Simples 60.000,00",
        "RECEITA LÍQUIDA 940.000,00", "CUSTOS 300.000,00", "Compras de Mercadorias 300.500,00",
        "Desconto Obtido Comercial -500,00", "LUCRO BRUTO 640.000,00", "DESPESAS OPERACIONAIS 240.000,00",
        "Salarios e Ordenados 200.000,00", "F.G.T.S. 16.000,00", "Material de Limpeza 24.000,00",
        "LUCRO LÍQUIDO DO EXERCÍCIO 400.000,00"]))
    d = doc.dres[0]
    assert doc.data_fim.month == 12 and d.meses == 12
    assert (d.deducoes, d.custo_vendas, d.despesas_pessoal) == (-60_000, -300_000, -216_000)
    assert d.lucro_liquido == 400_000 and not [a for a in doc.alertas if "Soma" in a]


def test_balancete_gera_dre_e_balanco():
    from captacao.parsers.demonstracoes_pdf import identificar_tipo, ler_demonstracao

    linhas = _linhas([
        "Empresa: EMPRESA FICTICIA LTDA Folha: 0001", "C.N.P.J.: 11.222.333/0001-81",
        "Período: 01/01/2025 - 31/12/2025", "BALANCETE",
        "Código Classificação Descrição da conta Saldo Anterior Débito Crédito Saldo Atual",
        "1 1 ATIVO 100,00D 1.000,00 500,00 600,00D", "2 1.1 CIRCULANTE 100,00D 1.000,00 500,00 600,00D",
        "3 1.1.01 DISPONIBILIDADES 100,00D 1.000,00 500,00 600,00D",
        "10 2 PASSIVO 100,00C 0,00 500,00 600,00C", "11 2.1 CIRCULANTE 100,00C 0,00 100,00 200,00C",
        "12 2.1.01 FORNECEDORES 100,00C 0,00 100,00 200,00C", "13 2.4 PATRIMONIO LIQUIDO 0,00 0,00 400,00 400,00C",
        "20 3 CUSTOS E DESPESAS 0,00 700,00 0,00 700,00D", "21 3.2 DESPESAS OPERACIONAIS 0,00 700,00 0,00 700,00D",
        "22 3.2.02 DESPESAS ADMINISTRATIVAS 0,00 700,00 0,00 700,00D",
        "23 3.2.02.01.0017 SALARIOS 0,00 500,00 0,00 500,00D", "24 3.2.02.03.0002 ALUGUEL DE IMOVEIS 0,00 200,00 0,00 200,00D",
        "30 4 RECEITAS 0,00 100,00 1.100,00 1.000,00C", "31 4.1 RECEITAS OPERACIONAIS 0,00 100,00 1.100,00 1.000,00C",
        "32 4.1.01 RECEITA BRUTA DE VENDAS 0,00 0,00 1.100,00 1.100,00C",
        "33 4.1.02 (-) DEDUCOES DA RECEITA BRUTA 0,00 100,00 0,00 100,00D"])
    assert identificar_tipo("\n".join(t for *_, t in linhas)) == "balancete"
    doc = ler_demonstracao("balancete_inexistente.pdf", linhas)
    d, b = doc.dres[0], doc.balancos[0]
    assert (d.receita_bruta, d.deducoes, d.receita_liquida) == (1_100, -100, 1_000)
    assert (d.despesas_pessoal, d.aluguel, d.lucro_liquido) == (-500, -200, 300)
    assert (b.caixa_aplicacoes, b.fornecedores, b.patrimonio_liquido) == (600, 200, 400)
    assert any("sem conta de custo" in a for a in doc.alertas)
