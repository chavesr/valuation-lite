"""Relatórios de ERP, posições de empréstimo e resumo da folha — dados sintéticos nos layouts reais."""

from datetime import date

import openpyxl

from captacao.parsers.emprestimos_pdf import consolidar_dividas, identificar, ler_emprestimos
from captacao.parsers.folha_pdf import ler_resumo_folha
from captacao.parsers.relatorios_erp import ler_relatorio_erp
from captacao.schemas import BalancoAnual, Metodo, Proveniencia
from tarantino.case import _alertas_dividas


def _xlsx(caminho, abas):
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for nome, linhas in abas.items():
        ws = wb.create_sheet(nome)
        for l in linhas:
            ws.append(l)
    wb.save(caminho)
    return caminho


def test_relatorios_erp_pelo_cabecalho(tmp_path):
    receber = ler_relatorio_erp(_xlsx(tmp_path / "Contas receber Matriz 0726.xlsx", {"Contas a receber": [
        ["Vencimento", "Cliente", "Histórico", "Nº banco", "Nº documento", "Data de emissão", "Valor", "Saldo", "Recebido"],
        ["05/07/2026", "CLIENTE A", "NF 1", "", "1/01", "20/06/2026", 1000, 1000, 0],
        ["10/08/2026", "CLIENTE B", "NF 2", "", "2/01", "01/07/2026", 2000, 2000, 0],
        ["15/06/2026", "CLIENTE C", "NF 3", "", "3/01", "01/06/2026", 500, 0, 500],
    ]}))
    assert (receber.tipo, receber.estabelecimento, receber.competencia) == ("contas_receber", "Matriz", "2026-07")
    assert receber.saldo_aberto() == 3000
    assert receber.aging(date(2026, 7, 1)) == {"vencido": 0.0, "0-30": 1000.0, "31-60": 2000.0, "61-90": 0.0, "91+": 0.0}

    pagar = ler_relatorio_erp(_xlsx(tmp_path / "Contas pagas.xlsx", {"Contas a pagar": [
        ["Vencimento", "Fornecedor", "Histórico", "Nº documento", "Data de emissão", "Valor", "Saldo", "Pago", "Empresa",
         "", "Fornecedor", "Categoria"],  # tabela auxiliar repetindo 'Fornecedor' ao lado
        ["30/06/2026", "Documento de Arrecadação", "O valor será atualizado a cada mês.", "REC. DIVITA ATIVA",
         "29/06/2026", 7185.79, 0, 7185.79, "Matriz", "", "OUTRO", "Impostos"],
        ["30/06/2026", "FORNECEDOR X", "NF 99", "99", "01/06/2026", 1200, 0, 1200, "Matriz", "", "", ""],
    ]}))
    assert pagar.tipo == "contas_pagar" and [t.contraparte for t in pagar.titulos] == ["Documento de Arrecadação", "FORNECEDOR X"]
    assert any("DIVITA ATIVA" in a for a in pagar.alertas)

    fat = ler_relatorio_erp(_xlsx(tmp_path / "Faturamento Matriz fulfillment 0726.xlsx", {
        "Vendas": [["Produto", "Código (SKU)", "Quantidade", "Valor", "Frete", "Total"], ["BOMBA X", "B1", 2, 900, 10, 910],
                   ["VALVULA Y", "V1", 1, 300, 0, 300]],
        "Devoluções": [["Produto", "Código (SKU)", "Quantidade", "Valor", "Acréscimos", "Total"], ["BOMBA X", "B1", 1, 450, 0, 450]],
    }))
    assert (fat.tipo, fat.fulfillment, fat.vendas_total, fat.devolucoes_total) == ("faturamento_produto", True, 1210, 450)

    est = ler_relatorio_erp(_xlsx(tmp_path / "Estoque Filial com custo.xlsx", {"Estoque": [
        ["Código (SKU)", "Produto", "NCM", "Quantidade", "Unidade", "Valor unitário", "Valor total"],
        ["B1", "BOMBA X", "8413", 10, "Un", 300, 3000], ["V1", "VALVULA Y", "8481", -2, "Un", 50, 0],
        ["K1", "KIT Z", "7307", 5, "Un", 0, 0],
    ]}))
    assert (est.tipo, est.estoque_total, est.estoque_negativos, est.estoque_sem_custo) == ("estoque", 3000, 1, 1)

    pj = ler_relatorio_erp(_xlsx(tmp_path / "Salários PJ.xlsx", {"Planilha1": [
        ["Nome", "Valor médio", "Serviço prestado"], ["PESSOA 1", 10000, "Compras"], ["PESSOA 2", 5000, "RH"], ["PESSOA 3", None, "TI"],
    ]}))
    assert (pj.tipo, pj.pj_quantidade, pj.pj_total_mensal) == ("colaboradores_pj", 2, 15000)


BB_CONSOLIDADO = """20/08/2026 12:06:52
Extrato de empréstimos, extrato de operação de crédito
Conta 12345-6 EMPRESA TESTE
BB CAPITAL DE GIRO DIGITAL
Operação Situação Data contratação Data fim Próximo débito Saldo devedor
111111111 NORMAL 06/12/2024 15/12/2028 15/09/2026 1.036.371,38
BB CAPITAL DE GIRO PEAC FGI
Operação Situação Data contratação Data fim Próximo débito Saldo devedor
222222222 NORMAL 05/02/2025 05/01/2030 08/09/2026 863.152,43
"""

