"""Leitor das respostas do Questionário do Empreendedor (Google Forms → planilha de respostas).

Fonte única do catálogo de perguntas: kit_captacao/formulario/criar_formulario.gs.
O formulário mostra só o texto da pergunta; aqui o título exato é convertido no código (Q01, I02a…).

A planilha do Google tem uma coluna por ocorrência da pergunta em cada um dos 7 caminhos
(≈270 colunas para 96 perguntas). O leitor junta as colunas de mesmo título e fica com a preenchida.

Uso:
    python -m captacao.questionario respostas.csv [--cnpj 00000000000100] [--saida questionario.json]
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import re
from datetime import datetime
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, Field

from captacao.schemas import Metodo, Proveniencia
from captacao.util import apenas_digitos, normalizar_texto, parse_numero_br

ARQUIVO_GS = Path(__file__).resolve().parents[1] / "kit_captacao" / "formulario" / "criar_formulario.gs"
TITULO_P03 = "Quais atividades representam 10% ou mais do faturamento?"
COLUNAS_SISTEMA = {"Carimbo de data/hora", "Timestamp", "Endereço de e-mail", "Email Address", "Pontuação", "Score"}
LIMIAR_MODULO = 10.0  # % do faturamento a partir do qual a atividade tem módulo completo

# atividade da Parte 0 → (código do %, prefixo do módulo, trecho da opção em P01)
ATIVIDADES = {
    "I": ("P01a", "Fabricação"),
    "C": ("P01b", "Comércio"),
    "S": ("P01c", "Prestação de serviços"),
}


# --------------------------------------------------------------------------- catálogo


class Pergunta(BaseModel):
    codigo: str
    tipo: str
    titulo: str
    opcoes: list[str] = Field(default_factory=list)
    essencial: bool = False
    obrigatoria: bool = False
    aceita_outro: bool = False

    @property
    def modulo(self) -> str | None:
        """'I', 'S' ou 'C' para perguntas da Parte B; None para as demais."""
        return self.codigo[0] if re.fullmatch(r"[ISC]\d+[a-z]?", self.codigo) else None


class Catalogo(BaseModel):
    perguntas: dict[str, Pergunta]  # por código
    combos: dict[str, list[str]]  # rótulo da P03 → módulos completos

    def por_titulo(self) -> dict[str, Pergunta]:
        return {p.titulo: p for p in self.perguntas.values()}


@lru_cache(maxsize=4)
def carregar_catalogo(caminho_gs: str | Path = ARQUIVO_GS) -> Catalogo:
    """Extrai as perguntas e combinações do script do formulário (os literais seguem um padrão fixo)."""
    texto = Path(caminho_gs).read_text(encoding="utf-8")
    perguntas: dict[str, Pergunta] = {}
    for m in re.finditer(r"\{ c: '([^']+)'(.*?)\}", texto, flags=re.S):
        codigo, corpo = m.group(1), m.group(2)
        tipo = re.search(r"\bt: '([^']+)'", corpo)
        titulo = re.search(r"\btitulo: '([^']+)'", corpo)
        if not (tipo and titulo):
            continue
        opcoes = re.search(r"\bop: \[(.*?)\]", corpo, flags=re.S)
        perguntas[codigo] = Pergunta(
            codigo=codigo, tipo=tipo.group(1), titulo=titulo.group(1),
            opcoes=re.findall(r"'([^']*)'", opcoes.group(1)) if opcoes else [],
            essencial=bool(re.search(r"\be: true", corpo)),
            obrigatoria=bool(re.search(r"\breq: true", corpo)),
            aceita_outro=bool(re.search(r"\boutro: true", corpo)),
        )
    combos = {m.group(1): re.findall(r"'([ISC])'", m.group(2))
              for m in re.finditer(r"\{ rotulo: '([^']+)', mods: \[([^\]]*)\] \}", texto)}
    perguntas["P03"] = Pergunta(codigo="P03", tipo="unica", titulo=TITULO_P03, opcoes=list(combos),
                                obrigatoria=True)
    titulos = [p.titulo for p in perguntas.values()]
    if len(set(titulos)) != len(titulos):
        raise ValueError("Catálogo com títulos repetidos: o leitor depende de títulos únicos.")
    return Catalogo(perguntas=perguntas, combos=combos)


# --------------------------------------------------------------------------- conversão de valores

_MULTIPLICADORES = [  # ordem importa: 'MILHOES' antes de 'MIL' e 'MI'
    (r"(MILHOES|MILHAO|MI|MM|M)$", 1_000_000.0),
    (r"(MIL|K)$", 1_000.0),
]


def parse_moeda(texto: str) -> float | None:
    """'4 mi' → 4e6 · '1,5 milhão' → 1.5e6 · 'R$ 150 mil' → 150e3 · 'R$ 20.000,00' → 20000."""
    s = normalizar_texto(texto).replace("R$", "").replace(" ", "").rstrip(".")
    if not s:
        return None
    fator = 1.0
    for padrao, mult in _MULTIPLICADORES:
        m = re.search(padrao, s)
        if m and re.search(r"\d", s[: m.start()]):
            fator, s = mult, s[: m.start()]
            break
    try:
        numero = parse_numero_br(s)
    except ValueError:
        return None
    return None if numero is None else numero * fator


def _parse_numero(texto: str) -> float | None:
    try:
        return parse_numero_br(texto.replace("%", "").strip())
    except ValueError:
        return None


def _separar_opcoes(texto: str, opcoes: list[str]) -> tuple[list[str], str | None]:
    """O Google junta as opções marcadas com ', ', mas as opções também contêm vírgulas.
    Reconhece as opções conhecidas por texto; o que sobrar é a resposta 'Outro'."""
    restante, marcadas = texto, []
    for op in sorted(opcoes, key=len, reverse=True):
        if op and op in restante:
            marcadas.append(op)
            restante = restante.replace(op, "", 1)
    sobra = re.sub(r"^[\s,]+|[\s,]+$", "", re.sub(r"(,\s*){2,}", ", ", restante))
    return [op for op in opcoes if op in marcadas], (sobra or None)


# --------------------------------------------------------------------------- modelo de saída

Valor = float | int | str | list[str] | None


class Resposta(BaseModel):
    codigo: str
    titulo: str
    tipo: str
    valor: Valor
    bruto: str
    outro: str | None = None  # texto livre da opção "Outro"


class RespostasQuestionario(BaseModel):
    respostas: dict[str, Resposta]
    carimbo: str | None = None
    empresa: str | None = None
    cnpj: str | None = None
    caminho: str | None = None  # resposta da P03
    modulos_completos: list[str] = Field(default_factory=list)
    alertas: list[str] = Field(default_factory=list)
    proveniencia: Proveniencia

    def valor(self, codigo: str, padrao: Valor = None) -> Valor:
        r = self.respostas.get(codigo)
        return padrao if r is None or r.valor is None else r.valor

    def pendentes(self, catalogo: Catalogo | None = None) -> list[str]:
        """Perguntas do caminho escolhido sem resposta (para cobrar na entrevista)."""
        cat = catalogo or carregar_catalogo()
        faltam = []
        for p in cat.perguntas.values():
            if p.modulo and p.modulo not in self.modulos_completos and not p.essencial:
                continue  # fora do caminho: não foi perguntada
            if p.modulo and p.modulo not in self.modulos_completos and not self._atua(p.modulo):
                continue  # essencial de atividade que a empresa não exerce
            if self.valor(p.codigo) in (None, "", []):
                faltam.append(p.codigo)
        return faltam

    def _atua(self, modulo: str) -> bool:
        marcadas = self.valor("P01", []) or []
        trecho = ATIVIDADES[modulo][1]
        return any(trecho in m for m in marcadas) or (self.valor(ATIVIDADES[modulo][0]) or 0) > 0


# --------------------------------------------------------------------------- leitura


def _ler_linhas(caminho: Path) -> list[list[str]]:
    if caminho.suffix.lower() in {".xlsx", ".xlsm"}:
        from openpyxl import load_workbook

        ws = load_workbook(caminho, read_only=True, data_only=True).worksheets[0]
        linhas = []
        for row in ws.iter_rows(values_only=True):
            linhas.append(["" if v is None else (v.strftime("%d/%m/%Y %H:%M:%S") if isinstance(v, datetime)
                                                   else str(v)) for v in row])
        return linhas
    bruto = caminho.read_bytes()
    for codificacao in ("utf-8-sig", "cp1252"):
        try:
            texto = bruto.decode(codificacao)
            break
        except UnicodeDecodeError:
            continue
    return list(csv.reader(io.StringIO(texto)))


def _converter(p: Pergunta, bruto: str, alertas: list[str]) -> tuple[Valor, str | None]:
    if p.tipo == "multipla":
        return _separar_opcoes(bruto, p.opcoes)
    if p.tipo == "unica":
        if bruto in p.opcoes:
            return bruto, None
        if p.aceita_outro:
            return "Outro", bruto
        alertas.append(f"{p.codigo}: resposta fora das opções ({bruto!r}).")
        return bruto, None
    if p.tipo == "moeda":
        v = parse_moeda(bruto)
        if v is None:
            alertas.append(f"{p.codigo}: valor em R$ não reconhecido ({bruto!r}); mantido como texto.")
            return bruto, None
        return v, None
    if p.tipo in {"pct", "numero", "ano"}:
        v = _parse_numero(bruto)
        if v is None:
            alertas.append(f"{p.codigo}: número não reconhecido ({bruto!r}).")
            return bruto, None
        return (int(v) if p.tipo == "ano" or (p.tipo == "numero" and v.is_integer()) else v), None
    return bruto, None


def _escolher_linha(linhas: list[list[str]], cabecalho: list[str], cnpj: str | None,
                    alertas: list[str]) -> int:
    dados = [i for i, l in enumerate(linhas[1:], start=1) if any(c.strip() for c in l)]
    if not dados:
        raise ValueError("A planilha não tem respostas.")
    if cnpj:
        col = cabecalho.index("CNPJ principal") if "CNPJ principal" in cabecalho else None
        alvo = apenas_digitos(cnpj)
        achadas = [i for i in dados if col is not None and apenas_digitos(linhas[i][col]) == alvo]
        if not achadas:
            raise ValueError(f"Nenhuma resposta com CNPJ {cnpj}.")
        if len(achadas) > 1:
            alertas.append(f"{len(achadas)} respostas para o CNPJ {cnpj}; usada a mais recente (linha "
                           f"{achadas[-1] + 1}).")
        return achadas[-1]
    if len(dados) > 1:
        alertas.append(f"Planilha com {len(dados)} respostas e nenhum CNPJ informado; usada a última "
                       f"(linha {dados[-1] + 1}). Informe --cnpj para escolher.")
    return dados[-1]


def ler_respostas(caminho: str | Path, cnpj: str | None = None,
                  catalogo: Catalogo | None = None) -> RespostasQuestionario:
    caminho = Path(caminho)
    cat = catalogo or carregar_catalogo()
    por_titulo = cat.por_titulo()
    linhas = _ler_linhas(caminho)
    cabecalho = [c.strip() for c in linhas[0]]
    alertas: list[str] = []

    desconhecidas = sorted({c for c in cabecalho if c and c not in por_titulo and c not in COLUNAS_SISTEMA})
    for c in desconhecidas:
        alertas.append(f"Coluna sem pergunta correspondente (título alterado no Forms?): {c!r}.")

    i = _escolher_linha(linhas, cabecalho, cnpj, alertas)
    linha = linhas[i] + [""] * (len(cabecalho) - len(linhas[i]))

    # junta as colunas repetidas (uma por caminho) e fica com a preenchida
    brutos: dict[str, str] = {}
    for titulo, valor in zip(cabecalho, linha):
        valor = valor.strip()
        p = por_titulo.get(titulo)
        if not p or not valor:
            continue
        if p.codigo in brutos and brutos[p.codigo] != valor:
            alertas.append(f"{p.codigo}: respostas diferentes na mesma linha ({brutos[p.codigo]!r} × {valor!r}); "
                           "mantida a primeira.")
            continue
        brutos.setdefault(p.codigo, valor)

    respostas = {}
    for codigo, bruto in brutos.items():
        p = cat.perguntas[codigo]
        valor, outro = _converter(p, bruto, alertas)
        respostas[codigo] = Resposta(codigo=codigo, titulo=p.titulo, tipo=p.tipo, valor=valor, bruto=bruto,
                                     outro=outro)

    carimbo = next((v for t, v in zip(cabecalho, linha) if t in {"Carimbo de data/hora", "Timestamp"}), None)
    caminho_p03 = brutos.get("P03")
    resultado = RespostasQuestionario(
        respostas=respostas, carimbo=carimbo or None,
        empresa=brutos.get("ID1"), cnpj=apenas_digitos(brutos.get("ID2")) or None,
        caminho=caminho_p03, modulos_completos=cat.combos.get(caminho_p03 or "", []),
        alertas=alertas,
        proveniencia=Proveniencia(arquivo=caminho.name, localizacao=f"linha {i + 1}", metodo=Metodo.PARSER),
    )
    _checar_consistencia(resultado, cat)
    return resultado


def _checar_consistencia(r: RespostasQuestionario, cat: Catalogo) -> None:
    a = r.alertas
    pcts = {m: r.valor(cod) for m, (cod, _) in ATIVIDADES.items()}
    informados = {m: v for m, v in pcts.items() if isinstance(v, (int, float))}
    if informados:
        soma = sum(informados.values())
        if not 95 <= soma <= 105:
            a.append(f"Parte 0: os % por atividade somam {soma:g}%, deveriam somar 100%.")

    marcadas = r.valor("P01", []) or []
    for m, (cod, trecho) in ATIVIDADES.items():
        marcou = any(trecho in x for x in marcadas)
        pct = informados.get(m)
        if marcou and pct is None:
            a.append(f"Parte 0: atividade '{trecho}' marcada sem % do faturamento ({cod}).")
        if not marcou and pct:
            a.append(f"Parte 0: {cod} = {pct:g}%, mas a atividade '{trecho}' não foi marcada em P01.")

    if r.caminho is None:
        a.append("P03 sem resposta: não dá para saber quais módulos da Parte B valem.")
    elif informados:
        esperado = [m for m in ATIVIDADES if (informados.get(m) or 0) >= LIMIAR_MODULO]
        if esperado and set(esperado) != set(r.modulos_completos):
            nomes = {"I": "fabricação", "C": "comércio", "S": "serviços"}
            a.append("P03 incoerente com a Parte 0: pelos % informados, os módulos completos seriam "
                     f"{' + '.join(nomes[m] for m in esperado)}; o cliente escolheu '{r.caminho}'.")


# --------------------------------------------------------------------------- CLI


def main() -> None:
    ap = argparse.ArgumentParser(description="Lê as respostas do Questionário do Empreendedor")
    ap.add_argument("arquivo", help="planilha de respostas exportada (.csv ou .xlsx)")
    ap.add_argument("--cnpj", help="escolhe a resposta pelo CNPJ principal")
    ap.add_argument("--saida", help="grava o resultado em JSON")
    args = ap.parse_args()
    r = ler_respostas(args.arquivo, cnpj=args.cnpj)
    if args.saida:
        Path(args.saida).write_text(r.model_dump_json(indent=2), encoding="utf-8")
    print(f"{r.empresa} · CNPJ {r.cnpj} · caminho: {r.caminho} · {len(r.respostas)} respostas")
    for c, resp in r.respostas.items():
        print(f"  {c:5} {json.dumps(resp.valor, ensure_ascii=False)[:80]}")
    pend = r.pendentes()
    print(f"\nSem resposta no caminho ({len(pend)}): {', '.join(pend)}")
    for al in r.alertas:
        print(f"ALERTA: {al}")


if __name__ == "__main__":
    main()
