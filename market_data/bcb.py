"""Dados de mercado do Banco Central: séries do SGS e expectativas do Focus (API Olinda).

Só dado público: nenhuma informação de case sai do computador. Cache por dia em market_data/cache/; sem internet,
usa o último cache disponível (e avisa). Os valores ficam em fração quando são taxas (% → /100), exceto câmbio.
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
PARAMETROS = RAIZ / "metodologia" / "parametros_mercado.json"
CACHE = Path(__file__).resolve().parent / "cache"


class DadoIndisponivel(RuntimeError):
    pass


def carregar_parametros() -> dict:
    return json.loads(PARAMETROS.read_text(encoding="utf-8"))


def _baixar_json(url: str, timeout: float) -> object:
    req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "valuation-lite"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _com_cache(chave: str, buscar, timeout: float) -> tuple[object, str]:
    """→ (dado, origem). Usa o cache de hoje; senão busca; se falhar, usa o último cache (avisando na origem)."""
    arq = CACHE / f"{chave}.json"
    antigo = json.loads(arq.read_text(encoding="utf-8")) if arq.exists() else None
    if antigo and antigo.get("consultado_em") == date.today().isoformat():
        return antigo["dado"], "Banco Central (cache de hoje)"
    try:
        dado = buscar(timeout)
    except Exception as e:  # noqa: BLE001 — sem internet ou API fora do ar
        if antigo:
            return antigo["dado"], f"Banco Central (cache de {antigo['consultado_em']}; consulta falhou)"
        raise DadoIndisponivel(f"{chave}: {e}") from e
    CACHE.mkdir(parents=True, exist_ok=True)
    arq.write_text(json.dumps({"consultado_em": date.today().isoformat(), "dado": dado}, ensure_ascii=False),
                   encoding="utf-8")
    return dado, "Banco Central"


def sgs_ultimo(codigo: int, timeout: float = 15.0, p: dict | None = None) -> dict:
    """Último valor de uma série do SGS → {"valor", "data", "origem"} (valor como publicado, ex.: 13.75)."""
    p = p or carregar_parametros()
    url = p["sgs"]["url"].format(codigo=codigo, n=1)
    dado, origem = _com_cache(f"sgs_{codigo}", lambda t: _baixar_json(url, t)[-1], timeout)
    return {"valor": float(str(dado["valor"]).replace(",", ".")), "data": dado["data"], "origem": f"{origem}, SGS {codigo}"}


def focus_anual(indicador: str, timeout: float = 20.0, p: dict | None = None) -> dict:
    """Medianas do relatório Focus mais recente → {"data", "medianas": {"2027": 12.5, ...}, "origem"}."""
    p = p or carregar_parametros()
    filtro = f"Indicador eq '{indicador}' and baseCalculo eq 0"
    query = urllib.parse.urlencode({"$top": "40", "$filter": filtro, "$orderby": "Data desc", "$format": "json",
                                    "$select": "Indicador,Data,DataReferencia,Mediana"}, quote_via=urllib.parse.quote)

    def buscar(t):
        linhas = _baixar_json(f"{p['focus']['url']}?{query}", t)["value"]
        if not linhas:
            raise DadoIndisponivel(f"Focus sem dados para {indicador}")
        ultima = max(x["Data"] for x in linhas)
        return {"data": ultima, "medianas": {x["DataReferencia"]: x["Mediana"] for x in linhas if x["Data"] == ultima}}

    chave = "focus_" + "".join(c for c in indicador.lower() if c.isalnum())
    dado, origem = _com_cache(chave, buscar, timeout)
    return {**dado, "origem": f"{origem}, Focus (mediana de {dado['data']})"}


def coletar_painel(timeout: float = 20.0) -> dict:
    """Fotografia do mercado: todas as séries SGS e indicadores Focus do catálogo. Falhas viram avisos."""
    p = carregar_parametros()
    painel = {"coletado_em": date.today().isoformat(), "sgs": {}, "focus": {}, "avisos": []}
    for nome, s in p["sgs"]["series"].items():
        try:
            painel["sgs"][nome] = {**sgs_ultimo(s["codigo"], timeout, p), "unidade": s["unidade"],
                                   "descricao": s["descricao"]}
        except DadoIndisponivel as e:
            painel["avisos"].append(str(e))
    for nome, f in p["focus"]["indicadores"].items():
        try:
            painel["focus"][nome] = {**focus_anual(f["nome"], timeout, p), "unidade": f["unidade"]}
        except DadoIndisponivel as e:
            painel["avisos"].append(str(e))
    return painel


def selic_referencia(painel: dict, ano_base: int, horizonte: int) -> tuple[float, str]:
    """Selic bruta de referência (fração): média das medianas Focus de fim de ano nos `horizonte` anos seguintes a
    `ano_base`; anos além do último publicado repetem o último. Sem Focus, cai para a Selic meta vigente."""
    focus = (painel.get("focus") or {}).get("selic")
    if focus and focus.get("medianas"):
        med = {int(a): v for a, v in focus["medianas"].items()}
        ultimo = max(med)
        anos = list(range(ano_base + 1, ano_base + horizonte + 1))
        valores = [med.get(a, med[ultimo] if a > ultimo else None) for a in anos]
        valores = [v for v in valores if v is not None]
        if valores:
            media = sum(valores) / len(valores)
            repetidos = [a for a in anos if a > ultimo]
            extra = f"; {', '.join(map(str, repetidos))} = último ano publicado ({ultimo})" if repetidos else ""
            return round(media / 100, 4), (f"média Focus {anos[0]}–{anos[-1]} da Selic de fim de ano "
                                           f"(mediana de {focus['data']}){extra}")
    meta = (painel.get("sgs") or {}).get("selic_meta")
    if meta:
        return round(meta["valor"] / 100, 4), f"Selic meta vigente {meta['data']} (Focus indisponível)"
    raise DadoIndisponivel("sem Focus nem Selic meta para a taxa de desconto")
