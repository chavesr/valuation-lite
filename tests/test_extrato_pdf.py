"""Extrato bancário em PDF — linhas sintéticas nos layouts reais de BB, Sicredi e Itaú (sem dados de clientes).

Cada linha é (x0, y, texto), como sai do pdfplumber.
"""

from datetime import date

import pytest

from captacao.parsers.extrato_pdf import ExtratoPdfNaoLido, ler_extrato_pdf, mesma_conta
from captacao.schemas import ExtratoConta, Metodo, Proveniencia


def _bb():
    return [
        (148, 10, "Consultas - Extrato de conta corrente"),
        (56, 20, "Conta corrente 12345-6EMPRESA TESTE LTDA"),
        (56, 30, "Período do extrato 07 / 2026"),
        (60, 40, "Dt. balancete Dt. movimento Ag. origem Lote Histórico Documento Valor R$ Saldo"),
        (65, 50, "30/06/2026 0000 00000000 Saldo Anterior 1.000,00 C"),
        (65, 60, "01/07/2026 5122 99015870 Transferência recebida 555.122.000.002.001 709,50 C"),
        (252, 75, "01/07 11:32 CLIENTE ALFA LTDA"),
        (65, 90, "01/07/2026 0000 13113124 Débito Serviço Cobrança 1.661.297.017.019 3,72 D"),
        (252, 105, "Tar. agrupadas - ocorrencia 30/06/2026"),
        # data do balancete 30/07, movimento 01/08: fora do mês do extrato (o OFX usa a do movimento)
        (65, 120, "30/07/2026 01/08/2026 0000 12378 619 Devolução Juros-Lim Esp 511.057.327 65,41 C"),
        (65, 135, "31/07/2026 0000 00000 999 S A L D O 1.771,19 C"),  # inclui o lançamento de 01/08
    ]


def test_bb_detalhe_na_linha_de_baixo_data_do_movimento_e_saldo():
    e, alertas = ler_extrato_pdf("BB_2026-07.pdf", linhas=_bb())
    assert (e.banco, e.conta) == ("001", "12345-6")
    assert [(t.data, t.valor) for t in e.transacoes] == [(date(2026, 7, 1), 709.50), (date(2026, 7, 1), -3.72)]
    assert e.transacoes[0].descricao == "Transferência recebida 01/07 11:32 CLIENTE ALFA LTDA"
    assert alertas == ["1 lançamento(s) fora do período do extrato ignorado(s)."]
    assert e.proveniencia.confianca == "alta" and "1 saldo(s) conferido(s)" in e.proveniencia.localizacao


def _sicredi(saldo_final="-1.010,00"):
    return [
        (54, 10, "Associado: EMPRESA TESTE LTDA"), (48, 20, "Cooperativa: 0101"), (75, 30, "Conta: 98765-4"),
        (46, 40, "Extrato (Período de 01/01/2026 a 31/01/2026)"),
        (48, 50, "Data Descrição Documento Valor (R$) Saldo (R$)"),
        (99, 60, "SALDO ANTERIOR -1.000,00"),
        (48, 70, "02/01/2026 RECEBIMENTO PIX 21428964000105 CLIENTE BETA PIX_CRED 1.333,60 333,60"),
        (48, 80, f"03/01/2026 LIQUIDACAO DE PARCELA C21733171 -1.343,60 {saldo_final}"),
        (46, 90, "Lançamentos Futuros (Próximos 30 dias)"),
        (48, 100, "06/02/2026 Debito Folha de Pagamento - 32XK -46.627,54 -47.637,54"),
    ]


def test_sicredi_ignora_lancamentos_futuros_e_confere_saldo():
    e, alertas = ler_extrato_pdf("Sicredi_2026-01.pdf", linhas=_sicredi())
    assert (e.banco, e.conta, len(e.transacoes)) == ("748", "98765-4", 2)
    assert e.transacoes[0].contraparte_doc == "21428964000105"
    assert alertas == [] and e.proveniencia.confianca == "alta"


def test_saldo_que_nao_fecha_vira_alerta():
    e, alertas = ler_extrato_pdf("Sicredi.pdf", linhas=_sicredi(saldo_final="-900,00"))
    assert e.proveniencia.confianca == "media"
    assert any("Saldo não confere em 1 de 2" in a for a in alertas)


def test_itau_historico_e_razao_social_quebrados():
    linhas = [
        (35, 10, "EMPRESA TESTE LTDA CNPJ Agência 4321 Conta 0012345-6"), (35, 20, "11.222.333/0001-81"),
        (35, 30, "Lançamentos do período: 01/08/2026 até 30/09/2026"),
        (35, 40, "Data Lançamentos Razão Social CNPJ/CPF Valor (R$) Saldo (R$)"),
        (35, 50, "31/07/2026 SALDO ANTERIOR 1.000,00"),
        (224, 60, "CLIENTE GAMA INDUSTRIA E"),
        (35, 70, "03/08/2026 PIX RECEBIDO CLIENTE03/08 COMERCIO 11.222.333/0001-81 30.000,00"),
        (224, 81, "LTDA"),
        # histórico longo: a linha da data fica só com o valor
        (88, 92, "RENDIMENTOS REND PAGO APLIC"), (35, 97, "03/08/2026 0,11"), (88, 102, "AUT MAIS"),
        (35, 116, "03/08/2026 SALDO TOTAL DISPONÍVEL DIA 31.000,11"),
    ]
    e, alertas = ler_extrato_pdf("Itau.pdf", linhas=linhas)
    assert (e.banco, e.conta, e.cnpj_titular) == ("341", "0012345-6", "11222333000181")
    assert [t.valor for t in e.transacoes] == [30_000.0, 0.11]
    assert e.transacoes[0].descricao.startswith("CLIENTE GAMA INDUSTRIA E PIX RECEBIDO") and "LTDA" in e.transacoes[0].descricao
    assert e.transacoes[1].descricao == "RENDIMENTOS REND PAGO APLIC AUT MAIS"
    assert alertas == []  # 1.000 + 30.000 + 0,11 = 31.000,11


def test_pdf_que_nao_e_extrato():
    with pytest.raises(ExtratoPdfNaoLido, match="escaneado"):
        ler_extrato_pdf("x.pdf", linhas=[])
    posicao_emprestimo = [(50, 10, "Associado: EMPRESA TESTE LTDA"), (50, 20, "Cooperativa: 0101"),
                          (50, 30, "Posição do contrato de crédito C617205708 — saldo devedor 120.000,00")]
    with pytest.raises(ExtratoPdfNaoLido, match="não reconhecido"):
        ler_extrato_pdf("posicao.pdf", linhas=posicao_emprestimo)


def test_mesma_conta_entre_pdf_e_ofx():
    def conta(banco, numero):
        return ExtratoConta(banco=banco, conta=numero, transacoes=[],
                            proveniencia=Proveniencia(arquivo="x", metodo=Metodo.PARSER))

    assert mesma_conta(conta("748", "54321-0"), conta("748", "01010000000543210"))  # cooperativa à esquerda
    assert mesma_conta(conta("341", "0012345-6"), conta("0341", "4321123456"))  # agência à esquerda
    assert not mesma_conta(conta("001", "98765-4"), conta("748", "98765-4"))  # banco diferente
    assert not mesma_conta(conta("001", "1-0"), conta("001", "31-0"))  # número curto demais para comparar
