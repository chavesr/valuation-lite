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
