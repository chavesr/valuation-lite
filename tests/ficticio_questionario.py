"""Gera uma planilha de respostas no mesmo formato da exportada pelo Google Forms.

A ordem das colunas segue a ordem dos itens no formulário (é assim que o Google monta a planilha):
identificação, Parte 0, Parte A, P03 e, para cada um dos 7 caminhos, os módulos completos seguidos
das perguntas essenciais das atividades secundárias. Por isso a mesma pergunta aparece em várias colunas.
"""

from __future__ import annotations

import csv
from pathlib import Path

from captacao.questionario import TITULO_P03, carregar_catalogo

ORDEM_SECUNDARIOS = ["I", "C", "S"]


def cabecalho_forms() -> list[str]:
    cat = carregar_catalogo()
    ps = list(cat.perguntas.values())
    base = [p for p in ps if p.modulo is None and p.codigo != "P03"]
    cab = ["Carimbo de data/hora"] + [p.titulo for p in base] + [TITULO_P03]
    for mods in cat.combos.values():
        for m in mods:
            cab += [p.titulo for p in ps if p.modulo == m]
        for m in ORDEM_SECUNDARIOS:
            if m not in mods:
                cab += [p.titulo for p in ps if p.modulo == m and p.essencial]
    return cab


def escrever_respostas(caminho: Path, linhas: list[dict[str, str]]) -> Path:
    """Cada linha: {título ou código: valor}. Valores de módulo vão para a coluna do caminho escolhido (P03)."""
    cat = carregar_catalogo()
    cab = cabecalho_forms()
    combos = list(cat.combos)
    rows = []
    for dados in linhas:
        por_titulo = {cat.perguntas[k].titulo if k in cat.perguntas else k: v for k, v in dados.items()}
        caminho_escolhido = por_titulo.get(TITULO_P03)
        # o bloco do caminho escolhido começa depois da P03 e dos blocos dos caminhos anteriores
        inicio_bloco = cab.index(TITULO_P03) + 1
        for rotulo in combos:
            n = _tamanho_bloco(cat.combos[rotulo])
            if rotulo == caminho_escolhido:
                fim_bloco = inicio_bloco + n
                break
            inicio_bloco += n
        else:
            inicio_bloco = fim_bloco = len(cab)
        row = []
        for j, titulo in enumerate(cab):
            eh_modulo = j > cab.index(TITULO_P03)
            if eh_modulo and not (inicio_bloco <= j < fim_bloco):
                row.append("")
            else:
                row.append(por_titulo.get(titulo, ""))
        rows.append(row)
    with open(caminho, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, quoting=csv.QUOTE_ALL)
        w.writerow(cab)
        w.writerows(rows)
    return caminho


def _tamanho_bloco(mods: list[str]) -> int:
    ps = list(carregar_catalogo().perguntas.values())
    n = sum(1 for p in ps if p.modulo in mods)
    n += sum(1 for p in ps if p.modulo and p.modulo not in mods and p.essencial)
    return n


# Resposta enviada no teste real de 06/11/2026 (empresa fictícia), valores como vieram da planilha do Google.
TESTE_REAL = {
    "Carimbo de data/hora": "06/11/2026 17:25:28",
    "ID1": "TESTE — Metalúrgica Fictícia Ltda",
    "ID2": "00.000.000/0001-00",
    "ID3": "Teste Sistema",
    "ID4": "Sócio",
    "ID5": "teste@exemplo.com",
    "P01": ("Fabricação / produção — transforma matéria-prima em produto (inclui montagem e produção sob "
            "encomenda), Comércio / revenda — compra produtos prontos e revende (loja, distribuição, peças, "
            "atacado), Prestação de serviços — vende trabalho ou conhecimento (manutenção, instalação, "
            "consultoria, transporte, saúde…)"),
    "P01a": "70", "P01b": "5", "P01c": "25",
    "P01d": "Fabricação e serviços no CNPJ A; peças no CNPJ B (teste)",
    "P02": "Sim, são complementares",
    "Q01": "1998", "Q02": "Aposentadoria", "Q03a": "4 mi", "Q04": "De 6 a 12 meses",
    "Q11": "120", "Q12a": "18", "Q24": "Não, parte é recebida sem nota", "Q28": "R$ 150 mil",
    "P03": "Fabricação + serviços",
    "I02a": "12", "S01a": "60", "C04": "45",
}
