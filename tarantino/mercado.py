"""Fotografia do mercado por case (_valuation/mercado.json): Selic, IPCA, câmbio, crédito PJ (SGS) e Focus.

Fica congelada na data do valuation para o relatório não mudar ao rodar de novo; `atualizar=True` coleta outra.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from market_data.bcb import DadoIndisponivel, coletar_painel, selic_referencia
from tarantino.inventario import PASTA_SAIDA

HORIZONTES = (3, 4, 5)


def obter_mercado(pasta_empresa: str | Path, atualizar: bool = False) -> dict:
    arq = Path(pasta_empresa) / PASTA_SAIDA / "mercado.json"
    if arq.exists() and not atualizar:
        return json.loads(arq.read_text(encoding="utf-8"))
    painel = coletar_painel()
    arq.write_text(json.dumps(painel, indent=2, ensure_ascii=False), encoding="utf-8")
    return painel


def selic_por_horizonte(painel: dict, ano_base: int | None = None) -> tuple[dict[int, float], dict[int, str]]:
    """{3: Selic média Focus 3 anos, 4: …, 5: …} a partir do ano seguinte à data da fotografia."""
    ano = ano_base or int((painel.get("coletado_em") or date.today().isoformat())[:4])
    valores, fontes = {}, {}
    for h in HORIZONTES:
        valores[h], fontes[h] = selic_referencia(painel, ano, h)
    return valores, fontes


__all__ = ["obter_mercado", "selic_por_horizonte", "DadoIndisponivel"]
