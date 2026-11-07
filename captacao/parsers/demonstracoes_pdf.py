"""Leitor de DRE e Balanço Patrimonial em PDF com texto (nível 0 do funil — zero tokens).

Layouts suportados:
  A) Visualizador do SPED (ECD): "Descrição | Nota | Saldo anterior/inicial | Saldo atual/final",
     valores "R$ 1.234,56" e "R$ (1.234,56)"; descrições longas quebram em 2–3 linhas (acima e
     abaixo da linha dos valores) — o agrupamento é por proximidade vertical, não pela ordem do texto.
  B) Sistemas contábeis (Domínio e similares): "Descrição | Saldo Atual", valores "1.234,56D" / "1.234,56C".

A hierarquia das contas vem da indentação (posição x da linha). O leitor monta a árvore completa,
confere se cada grupo bate com a soma das contas filhas e mapeia os grupos-chave para DREAnual /
BalancoAnual. PDF escaneado (sem texto) não é lido aqui: segue para OCR/IA.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Literal

from captacao.schemas import BalancoAnual, DREAnual, Metodo, Proveniencia
from captacao.util import apenas_digitos, brl, normalizar_texto

Tipo = Literal["dre", "balanco", "balancete"]


class DemonstracaoNaoLida(Exception):
    pass


# --------------------------------------------------------------------------- linhas → árvore

_VALOR_A = r"R\$\s*\(?-?[\d.]+,\d{2}\)?"
_RE_VALORES_A = re.compile(rf"\s*({_VALOR_A})(?:\s+({_VALOR_A}))?\s*$")
_RE_VALOR_B = re.compile(r"\s+(-?[\d.]+,\d{2})\s*([DC])?\s*$")
_RE_IGNORAR = re.compile(
    r"^(ENTIDADE:|PERIODO (DA ESCRITURACAO|SELECIONADO)|NUMERO DE ORDEM|DESCRICAO (NOTA|SALDO)|ESTE DOCUMENTO|ESTE RELATORIO|VERSAO |\S*(\.\S\S){8,}|"
    r"EMPRESA:|C\.N\.P\.J|CNPJ:|BALANCO ENCERRADO|DEMONSTRACAO D|BALANCO PATRIMONIAL$|FOLHA:|_{5,}|CPF:|"
    r"REG\. NO CRC|ADMINISTRADOR|CONTADOR|PAGINA \d)"
)


@dataclass
class Conta:
    nome: str
    nivel: int
    valores: list[float]  # [anterior, atual] (layout A) ou [atual] (layout B)
    filhos: list["Conta"] = field(default_factory=list)
    x0: float = 0.0

    @property
    def atual(self) -> float:
        return self.valores[-1]

    @property
    def anterior(self) -> float | None:
        return self.valores[0] if len(self.valores) > 1 else None

    def percorrer(self):
        yield self
        for f in self.filhos:
            yield from f.percorrer()


def _num_a(texto: str) -> float:
    neg = "(" in texto or "-" in texto
    v = float(re.sub(r"[^\d,]", "", texto).replace(",", "."))
    return -v if neg else v


def _separar(texto: str) -> tuple[str, list[float] | None, str | None]:
    """→ (rótulo, valores, natureza D/C)."""
    m = _RE_VALORES_A.search(texto)
    if m:
        valores = [_num_a(g) for g in m.groups() if g]
        return texto[: m.start()].strip(), valores, None
    m = _RE_VALOR_B.search(texto)
    if m:
        v = float(m.group(1).replace(".", "").replace(",", "."))
        return texto[: m.start()].strip(), [v], m.group(2)
    return texto.strip(), None, None


Linha = tuple[float, float, str]  # (x0, y, texto); y cresce página a página (página × 10000 + topo)
DIST_QUEBRA = 10.0  # pt: pedaços de descrição ficam a 4–9 pt da linha dos valores; contas vizinhas, a 13,5+ pt


def _registros(linhas: list[Linha]) -> list[tuple[float, str, list[float], str | None]]:
    """Agrupa as linhas em contas. Cada linha com valores é uma âncora; linhas só com texto a até
    DIST_QUEBRA pontos de uma âncora são pedaços da descrição dela (o PDF não garante a ordem)."""
    ancoras, textos = [], []
    for x0, y, texto in linhas:
        norm = normalizar_texto(texto)
        if not norm or _RE_IGNORAR.match(norm):
            continue
        rotulo, valores, natureza = _separar(texto)
        if valores is not None:
            ancoras.append({"y": y, "pedacos": [(y, x0, rotulo)] if rotulo else [], "valores": valores,
                            "natureza": natureza, "x0": x0})
        else:
            textos.append((y, x0, rotulo))
    for y, x0, rotulo in textos:
        perto = min(ancoras, key=lambda a: abs(a["y"] - y), default=None)
        if perto is not None and abs(perto["y"] - y) <= DIST_QUEBRA:
            perto["pedacos"].append((y, x0, rotulo))
    registros = []
    for a in sorted(ancoras, key=lambda a: a["y"]):
        pedacos = sorted(a["pedacos"])
        if not pedacos:
            continue
        x0 = pedacos[0][1]  # a indentação é a do primeiro pedaço (as continuações voltam para a margem)
        registros.append((x0, " ".join(p[2] for p in pedacos), a["valores"], a["natureza"]))
    return registros


def montar_arvore(linhas: list[Linha], tipo: Tipo) -> list[Conta]:
    """Devolve as contas de 1º nível com seus filhos, pela indentação."""
    registros = _registros(linhas)

    # níveis pela indentação (agrupa posições x próximas)
    posicoes: list[float] = []
    for x0 in sorted({round(r[0], 1) for r in registros}):
        if not posicoes or x0 - posicoes[-1] > 1.0:
            posicoes.append(x0)
    nivel_de = lambda x: max(i for i, p in enumerate(posicoes) if p <= round(x, 1) + 1.0)  # noqa: E731

    raizes: list[Conta] = []
    pilha: list[Conta] = []
    sinal_secao = 1
    for x0, rotulo, valores, natureza in registros:
        nivel = nivel_de(x0)
        nome = re.sub(r"\s+", " ", rotulo)
        if natureza:  # layout B: converte D/C para sinal natural da seção
            if nivel == 0:
                n = normalizar_texto(nome)
                sinal_secao = 1 if (tipo == "balanco" and n.startswith("ATIVO")) else -1
                if tipo == "dre":
                    sinal_secao = -1  # DRE: crédito (C) positivo, débito (D) negativo
            fator = 1 if natureza == "D" else -1
            valores = [v * fator * sinal_secao for v in valores]
        conta = Conta(nome=nome, nivel=nivel, valores=valores, x0=x0)
        while pilha and pilha[-1].nivel >= nivel:
            pilha.pop()
        (pilha[-1].filhos if pilha else raizes).append(conta)
        pilha.append(conta)
    return raizes


# Layout "classificação": "352 03 (=) RESULTADO LÍQUIDO 2.445.752,76C" — código reduzido, classificação
# hierárquica (01, 01.1, 01.1.1 …), nome e valor com natureza D/C (às vezes seguido de lixo de impressão).
_RE_CLASSIFICACAO = re.compile(r"^\s*\d+\s+(\d{1,2}(?:\.\d+)*)\s+(.+?)\s+(-?[\d.]+,\d{2})\s*([DC])(?![A-Za-z])")
_RE_VALOR_DC = re.compile(r"(-?[\d.]+,\d{2})\s*([DC])?(?![A-Za-z])")


def montar_arvore_classificacao(textos: list[str], tipo: Tipo) -> list[Conta]:
    """Uma ou duas colunas de valor (saldo anterior e saldo atual): valores = [anterior, atual] ou [atual]."""
    raizes: list[Conta] = []
    pilha: list[Conta] = []
    sinal_secao = 1
    for t in textos:
        m = _RE_CLASSIFICACAO.match(t)
        if not m:
            continue
        classif, nome = m.group(1), m.group(2)
        nivel = classif.count(".")
        if nivel == 0:
            sinal_secao = 1 if (tipo == "balanco" and normalizar_texto(nome).startswith("ATIVO")) else -1
        tokens = _RE_VALOR_DC.findall(t[m.start(3):])[:2]
        valores = [float(v.replace(".", "").replace(",", ".")) * (1 if nat != "C" else -1) * sinal_secao
                   for v, nat in tokens]
        conta = Conta(nome=re.sub(r"\s+", " ", nome).strip(), nivel=nivel, valores=valores)
        while pilha and pilha[-1].nivel >= nivel:
            pilha.pop()
        (pilha[-1].filhos if pilha else raizes).append(conta)
        pilha.append(conta)
    return raizes


_RE_GASTO = r"^(DEDUC|CUSTO|CMV|CPV|CSP|DESPESA|IMPOSTO)"
_RE_GANHO = r"^(RECEITA|LUCRO|RESULTADO|PREJUIZO|OUTRAS RECEITAS)"


def _negar(c: Conta) -> None:
    """Inverte a conta e os filhos, exceto subgrupos de receita (ex.: receitas não operacionais dentro das despesas)."""
    if re.search(r"^RECEITA", _n(c)):
        return
    c.valores = [-v for v in c.valores]
    for f in c.filhos:
        _negar(f)


def corrigir_sinais_dre(raizes: list[Conta]) -> list[Conta]:
    """Sistemas que imprimem deduções, custos e despesas como positivos (sem D/C): inverte esses grupos — e, em
    DREs sem indentação, as linhas que vêm logo abaixo deles até o próximo resultado — quando isso faz as
    fórmulas da DRE fecharem."""
    import copy

    if not verificar_formulas_dre(raizes):
        return raizes
    invertida = copy.deepcopy(raizes)
    em_gasto = False
    for c in invertida:
        n = _n(c)
        if re.search(_RE_GASTO, n):
            em_gasto = True
        elif re.search(_RE_GANHO, n):
            em_gasto = False
            continue
        if em_gasto and c.atual > 0:
            _negar(c)
        elif em_gasto and c.atual < 0 and not c.filhos:  # desconto obtido dentro do custo: reduz o gasto
            c.valores = [-v for v in c.valores]
    return invertida if len(verificar_formulas_dre(invertida)) < len(verificar_formulas_dre(raizes)) else raizes


_RE_CODIGO = re.compile(r"^\d+\s+\d+(?:\.\d+){2,}\s+")
_NUM_C = r"\(?-?\d[\d.,]*[.,]\d{2}\)?"
_RE_VALORES_C = re.compile(rf"\s+({_NUM_C})(?:\s+({_NUM_C}))?\s*$")


def _num_c(texto: str, americano: bool) -> float:
    neg = texto.startswith("(") or texto.startswith("-")
    digitos = texto.strip("()-")
    digitos = digitos.replace(",", "") if americano else digitos.replace(".", "").replace(",", ".")
    v = float(digitos)
    return -v if neg else v


def montar_arvore_grupos(linhas: list[Linha]) -> tuple[list[Conta], list[str]]:
    """Layout C (sistemas com 'Código Classificação Descrição Saldo Total' e cópias editadas em Excel):
    cabeçalhos de grupo sem valor, contas com o valor na 1ª coluna e o total do grupo na 2ª coluna da
    última conta, resultados (Receita Líquida, Lucro Bruto…) no nível dos cabeçalhos."""
    texto = "\n".join(t for _, _, t in linhas)
    americano = bool(re.search(r"\d,\d{3}\.\d{2}\b", texto)) and not re.search(r"\d\.\d{3},\d{2}\b", texto)
    uteis = [(x0, t) for x0, _, t in linhas if normalizar_texto(t) and not _RE_IGNORAR.match(normalizar_texto(t))]
    x_titulos = [round(x0) for x0, t in uteis if not _RE_VALORES_C.search(t) and not _RE_CODIGO.match(t)]
    x_titulo = max(set(x_titulos), key=x_titulos.count) if x_titulos else None

    raizes: list[Conta] = []
    alertas: list[str] = []
    grupo: Conta | None = None
    total_informado: dict[int, float] = {}
    for x0, t in uteis:
        m = _RE_VALORES_C.search(t)
        rotulo = _RE_CODIGO.sub("", t[: m.start()] if m else t).strip()
        if not m:  # cabeçalho de grupo
            grupo = Conta(nome=rotulo, nivel=0, valores=[0.0], x0=x0)
            raizes.append(grupo)
            continue
        valores = [_num_c(g, americano) for g in m.groups() if g]
        eh_resultado = x_titulo is not None and abs(round(x0) - x_titulo) <= 2 and not _RE_CODIGO.match(t)
        if eh_resultado or grupo is None:
            raizes.append(Conta(nome=rotulo, nivel=0, valores=[valores[0]], x0=x0))
            grupo = None
            continue
        grupo.filhos.append(Conta(nome=rotulo, nivel=1, valores=[valores[0]], x0=x0))
        if len(valores) == 2:
            total_informado[id(grupo)] = valores[1]
    for g in raizes:
        if g.filhos:
            soma = round(sum(f.atual for f in g.filhos), 2)
            informado = total_informado.get(id(g))
            g.valores = [informado if informado is not None else soma]
            if informado is not None and abs(informado - soma) > 1.0:
                alertas.append(f"Soma não confere — {g.nome}: total do grupo {brl(informado)} × soma das contas "
                               f"{brl(soma)} (diferença {brl(informado - soma)}).")
    raizes = [r for r in raizes if r.filhos or r.valores != [0.0]]
    return raizes, alertas


def verificar_somas(raizes: list[Conta], tolerancia: float = 1.0) -> list[str]:
    """Grupos cujo valor não bate com a soma dos filhos (indica erro de leitura ou de layout)."""
    erros = []
    for raiz in raizes:
        for c in raiz.percorrer():
            if c.filhos:
                soma = sum(f.atual for f in c.filhos)
                if abs(soma - c.atual) > tolerancia:
                    erros.append(f"{c.nome}: grupo {brl(c.atual)} × soma das contas {brl(soma)}")
    return erros


def verificar_formulas_dre(raizes: list[Conta], tolerancia: float = 1.0) -> list[str]:
    def v(padrao: str) -> float | None:
        c = _primeira(raizes, padrao)
        return c.atual if c else None

    bruta, ded, liq = v(r"^RECEITA (OPERACIONAL )?BRUTA|^RECEITA OPERACIONAL$|^RECEITAS? DE VENDAS?$"), v(r"^DEDUC"), v(r"^RECEITA (OPERACIONAL )?LIQUIDA")
    custo, lucro_bruto = v(r"^(CMV|CPV|CSP|CUSTOS?\b(?!.*DESPESA))"), v(r"^LUCRO BRUTO|^RESULTADO BRUTO")
    erros = []
    if None not in (bruta, ded, liq) and abs(bruta + ded - liq) > tolerancia:
        erros.append(f"Receita bruta {brl(bruta)} + deduções {brl(ded)} ≠ receita líquida {brl(liq)}.")
    if None not in (liq, lucro_bruto) and abs(liq + (custo or 0) - lucro_bruto) > tolerancia:
        erros.append(f"Receita líquida {brl(liq)} + custo {brl(custo or 0)} ≠ lucro bruto {brl(lucro_bruto)}.")
    for grupo in ("^DEDUC",):
        c = _primeira(raizes, grupo)
        if c and c.filhos and abs(sum(f.atual for f in c.filhos) - c.atual) > tolerancia:
            erros.append(f"{c.nome}: grupo {brl(c.atual)} × soma das contas {brl(sum(f.atual for f in c.filhos))}")
    return [f"Soma não confere — {e}" for e in erros]


# --------------------------------------------------------------------------- mapeamento

def _n(c: Conta) -> str:
    return normalizar_texto(c.nome).replace("(-)", "").strip()


def _primeira(contas: list[Conta], padrao: str) -> Conta | None:
    """Conta mais rasa (busca em largura) cujo nome casa com o padrão."""
    fila = list(contas)
    while fila:
        c = fila.pop(0)
        if re.search(padrao, _n(c)):
            return c
        fila.extend(c.filhos)
    return None


def _folhas(contas: list[Conta], padrao: str, excluir: str | None = None) -> list[Conta]:
    return [c for r in contas for c in r.percorrer()
            if not c.filhos and re.search(padrao, _n(c)) and not (excluir and re.search(excluir, _n(c)))]


def _valor(c: Conta | None, idx: int) -> float | None:
    if c is None:
        return None
    return c.valores[idx] if len(c.valores) > abs(idx) or idx == -1 else None


def _soma(contas: list[Conta], idx: int) -> float | None:
    vals = [c.valores[idx] for c in contas if len(c.valores) > abs(idx) or idx == -1]
    return round(sum(vals), 2) if vals else None


PESSOAL = r"SALARIO|ORDENADO|13. SALARIO|FERIAS|^INSS|^F\.?G\.?T\.?S|INDENIZ|AVISO PREVIO|^VALE |ASSISTENCIA MEDICA|PREMIOS|GRATIFIC|IRRF SOB FOLHA|ENCARGOS SOCIAIS"
FINANCEIRAS = r"JUROS|IOF|VARIAC.*CAMBIA.*PASSIVA|COMISS.*BANCARIA|DESPESAS BANCARIAS|ENCARGOS FINANCEIROS"


def mapear_dre(raizes: list[Conta], idx: int) -> dict:
    receitas_fin = _primeira(raizes, r"^RECEITAS? FINANCEIRAS?")
    despesas_fin = _primeira(raizes, r"^DESPESAS? FINANCEIRAS?")
    if despesas_fin is not None:
        desp_fin = _valor(despesas_fin, idx)
    else:
        desp_fin = _soma([c for c in _folhas(raizes, FINANCEIRAS) if c.valores[idx] < 0], idx)
    res_fin = None
    if receitas_fin is not None or desp_fin is not None:
        res_fin = round((_valor(receitas_fin, idx) or 0) + (desp_fin or 0), 2)
    lucro = [c for r in raizes for c in r.percorrer()
             if re.search(r"LUCRO LIQUIDO|PREJUIZO DO EXERCICIO|LUCRO DO EXERCICIO|RESULTADO LIQUIDO|"
                          r"LUCRO \(PREJUIZO\)|RESULTADO DO EXERCICIO", _n(c))]
    operacionais = [g for g in (_primeira(raizes, r"^DESPESAS ADMINISTRATIVAS"),
                                _primeira(raizes, r"^DESPESAS (COM VENDAS|COMERCIAIS)")) if g]
    fin_ops = _soma([c for c in _folhas(operacionais, FINANCEIRAS) if len(c.valores) > abs(idx) or idx == -1], idx)
    return {
        "financeiras_nas_operacionais": fin_ops,
        "receita_bruta": _valor(_primeira(raizes, r"^RECEITA (OPERACIONAL )?BRUTA|^RECEITA OPERACIONAL$|^RECEITAS? DE VENDAS?$"), idx),
        "deducoes": _valor(_primeira(raizes, r"^DEDUC"), idx),
        "receita_liquida": _valor(_primeira(raizes, r"^RECEITA (OPERACIONAL )?LIQUIDA"), idx),
        "custo_vendas": _valor(_primeira(raizes, r"^(CMV|CPV|CSP|CUSTOS?\b(?!.*DESPESA))"), idx),
        "despesas_comerciais": _valor(_primeira(raizes, r"^DESPESAS (COM VENDAS|COMERCIAIS)"), idx),
        "despesas_administrativas": _valor(_primeira(raizes, r"^DESPESAS ADMINISTRATIVAS"), idx),
        "despesas_pessoal": _soma(_folhas(raizes, PESSOAL, excluir=r"PRO.?LABORE|ADIANTAMENTO"), idx),
        "pro_labore": _soma(_folhas(raizes, r"PRO.?LABORE"), idx),
        "aluguel": _soma(_folhas(raizes, r"ALUGU"), idx),
        "depreciacao_amortizacao": _soma(_folhas(raizes, r"DEPRECIA|AMORTIZA"), idx),
        "outras_receitas_despesas": _valor(_primeira(raizes, r"^OUTRAS (RECEITAS|DESPESAS)"), idx),
        "resultado_financeiro": res_fin,
        "ir_csll": _valor(_primeira(raizes, r"PROVIS.*(IR|IMPOSTO)|^IRPJ|^CSLL|IMPOSTO DE RENDA E CONTRIB"), idx),
        "lucro_liquido": _valor(lucro[-1], idx) if lucro else None,
    }


def _secao(raizes: list[Conta], padrao: str) -> list[Conta]:
    c = _primeira(raizes, padrao)
    return [c] if c else []


def mapear_balanco(raizes: list[Conta], idx: int) -> dict:
    ac = _secao(raizes, r"^ATIVO CIRCULANTE")
    anc = _secao(raizes, r"^ATIVO NAO.?CIRCULANTE")
    pc = _secao(raizes, r"^PASSIVO CIRCULANTE")
    pnc = _secao(raizes, r"^PASSIVO NAO.?CIRCULANTE|^PASSIVO EXIGIVEL A LONGO")
    pl = _primeira(raizes, r"^PATRIMONIO LIQUIDO")
    parcel = [c for c in (_primeira(pc, r"PARCELAMENT"), _primeira(pnc, r"PARCELAMENT")) if c]
    mutuos = [c for c in (_primeira(pc, r"SOCIOS|MUTUO|PESSOAS LIGADAS"),
                          _primeira(pnc, r"SOCIOS|MUTUO|PESSOAS LIGADAS")) if c]
    return {
        "caixa_aplicacoes": _valor(_primeira(ac, r"^DISPONI|^CAIXA E EQUIVALENTES"), idx),
        "contas_receber": _valor(_primeira(ac, r"^CLIENTES|^DUPLICATAS A RECEBER|^CONTAS A RECEBER|^CREDITOS? DE CLIENTES"), idx),
        "estoques": _valor(_primeira(ac, r"^ESTOQUES?"), idx),
        "imobilizado_liquido": _valor(_primeira(anc, r"^IMOBILIZADO"), idx),
        "fornecedores": _valor(_primeira(pc, r"^FORNECEDORES"), idx),
        "obrigacoes_trabalhistas": _valor(_primeira(pc, r"TRABALHIST|^OBRIGACOES SOCIAIS"), idx),
        "obrigacoes_fiscais": _valor(_primeira(pc, r"^OBRIGACOES (FISCAIS|TRIBUTARIAS)|^IMPOSTOS E CONTRIBUICOES"), idx),
        "parcelamentos_fiscais": _soma(parcel, idx),
        "emprestimos_cp": _valor(_primeira(pc, r"^EMPRESTIMOS|^FINANCIAMENTOS"), idx),
        "emprestimos_lp": _valor(_primeira(pnc, r"^EMPRESTIMOS|^FINANCIAMENTOS"), idx),
        "mutuos_socios": _soma(mutuos, idx),
        "patrimonio_liquido": _valor(pl, idx),
    }


# --------------------------------------------------------------------------- balancete

# "1639 3.2.02.01.0017 SALARIOS 0,00 516.169,02 24.026,22 492.142,80D": código, classificação, descrição,
# saldo anterior, débito, crédito e saldo atual (natureza D/C nos saldos; 0,00 sem natureza)
_V = r"-?[\d.]+,\d{2}"
_RE_BALANCETE = re.compile(
    rf"^\s*\d+\s+(\d+(?:\.\d+)*)\s+(.+?)\s+({_V})\s*([DC])?\s+({_V})\s+({_V})\s+({_V})\s*([DC])?\s*$")
_RE_PATRIMONIAL = r"^(ATIVO|PASSIVO|PATRIMONIO)"


def montar_arvore_balancete(textos: list[str]) -> list[Conta]:
    """Árvore pela classificação, com o saldo atual. Patrimoniais: ativo devedor positivo, passivo/PL credor
    positivo. Resultado: crédito positivo, débito negativo (convenção da DRE)."""
    raizes: list[Conta] = []
    pilha: list[Conta] = []
    secao = ""
    for t in textos:
        m = _RE_BALANCETE.match(t)
        if not m:
            continue
        classif, nome, *_, atual, natureza = m.groups()
        nivel = classif.count(".")
        nome = re.sub(r"\s+", " ", nome).strip()
        if nivel == 0:
            secao = normalizar_texto(nome)
        v = float(atual.replace(".", "").replace(",", "."))
        devedor = natureza != "C"
        positivo = devedor if secao.startswith("ATIVO") else not devedor
        if nivel == 1 and normalizar_texto(nome) == "CIRCULANTE":  # "CIRCULANTE" sob ATIVO/PASSIVO
            nome = f"{'ATIVO' if secao.startswith('ATIVO') else 'PASSIVO'} CIRCULANTE"
        conta = Conta(nome=nome, nivel=nivel, valores=[v if positivo else -v])
        while pilha and pilha[-1].nivel >= nivel:
            pilha.pop()
        (pilha[-1].filhos if pilha else raizes).append(conta)
        pilha.append(conta)
    return raizes


def ler_linhas_sem_sobreposicao(caminho: str | Path) -> list[Linha]:
    """Alguns sistemas imprimem por cima da tabela o nome do grupo em fonte maior ("CIRCU2L1A.N1TE"):
    descarta os caracteres bem maiores que o tamanho dominante da página."""
    import statistics

    import pdfplumber

    linhas = []
    with pdfplumber.open(caminho) as pdf:
        for i, p in enumerate(pdf.pages):
            tamanhos = [round(c["size"], 1) for c in p.chars]
            if tamanhos:
                moda = statistics.mode(tamanhos)
                p = p.filter(lambda o, m=moda: o.get("object_type") != "char" or o["size"] <= m * 1.25)
            linhas += [(l["x0"], i * 10000 + (l["top"] + l["bottom"]) / 2, l["text"]) for l in p.extract_text_lines()]
    return linhas


def ler_balancete(caminho: Path, linhas: list[Linha], cabecalho: str) -> "DemonstracaoLida":
    raizes = montar_arvore_balancete([t for _, _, t in sorted(linhas, key=lambda l: l[1])])
    if not raizes:
        raise DemonstracaoNaoLida("balancete sem contas reconhecidas")
    inicio, fim = _datas(cabecalho)
    if fim is None:
        raise DemonstracaoNaoLida("data de encerramento não encontrada no cabeçalho")
    ent = re.search(r"(?:Entidade|Empresa):\s*(.+?)(?:\s+Folha:.*)?$", cabecalho, flags=re.M)
    cnpj = re.search(r"\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}", cabecalho)
    patrimoniais = [r for r in raizes if re.search(_RE_PATRIMONIAL, _n(r))]
    resultado = [r for r in raizes if r not in patrimoniais]
    doc = DemonstracaoLida(tipo="balancete", layout="balancete", entidade=ent.group(1).strip() if ent else None,
                           cnpj=apenas_digitos(cnpj.group(0)) if cnpj else None, data_fim=fim, data_inicio=inicio,
                           contas=raizes, alertas=[])
    meses = (fim.month - inicio.month + 1 + 12 * (fim.year - inicio.year)) if inicio else fim.month
    prov = Proveniencia(arquivo=caminho.name, localizacao="balancete (saldo atual)", metodo=Metodo.PARSER,
                        confianca="media")
    if resultado:
        campos = mapear_dre(resultado, -1)
        if campos.get("lucro_liquido") is None:  # balancete antes do encerramento: resultado = soma das contas
            campos["lucro_liquido"] = round(sum(r.atual for r in resultado), 2)
        if campos.get("receita_liquida") is None and campos.get("receita_bruta") is not None:
            campos["receita_liquida"] = round(campos["receita_bruta"] + (campos.get("deducoes") or 0), 2)
        doc.dres.append(DREAnual(cnpj=doc.cnpj or "", exercicio=fim.year, meses=meses, proveniencia=prov, **campos))
        if not campos.get("custo_vendas"):
            doc.alertas.append("Balancete sem conta de custo (CMV/CPV/CSP): custo pode estar nas despesas ou não "
                               "ter sido contabilizado.")
    if patrimoniais:
        doc.balancos.append(BalancoAnual(cnpj=doc.cnpj or "", exercicio=fim.year, data_base=fim, proveniencia=prov,
                                         **mapear_balanco(patrimoniais, -1)))
    if doc.cnpj is None:
        doc.alertas.append("CNPJ não encontrado no cabeçalho.")
    return doc


# --------------------------------------------------------------------------- documento


@dataclass
class DemonstracaoLida:
    tipo: Tipo
    layout: Literal["sped", "sistema", "grupos", "classificacao", "balancete"]
    entidade: str | None
    cnpj: str | None
    data_fim: date
    data_inicio: date | None
    contas: list[Conta]
    alertas: list[str]
    dres: list[DREAnual] = field(default_factory=list)
    balancos: list[BalancoAnual] = field(default_factory=list)
    gerencial: bool = False  # "DRE gerencial" no mesmo formato da contábil (versão do dono)


_MESES = {m: i for i, m in enumerate(["JANEIRO", "FEVEREIRO", "MARCO", "ABRIL", "MAIO", "JUNHO", "JULHO",
                                      "AGOSTO", "SETEMBRO", "OUTUBRO", "NOVEMBRO", "DEZEMBRO"], start=1)}


def _datas(cabecalho: str) -> tuple[date | None, date | None]:
    n = normalizar_texto(cabecalho)
    m = re.search(r"PERIODO SELECIONADO: (\d{1,2}) DE (\w+) DE (\d{4}) A (\d{1,2}) DE (\w+) DE (\d{4})", n)
    if m:
        d1, m1, a1, d2, m2, a2 = m.groups()
        return date(int(a1), _MESES[m1], int(d1)), date(int(a2), _MESES[m2], int(d2))
    m = re.search(r"PERIODO DA ESCRITURACAO: (\d\d)/(\d\d)/(\d{4}) A (\d\d)/(\d\d)/(\d{4})", n)
    if m:
        d1, m1, a1, d2, m2, a2 = map(int, m.groups())
        return date(a1, m1, d1), date(a2, m2, d2)
    m = re.search(r"(ENCERRADO EM|PERIODO:?\s*\d\d/\d\d/\d{4} A|ATE|EM):?\s*(\d\d)/(\d\d)/(\d{4})(?! A \d)", n)
    if m:
        d, mm, a = map(int, m.groups()[1:])
        return None, date(a, mm, d)
    # "Demonstração do Resultado de 01/01/2024 a 31/12/2024", "Balanço Patrimonial em 01/01/2024 a 31/12/2024"
    m = re.search(r"(\d\d)/(\d\d)/(\d{4}) A (\d\d)/(\d\d)/(\d{4})", n)
    if m:
        d1, m1, a1, d2, m2, a2 = map(int, m.groups())
        return date(a1, m1, d1), date(a2, m2, d2)
    # "Período: 01/01/2025 - 31/12/2025" (balancetes)
    m = re.search(r"(\d\d)/(\d\d)/(\d{4}) ?- ?(\d\d)/(\d\d)/(\d{4})", n)
    if m:
        d1, m1, a1, d2, m2, a2 = map(int, m.groups())
        return date(a1, m1, d1), date(a2, m2, d2)
    # "Período: 01/2025 a 12/2025" (mês/ano)
    m = re.search(r"PERIODO:?\s*(\d\d)/(\d{4}) A (\d\d)/(\d{4})", n)
    if m:
        m1, a1, m2, a2 = map(int, m.groups())
        ultimo = (date(a2 + (m2 == 12), m2 % 12 + 1, 1) - date.resolution)
        return date(a1, m1, 1), ultimo
    return None, None


def identificar_tipo(texto_inicial: str) -> Tipo | None:
    n = normalizar_texto(texto_inicial[:600])
    if re.search(r"\bBALANCETE\b", n):
        return "balancete"
    if "BALANCO PATRIMONIAL" in n:
        return "balanco"
    if re.search(r"DEMONSTRA\w* D[OE]S? RESULTADO|\bDRE\b", n):
        return "dre"
    return None


def ler_linhas_pdf(caminho: str | Path) -> list[Linha]:
    import pdfplumber

    with pdfplumber.open(caminho) as pdf:
        return [(l["x0"], i * 10000 + (l["top"] + l["bottom"]) / 2, l["text"])
                for i, p in enumerate(pdf.pages) for l in p.extract_text_lines()]


def ler_demonstracao(caminho: str | Path, linhas: list[Linha] | None = None) -> DemonstracaoLida:
    caminho = Path(caminho)
    linhas = linhas if linhas is not None else ler_linhas_pdf(caminho)
    texto = "\n".join(t for _, _, t in linhas)
    if len(texto.strip()) < 50:
        raise DemonstracaoNaoLida("PDF sem texto (escaneado): precisa de OCR/IA ou do arquivo original")
    tipo = identificar_tipo(texto)
    if tipo is None:
        raise DemonstracaoNaoLida("não parece DRE nem Balanço Patrimonial")
    if tipo == "balancete":
        if caminho.exists():
            linhas = ler_linhas_sem_sobreposicao(caminho)
            texto = "\n".join(t for _, _, t in linhas)
        return ler_balancete(caminho, linhas, texto[:800])

    cabecalho = texto[:800]
    if re.search(r"R\$\s*\(?[\d.]+,\d{2}", texto):
        layout = "sped"
    elif sum(1 for _, _, t in linhas if _RE_CLASSIFICACAO.match(t)) >= 5:
        layout = "classificacao"
    elif any(normalizar_texto(lin).endswith("SALDO TOTAL") for lin in cabecalho.splitlines()) or \
            sum(1 for _, _, t in linhas if _RE_CODIGO.match(t)) >= 5:
        layout = "grupos"
    else:
        layout = "sistema"
    gerencial = "GERENCIAL" in normalizar_texto(f"{caminho.name} {cabecalho}")
    ent = re.search(r"(?:Entidade|Empresa):\s*(.+?)(?:\s+Folha:.*)?$", cabecalho, flags=re.M)
    cnpj = re.search(r"\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}", cabecalho)
    inicio, fim = _datas(cabecalho)
    if fim is None:
        raise DemonstracaoNaoLida("data de encerramento não encontrada no cabeçalho")

    alertas: list[str] = []
    if layout == "grupos":
        contas, alertas = montar_arvore_grupos(linhas)
    elif layout == "classificacao":
        contas = montar_arvore_classificacao([t for _, _, t in sorted(linhas, key=lambda l: l[1])], tipo)
    else:
        contas = montar_arvore(linhas, tipo)
        if tipo == "dre":
            contas = corrigir_sinais_dre(contas)
    if not contas:
        raise DemonstracaoNaoLida("nenhuma conta com valor reconhecida")
    if tipo == "balanco":
        alertas += [f"Soma não confere — {e}" for e in verificar_somas(contas)]
    else:  # na DRE os subtotais não são a soma das linhas abaixo: confere as fórmulas
        alertas += verificar_formulas_dre(contas)

    doc = DemonstracaoLida(tipo=tipo, layout=layout, entidade=ent.group(1).strip() if ent else None,
                           cnpj=apenas_digitos(cnpj.group(0)) if cnpj else None, data_fim=fim,
                           data_inicio=inicio, contas=contas, alertas=alertas, gerencial=gerencial)
    confianca = "alta" if not alertas else "media"
    colunas = [(-1, fim.year, "saldo atual")]
    if layout in ("sped", "classificacao") and len(contas[0].valores) == 2:
        colunas.append((0, fim.year - 1, "comparativo (saldo anterior)"))
    if doc.cnpj is None:
        doc.alertas.append("CNPJ não encontrado no cabeçalho.")
    meses = (fim.month - inicio.month + 1 + 12 * (fim.year - inicio.year)) if inicio else fim.month
    for idx, exercicio, onde in colunas:
        if gerencial:
            onde = f"gerencial ({onde})"
        prov = Proveniencia(arquivo=caminho.name, localizacao=onde, metodo=Metodo.PARSER,
                            confianca=confianca if idx == -1 else "media")
        if tipo == "dre":
            doc.dres.append(DREAnual(cnpj=doc.cnpj or "", exercicio=exercicio, meses=meses if idx == -1 else 12,
                                     proveniencia=prov, **mapear_dre(contas, idx)))
        else:
            doc.balancos.append(BalancoAnual(cnpj=doc.cnpj or "", exercicio=exercicio,
                                             data_base=fim if idx == -1 else date(exercicio, 12, 31),
                                             proveniencia=prov, **mapear_balanco(contas, idx)))
    if tipo == "balanco":
        ativo = _primeira(contas, r"^ATIVO$")
        passivo = _primeira(contas, r"^PASSIVO$|^PASSIVO E PATRIMONIO")
        pl = _primeira(contas, r"^PATRIMONIO LIQUIDO")
        if ativo and passivo:
            total_p = passivo.atual + (pl.atual if pl and pl not in list(passivo.percorrer()) else 0)
            if abs(ativo.atual - total_p) > 1.0:
                doc.alertas.append(f"Ativo ({brl(ativo.atual)}) diferente de Passivo + PL ({brl(total_p)}).")
    return doc


# --------------------------------------------------------------------------- contábil × gerencial


@dataclass
class DiferencaConta:
    conta: str
    contabil: float | None
    gerencial: float | None

    @property
    def diferenca(self) -> float:
        return round((self.gerencial or 0.0) - (self.contabil or 0.0), 2)

    @property
    def redonda(self) -> bool:
        """Diferença em número redondo (múltiplo de R$ 1.000): sinal de ajuste manual."""
        d = abs(self.diferenca)
        return d >= 1000 and abs(d - round(d, -3)) < 0.01


def comparar_linhas(contabil: DemonstracaoLida, gerencial: DemonstracaoLida) -> list[DiferencaConta]:
    """Contas (e grupos) com valor diferente entre a versão contábil e a gerencial do mesmo período."""
    def valores(doc: DemonstracaoLida) -> dict[str, float]:
        saida: dict[str, float] = {}
        for raiz in doc.contas:
            for c in raiz.percorrer():
                chave = _n(c)
                saida[chave] = round(saida.get(chave, 0.0) + c.atual, 2) if chave in saida else c.atual
        return saida

    a, b = valores(contabil), valores(gerencial)
    nomes = {_n(c): c.nome for doc in (contabil, gerencial) for r in doc.contas for c in r.percorrer()}
    difs = [DiferencaConta(conta=nomes[k], contabil=a.get(k), gerencial=b.get(k))
            for k in dict.fromkeys(list(a) + list(b))
            if abs((a.get(k) or 0.0) - (b.get(k) or 0.0)) > 1.0]
    return sorted(difs, key=lambda d: -abs(d.diferenca))
