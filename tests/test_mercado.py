"""D3 — dados de mercado (BCB/Focus) sem internet: Selic de referência e fotografia congelada por case."""

import json

import pytest

from market_data import bcb
from market_data.bcb import DadoIndisponivel, selic_referencia

PAINEL = {
    "coletado_em": "2026-11-07",
    "sgs": {"selic_meta": {"valor": 13.75, "data": "09/12/2026"}},
    "focus": {"selic": {"data": "2026-10-30",
                        "medianas": {"2026": 13.5, "2027": 12.5, "2028": 11.0, "2029": 10.25, "2030": 10.0}}},
    "avisos": [],
}


def test_selic_referencia_media_dos_anos_do_horizonte():
    v, fonte = selic_referencia(PAINEL, 2026, 4)
    assert v == pytest.approx((12.5 + 11.0 + 10.25 + 10.0) / 4 / 100, abs=1e-4)  # 10,94%
    assert "2027–2030" in fonte and "2026-10-30" in fonte


def test_anos_alem_do_ultimo_publicado_repetem_o_ultimo():
    v, fonte = selic_referencia(PAINEL, 2026, 5)
    assert v == pytest.approx((12.5 + 11.0 + 10.25 + 10.0 + 10.0) / 5 / 100, abs=1e-4)
    assert "2031 = último ano publicado (2030)" in fonte


def test_sem_focus_usa_selic_meta_e_sem_nada_falha():
    v, fonte = selic_referencia({**PAINEL, "focus": {}}, 2026, 4)
    assert v == 0.1375 and "Focus indisponível" in fonte
    with pytest.raises(DadoIndisponivel):
        selic_referencia({"focus": {}, "sgs": {}}, 2026, 4)


def test_cache_sem_internet_usa_o_ultimo_disponivel(tmp_path, monkeypatch):
    monkeypatch.setattr(bcb, "CACHE", tmp_path)
    (tmp_path / "sgs_432.json").write_text(json.dumps({"consultado_em": "2026-11-01",
                                                       "dado": {"data": "05/11/2026", "valor": "13.75"}}))

    def sem_internet(url, timeout):
        raise OSError("sem rede")

    monkeypatch.setattr(bcb, "_baixar_json", sem_internet)
    r = bcb.sgs_ultimo(432)
    assert r["valor"] == 13.75 and "cache de 2026-11-01" in r["origem"]
    with pytest.raises(DadoIndisponivel):
        bcb.sgs_ultimo(433)


def test_fotografia_do_case_fica_congelada_ate_atualizar(tmp_path, monkeypatch):
    from tarantino import mercado

    chamadas = []
    monkeypatch.setattr(mercado, "coletar_painel", lambda: chamadas.append(1) or dict(PAINEL))
    (tmp_path / "_valuation").mkdir()
    assert mercado.obter_mercado(tmp_path)["focus"]["selic"]["data"] == "2026-10-30"
    mercado.obter_mercado(tmp_path)
    assert len(chamadas) == 1  # segunda vez lê _valuation/mercado.json
    mercado.obter_mercado(tmp_path, atualizar=True)
    assert len(chamadas) == 2
    valores, fontes = mercado.selic_por_horizonte(PAINEL)
    assert set(valores) == {3, 4, 5} and valores[3] == pytest.approx(0.1125, abs=1e-4)
