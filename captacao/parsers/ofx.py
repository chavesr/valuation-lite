"""Leitor de extratos OFX (v1 SGML e v2 XML), tolerante a tags não fechadas e a vírgula decimal."""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from captacao.schemas import ExtratoConta, Metodo, Proveniencia, Transacao
from captacao.util import normalizar_texto, parse_numero_br

_BLOCO_TRANSACAO = re.compile(
    r"<STMTTRN>(.*?)(?=</STMTTRN>|<STMTTRN>|</BANKTRANLIST>)", re.IGNORECASE | re.DOTALL
)


_RE_SALDO = re.compile(r"^(S ?A ?L ?D ?O\b|SDO\b|SALDO\b)")


def _ler_texto(caminho: Path) -> str:
    bruto = caminho.read_bytes()
    for codificacao in ("utf-8", "cp1252"):
        try:
            return bruto.decode(codificacao)
        except UnicodeDecodeError:
            continue
    return bruto.decode("latin-1")


def _tag(bloco: str, nome: str) -> str | None:
    m = re.search(rf"<{nome}>\s*([^<\r\n]*)", bloco, re.IGNORECASE)
    valor = m.group(1).strip() if m else None
    return valor or None


def _data_ofx(texto: str) -> date:
    return date(int(texto[0:4]), int(texto[4:6]), int(texto[6:8]))


def ler_ofx(caminho: str | Path, cnpj_titular: str | None = None) -> ExtratoConta:
    caminho = Path(caminho)
    texto = _ler_texto(caminho)

    conta_bloco = re.search(r"<(?:BANKACCTFROM|CCACCTFROM)>(.*?)</(?:BANKACCTFROM|CCACCTFROM)>",
                            texto, re.IGNORECASE | re.DOTALL)
    escopo_conta = conta_bloco.group(1) if conta_bloco else texto

    transacoes: list[Transacao] = []
    for i, bloco in enumerate(_BLOCO_TRANSACAO.findall(texto), start=1):
        data_txt, valor_txt = _tag(bloco, "DTPOSTED"), _tag(bloco, "TRNAMT")
        if not data_txt or not valor_txt:
            continue
        nome, memo = _tag(bloco, "NAME"), _tag(bloco, "MEMO")
        partes = [p for p in (nome, memo) if p]
        if nome and memo and (nome in memo or memo in nome):
            partes = [max(nome, memo, key=len)]
        if _RE_SALDO.match(normalizar_texto(" ".join(partes))):
            continue  # alguns bancos (ex.: Itaú) exportam o saldo do dia como se fosse lançamento
        transacoes.append(
            Transacao(
                data=_data_ofx(data_txt),
                valor=parse_numero_br(valor_txt) or 0.0,
                descricao=" ".join(partes) or "(sem descrição)",
                id_banco=_tag(bloco, "FITID") or f"linha-{i}",
            )
        )

    return ExtratoConta(
        cnpj_titular=cnpj_titular,
        banco=_tag(escopo_conta, "BANKID"),
        conta=_tag(escopo_conta, "ACCTID"),
        transacoes=transacoes,
        proveniencia=Proveniencia(arquivo=str(caminho), metodo=Metodo.PARSER, confianca="alta"),
    )
