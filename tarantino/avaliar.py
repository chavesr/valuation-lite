"""F6 no tarantino_agent: Score de Risco + valuation. Lê dados_brutos.json, gci.json e dre_economica.json; grava:

    score_notas.json   notas por dimensão (código/questionário/padrão) — o analista ajusta "nota" e "justificativa"
    valuation.json     resultado completo (cenários, sensibilidade, contingências, preço recomendado)
    valuation.md       leitura para o analista
"""

from __future__ import annotations

import json
from pathlib import Path

from captacao.util import brl
from engine.gci import ResultadoGCI
from engine.normalizacao import DREEconomica
from engine.risco import avaliar_risco
from engine.score_case import NotaDimensao, propor_notas
from engine.valuation import ResultadoValuation, avaliar, carregar_parametros
from market_data.selic import selic_atual
from tarantino.case import DadosCase, ler_estado
from tarantino.inventario import PASTA_SAIDA

NOMES = {"confiabilidade_informacao": "Confiabilidade da informação", "dependencia_dono": "Dependência do dono",
         "concentracao_clientes": "Concentração de clientes", "recorrencia_receita": "Recorrência de receita",
         "historico_mercado": "Histórico e tempo de mercado", "estabilidade_resultados": "Estabilidade de resultados",
         "endividamento_liquidez": "Endividamento e liquidez", "contingencias": "Contingências",
         "setor_posicao_competitiva": "Setor e posição competitiva"}


def _md(empresa: str, caso: str, r: ResultadoValuation, selic_fonte: str) -> str:
    b = r.base
    linhas = [f"# Valuation — {empresa} ({caso})", "",
              f"**Preço recomendado (com margem de segurança): R$ {brl(r.preco_recomendado, 0)}**  ",
              f"Faixa pelo fluxo: conservador R$ {brl(r.cenarios[0].valor_patrimonio, 0)} · **base R$ "
              f"{brl(b.valor_patrimonio, 0)}** · otimista R$ {brl(r.cenarios[2].valor_patrimonio, 0)}", "",
              "## Premissas",
              f"- Fluxo base (owner earnings sustentável): **R$ {brl(r.fluxo_base, 0)}/ano** — {r.fluxo_fonte}",
              f"- EBITDA econômico do período base ({r.periodo_base}): R$ {brl(r.ebitda_base, 0)} · receita R$ {brl(r.receita_base, 0)}",
              f"- Crescimento histórico da receita: {r.crescimento_historico:.1%}" if r.crescimento_historico is not None
              else "- Crescimento histórico: não calculável (menos de 2 exercícios)",
              f"- Score de Risco **{r.risco.score:.0f}/100** → taxa **{r.risco.taxa_desconto:.1%}** a.a. (Selic "
              f"{r.risco.selic:.2%} — {selic_fonte} — + prêmio {r.risco.premio_implicito:.1%}) · horizonte "
              f"**{r.risco.horizonte_anos} anos**"
              + (f" — **taxa provisória**: entre {r.taxa_provisoria['minima']:.1%} e {r.taxa_provisoria['maxima']:.1%} "
                 "conforme as notas pendentes (⚠) forem decididas" if r.taxa_provisoria else ""),
              f"- Perpetuidade: {'sim' if r.perpetuidade else 'não'} ({r.perpetuidade_motivo})", "",
              "## Score de Risco", "", "| Dimensão | Nota | Origem | Evidência |", "|---|:-:|---|---|"]
    for n in r.notas.values():
        linhas.append(f"| {NOMES[n.dimensao]} | {n.nota}{' ⚠' if n.pendente else ''} | {n.origem} | {n.evidencia} |")
    linhas += ["", "⚠ = sem informação (nota neutra 3) ou aguardando o analista (editar `score_notas.json`).", "",
               "## Cenários (DCF de horizonte finito)", "",
               "| Cenário | Taxa | Crescimento | Valor terminal | Valor da empresa | Valor do patrimônio | × fluxo |",
               "|---|---:|---:|---:|---:|---:|---:|"]
    for c in r.cenarios:
        linhas.append(f"| {c.nome} | {c.taxa:.1%} | {c.crescimento:.1%} | {brl(c.valor_terminal, 0)} | "
                      f"{brl(c.valor_empresa, 0)} | {brl(c.valor_patrimonio, 0)} | {c.multiplo_do_fluxo:.2f} |")
    linhas += ["", "## Da empresa ao patrimônio",
               f"- Dívida bruta R$ {brl(r.divida_bruta, 0)} ({r.divida_fonte}) − caixa R$ {brl(r.caixa, 0)} = dívida "
               f"líquida **R$ {brl(r.divida_bruta - r.caixa, 0)}**"]
    for c in r.contingencias:
        linhas.append(f"- Contingência: {c.descricao} — R$ {brl(c.valor_bruto, 0)} × {c.probabilidade:.0%} = "
                      f"**R$ {brl(c.valor, 0)}** ({c.fonte})")
    linhas += ["", "## Referências",
               f"- Piso patrimonial (liquidação ordenada): R$ {brl(r.piso_patrimonial, 0)}" if r.piso_patrimonial is not None
               else "- Piso patrimonial: sem Balanço",
               f"- EPV (sem crescimento, perpetuidade — só referência): R$ {brl(r.epv, 0)}" if r.epv is not None else "- EPV: —"]
    if r.multiplo_ebitda:
        linhas.append(f"- Checagem por múltiplo de EBITDA (3–5×): R$ {brl(r.multiplo_ebitda['min'], 0)} a "
                      f"R$ {brl(r.multiplo_ebitda['max'], 0)} · múltiplo implícito do cenário base "
                      f"{r.multiplo_ebitda['implicito_base']:.1f}× EBITDA")
    linhas += ["", "## Sensibilidade (valor do patrimônio, cenário base)", ""]
    gs = list(next(iter(r.sensibilidade.values())).keys())
    linhas.append("| Taxa \\ crescimento | " + " | ".join(gs) + " |")
    linhas.append("|---|" + "---:|" * len(gs))
    for taxa, linha in r.sensibilidade.items():
        linhas.append(f"| {taxa} | " + " | ".join(brl(v, 0) for v in linha.values()) + " |")
    linhas += ["", "## Alertas", *[f"- {a}" for a in r.alertas]]
    return "\n".join(linhas)


