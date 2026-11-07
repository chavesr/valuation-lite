"""Executa um pacote de julgamento no modo escolhido e extrai o JSON da resposta.

Modos:
    claude-code   roda `claude -p` (Claude Code não interativo, conta logada) com o pacote na entrada padrão
    manual        só grava o pacote; alguém (Claude Code interativo, claude.ai, analista) grava a saída JSON
    api           reservado para quando houver chave da API (ainda não implementado)
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile

MODOS = ("claude-code", "manual", "api")


class ErroJulgamento(RuntimeError):
    pass


def extrair_json(texto: str) -> dict:
    """Primeiro objeto JSON da resposta (aceita bloco ```json ... ``` ou texto em volta)."""
    bloco = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", texto, flags=re.S)
    candidato = bloco.group(1) if bloco else None
    if candidato is None:
        inicio = texto.find("{")
        if inicio < 0:
            raise ErroJulgamento("a resposta não contém JSON")
        try:
            obj, _ = json.JSONDecoder().raw_decode(texto[inicio:])
            return obj
        except json.JSONDecodeError as e:
            raise ErroJulgamento(f"JSON inválido na resposta: {e}") from e
    try:
        return json.loads(candidato)
    except json.JSONDecodeError as e:
        raise ErroJulgamento(f"JSON inválido na resposta: {e}") from e


def executar_claude_code(prompt: str, modelo: str | None = None, timeout: int = 1200) -> str:
    """Roda o Claude Code em modo não interativo. Usa uma pasta temporária neutra como diretório de trabalho
    para não carregar instruções de projeto nem ler arquivos do cliente: tudo o que o agente vê está no pacote."""
    exe = shutil.which("claude")
    if not exe:
        raise ErroJulgamento("Claude Code não encontrado no PATH (comando 'claude'). Use --modo manual.")
    cmd = [exe, "-p", "--output-format", "text"]
    if modelo:
        cmd += ["--model", modelo]
    with tempfile.TemporaryDirectory(prefix="tarantino_") as neutra:
        try:
            r = subprocess.run(cmd, input=prompt, capture_output=True, text=True, encoding="utf-8",
                               timeout=timeout, cwd=neutra)
        except subprocess.TimeoutExpired as e:
            raise ErroJulgamento(f"Claude Code não respondeu em {timeout // 60} min") from e
    if r.returncode != 0:
        raise ErroJulgamento(f"Claude Code terminou com erro ({r.returncode}): {(r.stderr or r.stdout).strip()[:500]}")
    return r.stdout
