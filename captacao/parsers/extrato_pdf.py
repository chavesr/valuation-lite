"""Leitor de extrato bancário em PDF com texto (nível 0 do funil — zero tokens).

Layouts suportados (validados contra o OFX do mesmo mês):
  * Banco do Brasil (autoatendimento PJ): "Dt. balancete | Dt. movimento | Ag. origem | Lote | Histórico |
    Documento | Valor R$ D/C | Saldo D/C"; o favorecido/detalhe vem na linha de baixo.
  * Sicredi: "Data | Descrição | Documento | Valor (R$) | Saldo (R$)" com saldo em todas as linhas;
    a seção "Lançamentos Futuros" no fim do PDF é ignorada.
  * Itaú (extrato detalhado): "Data | Lançamentos | Razão Social | CNPJ/CPF | Valor | Saldo"; a razão social
    quebra acima e abaixo da linha do lançamento; "SALDO TOTAL DISPONÍVEL DIA" a cada dia.

Autoconferência: quando o extrato traz saldos, o leitor confere saldo anterior + lançamentos = saldo
informado. Divergência = lançamento perdido ou lido errado → confiança média e alerta.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from captacao.schemas import ExtratoConta, Metodo, Proveniencia, Transacao
from captacao.util import apenas_digitos, brl, normalizar_texto

_NUM = r"-?[\d.]+,\d{2}"
_DOC = r"\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}|\d{3}\.\d{3}\.\d{3}-\d{2}|\b\d{14}\b|\b\d{11}\b"
_SALDO = re.compile(r"^(S ?A ?L ?D ?O\b|SDO\b)")


class ExtratoPdfNaoLido(Exception):
    pass


@dataclass
class Layout:
    banco: str  # código FEBRABAN
    nome: str
    detectar: re.Pattern
    linha: re.Pattern  # grupos: data, desc, valor, [dc], [saldo], [sdc]
    fim_secao: re.Pattern | None = None


LAYOUTS = [
    Layout("001", "Banco do Brasil",
           re.compile(r"BANCO DO BRASIL|AUTOATENDIMENTO\.BB|DT\. BALANCETE|AG\. ORIGEM LOTE HISTORICO"),
           # data do balancete e (opcional) do movimento — o OFX usa a do movimento; lote e histórico às vezes
           # vêm grudados ('00000870')
           re.compile(rf"^(?P<data>\d{{2}}/\d{{2}}/\d{{4}})\s+(?:(?P<data2>\d{{2}}/\d{{2}}/\d{{4}})\s+)?\d{{4}}\s+\d{{5}}\s*\d{{3}}\s+"
                      rf"(?P<desc>.+?)\s+(?:[\d.]+\s+)?(?P<valor>[\d.]+,\d{{2}})\s(?P<dc>[DC])"
                      rf"(?:\s+(?P<saldo>[\d.]+,\d{{2}})\s(?P<sdc>[DC]))?$")),
    # exige o título do extrato: posições de empréstimo do Sicredi também trazem "Associado/Cooperativa"
    Layout("748", "Sicredi", re.compile(r"(ASSOCIADO|COOPERATIVA):.*EXTRATO \(PERIODO", re.S),
           re.compile(rf"^(?P<data>\d{{2}}/\d{{2}}/\d{{4}})\s+(?P<desc>.+?)\s+(?P<valor>{_NUM})\s+(?P<saldo>{_NUM})$"),
           fim_secao=re.compile(r"^LANCAMENTOS FUTUROS")),
    Layout("341", "Itaú", re.compile(r"LANCAMENTOS DO PERIODO|SALDO TOTAL DISPONIVEL DIA"),
           # histórico longo quebra acima/abaixo e a linha da data fica só com o valor: '13/01/2026 0,11'
           re.compile(rf"^(?P<data>\d{{2}}/\d{{2}}/\d{{4}})(?:\s+(?P<desc>.+?))?\s+(?P<valor>{_NUM})"
                      rf"(?:\s+(?P<saldo>{_NUM}))?$")),
]


def _num(txt: str) -> float:
    return float(txt.replace(".", "").replace(",", "."))


def _data(txt: str) -> date:
    return datetime.strptime(txt, "%d/%m/%Y").date()


def identificar_banco(texto: str) -> Layout | None:
    n = normalizar_texto(texto[:3000]).replace("\n", " ")
    cab = "\n".join(normalizar_texto(l) for l in texto[:3000].splitlines())
    for layout in LAYOUTS:
        if layout.detectar.search(cab) or layout.detectar.search(n):
            return layout
    return None


def _periodo(texto: str) -> tuple[date | None, date | None]:
    n = normalizar_texto(" ".join(texto[:3000].split()))
    m = re.search(r"PERIODO (?:DE |DO PERIODO:? )?(\d{2}/\d{2}/\d{4}) (?:A|ATE) (\d{2}/\d{2}/\d{4})", n) or \
        re.search(r"LANCAMENTOS DO PERIODO:? (\d{2}/\d{2}/\d{4}) ATE (\d{2}/\d{2}/\d{4})", n)
    if m:
        return _data(m.group(1)), _data(m.group(2))
    m = re.search(r"PERIODO DO (\d{2}) / (\d{4})", n) or re.search(r"\b(\d{2}) / (\d{4})\b", n)
    if m:  # BB: "Período do extrato 01 / 2026"
        mes, ano = int(m.group(1)), int(m.group(2))
        prox = date(ano + (mes == 12), mes % 12 + 1, 1)
        return date(ano, mes, 1), date.fromordinal(prox.toordinal() - 1)
    return None, None


def _conta(texto: str) -> str | None:
    n = normalizar_texto(texto[:3000])
    m = re.search(r"CONTA(?: CORRENTE)?:?\s*([\d.]+-[\dX])", n)
    return m.group(1) if m else None


def ler_extrato_pdf(caminho: str | Path,
                    linhas: list[tuple[float, float, str]] | None = None) -> tuple[ExtratoConta, list[str]]:
    """`linhas` = [(x0, y, texto)] (para testes); por padrão lê o PDF com pdfplumber."""
    caminho = Path(caminho)
    if linhas is None:
        from captacao.parsers.demonstracoes_pdf import ler_linhas_pdf

        linhas = ler_linhas_pdf(caminho)
    texto = "\n".join(t for _, _, t in linhas)
    if len(texto.strip()) < 50:
        raise ExtratoPdfNaoLido("PDF sem texto (escaneado)")
    layout = identificar_banco(texto)
    if layout is None:
        raise ExtratoPdfNaoLido("banco/layout de extrato não reconhecido")
    inicio, fim = _periodo(texto)

    ancoras: list[dict] = []
    soltas: list[tuple[float, str]] = []
    saldo_anterior = None
    for x0, y, t in linhas:
        n = normalizar_texto(t)
        if layout.fim_secao and layout.fim_secao.match(n):
            break
        m = layout.linha.match(t.strip())
        if not m:
            ms = re.match(rf"^(?:\d{{2}}/\d{{2}}/\d{{4}}\s+(?:\d{{4}}\s+\d{{5}}\s+\d{{3}}\s+)?)?(?:SALDO ANTERIOR|S A L D O)\s+({_NUM})\s*([DC])?",
                          n)
            if ms and saldo_anterior is None and not ancoras:
                saldo_anterior = _num(ms.group(1)) * (-1 if ms.group(2) == "D" else 1)
            elif x0 > 60 and not re.match(r"\d{2}/\d{2}/\d{4}", t):
                soltas.append((y, t.strip()))  # razão social / detalhe quebrado em outra linha
            continue
        g = m.groupdict()
        desc = (g["desc"] or "").strip()
        valor = _num(g["valor"])
        if g.get("dc") == "D":
            valor = -abs(valor)
        saldo = None
        if g.get("saldo"):
            saldo = _num(g["saldo"]) * (-1 if g.get("sdc") == "D" else 1)
        if _SALDO.match(normalizar_texto(desc)):
            if "ANTERIOR" in normalizar_texto(desc):
                saldo_anterior = valor
            else:
                ancoras.append({"y": y, "saldo_dia": valor if not g.get("saldo") else saldo})
            continue
        ancoras.append({"y": y, "data": _data(g.get("data2") or g["data"]), "desc": desc, "valor": valor, "saldo": saldo,
                        "extras": []})

    lancamentos = [a for a in ancoras if "data" in a]
    for y, t in soltas:
        perto = min(lancamentos, key=lambda a: abs(a["y"] - y), default=None)
        if perto is not None and abs(perto["y"] - y) <= 18:
            perto["extras"].append((y, t))

    transacoes: list[Transacao] = []
    alertas: list[str] = []
    fora = 0
    for i, a in enumerate(lancamentos, start=1):
        if (inicio and a["data"] < inicio) or (fim and a["data"] > fim):
            fora += 1
            continue
        partes = [p for _, p in sorted(a["extras"] + [(a["y"], a["desc"])])]
        descricao = re.sub(r"\s+", " ", " ".join(partes))
        doc = re.search(_DOC, descricao)
        transacoes.append(Transacao(data=a["data"], valor=a["valor"], descricao=descricao,
                                    id_banco=f"pdf-{i}", contraparte_doc=apenas_digitos(doc.group(0)) if doc else None))
    if not transacoes and not fora:
        raise ExtratoPdfNaoLido(f"nenhum lançamento reconhecido no layout {layout.nome}")
    if fora:
        alertas.append(f"{fora} lançamento(s) fora do período do extrato ignorado(s).")

    # autoconferência pelos saldos informados no próprio extrato
    divergencias = conferidos = 0
    if saldo_anterior is not None:
        corrente = saldo_anterior
        for a in ancoras:
            if "data" in a:
                corrente = round(corrente + a["valor"], 2)
                informado = a.get("saldo")
            else:
                informado = a.get("saldo_dia")
            if informado is not None:
                conferidos += 1
                if abs(corrente - informado) > 0.02:
                    divergencias += 1
                    corrente = informado  # reancora para não propagar o erro
    if divergencias:
        alertas.append(f"Saldo não confere em {divergencias} de {conferidos} ponto(s): pode haver lançamento "
                       "perdido ou lido errado — conferir com o OFX.")

    cab = normalizar_texto(texto[:1500])
    cnpj = re.search(r"\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}", texto[:600])
    prov = Proveniencia(arquivo=str(caminho), metodo=Metodo.PARSER,
                        localizacao=f"{layout.nome}; {conferidos} saldo(s) conferido(s)" if conferidos else layout.nome,
                        confianca="media" if divergencias or not conferidos else "alta")
    extrato = ExtratoConta(cnpj_titular=apenas_digitos(cnpj.group(0)) if cnpj and "CNPJ" in cab else None,
                           banco=layout.banco, conta=_conta(texto), transacoes=transacoes, proveniencia=prov)
    return extrato, alertas


def mesma_conta(a: ExtratoConta, b: ExtratoConta) -> bool:
    """Mesmo banco e mesmo número de conta, tolerando zeros e agência/cooperativa à esquerda
    (ex.: PDF '54321-0' × OFX '01010000000543210'; PDF '0012345-6' × OFX '4321123456')."""
    if not (a.banco and b.banco and a.conta and b.conta):
        return False
    if int(apenas_digitos(a.banco) or 0) != int(apenas_digitos(b.banco) or 0):
        return False
    x, y = apenas_digitos(a.conta).lstrip("0"), apenas_digitos(b.conta).lstrip("0")
    curto, longo = sorted((x, y), key=len)
    return len(curto) >= 5 and longo.endswith(curto)


def resumo(extrato: ExtratoConta) -> str:
    cred = sum(t.valor for t in extrato.transacoes if t.valor > 0)
    deb = sum(t.valor for t in extrato.transacoes if t.valor < 0)
    return f"{len(extrato.transacoes)} lançamentos, créditos R$ {brl(cred)}, débitos R$ {brl(deb)}"
