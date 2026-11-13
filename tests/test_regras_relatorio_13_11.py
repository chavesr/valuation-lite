"""Regras do relatório definidas pelo usuário a partir do Word editado da Vedis (13/11/2026)."""

import re

from relatorio import graficos as g
from relatorio.render import _leitura, _nd_nota, _secao, _ul


def test_negrito_marcado_com_asteriscos_vira_b_e_texto_e_escapado():
    html = _ul(["**30 anos de mercado** e fábrica <nova>"])
    assert "<b>30 anos de mercado</b>" in html and "&lt;nova&gt;" in html and "**" not in html


def test_leitura_em_paragrafos_vira_lista_com_marcador_e_um_paragrafo_continua_corrido():
    lista = _leitura("**Receita.** Estável.\n**Margens.** Em alta.")
    assert "marcador leitura" in lista and lista.count("<li>") == 2 and "<b>Receita.</b>" in lista
    assert _leitura("Texto corrido de um parágrafo.") == "<p>Texto corrido de um parágrafo.</p>"


def test_secao_sem_dado_sai_do_relatorio():
    assert _nd_nota("os balanços") == ""
    assert _secao("Análise operacional", "ebitda", _nd_nota("indicadores")) == ""


def test_mapa_de_posicionamento_nao_sobrepoe_pontos_com_a_mesma_nota():
    conc = [{"nome": f"Concorrente {i}", "preco": 3, "especializacao": 3} for i in range(4)]
    svg = g.mapa_posicionamento(conc, ("Empresa", 3, 3))
    centros = re.findall(r'<circle cx="([\d.]+)" cy="([\d.]+)"', svg)
    assert len(centros) == 5 and len(set(centros)) == 5
    ys = sorted(float(y) for _, y in centros)
    assert min(b - a for a, b in zip(ys, ys[1:])) >= 15  # rótulos de 1 linha não se cruzam


def test_rotulo_de_valor_negativo_nao_cai_em_cima_do_ano():
    svg = g.colunas_serie([("2025", -1_100_000, "")], titulo="Dívida líquida por ano")
    textos = [float(y) for y in re.findall(r'<text x="[\d.]+" y="([\d.]+)"', svg)]
    valor, ano = textos[0], textos[-1]
    assert ano - valor >= 10