SICREDI_DESCRITIVO = """Data de Emissão: 07/10/2026
Documento Descritivo de Crédito
Código do contrato / OID: Modalidade Bacen do Contrato:
C600000001 / 74312886 0216 - CAPITAL DE GIRO COM PRAZO DE
Taxa de Juros Efetiva % a.a.: Taxa de Juros Anual % a.a.:
10,03 9,60
Tipo de Taxa: Indexador:
Pós-fixado CDI
Total de Parcelas da Operação: Parcelas Remanescentes da Operação:
60 59
Data da Liberação da Operação: Data do Último Vencimento da Operação:
14/08/2026 14/08/2031
Data da Informação do Saldo Devedor: Valor do Saldo Devedor Atualizado:
07/10/2026 R$ 1.544.940,25
"""

SICREDI_CONSULTA = """06/08/2026, 14:27 Internet Banking Sicredi
Cooperativa: 0101 Conta Corrente: 98765-4 Impresso em 06/08/2026 14:26:43
Consulta Empréstimos
Nro do Título C500000002
Situação NORMAL
Data de Liberação 30/06/2025
Valor Liberado (R$) 450,205.92
Taxa de Juros ao Mês 2.31 %
Correção Monetária Mensal NULA
Saldo Devedor (R$) 300,137.28
Total de Parcelas 36
Parcelas Pagas 12
"""


def test_emprestimos_tres_formatos_e_consolidacao():
    bb = ler_emprestimos("BB_Consolidado.pdf", texto=BB_CONSOLIDADO)
    assert identificar(BB_CONSOLIDADO) == "bb_consolidado"
    assert [(d.contrato, d.saldo_devedor, d.modalidade) for d in bb] == [
        ("111111111", 1_036_371.38, "BB CAPITAL DE GIRO DIGITAL"), ("222222222", 863_152.43, "BB CAPITAL DE GIRO PEAC FGI")]
    (desc,) = ler_emprestimos("Sicredi_KGiro.pdf", texto=SICREDI_DESCRITIVO)
    assert (desc.contrato, desc.saldo_devedor, desc.taxa_aa, desc.parcelas_restantes, desc.indexador) == \
        ("C600000001", 1_544_940.25, 10.03, 59, "CDI")
    assert desc.vencimento_final == date(2031, 8, 14) and desc.data_posicao == date(2026, 10, 7)
    (cons,) = ler_emprestimos("Sicredi_C5.pdf", texto=SICREDI_CONSULTA)
    assert (cons.saldo_devedor, cons.valor_contratado, cons.taxa_am, cons.parcelas_restantes) == (300_137.28, 450_205.92, 2.31, 24)

    # mesmo contrato em dois documentos: fica a posição mais recente
    antigo = bb[0].model_copy(update={"saldo_devedor": 1_084_062.62, "data_posicao": date(2026, 7, 31)})
    todos = consolidar_dividas(bb + [antigo, desc, cons])
    assert len(todos) == 4 and next(d for d in todos if d.contrato == "111111111").saldo_devedor == 1_036_371.38


def test_divida_fora_do_balanco_gera_alerta():
    bb = ler_emprestimos("BB.pdf", texto=BB_CONSOLIDADO)
    bp = BalancoAnual(cnpj="1", exercicio=2026, data_base=date(2026, 6, 30), emprestimos_lp=500_000,
                      proveniencia=Proveniencia(arquivo="bp", metodo=Metodo.PARSER))
    alertas = _alertas_dividas(bb, [bp])
    assert alertas[0].startswith("Dívida bancária: R$ 1.899.524 em 2 contrato(s) (BB R$ 1.899.524")
    assert any("Balanço dessa data registra R$ 500.000" in a for a in alertas)


def test_resumo_da_folha_so_totais():
    pagina = """Empresa: EMPRESA TESTE Página: 1/2
CNPJ: 11.222.333/0001-81 Emissão: 06/10/2026
Competência: 01/2026
RESUMO DA FOLHA
Rubrica Nome da Rubrica Nº Empregados/Contribuintes Valor informado Valor Calculado
PROVENTOS
1 HORAS NORMAIS 16 3.219,33 39.341,07
100 PRO-LABORE 1 220,00 5.000,00
Total: 44.341,07
DESCONTOS
998 I.N.S.S. 16 137,24 4.459,52
Total: 4.459,52
INFORMATIVA
996 F.G.T.S DO MES 16 0,00 3.942,18*
Segurados: 5.009,52
Total INSS: 20.201,59
"""
    (f,) = ler_resumo_folha("Resumo Mensal.pdf", paginas=[pagina, "Página: 2/2 sem proventos"])
    assert (f.cnpj, f.competencia, f.empregados, f.proventos, f.pro_labore, f.fgts) == \
        ("11222333000181", "2026-01", 16, 44_341.07, 5_000.0, 3_942.18)
    assert f.custo_empresa == round(44_341.07 + 3_942.18 + 20_201.59 - 5_009.52, 2)
