"""Carrega extratos bancários usando os parsers de nível 0 (OFX/CSV)."""

from __future__ import annotations

import json
from pathlib import Path

from captacao.classificacao import deduplicar
from captacao.parsers.csv_extrato import FormatoNaoReconhecido, ler_csv_extrato
from captacao.parsers.ofx import ler_ofx
from captacao.schemas import ExtratoConta

SUFIXOS_EXTRATO = {".ofx", ".csv"}


class ExtratoNaoLido(Exception):
    """O arquivo não pôde ser lido por código e segue para os níveis 1–2 do funil (PDF/OCR/IA)."""


def ler_extrato(arquivo: str | Path, info: dict | None = None) -> ExtratoConta:
    """Lê um .ofx ou .csv. `info` (opcional) traz {"cnpj", "banco", "conta"} do arquivo `contas.json`."""
    arquivo, info = Path(arquivo), info or {}
    sufixo = arquivo.suffix.lower()
    try:
        if sufixo == ".ofx":
            extrato = ler_ofx(arquivo, cnpj_titular=info.get("cnpj"))
            extrato.banco = info.get("banco", extrato.banco)
            extrato.conta = info.get("conta", extrato.conta)
            return extrato
        if sufixo == ".csv":
            return ler_csv_extrato(arquivo, info.get("cnpj"), info.get("banco"), info.get("conta"))
        if sufixo in {".xlsx", ".xls"}:
            from captacao.parsers.extrato_planilha import ExtratoPlanilhaNaoLido, ler_extrato_planilha

            try:
                extrato = ler_extrato_planilha(arquivo)
            except ExtratoPlanilhaNaoLido as erro:
                raise ExtratoNaoLido(str(erro)) from erro
            extrato.cnpj_titular = info.get("cnpj") or extrato.cnpj_titular
            extrato.banco = info.get("banco", extrato.banco)
            extrato.conta = info.get("conta", extrato.conta)
            return extrato
    except (FormatoNaoReconhecido, ValueError, KeyError) as erro:
        raise ExtratoNaoLido(str(erro)) from erro
    raise ExtratoNaoLido(f"formato {sufixo or 'sem extensão'} não suportado")


def ler_mapa_contas(pasta: Path) -> dict:
    """`contas.json` associa arquivos a titular/banco/conta:
    {"itau_cnpj1.csv": {"cnpj": "...", "banco": "341", "conta": "12345-6"}}"""
    arq = pasta / "contas.json"
    return json.loads(arq.read_text(encoding="utf-8")) if arq.exists() else {}


def carregar_extratos(pasta_bancario: str | Path) -> tuple[list[ExtratoConta], list[str]]:
    """Lê todos os .ofx e .csv da pasta (recursivo). Retorna (extratos, pendências)."""
    pasta = Path(pasta_bancario)
    mapa_contas = ler_mapa_contas(pasta)
    extratos: list[ExtratoConta] = []
    pendencias: list[str] = []
    for arquivo in sorted(pasta.rglob("*")):
        if not arquivo.is_file() or arquivo.name == "contas.json":
            continue
        if arquivo.suffix.lower() not in SUFIXOS_EXTRATO:
            pendencias.append(str(arquivo))
            continue
        try:
            extratos.append(ler_extrato(arquivo, mapa_contas.get(arquivo.name)))
        except ExtratoNaoLido as erro:
            pendencias.append(f"{arquivo} ({erro})")
    return deduplicar(extratos), pendencias
