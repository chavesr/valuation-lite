from datetime import date

import pytest

from captacao.carregador import carregar_extratos
from captacao.classificacao import (Classificador, deduplicar, padrao_descricao, pendentes_para_ia,
                                    pct_creditos_nao_classificados)
from captacao.parsers.csv_extrato import ler_csv_extrato
from captacao.schemas import (Categoria, Empresa, EmpresaGrupo, ExtratoConta, Metodo, Proveniencia, Socio,
                              Transacao)
from captacao.util import parse_numero_br
from tests.ficticio import gerar_case


@pytest.mark.parametrize("entrada,esperado", [
    ("1.234,56", 1234.56), ("-1.234,56", -1234.56), ("1234.56", 1234.56), ("(1.234,56)", -1234.56),
    ("1.234,56 D", -1234.56), ("R$ 10,00", 10.0), ("1.234", 1234.0), ("1,5", 1.5), ("", None),
    ("1,234.56", 1234.56), ("500,00-", -500.0),
])
def test_parse_numero_br(entrada, esperado):
    assert parse_numero_br(entrada) == esperado


def test_ofx_ficticio_le_contas_e_virgula_decimal(tmp_path):
    gerar_case(tmp_path, "charlie")
    extratos, pendencias = carregar_extratos(tmp_path / "03_Bancario")
    assert pendencias == []
    assert {e.banco for e in extratos} == {"237", "001"}
    conta_virgula = next(e for e in extratos if e.banco == "001")
    assert all(isinstance(t.valor, float) for t in conta_virgula.transacoes)
    assert any(t.valor == 20_000.0 for t in conta_virgula.transacoes)  # "20000,00"


def test_csv_com_preambulo_credito_debito_e_saldo(tmp_path):
    arquivo = tmp_path / "extrato.csv"
    arquivo.write_text(
        "Banco XPTO - Extrato de conta corrente\n"
        "Período: 01/01/2025 a 31/01/2025\n"
        "\n"
        "Data;Histórico;Crédito (R$);Débito (R$);Saldo (R$)\n"
        "01/01/2025;SALDO ANTERIOR;;;10.000,00\n"
        "02/01/2025;PIX RECEBIDO CLIENTE A;1.500,00;;11.500,00\n"
        "03/01/2025;TARIFA PACOTE;;45,90;11.454,10\n"
        "03/01/2025;Pagamento à vista;;1.000,00;10.454,10\n",
        encoding="cp1252",
    )
    extrato = ler_csv_extrato(arquivo)
    assert [t.valor for t in extrato.transacoes] == [1500.0, -45.9, -1000.0]
    assert extrato.transacoes[2].descricao == "Pagamento à vista"


def _empresa_charlie():
    return Empresa(
        nome="Charlie",
        cnpjs=[EmpresaGrupo(cnpj="22.222.222/0001-22", razao_social="CHARLIE COMERCIO DE ALIMENTOS LTDA"),
               EmpresaGrupo(cnpj="33.333.333/0001-33", razao_social="CHARLIE SERVICOS ALIMENTARES LTDA")],
        socios=[Socio(nome="Maria Aparecida Oliveira", cpf="555.666.777-88")],
    )


@pytest.mark.parametrize("descricao,valor,categoria", [
    ("TED RECEBIDA CHARLIE SERVICOS ALIMENTARES", 20_000, Categoria.TRANSFERENCIA_INTERNA),
    ("PIX ENVIADO 33333333000133", -5_000, Categoria.TRANSFERENCIA_INTERNA),
    ("PIX RECEBIDO MARIA A OLIVEIRA", 30_000, Categoria.APORTE_SOCIO),
    ("PIX ENVIADO MARIA APARECIDA OLIVEIRA", -25_000, Categoria.RETIRADA_SOCIO),
    ("PIX RECEBIDO PADARIA SAO JOSE", 1_200, Categoria.RECEITA_OPERACIONAL),
    ("CRED CIELO VENDAS CARTAO", 3_000, Categoria.RECEITA_OPERACIONAL),
    ("LIBERACAO CAPITAL DE GIRO", 150_000, Categoria.EMPRESTIMO_RECEBIDO),
    ("RESGATE CDB", 10_000, Categoria.RESGATE_APLICACAO),
    ("PAGAMENTO DAS SIMPLES NACIONAL", -9_000, Categoria.IMPOSTO),
    ("GPS INSS EMPRESA", -2_000, Categoria.ENCARGOS_FOLHA),
    ("Pagamento Pró-labore", -5_000, Categoria.RETIRADA_SOCIO),
    ("TARIFA CESTA SERVICOS", -150, Categoria.TARIFA_BANCARIA),
    ("APLICACAO CDB DI", -10_000, Categoria.APLICACAO_FINANCEIRA),
    ("CR DIVERSOS 1234", 300, Categoria.NAO_CLASSIFICADO),
])
def test_classificacao_por_regras(descricao, valor, categoria):
    t = Transacao(data=date(2025, 1, 2), valor=valor, descricao=descricao)
    assert Classificador(_empresa_charlie()).classificar_transacao(t).categoria == categoria


def test_pendentes_deduplicados_e_aprendizado(tmp_path):
    prov = Proveniencia(arquivo="x", metodo=Metodo.PARSER)
    extrato = ExtratoConta(proveniencia=prov, transacoes=[
        Transacao(data=date(2025, 1, d), valor=100.0, descricao=f"CR DIVERSOS {1000 + d}") for d in range(1, 11)
    ])
    classificador = Classificador(_empresa_charlie(), tmp_path / "regras.json")
    classificador.classificar([extrato])
    pendentes = pendentes_para_ia([extrato])
    assert len(pendentes) == 1 and pendentes[0]["ocorrencias"] == 10  # 10 linhas → 1 item para a IA

    classificador.aprender({pendentes[0]["padrao"]: Categoria.RECEITA_OPERACIONAL})
    novo = Classificador(_empresa_charlie(), tmp_path / "regras.json")  # recarrega do disco
    novo.classificar([extrato])
    assert pct_creditos_nao_classificados([extrato]) == 0
    assert padrao_descricao("CR DIVERSOS 1234") == "CR DIVERSOS"


def test_deduplicacao_entre_arquivos_mantem_repetidas_no_mesmo_arquivo():
    prov = Proveniencia(arquivo="x", metodo=Metodo.PARSER)
    t = lambda: Transacao(data=date(2025, 1, 2), valor=100.0, descricao="PIX RECEBIDO A", id_banco="linha-1")  # noqa
    a = ExtratoConta(banco="1", conta="1", proveniencia=prov, transacoes=[t(), t()])
    b = ExtratoConta(banco="1", conta="1", proveniencia=prov, transacoes=[t(), t()])  # arquivo sobreposto
    deduplicar([a, b])
    assert len(a.transacoes) == 2 and len(b.transacoes) == 0
