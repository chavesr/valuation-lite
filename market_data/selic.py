"""Selic meta vigente (Banco Central, SGS série 432) com cache local. Dado público; nenhuma informação de case
é enviada. Sem internet, usa o cache; sem cache, o valor padrão de metodologia/parametros_valuation.json."""

from __future__ import annotations

import json
import urllib.request
from datetime import date
from pathlib import Path

CACHE = Path(__file__).resolve().parent / "cache" / "selic.json"
URL = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.432/dados/ultimos/1?formato=json"


def selic_atual(padrao: dict | None = None, timeout: float = 10.0) -> tuple[float, str, str]:
    """→ (taxa a.a. em fração, data de referência, fonte)."""
    if CACHE.exists():
        c = json.loads(CACHE.read_text(encoding="utf-8"))
        if c.get("consultado_em") == date.today().isoformat():
            return c["valor"], c["data"], "Banco Central (cache de hoje)"
    try:
        with urllib.request.urlopen(URL, timeout=timeout) as r:
            dado = json.loads(r.read().decode("utf-8"))[-1]
        valor = float(dado["valor"].replace(",", ".")) / 100
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        CACHE.write_text(json.dumps({"valor": valor, "data": dado["data"], "consultado_em": date.today().isoformat()}),
                         encoding="utf-8")
        return valor, dado["data"], "Banco Central (SGS 432)"
    except Exception:  # noqa: BLE001 — sem internet ou API fora do ar
        if CACHE.exists():
            c = json.loads(CACHE.read_text(encoding="utf-8"))
            return c["valor"], c["data"], f"Banco Central (cache de {c['consultado_em']})"
        p = padrao or {"valor": 0.1375, "data": "?"}
        return p["valor"], p["data"], "valor padrão dos parâmetros (sem consulta)"
