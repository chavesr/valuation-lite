"""Medição de concordância da F5 com o gabarito da ND (metodologia/calibracao/gabarito_f5.json).

Para cada caso de referência: copia a pasta de documentos para um diretório de trabalho (nunca grava na pasta
original), roda abrir → normalizar → F5 sem a referência do próprio caso (leave-one-out) e compara as notas.
O mapa caso → pasta fica em cases/calibracao.json (fora do git, pois tem nomes de clientes).
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from julgamento.esquemas import DIMENSOES_JULGAMENTO

RAIZ = Path(__file__).resolve().parents[1]
GABARITO = RAIZ / "metodologia" / "calibracao" / "gabarito_f5.json"
MAPA = RAIZ / "cases" / "calibracao.json"
# 04_reports guarda o que a ND produziu (relatório, briefing, modelo, atas): o agente não pode ver o gabarito.
# Atalhos do Google (.gdoc/.gsheet) não são copiáveis; _valuation antigo é descartado.
IGNORAR = ("04_reports", "_valuation", "*.gdoc", "*.gsheet", "*.gslides", "desktop.ini")


def _copiar_entrevistas(origem: Path, copia: Path) -> None:
    """Briefings e kick-offs são entrada (o que o dono contou), mesmo guardados em 04_reports."""
    from captacao.parsers.entrevista import FORMATOS, eh_entrevista

    destino = copia / "03_fundamentos" / "entrevistas"
    for arq in (origem / "04_reports").rglob("*") if (origem / "04_reports").exists() else []:
        if arq.is_file() and arq.suffix.lower() in FORMATOS and eh_entrevista(arq.name):
            destino.mkdir(parents=True, exist_ok=True)
            shutil.copy2(arq, destino / arq.name)


def _corrigir_extensoes(copia: Path) -> None:
    """Na cópia de trabalho (nunca na pasta do cliente), planilha salva como .pdf volta a ser .xlsx."""
    from tarantino.inventario import formato_real

    for arq in list(copia.rglob("*.pdf")):
        if formato_real(arq) == "zip":
            arq.rename(arq.with_suffix(".xlsx"))


def carregar_gabarito() -> dict[str, dict[str, int]]:
    return json.loads(GABARITO.read_text(encoding="utf-8"))["casos"]


def comparar(gabarito: dict[str, dict[str, int]], propostas: dict[str, dict[str, int]]) -> dict:
    """→ métricas por caso e no total (só casos presentes nos dois lados)."""
    linhas, exatas, perto, total, erro_abs = [], 0, 0, 0, 0
    for caso in sorted(set(gabarito) & set(propostas)):
        for dim in DIMENSOES_JULGAMENTO:
            g, p = gabarito[caso][dim], propostas[caso][dim]
            d = p - g
            linhas.append({"caso": caso, "dimensao": dim, "gabarito": g, "agente": p, "diferenca": d})
            total += 1
            exatas += d == 0
            perto += abs(d) <= 1
            erro_abs += abs(d)
    return {"notas": total, "exatas": exatas, "ate_1_ponto": perto,
            "erro_medio": round(erro_abs / total, 2) if total else None,
            "vies_medio": round(sum(l["diferenca"] for l in linhas) / total, 2) if total else None,
            "linhas": linhas}


def rodar_calibracao(mapa: dict[str, str], destino: Path, executor=None, so: list[str] | None = None) -> dict:
    """Roda a F5 em cópias das pastas do mapa e compara com o gabarito. Grava destino/calibracao.json."""
    from tarantino import case as case_mod
    from tarantino.case import abrir_case
    from tarantino.normalizar import normalizar_case
    from tarantino.qualitativo import rodar_f5

    destino.mkdir(parents=True, exist_ok=True)
    case_mod.REGISTRO = destino / "registro.json"  # não mistura os ids de calibração com os cases reais
    gab = carregar_gabarito()
    propostas, erros, detalhes = {}, {}, {}
    for caso, origem in mapa.items():
        if so and caso not in so:
            continue
        copia = destino / caso
        if not copia.exists():
            shutil.copytree(origem, copia, ignore=shutil.ignore_patterns(*IGNORAR))
            _copiar_entrevistas(Path(origem), copia)
            _corrigir_extensoes(copia)
        try:
            abrir_case(copia)
            normalizar_case(copia)
            kwargs = {"excluir_referencia": caso}
            if executor:
                kwargs["executor"] = executor
            q = rodar_f5(copia, **kwargs)
            propostas[caso] = {n.dimensao: n.nota for n in q.notas_score}
            detalhes[caso] = {n.dimensao: {"nota": n.nota, "confianca": n.confianca, "justificativa": n.justificativa}
                              for n in q.notas_score}
        except Exception as e:  # um caso com problema não derruba a medição dos outros
            erros[caso] = f"{type(e).__name__}: {e}"
    resultado = {**comparar(gab, propostas), "erros": erros, "detalhes": detalhes}
    (destino / "calibracao.json").write_text(json.dumps(resultado, indent=2, ensure_ascii=False), encoding="utf-8")
    return resultado
