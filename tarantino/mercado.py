"""Mercado por case: _valuation/mercado.json é a fotografia do painel único (market_data/painel/) na data do valuation.

Fica congelada para o relatório não mudar ao rodar de novo. A cada avaliação o painel é conferido (e atualizado pelo
calendário do Banco Central); se a Selic mudou, o analista é avisado do impacto e decide se atualiza o case.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from market_data.bcb import DadoIndisponivel, carregar_parametros, selic_referencia
from market_data.painel import atualizar_painel
from tarantino.inventario import PASTA_SAIDA

HORIZONTES = (3, 4, 5)


def obter_mercado(pasta_empresa: str | Path, atualizar: bool = False) -> tuple[dict, dict]:
    """→ (fotografia do case, painel atual). Case sem fotografia (ou atualizar=True) recebe a cópia do painel atual."""
    arq = Path(pasta_empresa) / PASTA_SAIDA / "mercado.json"
    painel = atualizar_painel()
    if arq.exists() and not atualizar:
        return json.loads(arq.read_text(encoding="utf-8")), painel
    foto = {k: v for k, v in painel.items() if k != "atualizados"}
    arq.write_text(json.dumps(foto, indent=2, ensure_ascii=False), encoding="utf-8")
    return foto, painel


def selic_por_horizonte(painel: dict, ano_base: int | None = None) -> tuple[dict[int, float], dict[int, str]]:
    """{3: Selic média Focus 3 anos, 4: …, 5: …} a partir do ano seguinte à data da fotografia."""
    ano = ano_base or int((painel.get("coletado_em") or date.today().isoformat())[:4])
    valores, fontes = {}, {}
    for h in HORIZONTES:
        valores[h], fontes[h] = selic_referencia(painel, ano, h)
    return valores, fontes


def mudancas(foto: dict, painel: dict, horizonte: int) -> list[str]:
    """O que mudou no mercado desde a fotografia do case que mexe na taxa (vazio = nada relevante)."""
    out = []
    a, b = (foto.get("sgs") or {}).get("selic_meta"), (painel.get("sgs") or {}).get("selic_meta")
    if a and b and a["valor"] != b["valor"]:
        out.append(f"Selic meta {a['valor']:.2f}% → {b['valor']:.2f}% (Copom)")
    try:
        ano = int((foto.get("coletado_em") or date.today().isoformat())[:4])
        ref_a, _ = selic_referencia(foto, ano, horizonte)
        ref_b, _ = selic_referencia(painel, ano, horizonte)
    except DadoIndisponivel:
        return out
    limite = carregar_parametros()["calendario"]["aviso_variacao_selic_referencia"]
    if abs(ref_b - ref_a) >= limite - 1e-9:
        out.append(f"Selic de referência (Focus, {horizonte} anos) {ref_a:.2%} → {ref_b:.2%}")
    return out


__all__ = ["obter_mercado", "selic_por_horizonte", "mudancas", "DadoIndisponivel"]
