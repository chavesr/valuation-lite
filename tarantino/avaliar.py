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
from engine.score_case import NotaDimensao, aplicar_qualitativo, propor_notas
from engine.finalidade import leitura, ler_finalidade
from engine.valuation import ResultadoValuation, avaliar, carregar_parametros
from tarantino.mercado import DadoIndisponivel, mudancas, obter_mercado, selic_por_horizonte
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
    rotulo = {"provavel": "provável → desconta", "possivel": "possível → retenção", "remota": "remota → não afeta"}
    for c in r.contingencias:
        linhas.append(f"- Contingência {rotulo[c.classificacao]}: {c.descricao} — **R$ {brl(c.valor_bruto, 0)}** "
                      f"({c.fonte}){' — ' + c.nota if c.nota else ''}")
    if r.retencao_sugerida:
        linhas.append(f"- **Retenção sugerida no fechamento: R$ {brl(r.retencao_sugerida, 0)}** (não reduz o preço; "
                      "`contingencias_decisoes.json` para reclassificar)")
    if r.leitura_finalidade:
        linhas += ["", "## Finalidade da transação", "", *[f"- {x}" for x in r.leitura_finalidade]]
    if r.valor_oferta is not None:
        linhas += ["", "## Valor de referência (teto para a oferta na rede) e ponte para o dono", "",
                   f"Maior entre o valor da empresa pelo fluxo e os ativos a mercado (critério da ND): **R$ "
                   f"{brl(r.valor_oferta, 0)}** — vem de {r.valor_oferta_origem}. É o teto para ofertar; o alvo "
                   f"da negociação é o preço recomendado (R$ {brl(r.preco_recomendado, 0)}).", "",
                   "| Ponte | R$ |", "|---|---:|"]
        linhas += [f"| {nome} | {brl(v, 0)} |" for nome, v in r.ponte_dono]
    if r.faixa_venda:
        linhas += ["", "## Faixa de venda", "",
                   f"- Venda forçada (cenário conservador): R$ {brl(r.faixa_venda['forcada'], 0)}",
                   f"- **Venda a mercado (preço recomendado): R$ {brl(r.faixa_venda['mercado'], 0)}**",
                   f"- Potencial máximo (cenário otimista): R$ {brl(r.faixa_venda['maximo'], 0)}"]
    if r.regua_payback:
        nomes = {"forcada": "Venda forçada", "mercado": "Mercado", "maximo": "Máximo (régua da casa)"}
        linhas += ["", "## Conferência: régua da casa (payback)", "",
                   "Quantos anos de fluxo o comprador leva para recuperar o que paga (preço + dívida líquida + "
                   "contingências prováveis).", "",
                   "| Régua | Anos de fluxo | Valor da empresa | Valor do patrimônio |", "|---|---:|---:|---:|"]
        for k, v in r.regua_payback.items():
            linhas.append(f"| {nomes[k]} | {v['anos']:.1f} | {brl(v['valor_empresa'], 0)} | "
                          f"{brl(v['valor_patrimonio'], 0)} |")
        linhas.append(f"\nO preço recomendado (R$ {brl(r.preco_recomendado, 0)}) se paga em "
                      f"**{r.payback_preco:.2f} anos** de fluxo.")
    usado = " ← **piso do preço** (`valuation_decisoes.json`)"
    linhas += ["", "## Referências",
               f"- Patrimônio em liquidação ordenada (venda forçada): R$ {brl(r.piso_patrimonial, 0)}"
               f"{usado if r.piso_usado == 'liquidacao' else ''}" if r.piso_patrimonial is not None
               else "- Patrimônio: sem Balanço",
               f"- Ativos a mercado (brutos, sem descontar passivos): R$ {brl(r.ativos_mercado, 0)}"
               if r.ativos_mercado is not None else "",
               f"- Patrimônio a mercado (ativos a mercado − passivos): R$ {brl(r.patrimonio_mercado, 0)}"
               f"{usado if r.piso_usado == 'mercado' else ''}" if r.patrimonio_mercado is not None else "",
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


def avaliar_case(pasta_empresa: str | Path, selic: float | None = None,
                 atualizar_mercado: bool = False) -> ResultadoValuation:
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
    if (saida / "qualitativo.json").exists():  # F5: notas propostas pelo agente
        aplicar_qualitativo(notas, json.loads((saida / "qualitativo.json").read_text(encoding="utf-8"))["notas_score"])
    arq_notas = saida / "score_notas.json"
    decididas = json.loads(arq_notas.read_text(encoding="utf-8")) if arq_notas.exists() else {}
    for dim, d in decididas.items():  # o analista prevalece
        if d.get("origem") == "analista" and dim in notas:
            notas[dim] = NotaDimensao(**{**d, "pendente": False})
    arq_notas.write_text(json.dumps({k: v.model_dump() for k, v in notas.items()}, indent=2, ensure_ascii=False),
                         encoding="utf-8")

    fonte_selic = "informada"
    ref: float | dict[int, float] = selic if selic is not None else 0.0
    foto = painel = None
    if selic is None:
        try:
            foto, painel = obter_mercado(pasta, atualizar_mercado)
            ref, fontes = selic_por_horizonte(foto)
        except DadoIndisponivel:
            ref, fontes = p["selic_padrao"]["valor"], None
            fonte_selic = "valor padrão dos parâmetros (sem Focus nem Selic meta)"
    risco = avaliar_risco({k: v.nota for k, v in notas.items()}, ref)
    if selic is None and fontes:
        fonte_selic = fontes[risco.horizonte_anos]
    aviso_mercado = None
    if foto and painel:
        mudou = mudancas(foto, painel, risco.horizonte_anos)
        if mudou:
            nova = avaliar_risco({k: v.nota for k, v in notas.items()}, selic_por_horizonte(painel)[0])
            aviso_mercado = (f"Mercado mudou desde a fotografia deste case ({foto['coletado_em']}): "
                             f"{'; '.join(mudou)}. Taxa iria de {risco.taxa_desconto:.1%} para "
                             f"{nova.taxa_desconto:.1%}. Para usar os números novos: "
                             f"python -m tarantino avaliar \"{pasta}\" --atualizar-mercado")
    arq_cont = saida / "contingencias_decisoes.json"
    dec_cont = json.loads(arq_cont.read_text(encoding="utf-8")) if arq_cont.exists() else {}
    arq_val = saida / "valuation_decisoes.json"
    dec_val = json.loads(arq_val.read_text(encoding="utf-8")) if arq_val.exists() else {}
    dec_val.setdefault("piso", "liquidacao")
    dec_val.setdefault("_leia", "piso: liquidacao (ativos em venda forçada; padrão, mais conservador) | mercado "
                                 "(ativos a valor de mercado, critério da ND). Define o valor mínimo do preço.")
    arq_val.write_text(json.dumps(dec_val, indent=2, ensure_ascii=False), encoding="utf-8")
    resultado = avaliar(dados, dres, gci, risco, notas, p, dec_cont, dec_val["piso"])
    fin = ler_finalidade(saida)  # D7
    resultado.finalidade = fin.descricao
    resultado.leitura_finalidade, alertas_fin = leitura(fin, resultado.preco_recomendado, resultado.valor_oferta,
                                                        resultado.fluxo_base)
    resultado.alertas += alertas_fin
    if aviso_mercado:
        resultado.alertas.insert(0, aviso_mercado)
    resultado.aviso_mercado = aviso_mercado
    for c in resultado.contingencias:  # Checkpoint: o analista reclassifica, corrige ou acrescenta
        dec_cont.setdefault(c.id, {"descricao": c.descricao, "valor_calculado": c.valor_bruto,
                                   "classificacao": None, "valor_bruto": None, "nota": None})
    dec_cont.setdefault("_leia", "classificacao: provavel (desconta) | possivel (retenção) | remota (ignora). "
                                  "Para acrescentar: nova chave com descricao, valor_bruto, classificacao e fonte.")
    arq_cont.write_text(json.dumps(dec_cont, indent=2, ensure_ascii=False), encoding="utf-8")

    estado = ler_estado(pasta)
    (saida / "valuation.json").write_text(resultado.model_dump_json(indent=2), encoding="utf-8")
    (saida / "valuation.md").write_text(_md(estado.empresa, estado.id, resultado, fonte_selic), encoding="utf-8")
    estado.registrar("F6", "avaliado", f"Score {risco.score:.0f}, taxa {risco.taxa_desconto:.1%}, base R$ "
                     f"{brl(resultado.base.valor_patrimonio, 0)}, preço recomendado R$ {brl(resultado.preco_recomendado, 0)}")
    (saida / "state.json").write_text(estado.model_dump_json(indent=2), encoding="utf-8")
    return resultado
