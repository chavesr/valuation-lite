"""F5 no tarantino_agent: análise qualitativa (agente analista fundamentalista).

    f5_entrada.md       pacote para o agente: instruções + playbook + fatos do case + esquema da resposta
    f5_saida.json       resposta do agente (gravada pelo modo claude-code, ou à mão no modo manual)
    f5_saida_bruta.txt  texto integral devolvido pelo Claude Code (para auditoria)
    qualitativo.json    saída validada · qualitativo.md  leitura para o analista

As notas propostas entram no Score (rodar 'avaliar' depois) como "F5 (proposta)", ainda pendentes:
o analista aprova trocando a origem para "analista" em score_notas.json.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from captacao.util import brl
from engine.gci import ResultadoGCI
from engine.normalizacao import DREEconomica, atividade_evidenciada
from engine.finalidade import ler_finalidade
from engine.score_case import divida_liquida, propor_notas
from julgamento.esquemas import Qualitativo
from julgamento.executor import ErroJulgamento, executar_claude_code, extrair_json
from tarantino.case import DadosCase, ler_estado
from tarantino.inventario import PASTA_SAIDA

RAIZ = Path(__file__).resolve().parents[1]
INSTRUCOES = RAIZ / "agents" / "f5_qualitativo.md"
PLAYBOOKS = RAIZ / "metodologia" / "playbooks"
CASOS_REFERENCIA = RAIZ / "metodologia" / "casos_referencia.md"
LIMITE_OUTROS = 30000  # caracteres somados dos trechos de outros documentos
LIMITE_ENTREVISTAS = 60000  # caracteres somados de todas as entrevistas no pacote
LIMITE_BLOCO = 4000  # caracteres por bloco de dados soltos (ERP, pendências) para manter o pacote enxuto


def _json(obj, limite: int = LIMITE_BLOCO) -> str:
    t = json.dumps(obj, ensure_ascii=False, default=str, indent=1)
    return t if len(t) <= limite else t[:limite] + "\n… (cortado)"


def _carregar(pasta: Path):
    saida = pasta / PASTA_SAIDA
    for nome in ("dados_brutos.json", "dre_economica.json"):
        if not (saida / nome).exists():
            raise FileNotFoundError(f"{nome} não encontrado: rode antes 'abrir' e 'normalizar'.")
    dados = DadosCase.model_validate_json((saida / "dados_brutos.json").read_text(encoding="utf-8"))
    dres = [DREEconomica.model_validate(d) for d in json.loads((saida / "dre_economica.json").read_text(encoding="utf-8"))]
    gci = ResultadoGCI.model_validate_json((saida / "gci.json").read_text(encoding="utf-8")) \
        if (saida / "gci.json").exists() else None
    return dados, dres, gci


def casos_referencia(excluir: str | None = None) -> str:
    """Casos de referência da ND; `excluir` (ex.: "R1") tira o próprio case na medição de concordância."""
    texto = CASOS_REFERENCIA.read_text(encoding="utf-8")
    if not excluir:
        return texto
    blocos = re.split(r"(?m)^(?=## )", texto)
    return "".join(b for b in blocos if not b.startswith(f"## {excluir} "))


def montar_entrada(pasta_empresa: str | Path, excluir_referencia: str | None = None) -> tuple[str, str]:
    """→ (texto do pacote, playbook usado)."""
    pasta = Path(pasta_empresa)
    saida = pasta / PASTA_SAIDA
    dados, dres, gci = _carregar(pasta)
    estado = ler_estado(pasta)
    playbook = atividade_evidenciada(dados) or "indefinido"
    if playbook == "indefinido":  # sem questionário, PGDAS nem SPED: o agente escolhe pelo que leu
        setoriais = ["_Atividade principal não informada: use o(s) playbook(s) que se aplica(m) ao que os "
                     "documentos e entrevistas mostram._"] + [(PLAYBOOKS / f"{a}.md").read_text(encoding="utf-8")
                                                            for a in ("industria", "comercio", "servicos")]
    else:
        setoriais = [(PLAYBOOKS / f"{playbook}.md").read_text(encoding="utf-8")]

    p = [INSTRUCOES.read_text(encoding="utf-8"), "", "---", "",
         (PLAYBOOKS / "geral.md").read_text(encoding="utf-8"), "",
         "\n\n".join(setoriais), "", "---", "",
         casos_referencia(excluir_referencia), "", "---", "",
         f"# Case {estado.id} — fatos levantados pelo sistema", "",
         f"- Período analisado: {estado.periodo_inicio} a {estado.periodo_fim}",
         f"- Atividade principal (playbook): {playbook}",
         f"- Finalidade da transação: {ler_finalidade(saida).descricao}",
         f"- CNPJs no grupo: {len(dados.empresa.cnpjs)} · sócios: {len(dados.empresa.socios)}"]
    if gci:
        p.append(f"- GCI (confiabilidade da informação) {gci.indice:.1f}, nível {gci.nivel}: receita caixa 12m "
                 f"R$ {brl(gci.receita_caixa_12m, 0)} · fiscal 12m R$ {brl(gci.receita_fiscal_12m, 0)} · "
                 f"não declarada 12m R$ {brl(gci.receita_nao_declarada_12m, 0)}")
    else:
        p.append("- GCI: não calculado (sem extratos ou sem fonte fiscal)")

    p += ["", "## DRE econômica (normalizada pelo sistema)", "",
          "| Período | Fonte da receita | Receita bruta | EBITDA | Margem | Lucro econômico | Owner earnings | Confiança |",
          "|---|---|---:|---:|---:|---:|---:|---|"]
    for d in dres:
        m = f"{d.margem_ebitda:.1%}" if d.margem_ebitda is not None else "—"
        oe = brl(d.owner_earnings, 0) if d.owner_earnings is not None else "—"
        p.append(f"| {d.periodo} | {d.receita_fonte} | {brl(d.valor('Receita bruta'), 0)} | {brl(d.ebitda, 0)} | {m} | "
                 f"{brl(d.lucro_economico, 0)} | {oe} | {d.confianca} |")
    ajustes = [(d.periodo, a) for d in dres for a in d.ajustes]
    if ajustes:
        p += ["", "Ajustes de normalização:"]
        p += [f"- {per}: {a.descricao} — R$ {brl(a.valor, 0)} [{a.status}]" for per, a in ajustes[:30]]

    base = next((d for d in dres if d.confianca != "baixa"), dres[0]) if dres else None
    notas = propor_notas(dados, gci, dres, base)
    p += ["", "## Score de Risco — notas atuais (código/questionário)", "",
          "| Dimensão | Nota | Origem | Evidência |", "|---|:-:|---|---|"]
    p += [f"| {n.dimensao} | {n.nota} | {n.origem} | {n.evidencia} |" for n in notas.values()]

    bruta, caixa, fonte = divida_liquida(dados)
    p += ["", "## Endividamento", f"- Dívida bruta R$ {brl(bruta, 0)} · caixa R$ {brl(caixa, 0)} ({fonte})"]
    for dv in dados.dividas[:15]:
        p.append(f"- {dv.banco} {dv.modalidade or ''}: saldo R$ {brl(dv.saldo_devedor, 0)}"
                 + (f", {dv.taxa_aa:.1f}% a.a." if dv.taxa_aa else "")
                 + (f", até {dv.vencimento_final:%m/%Y}" if dv.vencimento_final else ""))

    if dados.folha:
        f = max(dados.folha, key=lambda x: x.competencia)
        p += ["", "## Folha (último mês)", f"- {f.competencia}: {f.empregados or '?'} empregados, proventos "
              f"R$ {brl(f.proventos, 0)}, pró-labore R$ {brl(f.pro_labore, 0)}"]
    if dados.concentracao_clientes:
        p += ["", "## Concentração de clientes (SPED)", _json(dados.concentracao_clientes, 1500)]
    if dados.simples:
        p += ["", "## Simples Nacional (PGDAS-D mais recente)", _json(dados.simples, 1500)]
    if dados.erp:
        p += ["", "## Relatórios do ERP (resumo)", _json(dados.erp)]
    if dados.alertas:
        p += ["", "## Alertas da captação", *[f"- {a}" for a in dados.alertas[:40]]]

    if dados.entrevistas:
        p += ["", "## Entrevistas e briefings com o dono (relato — declarado, não comprovado)", "",
              "Use para entender o negócio, o papel do dono, clientes, concorrência e planos. Números citados aqui "
              "valem como declaração: só os documentos comprovam."]
        restante = LIMITE_ENTREVISTAS
        for e in dados.entrevistas:
            trecho = e.texto[:max(restante, 0)]
            restante -= len(trecho)
            cortado = "\n… (cortado)" if len(trecho) < len(e.texto) else ""
            p += ["", f"### {Path(e.arquivo).name}", trecho + cortado]
    if dados.outros_documentos:
        p += ["", "## Outros documentos do data room (início de cada um; sem leitura estruturada)", "",
              "Certidões, contratos, licenças, patentes e planilhas avulsas. Use como evidência qualitativa "
              "(regularidade, prazos, clientes, concentração); números aqui não foram conferidos."]
        restante = LIMITE_OUTROS
        for t in dados.outros_documentos:
            if restante <= 0:
                p.append(f"- (mais {len(dados.outros_documentos)} documento(s) omitidos pelo limite do pacote)")
                break
            trecho = t.texto[:restante]
            restante -= len(trecho)
            p += ["", f"### {t.arquivo}", trecho]
    q = dados.questionario
    if q:
        p += ["", "## Questionário do empreendedor (respostas do dono — não comprovadas)", ""]
        for cod, r in q.respostas.items():
            if r.valor in (None, "", []):
                continue
            v = ", ".join(map(str, r.valor)) if isinstance(r.valor, list) else r.valor
            p.append(f"- [{cod}] {r.titulo}: {v}" + (f" ({r.outro})" if r.outro else ""))
    else:
        p += ["", "## Questionário do empreendedor", "_Não respondido._"]

    if (saida / "pendencias.md").exists():
        p += ["", "## Pendências levantadas na captação",
              (saida / "pendencias.md").read_text(encoding="utf-8")[:LIMITE_BLOCO]]

    esquema = json.dumps(Qualitativo.model_json_schema(), ensure_ascii=False, indent=1)
    p += ["", "---", "", "# Formato da resposta",
          "Responda **somente** com um objeto JSON válido (sem texto antes ou depois) conforme o esquema abaixo.",
          f'Use "case_id": "{estado.id}" e "playbook": "{playbook}". Em `notas_score`, inclua exatamente uma nota '
          "para cada uma das 4 dimensões de julgamento.",
          f"No modo manual, grave o JSON em `{PASTA_SAIDA}/f5_saida.json` na pasta do case.", "",
          "```json", esquema, "```"]
    return "\n".join(p), playbook


def _md(empresa: str, q: Qualitativo) -> str:
    l = [f"# Análise qualitativa — {empresa} ({q.case_id})", "", f"_Playbook: {q.playbook}_", "",
         "## Resumo", q.resumo, "", "## Modelo de negócio", q.modelo_negocio, "",
         f"## Fosso: {q.fosso.forca}", f"Fontes: {', '.join(q.fosso.fontes) or '—'}. {q.fosso.justificativa}", "",
         "## Gestão", q.gestao.avaliacao, *[f"- {x}" for x in q.gestao.pontos_atencao], "",
         "## Notas propostas para o Score (aguardam aprovação do analista)", "",
         "| Dimensão | Nota | Confiança | Justificativa |", "|---|:-:|---|---|"]
    l += [f"| {n.dimensao} | {n.nota} | {n.confianca} | {n.justificativa} |" for n in q.notas_score]
    l += ["", "## Riscos", *[f"- **[{r.severidade}]** {r.descricao} — {r.evidencia}"
                             + (f" (mitigante: {r.mitigante})" if r.mitigante else "") for r in q.riscos]]
    l += ["", "## Pontos fortes", *[f"- {x}" for x in q.pontos_fortes]]
    l += ["", "## Perguntas para a entrevista", *[f"{i}. {x}" for i, x in enumerate(q.perguntas_entrevista, 1)]]
    l += ["", "## Lacunas de informação", *[f"- {x}" for x in q.lacunas_informacao]]
    if q.funcoes_do_dono:
        l += ["", "## Funções do dono a substituir (custo proposto em ajustes_decisoes.json)",
              *[f"- **{f.eixo}**: {f.descricao} — {f.evidencia}" for f in q.funcoes_do_dono]]
    return "\n".join(l)


def propor_custos_substituicao(saida: Path, q: Qualitativo) -> int:
    """D1: cada função do dono sem substituto vira ajuste de julgamento proposto (Checkpoint 2). Decisões já
    tomadas pelo analista não são tocadas; propostas antigas que a F5 não repetiu saem se ainda pendentes."""
    from engine.normalizacao import carregar_parametros

    p = carregar_parametros()
    cfg, enc = p["custo_substituicao_dono"], p["encargos_pj_para_clt"]["percentual"]
    arq = saida / "ajustes_decisoes.json"
    decisoes = json.loads(arq.read_text(encoding="utf-8")) if arq.exists() else {}
    novos = {f"substituicao_{f.eixo}": f for f in q.funcoes_do_dono}
    for k in [k for k, v in decisoes.items() if k.startswith("substituicao_") and k not in novos
              and v.get("aprovado") is None]:
        del decisoes[k]
    for k, f in novos.items():
        anual = cfg["mensal"][f.eixo] * cfg["meses_por_ano"] * (1 + enc)
        atual = decisoes.get(k, {})
        if atual.get("aprovado") is not None:
            continue
        decisoes[k] = {"descricao": f"Custo de substituir o dono na função {f.eixo}: {f.descricao}",
                       "valor_proposto": round(-anual, 2), "aprovado": None, "valor": None, "nota": None,
                       "origem": "F5", "evidencia": f.evidencia}
    arq.write_text(json.dumps(decisoes, indent=2, ensure_ascii=False), encoding="utf-8")
    return len(novos)


def importar_f5(pasta_empresa: str | Path) -> Qualitativo:
    """Valida f5_saida.json e grava qualitativo.json/.md."""
    pasta = Path(pasta_empresa)
    saida = pasta / PASTA_SAIDA
    arq = saida / "f5_saida.json"
    if not arq.exists():
        raise FileNotFoundError(f"{arq} não encontrado: grave a resposta do agente nesse arquivo.")
    estado = ler_estado(pasta)
    bruto = json.loads(arq.read_text(encoding="utf-8"))
    q = Qualitativo.model_validate({**bruto, "case_id": estado.id})
    (saida / "qualitativo.json").write_text(q.model_dump_json(indent=2), encoding="utf-8")
    propor_custos_substituicao(saida, q)
    (saida / "qualitativo.md").write_text(_md(estado.empresa, q), encoding="utf-8")
    notas = ", ".join(f"{n.dimensao} {n.nota}" for n in q.notas_score)
    estado.registrar("F5", "qualitativo", f"fosso {q.fosso.forca}; {len(q.riscos)} risco(s); notas propostas: {notas}")
    (saida / "state.json").write_text(estado.model_dump_json(indent=2), encoding="utf-8")
    return q


def rodar_f5(pasta_empresa: str | Path, modo: str = "claude-code", modelo: str | None = None,
             executor=executar_claude_code, excluir_referencia: str | None = None) -> Qualitativo | Path:
    """Grava o pacote; no modo claude-code executa e importa (→ Qualitativo); no manual devolve o caminho do pacote."""
    pasta = Path(pasta_empresa)
    saida = pasta / PASTA_SAIDA
    texto, _ = montar_entrada(pasta, excluir_referencia)
    entrada = saida / "f5_entrada.md"
    entrada.write_text(texto, encoding="utf-8")
    if modo == "manual":
        return entrada
    if modo == "api":
        raise ErroJulgamento("modo 'api' ainda não implementado — use claude-code ou manual.")
    resposta = executor(texto, modelo=modelo)
    (saida / "f5_saida_bruta.txt").write_text(resposta, encoding="utf-8")
    obj = extrair_json(resposta)
    (saida / "f5_saida.json").write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")
    return importar_f5(pasta)
