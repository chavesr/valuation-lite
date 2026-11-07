"""Leitor genérico de extratos CSV exportados por bancos brasileiros.

Detecta automaticamente: linha de cabeçalho (ignora preâmbulos), separador, codificação e colunas
(data, descrição, valor único ou crédito/débito). Ignora linhas de saldo.
"""

from __future__ import annotations

import io
import re
from pathlib import Path

import pandas as pd

from captacao.schemas import ExtratoConta, Metodo, Proveniencia, Transacao
from captacao.util import normalizar_texto, parse_numero_br

_ALIASES = {
    "data": ["data", "data lancamento", "data movimento", "data mov", "dt lancamento", "dt"],
    "descricao": ["descricao", "historico", "lancamento", "detalhes", "memo", "descricao lancamento"],
    "valor": ["valor", "valor r", "montante", "valor lancamento"],
    "credito": ["credito", "entrada", "entradas", "credito r"],
    "debito": ["debito", "saida", "saidas", "debito r"],
}


class FormatoNaoReconhecido(ValueError):
    pass


def _norm_coluna(nome: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", normalizar_texto(str(nome)).lower())).strip()


def _mapear_colunas(colunas: list[str]) -> dict[str, str]:
    normalizadas = {c: _norm_coluna(c) for c in colunas}
    mapa: dict[str, str] = {}
    for campo, aliases in _ALIASES.items():
        for original, norm in normalizadas.items():
            if original in mapa.values():
                continue
            if norm in aliases or any(norm.startswith(a + " ") for a in aliases):
                mapa[campo] = original
                break
    return mapa


def _ler_linhas(caminho: Path) -> list[str]:
    bruto = caminho.read_bytes()
    for codificacao in ("utf-8-sig", "cp1252"):
        try:
            return bruto.decode(codificacao).splitlines()
        except UnicodeDecodeError:
            continue
    return bruto.decode("latin-1").splitlines()


def _achar_cabecalho(linhas: list[str]) -> tuple[int, str]:
    for i, linha in enumerate(linhas[:40]):
        separador = max([";", ",", "\t"], key=linha.count)
        celulas = [c.strip().strip('"') for c in linha.split(separador)]
        mapa = _mapear_colunas(celulas)
        if "data" in mapa and "descricao" in mapa and ("valor" in mapa or "credito" in mapa):
            return i, separador
    raise FormatoNaoReconhecido("cabeçalho do extrato não encontrado (data/descrição/valor)")


def ler_csv_extrato(
    caminho: str | Path,
    cnpj_titular: str | None = None,
    banco: str | None = None,
    conta: str | None = None,
) -> ExtratoConta:
    caminho = Path(caminho)
    linhas = _ler_linhas(caminho)
    inicio, separador = _achar_cabecalho(linhas)
    df = pd.read_csv(io.StringIO("\n".join(linhas[inicio:])), sep=separador, dtype=str,
                     keep_default_na=False)
    mapa = _mapear_colunas(list(df.columns))

    datas = pd.to_datetime(df[mapa["data"]], dayfirst=True, errors="coerce")
    transacoes: list[Transacao] = []
    for idx, linha in df.iterrows():
        if pd.isna(datas[idx]):
            continue
        descricao = str(linha[mapa["descricao"]]).strip()
        if "SALDO" in normalizar_texto(descricao):
            continue
        if "valor" in mapa:
            valor = parse_numero_br(linha[mapa["valor"]])
        else:
            credito = parse_numero_br(linha[mapa["credito"]]) or 0.0
            debito = parse_numero_br(linha.get(mapa.get("debito", ""), None)) or 0.0
            valor = abs(credito) - abs(debito)
        if not valor:
            continue
        transacoes.append(
            Transacao(
                data=datas[idx].date(),
                valor=valor,
                descricao=descricao or "(sem descrição)",
                id_banco=f"linha-{inicio + idx + 2}",
            )
        )

    return ExtratoConta(
        cnpj_titular=cnpj_titular,
        banco=banco,
        conta=conta,
        transacoes=transacoes,
        proveniencia=Proveniencia(arquivo=str(caminho), metodo=Metodo.PARSER, confianca="alta"),
    )
