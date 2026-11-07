"""Extrato bancário exportado em planilha (.xlsx/.xls) — internet banking "Extrato de lançamentos".

Formato típico: linhas de identificação (Nome, Agência, Conta, Período) e depois a tabela
"Data | Lançamento/Histórico | (CPF/CNPJ) | Valor | (Saldo)" — às vezes com Crédito e Débito separados.
Zero tokens.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from pathlib import Path

from captacao.parsers.relatorios_erp import abrir_planilha
from captacao.schemas import ExtratoConta, Metodo, Proveniencia, Transacao
from captacao.util import apenas_digitos, normalizar_texto, parse_numero_br

_SALDO = re.compile(r"^(SALDO|S A L D O|SDO)\b")


class ExtratoPlanilhaNaoLido(Exception):
    pass


def _cab(linha: list) -> list[str]:
    return [normalizar_texto(str(c or "")) for c in linha]


def achar_tabela(linhas: list[list]) -> tuple[int, dict[str, int]] | None:
    """Linha de cabeçalho com DATA + (LANÇAMENTO|HISTÓRICO|DESCRIÇÃO) + VALOR (ou CRÉDITO/DÉBITO)."""
    for i, linha in enumerate(linhas[:40]):
        cab = _cab(linha)
        def col(*nomes):
            return next((j for j, c in enumerate(cab) if any(c.startswith(n) for n in nomes)), None)
        data, desc = col("DATA"), col("LANCAMENTO", "HISTORICO", "DESCRICAO")
        valor, cred, deb = col("VALOR"), col("CREDITO"), col("DEBITO")
        if data is not None and desc is not None and (valor is not None or (cred is not None and deb is not None)):
            return i, {k: v for k, v in {"data": data, "desc": desc, "valor": valor, "credito": cred, "debito": deb,
                                          "doc": col("CPF", "CNPJ", "DOCUMENTO"), "saldo": col("SALDO")}.items()
                       if v is not None}
    return None


def eh_extrato_planilha(abas: dict[str, list[list]]) -> bool:
    return any(achar_tabela(l) for l in abas.values())


def _data(v) -> date | None:
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    m = re.match(r"(\d{2})/(\d{2})/(\d{4})", str(v or "").strip())
    return date(int(m.group(3)), int(m.group(2)), int(m.group(1))) if m else None


def _num(v) -> float | None:
    if v in (None, ""):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip()
    if re.fullmatch(r"-?\d+(\.\d+)?", s):  # '-60000.0' (número gravado como texto em formato americano)
        return float(s)
    try:
        return parse_numero_br(s)
    except ValueError:
        return None


def ler_extrato_planilha(caminho: str | Path) -> ExtratoConta:
    caminho = Path(caminho)
    abas = abrir_planilha(caminho)
    for nome, linhas in abas.items():
        achado = achar_tabela(linhas)
        if achado:
            break
    else:
        raise ExtratoPlanilhaNaoLido("tabela de lançamentos não encontrada")
    i_cab, cols = achado
    meta = {normalizar_texto(str(l[0] or "")).rstrip(":"): str(l[1] or "").strip()
            for l in linhas[:i_cab] if len(l) > 1 and l[0]}
    transacoes = []
    for j, l in enumerate(linhas[i_cab + 1:], start=i_cab + 2):
        d = _data(l[cols["data"]]) if cols["data"] < len(l) else None
        desc = str(l[cols["desc"]] or "").strip() if cols["desc"] < len(l) else ""
        if not d or not desc or _SALDO.match(normalizar_texto(desc)):
            continue
        if "valor" in cols:
            valor = _num(l[cols["valor"]])
        else:
            cred, deb = _num(l[cols["credito"]]) or 0.0, _num(l[cols["debito"]]) or 0.0
            valor = cred - abs(deb)
        if valor is None:
            continue
        doc = apenas_digitos(str(l[cols["doc"]] or "")) if "doc" in cols and cols["doc"] < len(l) else ""
        transacoes.append(Transacao(data=d, valor=valor, descricao=re.sub(r"\s+", " ", desc),
                                    contraparte_doc=doc or None, id_banco=f"linha-{j}"))
    if not transacoes:
        raise ExtratoPlanilhaNaoLido("nenhum lançamento na tabela")
    transacoes.sort(key=lambda t: t.data)
    return ExtratoConta(
        banco=meta.get("BANCO") or None, conta=meta.get("CONTA") or None,
        transacoes=transacoes,
        proveniencia=Proveniencia(arquivo=caminho.name, metodo=Metodo.PARSER,
                                  localizacao=f"{nome}; titular {meta.get('NOME', '?')}; agência {meta.get('AGENCIA', '?')}"))
