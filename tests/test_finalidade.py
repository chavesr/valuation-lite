"""D7 — finalidade da transação: leitura da participação, do aporte e do pedido do vendedor."""

import pytest

from engine.finalidade import Finalidade, leitura, ler_finalidade


def test_modelo_padrao_e_venda_total(tmp_path):
    f = ler_finalidade(tmp_path)
    assert (f.tipo, f.percentual) == ("venda_total", 1.0) and (tmp_path / "finalidade.json").exists()


def test_venda_total_com_pedido_acima_do_teto():
    linhas, alertas = leitura(Finalidade(pedido_vendedor=2_000_000), preco=1_400_000, teto=1_900_000, fluxo=500_000)
    assert any("1.4× o preço recomendado" in l and "4.0 anos de fluxo" in l for l in linhas)
    assert any("acima do valor de referência" in a for a in alertas)


def test_entrada_de_socio_com_aporte_participacao_justa():
    f = Finalidade(tipo="entrada_socio", percentual=0.30, aporte=2_000_000, pedido_vendedor=2_000_000)
    linhas, alertas = leitura(f, preco=3_000_000, teto=3_500_000, fluxo=600_000)
    # pós-aporte 5,0 mi → justa = 2/5 = 40% > 30% oferecidos; pedido implica pré-aporte de 2/0,3 − 2 = 4,67 mi
    assert any("40%" in l for l in linhas)
    assert any("pré-aporte implícito de **R$ 4.666.667**" in l for l in linhas)
    assert any("abaixo da justa" in a for a in alertas) and any("acima do valor de referência" in a for a in alertas)


def test_venda_parcial_mostra_valor_da_participacao():
    linhas, _ = leitura(Finalidade(tipo="venda_parcial", percentual=0.5), preco=1_000_000, teto=None, fluxo=0)
    assert any("Valor da participação (50%)" in l and "500.000" in l for l in linhas)


def test_percentual_invalido_e_rejeitado():
    with pytest.raises(ValueError):
        Finalidade(percentual=1.5)


def test_cotas_sem_valor_nao_calcula_participacao_justa():
    f = Finalidade(tipo="entrada_socio", percentual=0.3, aporte=2_000_000)
    linhas, alertas = leitura(f, preco=0, teto=1_400_000, fluxo=100_000)
    assert any("valem zero" in l for l in linhas) and not any("deveria receber" in l for l in linhas)
    assert any("tratar a dívida" in a for a in alertas)
