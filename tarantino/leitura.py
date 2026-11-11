"""Trava de leitura integral (decisão de Guilherme, 11/11/2026, depois de IBRATE e Emunah).

Nenhum relatório sai sem que TODOS os documentos enviados pela empresa tenham sido lidos por inteiro e registrados em
`_valuation/leitura.json`. "Lido pelo parser" não basta: o parser tira números, não o que o documento diz.

    {
      "pasta_origem": "G:/.../Clinica Emunah",          # opcional: pasta original da empresa, se o case é uma cópia
      "arquivos": {
        "Balanço 2025.pdf": {"paginas": 2, "resumo": "o que o documento traz e onde entra no relatório"},
        "Balanço 2025 (1).pdf": {"duplicata_de": "..."}  # ou {"sem_conteudo": "motivo"}
      }
    }

Os caminhos são relativos à pasta (do case ou de origem). Arquivos da pasta `_valuation/` não contam.
"""

from __future__ import annotations

import json
from pathlib import Path

from tarantino.inventario import PASTA_SAIDA

ARQUIVO = "leitura.json"
IGNORAR = {"desktop.ini", "thumbs.db", ".ds_store"}


def documentos(pasta: Path) -> list[str]:
    """Todos os arquivos da pasta, recursivo, fora de _valuation/ e de arquivos de sistema."""
    if not pasta.exists():
        return []
    return sorted(str(f.relative_to(pasta)).replace("\\", "/") for f in pasta.rglob("*")
                  if f.is_file() and PASTA_SAIDA not in f.relative_to(pasta).parts
                  and f.name.lower() not in IGNORAR and not f.name.startswith("~$"))


def _registrado(item: dict | None) -> bool:
    if not isinstance(item, dict):
        return False
    return bool((item.get("resumo") or "").strip() or item.get("duplicata_de") or (item.get("sem_conteudo") or "").strip())


def nao_lidos(pasta_case: str | Path) -> list[str]:
    """→ documentos da empresa (pasta do case e, se registrada, a de origem) sem leitura registrada."""
    pasta = Path(pasta_case)
    reg = pasta / PASTA_SAIDA / ARQUIVO
    dados = json.loads(reg.read_text(encoding="utf-8")) if reg.exists() else {}
    lidos = dados.get("arquivos") or {}
    faltam = [d for d in documentos(pasta) if not _registrado(lidos.get(d))]
    if dados.get("pasta_origem"):
        origem = Path(dados["pasta_origem"])
        if not origem.exists():
            faltam.append(f"(pasta de origem não encontrada: {origem})")
        faltam += [f"{origem.name}/{d}" for d in documentos(origem) if not _registrado(lidos.get(d))]
    return faltam


def resumos(pasta_case: str | Path, limite: int = 25000) -> str:
    """Bloco markdown com o que cada documento traz (leitura integral do analista), para os agentes F5 e F8."""
    reg = Path(pasta_case) / PASTA_SAIDA / ARQUIVO
    if not reg.exists():
        return ""
    dados = json.loads(reg.read_text(encoding="utf-8"))
    linhas = ["## Leitura integral dos documentos da empresa (analista) — use estes fatos; nunca escreva "
              "\"não informado\" para algo que aparece aqui"]
    if dados.get("fatos_chave"):
        linhas += ["", "Fatos-chave:"] + [f"- {x}" for x in dados["fatos_chave"]]
    linhas.append("")
    for nome, item in (dados.get("arquivos") or {}).items():
        if isinstance(item, dict) and (item.get("resumo") or "").strip():
            linhas.append(f"- **{nome}**: {item['resumo'].strip()}")
    texto = "\n".join(linhas)
    return texto if len(texto) <= limite else texto[:limite] + "\n… (cortado)"
