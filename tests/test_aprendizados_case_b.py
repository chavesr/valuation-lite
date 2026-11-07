"""O que o case B ensinou — reproduzido com dados sintéticos (sem dados do cliente).

1. Itaú exporta "SALDO TOTAL DISPONÍVEL DIA" como lançamento no OFX.
2. BB grava "PIX - ENVIADO - 24/02 15:40 FORNECEDOR" (pontuação, data e hora no meio do histórico).
3. Transferências entre empresas do grupo aparecem só com o nome distintivo ("ALFAPRESS COMERCIO").
4. Layout contábil "Código | Classificação | Descrição | Saldo | Total" com cabeçalhos de grupo sem valor.
5. "DRE gerencial" = cópia da contábil editada em Excel (formato americano, valores redondos, total errado).
6. Empresa fora do Simples: não há PGDAS; o GCI compara o caixa com a DRE contábil do período dos extratos.
"""

from datetime import date

import pytest

from captacao.classificacao import Classificador
from captacao.parsers.demonstracoes_pdf import comparar_linhas, ler_demonstracao
from captacao.parsers.ofx import ler_ofx
from captacao.schemas import (Categoria, DadosBrutos, DREAnual, Empresa, EmpresaGrupo, ExtratoConta, Metodo,
                              Proveniencia, Transacao)
from engine.gci import calcular_gci


def test_ofx_ignora_linhas_de_saldo(tmp_path):
    def trn(data, valor, memo, i):
        return (f"<STMTTRN><TRNTYPE>OTHER<DTPOSTED>{data}<TRNAMT>{valor}<FITID>{i}"
                f"<MEMO>{memo}</STMTTRN>")
    ofx = ("OFXHEADER:100\n<OFX><BANKMSGSRSV1><STMTTRNRS><STMTRS><BANKACCTFROM><BANKID>0341<ACCTID>123"
           "</BANKACCTFROM><BANKTRANLIST>"
           + trn("20260102", "-37716.33", "SALDO ANTERIOR", 1)
           + trn("20260102", "24041.69", "PIX RECEBIDO PAYPAL 02/01", 2)
           + trn("20260102", "-13674.64", "SALDO TOTAL DISPONÍVEL DIA", 3)
           + "</BANKTRANLIST></STMTRS></STMTTRNRS></BANKMSGSRSV1></OFX>")
    arq = tmp_path / "itau.ofx"
    arq.write_text(ofx, encoding="utf-8")
    assert [t.descricao for t in ler_ofx(arq).transacoes] == ["PIX RECEBIDO PAYPAL 02/01"]


def _t(valor, descricao):
    return Transacao(data=date(2026, 2, 24), valor=valor, descricao=descricao)


def test_historicos_bb_sicredi_itau_e_empresa_do_grupo():
    empresa = Empresa(nome="Alfa", cnpjs=[EmpresaGrupo(cnpj="1", razao_social="ALFAPRESS IND E COM DE PECAS LTDA")])
    c = Classificador(empresa)
    casos = {
        ("PIX - ENVIADO - 24/02 15:40 TRANSPORTADORA XYZ", -1000): Categoria.DESPESA_OPERACIONAL,
        ("RECEBIMENTO PIX 10871186000108 CLIENTE ABC PIX_CRED", 5000): Categoria.RECEITA_OPERACIONAL,
        ("PIX RECEBIDO ALFAPRESS COMERCIO DE PECAS", 90000): Categoria.TRANSFERENCIA_INTERNA,
        ("BB RENDE FACIL", -50000): Categoria.APLICACAO_FINANCEIRA,
        ("BB RENDE FACIL", 50000): Categoria.RESGATE_APLICACAO,
        ("CAPITAL GIRO PEAC FGI", -24000): Categoria.PAGAMENTO_EMPRESTIMO,
        ("CONTRAT CAMBIO IMPORTACAO", -80000): Categoria.DESPESA_OPERACIONAL,
        ("SISPAG VISA AT", 5000): Categoria.RECEITA_OPERACIONAL,
        ("PIX REJEITADO ERRO TEMPO EXCEDIDO", 50000): Categoria.ESTORNO,
        ("TED 422.0001BANCO SAFRA", 7000): Categoria.RECEITA_OPERACIONAL,
    }
    for (desc, valor), esperado in casos.items():
        assert c.classificar_transacao(_t(valor, desc)).categoria == esperado, desc


CAB_CODIGO = [(1, 10, "Empresa: EMPRESA TESTE IND E COM LTDA Folha: 0001"), (1, 20, "C.N.P.J.: 11.222.333/0001-81"),
              (145, 30, "DEMONSTRAÇÃO DO RESULTADO DO EXERCÍCIO EM 31/12/2025"),
              (22, 40, "Código Classificação Descrição Saldo Total")]


