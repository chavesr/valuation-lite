"""F1 — Inventário: lista e identifica todos os arquivos da pasta da empresa, sem mover nem alterar nada.

Identificação por regra (extensão + conteúdo). Duplicatas exatas (mesmo conteúdo) são marcadas e
lidas uma única vez. A pasta `_valuation/` (saídas do case) é ignorada.
"""

from __future__ import annotations

import csv
import hashlib
import os
import re
from enum import Enum
from pathlib import Path

from pydantic import BaseModel

PASTA_SAIDA = "_valuation"


class Tipo(str, Enum):
    EXTRATO = "extrato"  # .ofx / .csv de banco
    PLANILHA_ND = "planilha_nd"
    QUESTIONARIO = "questionario"  # planilha de respostas do Google Forms
    DEMONSTRACAO = "demonstracao"  # DRE ou Balanço Patrimonial em PDF com texto
    GERENCIAL = "gerencial"  # DRE/fluxo de caixa gerencial mensal em Excel
    SPED = "sped"  # SPED Fiscal (EFD ICMS/IPI) em .txt
    RELATORIO_ERP = "relatorio_erp"  # contas a receber/pagar, faturamento por produto, estoque
    EMPRESTIMO = "emprestimo"  # posição/extrato de empréstimo ou financiamento (PDF)
    FOLHA = "folha"  # resumo mensal da folha (só totais da empresa)
    SIMPLES = "simples"  # Extrato do PGDAS-D ou DEFIS (PDF)
    RECIBO = "recibo"  # recibo de entrega de declaração (sem dados)
    NOTA_FISCAL = "nota_fiscal"  # DANFE avulsa: os valores vêm do SPED Fiscal
    DADOS_PESSOAIS = "dados_pessoais"  # holerite/extrato por funcionário: não é lido (privacidade)
    PDF_ESCANEADO = "pdf_escaneado"  # PDF sem texto (imagem): precisa de OCR/IA ou do original
    PDF = "pdf"  # PDF com texto ainda sem leitor (extrato em PDF, PGDAS…)
    COMPACTADO = "compactado"
    PLANILHA_OUTRA = "planilha_outra"
    OUTRO = "outro"


LIDOS_POR_CODIGO = {Tipo.EXTRATO, Tipo.PLANILHA_ND, Tipo.QUESTIONARIO, Tipo.DEMONSTRACAO, Tipo.GERENCIAL, Tipo.SPED, Tipo.RELATORIO_ERP, Tipo.EMPRESTIMO, Tipo.FOLHA, Tipo.SIMPLES}


class Arquivo(BaseModel):
    caminho: str  # relativo à pasta da empresa
    tipo: Tipo
    tamanho: int
    sha1: str
    duplicata_de: str | None = None
    status: str = "pendente"  # lido | duplicado | não lido | erro
    detalhe: str | None = None


