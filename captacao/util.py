"""Funções utilitárias de texto, números e datas no padrão brasileiro."""

from __future__ import annotations

import re
import unicodedata
from datetime import date


def normalizar_texto(texto: str) -> str:
    """Maiúsculas, sem acentos e com espaços simples."""
    sem_acento = unicodedata.normalize("NFKD", texto or "")
    sem_acento = "".join(c for c in sem_acento if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", sem_acento.upper()).strip()


def apenas_digitos(texto: str | None) -> str:
    return re.sub(r"\D", "", texto or "")


def parse_numero_br(valor: str | float | int | None) -> float | None:
    """Converte '1.234,56', '-1234.56', '(1.234,56)', '1.234,56 D', 'R$ 10,00' em float.

    Retorna None para valores vazios.
    """
    if valor is None:
        return None
    if isinstance(valor, (int, float)):
        return float(valor)
    s = str(valor).strip().upper().replace("R$", "").replace(" ", "")
    if s in {"", "-", "NAN", "NONE"}:
        return None

    negativo = False
    if s.startswith("(") and s.endswith(")"):
        negativo, s = True, s[1:-1]
    if s.endswith("D"):
        negativo, s = True, s[:-1]
    elif s.endswith("C"):
        s = s[:-1]
    if s.endswith("-"):
        negativo, s = True, s[:-1]
    if s.startswith("-"):
        negativo, s = (not negativo), s[1:]
    if s.startswith("+"):
        s = s[1:]

    if "," in s and "." in s:
        # o separador que aparece por último é o decimal
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        s = s.replace(",", ".")
    elif s.count(".") > 1 or re.fullmatch(r"\d{1,3}\.\d{3}", s):
        # '1.234' ou '1.234.567' → separador de milhar
        s = s.replace(".", "")

    numero = float(s)
    return -numero if negativo else numero


def brl(valor: float, casas: int = 2) -> str:
    """1234567.8 → '1.234.567,80' (padrão brasileiro)."""
    valor = round(valor, casas) or 0.0  # evita "-0"
    return f"{valor:,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def mes(d: date) -> str:
    """Chave de competência 'AAAA-MM'."""
    return f"{d.year:04d}-{d.month:02d}"


def meses_entre(inicio: str, fim: str) -> list[str]:
    """Lista de competências 'AAAA-MM' de inicio a fim, inclusive."""
    ano, m = map(int, inicio.split("-"))
    ano_fim, m_fim = map(int, fim.split("-"))
    saida = []
    while (ano, m) <= (ano_fim, m_fim):
        saida.append(f"{ano:04d}-{m:02d}")
        m += 1
        if m > 12:
            ano, m = ano + 1, 1
    return saida
