"""F7 no tarantino_agent: revisão cética antes do relatório (rodar depois de 'avaliar').

    f7_entrada.md        pacote: instruções + princípios da casa + resumos (normalização, qualitativo, valuation,
                         pendências) + decisões ainda abertas + esquema da resposta
    f7_saida.json        resposta do agente · f7_saida_bruta.txt  texto integral (auditoria)
    revisao.json / .md   saída validada (com a impressão digital do pacote: se não mudar, não roda de novo)
    revisao_decisoes.json Checkpoint: para cada alerta, status resolvido | aceito_risco | descartado (+ nota)
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from julgamento.esquemas import Revisao
from julgamento.executor import ErroJulgamento, executar_claude_code, extrair_json
from tarantino.case import ler_estado
from tarantino.inventario import PASTA_SAIDA

RAIZ = Path(__file__).resolve().parents[1]
INSTRUCOES = RAIZ / "agents" / "f7_revisor.md"
PLAYBOOK_GERAL = RAIZ / "metodologia" / "playbooks" / "geral.md"
STATUS = ("resolvido", "aceito_risco", "descartado")


def _ler(arq: Path, limite: int | None = None) -> str | None:
    if not arq.exists():
        return None
    t = arq.read_text(encoding="utf-8")
    return t[:limite] + "\n… (cortado)" if limite and len(t) > limite else t


def decisoes_abertas(saida: Path) -> list[str]:
    """O que o analista ainda não decidiu (o revisor deve pesar isso)."""
    out = []
    aj = json.loads(_ler(saida / "ajustes_decisoes.json") or "{}")
    for k, v in aj.items():
        if isinstance(v, dict) and v.get("aprovado") is None:
            valor = v.get("valor_proposto")
            out.append(f"Ajuste da normalização pendente: {v.get('descricao', k)}"
                       + (f" (R$ {valor:,.0f})".replace(",", ".") if isinstance(valor, (int, float)) else ""))
    notas = json.loads(_ler(saida / "score_notas.json") or "{}")
    for k, v in notas.items():
        if v.get("pendente"):
            out.append(f"Nota do Score pendente: {k} = {v.get('nota')} ({v.get('origem')})")
    cont = json.loads(_ler(saida / "contingencias_decisoes.json") or "{}")
    for k, v in cont.items():
        if not k.startswith("_") and isinstance(v, dict) and not v.get("classificacao") and v.get("valor_calculado"):
            out.append(f"Contingência com classificação padrão (analista não decidiu): {v.get('descricao', k)}")
    return out


def montar_entrada(pasta_empresa: str | Path) -> str:
    pasta = Path(pasta_empresa)
    saida = pasta / PASTA_SAIDA
    if not (saida / "valuation.md").exists():
        raise FileNotFoundError("valuation.md não encontrado: rode antes 'avaliar'.")
    estado = ler_estado(pasta)
    abertas = decisoes_abertas(saida)
    p = [INSTRUCOES.read_text(encoding="utf-8"), "", "---", "",
         "# Princípios da casa (resumo do playbook geral)", "", _ler(PLAYBOOK_GERAL, 6000), "", "---", "",
         f"# Case {estado.id} — material para revisão", "",
         "## Normalização (DRE econômica)", _ler(saida / "normalizacao.md", 15000) or "_não rodada_", "",
         "## Análise qualitativa (F5)", _ler(saida / "qualitativo.md", 12000) or "_F5 não rodada_", "",
         "## Valuation (F6)", _ler(saida / "valuation.md", 20000), "",
         "## Pendências da captação", _ler(saida / "pendencias.md", 6000) or "_nenhuma_", "",
         "## Decisões ainda abertas do analista", *([f"- {x}" for x in abertas] or ["_nenhuma_"]), ""]
    esquema = json.dumps(Revisao.model_json_schema(), ensure_ascii=False, indent=1)
    p += ["---", "", "# Formato da resposta",
          "Responda **somente** com um objeto JSON válido (sem texto antes ou depois) conforme o esquema abaixo.",
          f'Use "case_id": "{estado.id}".',
          f"No modo manual, grave o JSON em `{PASTA_SAIDA}/f7_saida.json` na pasta do case.", "",
          "```json", esquema, "```"]
    return "\n".join(p)


def _md(empresa: str, r: Revisao, decisoes: dict) -> str:
    rot = {"aprovado": "APROVADO", "aprovado_com_ressalvas": "APROVADO COM RESSALVAS", "refazer": "REFAZER"}
    l = [f"# Revisão — {empresa} ({r.case_id})", "", f"**Parecer: {rot[r.parecer]}**", "", r.resumo, "",
         "| Severidade | Fase | Alerta | Status |", "|---|---|---|---|"]
    ordem = {"alta": 0, "media": 1, "baixa": 2}
    for a in sorted(r.alertas, key=lambda a: ordem[a.severidade]):
        st = (decisoes.get(a.id) or {}).get("status") or "⚠ aberto"
        l.append(f"| {a.severidade} | {a.fase} | `{a.id}` | {st} |")
    for a in sorted(r.alertas, key=lambda a: ordem[a.severidade]):
        l += ["", f"### [{a.severidade}] {a.id}", f"- **Achado:** {a.achado}", f"- **Evidência:** {a.evidencia}",
              f"- **Sugestão:** {a.sugestao}"]
    if r.perguntas_ao_dono:
        l += ["", "## Perguntas ao dono", *[f"{i}. {x}" for i, x in enumerate(r.perguntas_ao_dono, 1)]]
    l += ["", "_Decida cada alerta em `revisao_decisoes.json` (status: resolvido | aceito_risco | descartado)._"]
    return "\n".join(l)


def pendentes_graves(saida: Path) -> list[str]:
    """Alertas de severidade alta ainda sem decisão (o relatório não deve sair com eles)."""
    if not (saida / "revisao.json").exists():
        return []
    r = Revisao.model_validate(json.loads((saida / "revisao.json").read_text(encoding="utf-8"))["revisao"])
    dec = json.loads(_ler(saida / "revisao_decisoes.json") or "{}")
    return [a.id for a in r.alertas if a.severidade == "alta" and (dec.get(a.id) or {}).get("status") not in STATUS]


def importar_f7(pasta_empresa: str | Path, hash_entrada: str | None = None) -> Revisao:
    pasta = Path(pasta_empresa)
    saida = pasta / PASTA_SAIDA
    arq = saida / "f7_saida.json"
    if not arq.exists():
        raise FileNotFoundError(f"{arq} não encontrado: grave a resposta do agente nesse arquivo.")
    estado = ler_estado(pasta)
    r = Revisao.model_validate({**json.loads(arq.read_text(encoding="utf-8")), "case_id": estado.id})
    if hash_entrada is None and (saida / "f7_entrada.md").exists():
        hash_entrada = hashlib.sha256((saida / "f7_entrada.md").read_bytes()).hexdigest()
    (saida / "revisao.json").write_text(json.dumps({"hash_entrada": hash_entrada, "revisao": r.model_dump()},
                                                   indent=2, ensure_ascii=False), encoding="utf-8")
    arq_dec = saida / "revisao_decisoes.json"
    dec = json.loads(_ler(arq_dec) or "{}")
    for a in r.alertas:  # decisões anteriores do analista são mantidas (mesmo id)
        dec.setdefault(a.id, {"severidade": a.severidade, "achado": a.achado, "status": None, "nota": None})
    dec.setdefault("_leia", "status: resolvido | aceito_risco | descartado; nota livre. Alerta 'alta' aberto "
                            "bloqueia o relatório.")
    arq_dec.write_text(json.dumps(dec, indent=2, ensure_ascii=False), encoding="utf-8")
    (saida / "revisao.md").write_text(_md(estado.empresa, r, dec), encoding="utf-8")
    graves = sum(1 for a in r.alertas if a.severidade == "alta")
    estado.registrar("F7", "revisado", f"parecer {r.parecer}; {len(r.alertas)} alerta(s), {graves} grave(s)")
    (saida / "state.json").write_text(estado.model_dump_json(indent=2), encoding="utf-8")
    return r


def rodar_f7(pasta_empresa: str | Path, modo: str = "claude-code", modelo: str | None = None,
             executor=executar_claude_code, forcar: bool = False) -> tuple[Revisao | Path, bool]:
    """→ (revisão ou caminho do pacote no modo manual, reaproveitada?). Pacote igual ao da última revisão = sem nova
    chamada ao agente (economia de tokens), salvo forcar=True."""
    pasta = Path(pasta_empresa)
    saida = pasta / PASTA_SAIDA
    texto = montar_entrada(pasta)
    (saida / "f7_entrada.md").write_text(texto, encoding="utf-8")
    h = hashlib.sha256(texto.encode("utf-8")).hexdigest()
    anterior = json.loads(_ler(saida / "revisao.json") or "{}")
    if not forcar and anterior.get("hash_entrada") == h and anterior.get("revisao"):
        return Revisao.model_validate(anterior["revisao"]), True
    if modo == "manual":
        return saida / "f7_entrada.md", False
    if modo == "api":
        raise ErroJulgamento("modo 'api' ainda não implementado — use claude-code ou manual.")
    resposta = executor(texto, modelo=modelo)
    (saida / "f7_saida_bruta.txt").write_text(resposta, encoding="utf-8")
    (saida / "f7_saida.json").write_text(json.dumps(extrair_json(resposta), indent=2, ensure_ascii=False),
                                         encoding="utf-8")
    return importar_f7(pasta, h), False
