"""Gráficos do relatório (SVG)."""

from relatorio.graficos import linha_do_tempo


def test_linha_do_tempo_nunca_corta_o_marco():
    """12/11/2026 (Emunah): marcos de até 80 caracteres (limite da F5) aparecem inteiros, sem reticências."""
    marcos = ["Fundação da Bona & Domingos (Simples), braço administrativo e patrimonial da clínica",
              "Laudo avalia o imóvel de Piraquara em R$ 3,0 mi (construção não averbada no RGI)"]
    eventos = [(2012 + i, marcos[i % 2][:80]) for i in range(8)]
    svg = linha_do_tempo(eventos)
    assert "…" not in svg
    for palavra in ("patrimonial", "averbada"):
        assert palavra in svg
    curto = linha_do_tempo([(2020, "Fundação"), (2024, "Mudança de sede")])
    assert 'height="168"' in curto or "168" in curto  # sem marcos longos, o tamanho de sempre
