"""F4 no tarantino_agent: lê _valuation/dados_brutos.json, aplica a normalização e grava:

    dre_economica.json      DRE econômica por período (linhas, fontes, ajustes, EBITDA, owner earnings)
    ajustes_decisoes.json   Checkpoint 2: um item por ajuste de julgamento; o analista preenche "aprovado"
                            (true/false), pode trocar "valor" e escrever "nota". Rodar de novo aplica as decisões.
    normalizacao.md         leitura para o analista
"""

from __future__ import annotations

import json
from pathlib import Path

from captacao.util import brl
from engine.normalizacao import DREEconomica, carregar_parametros, normalizar
from tarantino.case import DadosCase, EstadoCase, ler_estado
from tarantino.inventario import PASTA_SAIDA


def _md(estado: EstadoCase, dres: list[DREEconomica]) -> str:
    if not dres:
        return f"# Normalização — {estado.empresa}\n\n_Sem receita suficiente para montar a DRE econômica._\n"
    cab = "| Conta | " + " | ".join(d.periodo for d in dres) + " |\n|---|" + "---:|" * len(dres)
    contas = []
    for d in dres:
        for l in d.linhas:
            if l.conta not in contas:
                contas.append(l.conta)
    linhas = [f"| {c} | " + " | ".join(brl(d.valor(c), 0) for d in dres) + " |" for c in contas]
    linhas.append("| **Ajustes aplicados/aprovados** | " + " | ".join(
        brl(sum(a.valor for a in d.ajustes if a.status in ("aplicado", "aprovado")), 0) for d in dres) + " |")
    linhas.append("| **EBITDA econômico** | " + " | ".join(f"**{brl(d.ebitda, 0)}**" for d in dres) + " |")
    linhas.append("| Margem EBITDA | " + " | ".join(f"{d.margem_ebitda:.1%}" if d.margem_ebitda is not None else "—"
                                                      for d in dres) + " |")
    linhas.append("| **Lucro econômico** | " + " | ".join(f"**{brl(d.lucro_economico, 0)}**" for d in dres) + " |")
    linhas.append("| Owner earnings | " + " | ".join(brl(d.owner_earnings, 0) if d.owner_earnings is not None else "—"
                                                        for d in dres) + " |")
    partes = [f"# Normalização — {estado.empresa} ({estado.id})", "",
              "Valores em R$ no período indicado (LTM = últimos 12 meses). Ajustes de julgamento só entram depois de "
              "aprovados em `ajustes_decisoes.json`.", "", cab, *linhas, ""]
    for d in dres:
        partes.append(f"## {d.periodo}")
        partes.append(f"- Receita: **{d.receita_fonte}** · atividade {d.atividade} · regime do comprador "
                      f"{d.regime_comprador} · confiança {d.confianca}")
        fontes = ", ".join(f"{k} {brl(v, 0)}" for k, v in d.receitas_por_fonte.items() if v)
        partes.append(f"- Receitas por fonte: {fontes or '—'}")
        if d.capex_manutencao is not None:
            partes.append(f"- Capex de manutenção R$ {brl(d.capex_manutencao, 0)} ({d.capex_fonte})")
        for a in d.ajustes:
            partes.append(f"- Ajuste [{a.status}] {a.descricao}: R$ {brl(a.valor, 0)} ({a.fonte})"
                          + (f" — {a.nota}" if a.nota else ""))
        partes += [f"- ⚠ {x}" for x in d.alertas]
        partes.append("")
    return "\n".join(partes)


def normalizar_case(pasta_empresa: str | Path) -> list[DREEconomica]:
    pasta = Path(pasta_empresa)
    saida = pasta / PASTA_SAIDA
    arq_dados = saida / "dados_brutos.json"
    if not arq_dados.exists():
        raise FileNotFoundError("Rode antes: python -m tarantino abrir (dados_brutos.json não encontrado).")
    dados = DadosCase.model_validate_json(arq_dados.read_text(encoding="utf-8"))
    estado = ler_estado(pasta)

    arq_dec = saida / "ajustes_decisoes.json"
    decisoes = json.loads(arq_dec.read_text(encoding="utf-8")) if arq_dec.exists() else {}
    dres = normalizar(dados, decisoes, carregar_parametros())

    # Checkpoint 2: mantém o que o analista já decidiu e acrescenta os ajustes novos
    for d in dres:
        for a in d.ajustes:
            if a.tipo == "julgamento" and a.id not in decisoes:
                decisoes[a.id] = {"descricao": a.descricao, "valor_proposto": a.valor, "aprovado": None,
                                  "valor": None, "nota": None}
    arq_dec.write_text(json.dumps(decisoes, indent=2, ensure_ascii=False), encoding="utf-8")
    (saida / "dre_economica.json").write_text(
        json.dumps([d.model_dump(mode="json") for d in dres], indent=2, ensure_ascii=False), encoding="utf-8")
    (saida / "normalizacao.md").write_text(_md(estado, dres), encoding="utf-8")

    pendentes = sum(1 for v in decisoes.values() if v.get("aprovado") is None)
    resumo = "; ".join(f"{d.periodo}: EBITDA R$ {brl(d.ebitda, 0)}" for d in dres) or "sem DRE econômica"
    estado.registrar("F4", "normalizado", f"{resumo}; {pendentes} ajuste(s) aguardando o analista")
    (saida / "state.json").write_text(estado.model_dump_json(indent=2), encoding="utf-8")
    return dres
