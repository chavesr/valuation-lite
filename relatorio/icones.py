"""Ícones de linha (SVG inline, 24×24, traço 2) usados nos cartões e títulos de quadro. Custo zero: só código."""

from __future__ import annotations

_P = {
    "empresa": "M3 21h18M5 21V7l7-4 7 4v14M9 21v-6h6v6M9 10h.01M15 10h.01",
    "receita": "M4 19V5M4 19h16M8 16v-5M12 16V8M16 16v-3",
    "ebitda": "M3 17l6-6 4 4 8-8M15 7h6v6",
    "faixa": "M4 12h16M7 8v8M17 8v8M12 5v14",
    "relogio": "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM12 7v5l3 2",
    "divida": "M12 3v18M17 7H9.5a3 3 0 0 0 0 6h5a3 3 0 0 1 0 6H6",
    "positivo": "M20 6L9 17l-5-5",
    "alerta": "M12 3l10 18H2L12 3zM12 10v4M12 17h.01",
    "valor": "M3 6h18M3 12h12M3 18h7",
    "retorno": "M4 20V10M10 20V4M16 20v-8M22 20H2",
    "pessoas": "M16 19v-1a4 4 0 0 0-8 0v1M12 11a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM20 19v-1a3 3 0 0 0-3-3M4 19v-1a3 3 0 0 1 3-3",
    "local": "M12 21s-7-6.2-7-11a7 7 0 0 1 14 0c0 4.8-7 11-7 11zM12 12a2 2 0 1 0 0-4 2 2 0 0 0 0 4z",
    "calendario": "M4 6h16v14H4zM4 10h16M8 3v4M16 3v4",
    "documento": "M7 3h7l5 5v13H7zM14 3v5h5",
}


def icone(nome: str, cor: str = "#FF9900", tam: int = 14) -> str:
    return (f'<svg width="{tam}" height="{tam}" viewBox="0 0 24 24" fill="none" stroke="{cor}" stroke-width="2" '
            f'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="{_P[nome]}"/></svg>')
