"""Extrato do PGDAS-D, DEFIS e extrato bancário em planilha — textos sintéticos nos layouts oficiais."""

from datetime import date

import openpyxl
import pytest

from captacao.parsers.extrato_planilha import ler_extrato_planilha
from captacao.parsers.pgdas_pdf import SimplesNaoLido, identificar, ler_simples, pgdas_mensal
from tarantino.case import _resumo_simples

PGDAS = """Extrato do Simples Nacional
Gerado em 31/08/2026 12:04:16
Apurado em 18/08/2026 11:01:09
Apuração Original
1) Informações do Contribuinte
CNPJ Básico: 11.222.333 Nome Empresarial: EMPRESA TESTE LTDA
2) Informações da Apuração 11222333202607001
Período de Apuração (PA): 07/2026
2.1 Discriminativo de Receitas
Total de Receitas Brutas (R$) Mercado Interno Mercado Externo Total
Receita Bruta do PA (RPA) - Competência 140.000,00 10.000,00 150.000,00
Receita bruta acumulada nos doze meses anteriores ao PA
1.200.000,00 0,00 1.200.000,00
(RBT12)
Receita bruta acumulada no ano-calendário corrente (RBA) 900.000,00 0,00 900.000,00
Receita bruta acumulada no ano-calendário anterior
1.500.000,00 0,00 1.500.000,00
(RBAA)
2.2) Receitas Brutas Anteriores (R$)
2.2.1) Mercado Interno
05/2026 100.000,00 06/2026 110.000,00
2.2.2) Mercado Externo
05/2026 0,00 06/2026 5.000,00
2.3) Folha de Salários Anteriores (R$)
Nenhuma
3) Informações dos Estabelecimentos - valores referentes às Receitas Informadas
CNPJ Estabelecimento: 11.222.333/0001-81
Sublimite de Receita Anual (R$): 3.600.000,00 Impedido de recolher ICMS/ISS no DAS: Não
Valor do Débito por Tributo para a Atividade (R$):
Venda de mercadorias industrializadas pelo contribuinte
Receita Bruta Informada: R$ 150.000,00
4) Total Geral da Empresa
Total do Débito Declarado (exigível + suspenso) (R$)
IRPJ CSLL COFINS PIS/Pasep INSS/CPP ICMS IPI ISS Total
800,00 500,00 1.600,00 350,00 5.200,00 3.800,00 1.050,00 0,00 13.300,00
5) Este item não se aplica à primeira apuração do PA:
6) Informações sobre DAS Gerado na apuração: 11222333202607001
Número: 07202600000000001 Data limite para acolhimento: 20/08/2026
"""

DEFIS = """Declaração de Informações Socioeconômicas e
Fiscais(DEFIS)
Declaração Retificadora Exercício 2026 Ano-Calendário 2025
1. Identificação do Contribuinte
CNPJ Matriz: 11222333000181
Quantidade de empregados no início do período abrangido pela 3
declaração
Quantidade de empregados no final do período abrangido pela 0
declaração
2.2 Identificação e Rendimentos dos Sócios
CPF do sócio: 123.456.789-09
Nome: SOCIO UM
Rendimentos isentos pagos ao sócio pela empresa R$ 300.000,00
Rendimentos tributáveis pagos ao sócio pela empresa R$ 12.000,00
Percentual de participação do sócio no capital social da empresa no 90,00%
2.3 Percentual de participação em cotas em tesouraria
Estoque inicial do período abrangido pela declaração R$ 5.000.000,00
Estoque final do período abrangido pela declaração R$ 6.000.000,00
Saldo em caixa/banco no início do período abrangido pela declaração R$ 7.000,00
Saldo em caixa/banco no final do período abrangido pela declaração R$ 19.000,00
Total de aquisições de mercadorias para comercialização ou R$ 800.000,00
Total de despesas no período abrangido pela declaração R$ 200.000,00
"""


