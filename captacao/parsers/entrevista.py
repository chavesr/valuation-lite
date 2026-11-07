"""Entrevistas, briefings e anotações de reunião inicial com o dono (kick-off): texto livre para a F5.

São ENTRADA do julgamento (o que o dono contou), não saída da ND. Por isso o reconhecimento é pelo nome do
arquivo, e nomes de apresentação de valuation, laudo ou relatório ficam de fora (já trazem as conclusões).
"""

from __future__ import annotations

import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree

from captacao.util import normalizar_texto

FORMATOS = {".docx", ".pdf", ".txt", ".md"}
_ENTRADA = re.compile(r"BRIEFING|KICK ?OFF|ENTREVISTA|REUNIAO INICIAL|PRIMEIRA REUNIAO|ONBOARDING|"
                      r"GRAVAC|TRANSCRI|VISITA")  # visitas ao empreendedor, com ou sem investidores
_SAIDA = re.compile(r"APRESENTA|VALUATION|LAUDO|AVALIACAO|RELATORIO|DOSSIE")
_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


class EntrevistaNaoLida(ValueError):
    pass


def eh_entrevista(nome: str) -> bool:
    n = re.sub(r"[^A-Z0-9 ]", " ", normalizar_texto(Path(nome).stem))
    n = re.sub(r"\s+", " ", n)
    return bool(_ENTRADA.search(n)) and not _SAIDA.search(n)


def _docx(arquivo: Path) -> str:
    try:
        with zipfile.ZipFile(arquivo) as z:
            raiz = ElementTree.fromstring(z.read("word/document.xml"))
    except (zipfile.BadZipFile, KeyError, ElementTree.ParseError) as e:
        raise EntrevistaNaoLida(f"DOCX ilegível: {e}") from e
    paragrafos = ["".join(t.text or "" for t in p.iter(f"{_W}t")) for p in raiz.iter(f"{_W}p")]
    return "\n".join(p for p in paragrafos if p.strip())


def _pdf(arquivo: Path) -> str:
    import pdfplumber

    with pdfplumber.open(arquivo) as pdf:
        return "\n".join(p.extract_text() or "" for p in pdf.pages)


def extrair_texto(arquivo: str | Path) -> str:
    arquivo = Path(arquivo)
    sufixo = arquivo.suffix.lower()
    if sufixo == ".docx":
        texto = _docx(arquivo)
    elif sufixo == ".pdf":
        texto = _pdf(arquivo)
    elif sufixo in {".txt", ".md"}:
        texto = arquivo.read_text(encoding="utf-8", errors="replace")
    else:
        raise EntrevistaNaoLida(f"formato {sufixo} não suportado")
    texto = re.sub(r"\n{3,}", "\n\n", texto).strip()
    if len(texto) < 50:
        raise EntrevistaNaoLida("sem texto (documento vazio ou escaneado)")
    return texto