def _sha1(arquivo: Path) -> str:
    h = hashlib.sha1()
    with open(arquivo, "rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


def _cabecalho_csv(arquivo: Path) -> list[str]:
    for codificacao in ("utf-8-sig", "cp1252"):
        try:
            with open(arquivo, encoding=codificacao, newline="") as f:
                return next(csv.reader(f), [])
        except (UnicodeDecodeError, csv.Error):
            continue
    return []


def _eh_questionario(cabecalho: list[str]) -> bool:
    return "Nome da empresa" in cabecalho and "CNPJ principal" in cabecalho


def _tipo_pdf(arquivo: Path) -> Tipo:
    import pdfplumber

    from captacao.parsers.demonstracoes_pdf import identificar_tipo

    try:
        with pdfplumber.open(arquivo) as pdf:
            texto = "".join((p.extract_text() or "") for p in pdf.pages[:2])
    except Exception:  # noqa: BLE001 — PDF corrompido ou protegido: fica como PDF não lido
        return Tipo.PDF
    if len(texto.strip()) < 50:
        return Tipo.PDF_ESCANEADO
    from captacao.parsers.pgdas_pdf import identificar as identificar_simples

    simples = identificar_simples(texto)
    if simples in ("pgdas", "defis"):
        return Tipo.SIMPLES
    if simples == "defis_recibo":
        return Tipo.RECIBO
    if identificar_tipo(texto):
        return Tipo.DEMONSTRACAO
    from captacao.parsers.emprestimos_pdf import identificar as identificar_emprestimo
    from captacao.parsers.extrato_pdf import identificar_banco

    if identificar_emprestimo(texto):
        return Tipo.EMPRESTIMO
    from captacao.parsers.folha_pdf import eh_resumo_folha

    if eh_resumo_folha(texto):
        return Tipo.FOLHA
    if identificar_banco(texto):
        return Tipo.EXTRATO
    from captacao.util import normalizar_texto

    n = normalizar_texto(texto[:2000])
    if "DANFE" in n or "DOCUMENTO AUXILIAR DA NOTA FISCAL" in n:
        return Tipo.NOTA_FISCAL
    if re.search(r"FUNCIONARIO|EMPREGADO", n) and re.search(r"EXTRATO MENSAL|RECIBO DE PAGAMENTO|HOLERITE", n):
        return Tipo.DADOS_PESSOAIS
    return Tipo.PDF


def normalizar_nome(nome: str) -> str:
    from captacao.util import normalizar_texto

    return normalizar_texto(nome)


def _eh_relatorio_erp(arquivo: Path) -> bool:
    from captacao.parsers.relatorios_erp import abrir_planilha, identificar_relatorio

    try:
        return identificar_relatorio(abrir_planilha(arquivo)) is not None
    except Exception:  # noqa: BLE001 — planilha ilegível
        return False


def _eh_extrato_planilha(arquivo: Path) -> bool:
    from captacao.parsers.extrato_planilha import eh_extrato_planilha
    from captacao.parsers.relatorios_erp import abrir_planilha

    try:
        return eh_extrato_planilha(abrir_planilha(arquivo))
    except Exception:  # noqa: BLE001
        return False


def identificar(arquivo: Path) -> Tipo:
    sufixo = arquivo.suffix.lower()
    if sufixo == ".ofx":
        return Tipo.EXTRATO
    if sufixo == ".csv":
        return Tipo.QUESTIONARIO if _eh_questionario(_cabecalho_csv(arquivo)) else Tipo.EXTRATO
    if sufixo in {".xlsx", ".xlsm"}:
        from openpyxl import load_workbook

        try:
            wb = load_workbook(arquivo, read_only=True)
        except Exception:  # noqa: BLE001 — arquivo corrompido ou renomeado
            return Tipo.OUTRO
        if "1_Grupo" in wb.sheetnames and "4_Faturamento" in wb.sheetnames:
            return Tipo.PLANILHA_ND
        primeira = next(wb.worksheets[0].iter_rows(max_row=1, values_only=True), ())
        if _eh_questionario([str(c) for c in primeira if c is not None]):
            return Tipo.QUESTIONARIO
        if _eh_extrato_planilha(arquivo):
            return Tipo.EXTRATO
        if _eh_relatorio_erp(arquivo):
            return Tipo.RELATORIO_ERP
        from captacao.parsers.gerencial_xlsx import eh_gerencial

        return Tipo.GERENCIAL if eh_gerencial(arquivo) else Tipo.PLANILHA_OUTRA
    if sufixo == ".pdf":
        if re.search(r"FUNCIONARIO|HOLERITE|CONTRACHEQUE|CONTRA-CHEQUE", normalizar_nome(arquivo.name)):
            return Tipo.DADOS_PESSOAIS
        return _tipo_pdf(arquivo)
    if sufixo == ".txt":
        from captacao.parsers.sped_efd import eh_efd_icms

        with open(arquivo, "rb") as f:
            primeira = f.readline().decode("latin-1", errors="replace")
        return Tipo.SPED if eh_efd_icms(primeira) else Tipo.OUTRO
    if sufixo in {".zip", ".rar", ".7z"}:
        return Tipo.COMPACTADO
    if sufixo == ".xls":
        if _eh_extrato_planilha(arquivo):
            return Tipo.EXTRATO
        return Tipo.RELATORIO_ERP if _eh_relatorio_erp(arquivo) else Tipo.PLANILHA_OUTRA
    if sufixo == ".ods":
        return Tipo.PLANILHA_OUTRA
    return Tipo.OUTRO


def caminho_longo(pasta: str | Path) -> Path:
    """No Windows, caminhos com mais de 260 caracteres somem silenciosamente da listagem (ex.: notas fiscais
    nomeadas pela chave de 44 dígitos em pastas profundas). O prefixo \\\\?\\ libera o limite."""
    p = Path(pasta).resolve()
    if os.name == "nt" and not str(p).startswith("\\\\?\\"):
        return Path("\\\\?\\" + str(p))
    return p


def inventariar(pasta_empresa: str | Path) -> list[Arquivo]:
    pasta = caminho_longo(pasta_empresa)
    vistos: dict[str, str] = {}
    itens: list[Arquivo] = []
    for arq in sorted(p for p in pasta.rglob("*") if p.is_file()):
        rel = arq.relative_to(pasta)
        if rel.parts[0] == PASTA_SAIDA or arq.name in {"contas.json", "desktop.ini"} or arq.name.startswith("~$"):
            continue
        sha = _sha1(arq)
        item = Arquivo(caminho=rel.as_posix(), tipo=identificar(arq), tamanho=arq.stat().st_size, sha1=sha)
        if sha in vistos:
            item.duplicata_de, item.status = vistos[sha], "duplicado"
        else:
            vistos[sha] = item.caminho
            if item.tipo not in LIDOS_POR_CODIGO:
                item.status = "não lido"
                item.detalhe = {
                    Tipo.PDF: "PDF ainda sem leitor automático",
                    Tipo.PDF_ESCANEADO: "PDF escaneado (imagem): pedir o arquivo original ou o SPED em .txt",
                    Tipo.NOTA_FISCAL: "nota fiscal avulsa — valores já cobertos pelo SPED Fiscal",
                    Tipo.RECIBO: "recibo de entrega (sem dados; a declaração em si é que é lida)",
                    Tipo.DADOS_PESSOAIS: "dados individuais de funcionários — não lido (privacidade); usar o resumo da folha",
                    Tipo.COMPACTADO: "arquivo compactado: extrair o conteúdo na pasta",
                    Tipo.PLANILHA_OUTRA: "planilha fora do padrão ND",
                }.get(item.tipo, "formato não utilizado")
        itens.append(item)
    _zips_ja_extraidos(pasta, itens)
    return itens


def _hashes_zip(zf, nivel: int = 0) -> list[str]:
    """Hash de cada arquivo do zip; zips dentro do zip são abertos (até 2 níveis)."""
    import io
    import zipfile

    saida = []
    for m in zf.infolist():
        if m.is_dir() or "__macosx" in m.filename.lower():
            continue
        dados = zf.read(m)
        if m.filename.lower().endswith(".zip") and nivel < 2:
            try:
                with zipfile.ZipFile(io.BytesIO(dados)) as interno:
                    saida += _hashes_zip(interno, nivel + 1)
                continue
            except zipfile.BadZipFile:
                pass
        saida.append(hashlib.sha1(dados).hexdigest())
    return saida


def _zips_ja_extraidos(pasta: Path, itens: list[Arquivo]) -> None:
    """Zip cujo conteúdo já está extraído na pasta (mesmos nomes de arquivo) vira duplicata."""
    import zipfile

    # compara pelo conteúdo (hash): quem organiza a pasta costuma renomear os arquivos ao extrair
    hashes = {i.sha1 for i in itens if i.tipo != Tipo.COMPACTADO}
    for i in itens:
        if i.tipo != Tipo.COMPACTADO or i.status != "não lido":
            continue
        try:
            with zipfile.ZipFile(pasta / i.caminho) as zf:
                membros = _hashes_zip(zf)
        except (zipfile.BadZipFile, OSError):
            continue
        if membros and all(m in hashes for m in membros):
            i.status, i.detalhe = "duplicado", "conteúdo já extraído na pasta"
        elif membros:
            i.detalhe = f"compactado com {len(membros)} arquivo(s) ainda não extraído(s): extrair na pasta"