def avaliar_case(pasta_empresa: str | Path, selic: float | None = None) -> ResultadoValuation:
    pasta = Path(pasta_empresa)
    saida = pasta / PASTA_SAIDA
    for nome in ("dados_brutos.json", "dre_economica.json"):
        if not (saida / nome).exists():
            raise FileNotFoundError(f"{nome} não encontrado: rode antes 'abrir' e 'normalizar'.")
    dados = DadosCase.model_validate_json((saida / "dados_brutos.json").read_text(encoding="utf-8"))
    dres = [DREEconomica.model_validate(d) for d in json.loads((saida / "dre_economica.json").read_text(encoding="utf-8"))]
    if not dres:
        raise ValueError("Sem DRE econômica: a normalização não encontrou receita.")
    gci = ResultadoGCI.model_validate_json((saida / "gci.json").read_text(encoding="utf-8")) \
        if (saida / "gci.json").exists() else None
    p = carregar_parametros()

    base = next((d for d in dres if d.confianca != "baixa"), dres[0])
    notas = propor_notas(dados, gci, dres, base)
    arq_notas = saida / "score_notas.json"
    decididas = json.loads(arq_notas.read_text(encoding="utf-8")) if arq_notas.exists() else {}
    for dim, d in decididas.items():  # o analista prevalece
        if d.get("origem") == "analista" and dim in notas:
            notas[dim] = NotaDimensao(**{**d, "pendente": False})
    arq_notas.write_text(json.dumps({k: v.model_dump() for k, v in notas.items()}, indent=2, ensure_ascii=False),
                         encoding="utf-8")

    fonte_selic = "informada"
    if selic is None:
        selic, data_selic, fonte_selic = selic_atual(p["selic_padrao"])
        fonte_selic = f"{fonte_selic}, {data_selic}"
    risco = avaliar_risco({k: v.nota for k, v in notas.items()}, selic)
    resultado = avaliar(dados, dres, gci, risco, notas, p)

    estado = ler_estado(pasta)
    (saida / "valuation.json").write_text(resultado.model_dump_json(indent=2), encoding="utf-8")
    (saida / "valuation.md").write_text(_md(estado.empresa, estado.id, resultado, fonte_selic), encoding="utf-8")
    estado.registrar("F6", "avaliado", f"Score {risco.score:.0f}, taxa {risco.taxa_desconto:.1%}, base R$ "
                     f"{brl(resultado.base.valor_patrimonio, 0)}, preço recomendado R$ {brl(resultado.preco_recomendado, 0)}")
    (saida / "state.json").write_text(estado.model_dump_json(indent=2), encoding="utf-8")
    return resultado
