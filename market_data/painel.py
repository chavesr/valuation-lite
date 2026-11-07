"""Painel de mercado único para todos os cases: market_data/painel/painel_atual.json (+ uma cópia por dia de mudança).

Cada dado é buscado de novo só quando "vence" pelo calendário do Banco Central (metodologia/parametros_mercado.json:
diária, semanal às segundas para o Focus, mensal a partir do dia N). Sem internet, mantém o último valor e avisa.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

from market_data import bcb

PASTA = Path(__file__).resolve().parent / "painel"


def _ultima_ocorrencia(regra: str, hoje: date) -> date:
    """Data mais recente (≤ hoje) em que o dado é publicado, pela regra do calendário."""
    if regra == "diaria":
        return hoje
    if regra.startswith("semanal"):
        return hoje - timedelta(days=hoje.weekday())  # segunda-feira desta semana
    if regra.startswith("mensal:"):
        dia = int(regra.split(":")[1])
        if hoje.day >= dia:
            return hoje.replace(day=dia)
        anterior = hoje.replace(day=1) - timedelta(days=1)
        return anterior.replace(day=min(dia, anterior.day))
    raise ValueError(f"regra de calendário desconhecida: {regra}")


def vencido(item: dict | None, regra: str, hoje: date) -> bool:
    if not item or not item.get("consultado_em"):
        return True
    return date.fromisoformat(item["consultado_em"]) < _ultima_ocorrencia(regra, hoje)


def ler_painel() -> dict:
    arq = PASTA / "painel_atual.json"
    if arq.exists():
        return json.loads(arq.read_text(encoding="utf-8"))
    return {"sgs": {}, "focus": {}, "avisos": []}


def atualizar_painel(forcar: bool = False, hoje: date | None = None, timeout: float = 20.0) -> dict:
    """Atualiza só o que venceu e grava. Retorna o painel com 'atualizados' (o que mudou nesta chamada)."""
    hoje = hoje or date.today()
    p = bcb.carregar_parametros()
    painel = ler_painel()
    painel["avisos"], atualizados = [], []
    for grupo, catalogo, buscar in (
            ("sgs", p["sgs"]["series"], lambda c: bcb.sgs_ultimo(c["codigo"], timeout, p)),
            ("focus", p["focus"]["indicadores"], lambda c: bcb.focus_anual(c["nome"], timeout, p))):
        for nome, cfg in catalogo.items():
            atual = painel[grupo].get(nome)
            if not forcar and not vencido(atual, cfg["atualizacao"], hoje):
                continue
            try:
                novo = buscar(cfg)
            except bcb.DadoIndisponivel as e:
                painel["avisos"].append(f"{nome}: sem atualização ({e}); mantido o valor de "
                                        f"{(atual or {}).get('consultado_em', 'nunca')}")
                continue
            extras = {k: cfg[k] for k in ("unidade", "descricao") if k in cfg}
            painel[grupo][nome] = {**novo, **extras, "consultado_em": hoje.isoformat()}
            if not atual or {k: atual.get(k) for k in ("valor", "data", "medianas")} != \
                    {k: novo.get(k) for k in ("valor", "data", "medianas")}:
                atualizados.append(nome)
    painel["coletado_em"] = hoje.isoformat()
    PASTA.mkdir(parents=True, exist_ok=True)
    texto = json.dumps({k: v for k, v in painel.items() if k != "atualizados"}, indent=2, ensure_ascii=False)
    (PASTA / "painel_atual.json").write_text(texto, encoding="utf-8")
    if atualizados:  # histórico: uma cópia por dia em que algum dado mudou (rastro de qual número entrou em cada laudo)
        (PASTA / f"painel_{hoje.isoformat()}.json").write_text(texto, encoding="utf-8")
    painel["atualizados"] = atualizados
    return painel
