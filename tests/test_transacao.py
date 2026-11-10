"""Capítulo 6: comissão ND, IR sobre ganho de capital e estrutura de pagamento sugerida."""

from types import SimpleNamespace

from relatorio import transacao as tr

P = tr.PADRAO


def test_comissao_maior_entre_10pct_e_150_mil():
    assert tr.comissao(2_000_000, P) == 200_000
    assert tr.comissao(1_000_000, P) == 150_000
    assert tr.comissao(0, P) == 0


def test_ir_ganho_capital_progressivo():
    assert tr.ir_ganho_capital(1_000_000, P["ir_ganho_capital"]) == 150_000
    assert tr.ir_ganho_capital(6_000_000, P["ir_ganho_capital"]) == 5_000_000 * 0.15 + 1_000_000 * 0.175
    assert tr.ir_ganho_capital(-1, P["ir_ganho_capital"]) == 0


def _v(fluxo=400_000.0):
    fl = [fluxo * 1.05 ** t for t in (1, 2, 3, 4)]
    return {"preco_recomendado": 1_000_000.0, "fluxo_base": fluxo, "periodo_base": "2025", "divida_bruta": 300_000.0,
            "caixa": 100_000.0, "contingencias": [{"classificacao": "provavel", "valor_bruto": 50_000.0}],
            "retencao_sugerida": 80_000.0, "risco": {"selic": 0.11},
            "faixa_venda": {"forcada": 800_000.0, "mercado": 1_000_000.0, "maximo": 1_600_000.0},
            "cenarios": [{"nome": "conservador", "fluxos": fl, "valor_patrimonio": 800_000.0},
                         {"nome": "base", "fluxos": fl, "valor_terminal": 1_200_000.0, "valor_patrimonio": 1_333_000.0,
                          "valor_empresa": 1_583_000.0},
                         {"nome": "otimista", "fluxos": fl, "valor_patrimonio": 1_600_000.0}]}


def _dados():
    return SimpleNamespace(balancos=[], defis=[])


def test_cenarios_dono_fecham():
    fin = SimpleNamespace(percentual=1.0, custo_cotas=None)
    cen = tr.cenarios_dono(_v(), _dados(), fin, P)
    m = next(x for x in cen if x["chave"] == "mercado")
    assert m["bruto"] == 1_000_000 + 300_000 + 50_000  # sócio + dívida bruta + prováveis (caixa dentro, 10/11/2026)
    assert m["liquido_caixa"] == m["bruto"] - 100_000  # o caixa da empresa volta ao comprador
    assert m["comissao"] == 150_000  # 10% de 1,25 mi < 150 mil
    assert m["sobra"] == 1_000_000 - 150_000 - m["ir"]
    assert m["ir"] == round((1_000_000 - 150_000) * 0.15, 2)


def test_pagamento_sugere_entrada_que_cabe_no_caixa():
    fin = SimpleNamespace(percentual=1.0, custo_cotas=None, entrada_aceita=None, prazo_aceito_meses=None,
                          aceita_earnout=None)
    v = _v(fluxo=300_000.0)
    merc = next(x for x in tr.cenarios_dono(v, _dados(), fin, P) if x["chave"] == "mercado")
    pg = tr.pagamento(v, fin, P, merc, recente=450_000.0)
    vista, prem, sug = pg["estruturas"]
    assert prem["entrada_pct"] == 0.25 and prem["n"] == 24 and pg["origem"] == "premissa ND"
    assert sug["parcela_caixa"] <= 0.70 + 1e-9 and sug["entrada_pct"] >= 0.25
    assert round(sug["entrada_pct"] * 100) % 5 == 0
    assert abs(prem["vp_socio"] - 1_000_000) < 1  # corrigido pelo CDI = Selic: o sócio não perde
    assert sug["earnout"] == 600_000.0 and pg["earnout_meta"] == 450_000.0  # até o otimista (10/11/2026)
    assert vista["no_fechamento"] == 1_000_000 - 150_000 - 80_000  # comissão e escrow saem da entrada
    fin.aceita_earnout = False
    assert tr.pagamento(v, fin, P, merc)["estruturas"][-1]["earnout"] == 0