def _dre_codigo(gerencial=False):
    """Contábil: códigos + formato brasileiro. Gerencial: sem códigos, formato americano, contas alteradas."""
    def n(v):  # número no formato do documento
        txt = f"{abs(v):,.2f}" if gerencial else f"{abs(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        return f"({txt})" if v < 0 else txt

    cod = (lambda c: "") if gerencial else (lambda c: f"{c} 4.1.10.100.{c} ")
    x_tit, x_item = (197, 210) if gerencial else (127, 38)
    taxas = -267_466.42 if gerencial else -767_466.42
    cmv_item = -8_588_646.09 if gerencial else -10_910_668.97
    cmv_total = -8_888_646.09 if gerencial else -10_910_668.97  # gerencial: total do grupo digitado errado
    linhas = [
        (x_tit, "Receita Operacional"),
        (x_item, f"{cod(406)}VENDA DE MERCADORIAS {n(20_118_675.58)} {n(20_118_675.58)}"),
        (x_tit, "Deducoes"),
        (x_item, f"{cod(426)}(-) ICMS {n(-1_429_412.30)}"),
        (x_item, f"{cod(428)}(-) COFINS {n(-2_116_767.60)} {n(-3_546_179.90)}"),
        (x_tit, f"Receita Líquida {n(16_572_495.68)}"),
        (x_tit, "Custos Produtos Vendidos"),
        (x_item, f"{cod(272)}CUSTOS DOS PRODUTOS/MERCADORIAS VENDIDAS {n(cmv_item)} {n(cmv_total)}"),
        (x_tit, f"Lucro Bruto {n(16_572_495.68 + cmv_total)}"),
        (x_tit, "Despesas Administrativas"),
        (x_item, f"{cod(350)}TAXAS DIVERSAS {n(taxas)}"),
        (x_item, f"{cod(332)}PRÓ-LABORE {n(-60_000)} {n(taxas - 60_000)}"),
        (x_tit, f"LUCRO LÍQUIDO DO EXERCÍCIO {n(16_572_495.68 + cmv_total + taxas - 60_000)}"),
    ]
    return CAB_CODIGO + [(x, 50 + 12 * i, t) for i, (x, t) in enumerate(linhas)]


def test_layout_com_codigo_e_grupos():
    d = ler_demonstracao("D. R. E 2025.pdf", linhas=_dre_codigo())
    assert (d.layout, d.gerencial, d.alertas) == ("grupos", False, [])
    (dre,) = d.dres
    assert dre.receita_bruta == 20_118_675.58 and dre.deducoes == -3_546_179.90
    assert dre.receita_liquida == 16_572_495.68 and dre.custo_vendas == -10_910_668.97
    assert dre.pro_labore == -60_000 and dre.lucro_liquido == pytest.approx(16_572_495.68 - 10_910_668.97 - 827_466.42)


def test_dre_gerencial_editada_e_comparada_linha_a_linha():
    contabil = ler_demonstracao("D. R. E 2025.pdf", linhas=_dre_codigo())
    ger = ler_demonstracao("GERENCIAL - D. R. E 2025.pdf", linhas=_dre_codigo(gerencial=True))
    assert ger.gerencial and ger.dres[0].proveniencia.localizacao.startswith("gerencial")
    assert any("total do grupo -8.888.646,09 × soma das contas -8.588.646,09" in a for a in ger.alertas)

    difs = {d.conta: d for d in comparar_linhas(contabil, ger)}
    assert difs["TAXAS DIVERSAS"].diferenca == 500_000 and difs["TAXAS DIVERSAS"].redonda
    assert not difs["CUSTOS DOS PRODUTOS/MERCADORIAS VENDIDAS"].redonda
    assert "VENDA DE MERCADORIAS" not in difs  # receita igual nas duas versões


def test_gci_sem_pgdas_usa_dre_contabil_do_periodo_dos_extratos():
    prov = Proveniencia(arquivo="x", metodo=Metodo.PARSER)
    transacoes = [Transacao(data=date(2026, m, 10), valor=1_000_000, descricao="PIX RECEBIDO CLIENTE",
                            categoria=Categoria.RECEITA_OPERACIONAL) for m in range(1, 10)]
    dados = DadosBrutos(
        empresa=Empresa(nome="X", cnpjs=[EmpresaGrupo(cnpj="1", razao_social="X")]),
        periodo_inicio="2026-01", periodo_fim="2026-09",
        extratos=[ExtratoConta(transacoes=transacoes, proveniencia=prov)],
        dres=[DREAnual(cnpj="1", exercicio=2026, meses=6, receita_bruta=10_000_000, proveniencia=prov)],
    )
    g = calcular_gci(dados)
    assert g.metricas["gap_fiscal"] == round((6_000_000 - 10_000_000) / 6_000_000, 4)
    assert g.penalidades["cobertura_pgdas"] == 0.0 and not g.excede_limite_simples
    texto = " | ".join(g.alertas)
    assert "DRE contábil 2026-01 a 2026-06" in texto and "contas bancárias não informadas" in texto