def test_extrato_pgdas_com_receitas_anteriores_e_das_sem_pagamento():
    assert identificar(PGDAS) == "pgdas"
    a = ler_simples("PGDASD-EXTRATO.pdf", texto=PGDAS)
    assert (a.cnpj, a.competencia, a.retificadora) == ("11222333000181", "2026-07", False)
    assert (a.receita_pa, a.rbt12, a.rba, a.rbaa, a.sublimite) == (150_000, 1_200_000, 900_000, 1_500_000, 3_600_000)
    assert a.total_das == 13_300 and a.tributos["ICMS"] == 3_800 and a.aliquota_efetiva == round(13_300 / 150_000, 4)
    assert a.receitas_anteriores == {"2026-05": 100_000, "2026-06": 115_000}  # interno + externo
    meses, alertas = pgdas_mensal([a])
    assert [(m.competencia, m.receita_bruta) for m in meses] == [("2026-05", 100_000), ("2026-06", 115_000), ("2026-07", 150_000)]
    assert meses[-1].valor_das == 13_300 and "receitas anteriores" in meses[0].proveniencia.localizacao
    assert any("sem pagamento registrado" in x for x in alertas)


def test_retificacao_aparece_quando_extrato_posterior_cita_outro_valor():
    a07 = ler_simples("p07.pdf", texto=PGDAS)
    a06 = ler_simples("p06.pdf", texto=PGDAS.replace("(PA): 07/2026", "(PA): 06/2026")
                      .replace("140.000,00 10.000,00 150.000,00", "120.000,00 0,00 120.000,00"))
    _, alertas = pgdas_mensal([a06, a07])
    assert any("PGDAS 2026-06: apurado R$ 120.000,00, mas o extrato de 2026-07 cita R$ 115.000,00" in x for x in alertas)


def test_defis_e_alertas_do_simples():
    d = ler_simples("DEFIS.pdf", texto=DEFIS)
    assert (d.ano, d.retificadora, d.empregados_inicio, d.empregados_fim) == (2025, True, 3, 0)
    assert (d.estoque_final, d.caixa_final, d.distribuicao_socios, d.pro_labore_socios) == (6_000_000, 19_000, 300_000, 12_000)
    assert d.socios[0]["participacao"] == 90.0 and d.socios[0]["cpf"] == "12345678909"
    with pytest.raises(SimplesNaoLido, match="recibo"):
        ler_simples("recibo.pdf", texto="Declaração de Informações Socioeconômicas e Fiscais(DEFIS)\nRECIBO DE ENTREGA")

    from captacao.schemas import Metodo, PGDASMes, Proveniencia
    prov = Proveniencia(arquivo="x", metodo=Metodo.PARSER)
    pgdas = [PGDASMes(cnpj="1", competencia=f"2025-{m:02d}", receita_bruta=125_000, proveniencia=prov) for m in range(1, 13)]
    _, alertas = _resumo_simples([], [d], pgdas, folha=[])
    texto = " | ".join(alertas)
    assert "4.0 ano(s) de receita" in texto and "R$ 300.000 pagos aos sócios" in texto
    assert "0 no fim do ano" in texto and "retificadora" in texto


def test_extrato_bancario_em_planilha(tmp_path):
    wb = openpyxl.Workbook()
    ws = wb.active
    for linha in [[None], ["Atualização:", "28/08/2026 11:36:11"], ["Nome:", "EMPRESA TESTE"], ["Agência:", "4321"],
                  ["Conta:", "0007654-3"], [None], ["Lançamentos"], ["Periodo:", "01/09/2025 até 25/08/2026"], [None],
                  ["Data", "Lançamento", "CPF/CNPJ", "Valor (R$)", "Saldo (R$)"],
                  ["02/09/2025", "SALDO ANTERIOR", None, None, "1000.0"],
                  ["03/09/2025", "ENTRADA PIX TRANSF CLIENTE X", "11.222.333/0001-81", "1500.0", None],
                  ["04/09/2025", "SAÍDA PIX ENVIADO SOCIO UM", "123.456.789-09", "-60000.0", None]]:
        ws.append(linha)
    arq = tmp_path / "Extrato_Lancamentos.xlsx"
    wb.save(arq)
    e = ler_extrato_planilha(arq)
    assert e.conta == "0007654-3" and "agência 4321" in e.proveniencia.localizacao
    assert [(t.data, t.valor, t.contraparte_doc) for t in e.transacoes] == [
        (date(2025, 9, 3), 1500.0, "11222333000181"), (date(2025, 9, 4), -60000.0, "12345678909")]
