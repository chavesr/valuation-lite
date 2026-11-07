"""F4 — normalização com dados sintéticos: escolha da receita, custos, tributos do comprador e Checkpoint 2."""

from datetime import date

import pytest

from captacao.schemas import (Categoria, DadosBrutos, DREAnual, Empresa, EmpresaGrupo, ExtratoConta, Metodo, PGDASMes,
                              Proveniencia, Transacao)
from engine.normalizacao import carregar_parametros, normalizar, periodos

PROV = Proveniencia(arquivo="x", metodo=Metodo.PARSER)


def _dados(receita_pgdas=100_000.0, caixa=None, dre=True, cmv=-500_000.0):
    pgdas = [PGDASMes(cnpj="1", competencia=f"2025-{m:02d}", receita_bruta=receita_pgdas, proveniencia=PROV)
             for m in range(1, 13)]
    extratos = []
    if caixa:
        tx = [Transacao(data=date(2025, m, 10), valor=caixa, descricao="PIX RECEBIDO",
                        categoria=Categoria.RECEITA_OPERACIONAL) for m in range(1, 13)]
        extratos = [ExtratoConta(transacoes=tx, proveniencia=PROV)]
    dres = [DREAnual(cnpj="1", exercicio=2025, receita_bruta=1_200_000, custo_vendas=cmv,
                     despesas_administrativas=-300_000, despesas_pessoal=-150_000, pro_labore=-60_000,
                     depreciacao_amortizacao=-20_000, financeiras_nas_operacionais=-10_000,
                     proveniencia=PROV)] if dre else []
    return DadosBrutos(empresa=Empresa(nome="X", cnpjs=[EmpresaGrupo(cnpj="1", razao_social="X")]),
                       periodo_inicio="2025-01", periodo_fim="2025-12", pgdas=pgdas, extratos=extratos, dres=dres)


def test_periodos_ltm_e_exercicio():
    assert [n for n, _ in periodos(_dados())] == ["LTM 2025-01 a 2025-12", "2025"]


def test_receita_declarada_custos_da_dre_e_simples():
    p = carregar_parametros()
    (ltm, ano) = normalizar(_dados(), parametros=p)
    assert ano.receita_fonte == ltm.receita_fonte == "PGDAS-D"  # declarada ao fisco tem preferência sobre a DRE
    assert ano.valor("Receita bruta") == 1_200_000
    assert ano.regime_comprador.startswith("Simples")
    assert ano.valor("Tributos sobre a receita") == -1_200_000 * p["simples"]["aliquota_efetiva_padrao"]["comercio"]
    assert ano.valor("Custo das vendas") == -500_000
    # adm. 300 mil − (pessoal 150 + pró-labore 60 + D&A 20 + juros 10) = 60 mil de outras despesas
    assert ano.valor("Despesas administrativas e comerciais") == pytest.approx(-60_000)
    mercado = 12_000 * 12  # gestor PJ: 12 parcelas, sem encargos
    assert ano.ajustes[0].id == "pro_labore_mercado" and ano.ajustes[0].valor == pytest.approx(-mercado)
    esperado = 1_200_000 - 108_000 - 500_000 - 150_000 - 60_000 - mercado
    assert ano.ebitda == pytest.approx(esperado) and ano.ebit == pytest.approx(esperado - 20_000)


def test_caixa_acima_da_declarada_vira_receita_e_gera_contingencia():
    (ltm, _) = normalizar(_dados(caixa=130_000.0))
    assert ltm.receita_fonte.startswith("caixa") and ltm.valor("Receita bruta") == 1_560_000
    assert ltm.valor("Custo das vendas") == pytest.approx(-500_000 / 1_200_000 * 1_560_000)  # CMV proporcional
    assert any("contingência" in a for a in ltm.alertas) and ltm.confianca == "baixa"


def test_acima_do_limite_compara_presumido_e_real():
    p = carregar_parametros()
    # margem alta (CMV pequeno): o Presumido costuma ser mais barato
    (ltm, _) = normalizar(_dados(receita_pgdas=500_000.0, cmv=-100_000.0), parametros=p)
    assert ltm.regime_comprador == "Lucro Presumido"
    assert ltm.valor("IRPJ/CSLL (regime do comprador)") == pytest.approx(-6_000_000 * 0.0308)
    assert any("Lucro Presumido R$" in a and "Lucro Real R$" in a for a in ltm.alertas)
    # margem apertada (CMV alto): o Real fica mais barato (IR/CS sobre lucro pequeno + créditos de PIS/COFINS)
    (ltm, _) = normalizar(_dados(receita_pgdas=500_000.0, cmv=-1_000_000.0), parametros=p)
    assert ltm.regime_comprador == "Lucro Real"


def test_lucro_real_sem_lucro_nao_paga_ir():
    from engine.normalizacao import _lucro_real
    p = carregar_parametros()
    trib, ircs = _lucro_real(1_000_000, -900_000, -200_000, -100_000, "comercio", p)
    assert ircs == 0.0 and trib == pytest.approx(max(0, (1_000_000 - 900_000 - 100_000) * 0.0925) + 70_000)


def test_dre_sem_cmv_e_checkpoint_do_analista():
    dados = _dados(cmv=None)
    (_, ano) = normalizar(dados)
    assert any("sem linha de CMV" in a for a in ano.alertas) and ano.confianca == "baixa"
    # ajuste de julgamento vindo do questionário só entra depois de aprovado
    from captacao.questionario import Resposta, RespostasQuestionario
    q = RespostasQuestionario(respostas={
        "Q25a": Resposta(codigo="Q25a", titulo="", tipo="unica", valor="Sim", bruto="Sim"),
        "Q25b": Resposta(codigo="Q25b", titulo="", tipo="moeda", valor=5_000.0, bruto="5 mil")}, proveniencia=PROV)
    from tarantino.case import DadosCase
    dc = DadosCase(**dados.model_dump(), questionario=q)
    (_, ano) = normalizar(dc)
    aj = next(a for a in ano.ajustes if a.id == "despesas_pessoais")
    assert aj.status == "proposto" and aj.valor == 60_000
    (_, aprovado) = normalizar(dc, decisoes={"despesas_pessoais": {"aprovado": True, "valor": 48_000}})
    assert aprovado.ebitda == pytest.approx(ano.ebitda + 48_000)
