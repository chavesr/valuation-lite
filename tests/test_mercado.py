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


def test_calendario_de_vencimento():
    from datetime import date

    from market_data.painel import vencido

    qua = date(2026, 11, 11)  # quarta-feira
    assert vencido({"consultado_em": "2026-11-10"}, "diaria", qua)
    assert not vencido({"consultado_em": "2026-11-11"}, "diaria", qua)
    assert not vencido({"consultado_em": "2026-11-09"}, "semanal:segunda", qua)  # já pegou a Focus desta segunda
    assert vencido({"consultado_em": "2026-11-06"}, "semanal:segunda", qua)
    assert not vencido({"consultado_em": "2026-10-20"}, "mensal:12", qua)  # IPCA de novembro ainda não saiu
    assert vencido({"consultado_em": "2026-10-20"}, "mensal:12", date(2026, 11, 12))
    assert vencido(None, "mensal:28", qua)


def _painel_falso(tmp_path, monkeypatch, selic_meta=13.75, focus_2027=12.5):
    from market_data import painel

    monkeypatch.setattr(painel, "PASTA", tmp_path / "painel")
    chamadas = []

    def sgs(codigo, timeout=0, p=None):
        chamadas.append(codigo)
        return {"valor": selic_meta if codigo == 432 else 1.0, "data": "01/11/2026", "origem": "teste"}

    def focus(nome, timeout=0, p=None):
        chamadas.append(nome)
        med = {"2026": 13.5, "2027": focus_2027, "2028": 11.0, "2029": 10.25, "2030": 10.0}
        return {"data": "2026-10-30", "medianas": med, "origem": "teste"}

    monkeypatch.setattr(bcb, "sgs_ultimo", sgs)
    monkeypatch.setattr(bcb, "focus_anual", focus)
    return painel, chamadas


def test_painel_so_busca_o_que_venceu_e_guarda_historico(tmp_path, monkeypatch):
    from datetime import date

    painel, chamadas = _painel_falso(tmp_path, monkeypatch)
    p = painel.atualizar_painel(hoje=date(2026, 11, 11))
    assert len(chamadas) == 10 and set(p["atualizados"]) >= {"selic_meta", "selic"}
    assert (tmp_path / "painel" / "painel_2026-11-11.json").exists()
    chamadas.clear()
    p = painel.atualizar_painel(hoje=date(2026, 11, 12))  # quinta: só o diário (Selic meta e PTAX) e o IPCA do dia 12
    assert sorted(map(str, chamadas)) == ["1", "13522", "432", "433"]
    assert p["atualizados"] == []  # valores iguais: sem nova cópia no histórico
    assert not (tmp_path / "painel" / "painel_2026-11-12.json").exists()


def test_case_fica_congelado_e_e_avisado_quando_a_selic_muda(tmp_path, monkeypatch):
    from tarantino import mercado

    _painel_falso(tmp_path, monkeypatch)
    pasta = tmp_path / "case"
    (pasta / "_valuation").mkdir(parents=True)
    foto, atual = mercado.obter_mercado(pasta)
    assert (pasta / "_valuation" / "mercado.json").exists()
    assert mercado.mudancas(foto, atual, 4) == []

    _painel_falso(tmp_path, monkeypatch, selic_meta=14.25, focus_2027=14.0)
    novo_painel = mercado.atualizar_painel(forcar=True)
    foto2, atual2 = mercado.obter_mercado(pasta)  # o case continua com a fotografia antiga
    assert foto2["sgs"]["selic_meta"]["valor"] == 13.75 and atual2["sgs"]["selic_meta"]["valor"] == 14.25
    avisos = mercado.mudancas(foto2, novo_painel, 4)
    assert any("Selic meta 13.75% → 14.25%" in a for a in avisos)
    assert any("Selic de referência" in a for a in avisos)
    foto3, _ = mercado.obter_mercado(pasta, atualizar=True)  # o analista escolheu atualizar
    assert foto3["sgs"]["selic_meta"]["valor"] == 14.25
