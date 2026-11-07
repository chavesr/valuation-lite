"""Leitor de DRE gerencial / fluxo de caixa gerencial em Excel (nível 0 do funil — zero tokens).

Planilhas gerenciais não têm padrão. O leitor procura a estrutura mais comum nas PMEs:

  * formato largo: uma linha de cabeçalho com os meses (JANEIRO…, JAN/25, 01/2025 ou datas) e os
    nomes das contas numa coluna à esquerda; coluna opcional de acumulado/total;
  * formato longo: os meses descem numa coluna (datas ou nomes) e as contas estão no cabeçalho
    acima de cada bloco.

Hierarquia: linhas em negrito abrem um grupo; as linhas comuns logo abaixo (até a linha em branco ou o
próximo negrito) são as contas do grupo. Sem negrito, cada linha é uma conta.

Cada conta recebe uma categoria econômica (`Categoria`) pelo dicionário de regras, por herança do grupo
ou pelo mapa salvo do case (`mapa_gerencial.json`, preenchido pelo analista ou pela IA). O que não for
reconhecido fica PENDENTE — só os nomes das contas (sem valores) iriam para a IA.

A planilha gerencial costuma ser de CAIXA: mistura empréstimos recebidos, investimentos e juros com a
operação. As categorias separam operação, financeiro, investimento e financiamento para o valuation.
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime
from enum import Enum
from pathlib import Path

from pydantic import BaseModel, Field

from captacao.schemas import GerencialMes, Metodo, Proveniencia
from captacao.util import brl, normalizar_texto


class Categoria(str, Enum):
    RECEITA_OPERACIONAL = "receita_operacional"
    RECEITA_FINANCEIRA = "receita_financeira"
    DEDUCOES = "deducoes"  # tributos sobre venda, devoluções
    CUSTO_VARIAVEL = "custo_variavel"  # matéria-prima, mercadoria, comissões, frete
    DESPESA_PESSOAL = "despesa_pessoal"
    PRO_LABORE = "pro_labore"
    DESPESA_ADMINISTRATIVA = "despesa_administrativa"
    DESPESA_COMERCIAL = "despesa_comercial"
    DESPESA_FINANCEIRA = "despesa_financeira"  # juros, tarifas, IOF
    IMPOSTOS_LUCRO = "impostos_lucro"  # IRPJ/CSLL
    INVESTIMENTO = "investimento"  # capex
    VENDA_ATIVO = "venda_ativo"
    EMPRESTIMO_RECEBIDO = "emprestimo_recebido"
    EMPRESTIMO_PAGO = "emprestimo_pago"  # amortização do principal
    APORTE_SOCIO = "aporte_socio"
    RETIRADA_SOCIO = "retirada_socio"  # distribuição de lucros, retiradas
    NAO_OPERACIONAL_ENTRADA = "nao_operacional_entrada"
    NAO_OPERACIONAL_SAIDA = "nao_operacional_saida"
    SUBTOTAL = "subtotal"  # resultado/total calculado pela própria planilha
    IGNORAR = "ignorar"  # %, médias, acumulados
    PENDENTE = "pendente"


ENTRADAS = {Categoria.RECEITA_OPERACIONAL, Categoria.RECEITA_FINANCEIRA, Categoria.VENDA_ATIVO,
            Categoria.EMPRESTIMO_RECEBIDO, Categoria.APORTE_SOCIO, Categoria.NAO_OPERACIONAL_ENTRADA}
OPERACIONAIS = {Categoria.RECEITA_OPERACIONAL, Categoria.DEDUCOES, Categoria.CUSTO_VARIAVEL,
                Categoria.DESPESA_PESSOAL, Categoria.PRO_LABORE, Categoria.DESPESA_ADMINISTRATIVA,
                Categoria.DESPESA_COMERCIAL}
SEM_VALOR = {Categoria.SUBTOTAL, Categoria.IGNORAR}

# ordem importa: a primeira regra que casar vence
REGRAS: list[tuple[str, Categoria]] = [
    (r"%|MEDIA|ACUMUL|MARGEM|PARTICIPACAO|^AV$|^AH$", Categoria.IGNORAR),
    (r"^(RESULTADO|LUCRO|PREJUIZO|EBITDA|EBIT|SALDO|GERACAO DE CAIXA)|ENTRADAS TOTAIS|SAIDAS TOTAIS|"
     r"^TOTAL|RECEITA (OPERACIONAL )?LIQUIDA|MARGEM DE CONTRIBUICAO", Categoria.SUBTOTAL),
    (r"JUROS|IOF|TARIFA|DESPESAS? BANCARIA|^FINANCEIRO$|DESPESAS? FINANCEIRA|ENCARGOS FINANCEIROS",
     Categoria.DESPESA_FINANCEIRA),
    (r"RENDIMENTO|APLICAC|RECEITAS? FINANCEIRA", Categoria.RECEITA_FINANCEIRA),
    (r"(PAGAMENTO|AMORTIZ|PARCELA).*(EMPRESTIMO|FINANCIAMENTO)|(EMPRESTIMO|FINANCIAMENTO).*(PAGO|PAGAMENTO|"
     r"AMORTIZ|PARCELA)", Categoria.EMPRESTIMO_PAGO),
    (r"EMPRESTIMO|FINANCIAMENTO|CAPITAL DE GIRO|ANTECIPACAO DE RECEBIVEIS", Categoria.EMPRESTIMO_RECEBIDO),
    (r"VENDA (DE )?(VEICULO|ATIVO|IMOBILIZADO|MAQUINA|BEM)", Categoria.VENDA_ATIVO),
    (r"INVESTIMENTO|IMOBILIZADO|AQUISICAO DE (MAQUINA|EQUIPAMENTO|VEICULO)|OBRAS?$|REFORMA|BENFEITORIA",
     Categoria.INVESTIMENTO),
    (r"APORTE|INTEGRALIZACAO", Categoria.APORTE_SOCIO),
    (r"DISTRIBUI|RETIRADA|LUCROS? (PAGOS|DISTRIB)|DIVIDENDO", Categoria.RETIRADA_SOCIO),
    (r"PRO.?LABORE", Categoria.PRO_LABORE),
    (r"IRPJ|CSLL|IMPOSTO DE RENDA|CONTRIBUICAO SOCIAL", Categoria.IMPOSTOS_LUCRO),
    (r"DEDUC|TRIBUTO|IMPOSTOS?( SOBRE| S/)? VENDA|^IMPOSTOS?$|^DAS$|SIMPLES|ICMS|PIS|COFINS|^ISS|DEVOLUC",
     Categoria.DEDUCOES),
    (r"DESPESAS? VARIAVE|CUSTO|CMV|CPV|PRODUCAO|MATERIA.?PRIMA|INSUMO|MERCADORIA|COMISS|FRETE|EMBALAGE",
     Categoria.CUSTO_VARIAVEL),
    (r"PESSOAL|SALARI|FOLHA|ENCARGOS|BENEFICIO|FGTS|INSS|FERIAS|13|RESCIS|VALE ", Categoria.DESPESA_PESSOAL),
    (r"COMERCIAL|MARKETING|PUBLICIDADE|PROPAGANDA|FEIRA|DESPESAS? (COM|DE) VENDAS?",
     Categoria.DESPESA_COMERCIAL),
    (r"ADMINISTRATIV|ALUGUE|ENERGIA|AGUA|TELEFON|INTERNET|CONTAB|MANUTENC|VEICULO|COMBUSTIV|SEGURO|SISTEMA|"
     r"SOFTWARE|DESPESAS? FIXA|OCUPACAO|ESCRITORIO|LIMPEZA|VIAGE", Categoria.DESPESA_ADMINISTRATIVA),
    (r"RECEITA|FATURAMENTO|VENDAS?|SERVICOS?( PRESTADOS)?$|ENTRADAS? OPERACION", Categoria.RECEITA_OPERACIONAL),
    (r"OUTRAS ENTRADAS|OUTRAS RECEITAS|ENTRADAS? NAO OPERAC", Categoria.NAO_OPERACIONAL_ENTRADA),
    (r"OUTRAS SAIDAS|OUTRAS DESPESAS|SAIDAS? NAO OPERAC", Categoria.NAO_OPERACIONAL_SAIDA),
]

_MESES = {"JAN": 1, "FEV": 2, "MAR": 3, "ABR": 4, "MAI": 5, "JUN": 6, "JUL": 7, "AGO": 8, "SET": 9,
          "OUT": 10, "NOV": 11, "DEZ": 12}


def classificar(rotulo: str) -> Categoria | None:
    n = normalizar_texto(rotulo)
    for padrao, cat in REGRAS:
        if re.search(padrao, n):
            return cat
    return None


def _mes(valor, ano_padrao: int | None) -> tuple[int, int] | None:
    """Célula de cabeçalho → (ano, mês). Aceita data, 'JANEIRO', 'JAN/25', '01/2025', '2025-01'."""
    if isinstance(valor, (datetime, date)):
        return valor.year, valor.month
    if not isinstance(valor, str):
        return None
    n = normalizar_texto(valor)
    m = re.fullmatch(r"(\d{4})[-/](\d{1,2})", n) or re.fullmatch(r"(\d{1,2})[-/](\d{4})", n)
    if m:
        a, b = m.groups()
        ano, mes = (int(a), int(b)) if len(a) == 4 else (int(b), int(a))
        return (ano, mes) if 1 <= mes <= 12 else None
    m = re.fullmatch(r"([A-Z]{3})[A-Z]*\.?(?:[ /-]?(\d{2}|\d{4}))?", n)
    if m and m.group(1) in _MESES:
        ano = m.group(2)
        ano = (2000 + int(ano) if len(ano) == 2 else int(ano)) if ano else ano_padrao
        return (ano, _MESES[m.group(1)]) if ano else None
    return None


def _numero(v) -> float | None:
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    return None


# --------------------------------------------------------------------------- modelo


class LinhaGerencial(BaseModel):
    rotulo: str
    categoria: Categoria
    origem: str  # regra | grupo | mapa | pendente
    grupo: str | None = None
    eh_grupo: bool = False
    valores: dict[str, float] = Field(default_factory=dict)  # competência → valor com sinal (+ entra, − sai)
    acumulado: float | None = None  # total do ano informado pela planilha
    localizacao: str = ""


class DREGerencial(BaseModel):
    linhas: list[LinhaGerencial]
    competencias: list[str]
    alertas: list[str] = Field(default_factory=list)
    proveniencia: Proveniencia

    def contas(self) -> list[LinhaGerencial]:
        """Linhas que entram nas somas: contas (não grupos), sem subtotais/percentuais."""
        return [l for l in self.linhas if not l.eh_grupo and l.categoria not in SEM_VALOR]

    def pendentes(self) -> list[str]:
        return [l.rotulo for l in self.linhas if l.categoria == Categoria.PENDENTE]

    def por_categoria(self) -> dict[str, dict[str, float]]:
        """categoria → {competência: valor}."""
        saida: dict[str, dict[str, float]] = {}
        for l in self.contas():
            serie = saida.setdefault(l.categoria.value, {})
            for c, v in l.valores.items():
                serie[c] = round(serie.get(c, 0.0) + v, 2)
        return saida

    def receita_mensal(self) -> dict[str, float]:
        return self.por_categoria().get(Categoria.RECEITA_OPERACIONAL.value, {})

    def resultado_operacional(self) -> dict[str, float]:
        """Receita − deduções − custos − despesas operacionais (antes de financeiro, investimento e
        financiamento): o resultado da operação, comparável entre empresas."""
        cats = self.por_categoria()
        return {c: round(sum(cats.get(k.value, {}).get(c, 0.0) for k in OPERACIONAIS), 2)
                for c in self.competencias}

    def resumo_anual(self) -> dict[int, dict[str, float]]:
        anos: dict[int, dict[str, float]] = {}
        for cat, serie in self.por_categoria().items():
            for c, v in serie.items():
                ano = anos.setdefault(int(c[:4]), {})
                ano[cat] = round(ano.get(cat, 0.0) + v, 2)
        for ano, d in anos.items():
            d["resultado_operacional"] = round(sum(d.get(k.value, 0.0) for k in OPERACIONAIS), 2)
        return anos

    def gerencial_mensal(self) -> list[GerencialMes]:
        prov = self.proveniencia.model_copy(update={"confianca": "media"})
        return [GerencialMes(competencia=c, receita=v, proveniencia=prov)
                for c, v in sorted(self.receita_mensal().items())]


class GerencialNaoLido(Exception):
    pass


# --------------------------------------------------------------------------- leitura


def _ano_padrao(ws, caminho: Path) -> int | None:
    for row in ws.iter_rows(min_row=1, max_row=6, values_only=True):
        for v in row:
            if isinstance(v, str) and (m := re.search(r"\b(20\d{2})\b", v)):
                return int(m.group(1))
    m = re.search(r"\b(20\d{2})\b", f"{ws.title} {caminho.stem}")
    return int(m.group(1)) if m else None


def _blocos_largos(ws, ano: int | None):
    """Linhas de cabeçalho com 6+ meses → (linha, {coluna: competência}, coluna_acumulado)."""
    for row in ws.iter_rows(min_row=1, max_row=min(ws.max_row, 40)):
        meses = {}
        for c in row:
            m = _mes(c.value, ano)
            if m:
                meses[c.column] = f"{m[0]:04d}-{m[1]:02d}"
        if len(meses) >= 6 and len(set(meses.values())) == len(meses):
            acum = next((c.column for c in row if isinstance(c.value, str)
                         and re.search(r"ACUM|TOTAL", normalizar_texto(c.value))
                         and c.column > max(meses)), None)
            return row[0].row, meses, acum
    return None


def _ler_largo(ws, linha_cab: int, meses: dict[int, str], col_acum: int | None) -> list[dict]:
    col_rotulo = None
    primeira_mes = min(meses)
    contagem: dict[int, int] = {}
    for row in ws.iter_rows(min_row=linha_cab + 1, max_col=primeira_mes - 1):
        for c in row:
            if isinstance(c.value, str) and c.value.strip():
                contagem[c.column] = contagem.get(c.column, 0) + 1
    if not contagem:
        return []
    col_rotulo = max(contagem, key=contagem.get)
    brutas = []
    for r in range(linha_cab + 1, ws.max_row + 1):
        cel = ws.cell(row=r, column=col_rotulo)
        rotulo = cel.value.strip() if isinstance(cel.value, str) else None
        # zero = mês sem lançamento (planilhas do ano corrente trazem os meses futuros zerados)
        valores = {meses[c]: v for c in meses if (v := _numero(ws.cell(row=r, column=c).value))}
        brutas.append({"linha": r, "rotulo": rotulo, "negrito": bool(cel.font and cel.font.bold),
                       "valores": valores,
                       "acumulado": _numero(ws.cell(row=r, column=col_acum).value) if col_acum else None,
                       "local": f"{ws.title}!{cel.column_letter}{r}"})
    return brutas


def _ler_longo(ws, ano: int | None) -> list[dict]:
    """Meses descendo numa coluna; contas no cabeçalho do bloco (linha acima do 1º mês)."""
    brutas: list[dict] = []
    for col in range(1, min(ws.max_column, 30) + 1):
        corrida: list[tuple[int, str]] = []
        for r in range(1, ws.max_row + 2):
            m = _mes(ws.cell(row=r, column=col).value, ano) if r <= ws.max_row else None
            if m:
                corrida.append((r, f"{m[0]:04d}-{m[1]:02d}"))
                continue
            if len(corrida) >= 6:
                cab = corrida[0][0] - 1
                titulo = next((ws.cell(row=rr, column=col).value for rr in range(cab - 1, max(cab - 3, 0), -1)
                               if isinstance(ws.cell(row=rr, column=col).value, str)), None)
                if titulo:
                    brutas.append({"linha": cab - 1, "rotulo": titulo.strip(), "negrito": True, "valores": {},
                                   "so_titulo": True,
                                   "acumulado": None, "local": f"{ws.title}!{ws.cell(row=cab, column=col).column_letter}{cab - 1}"})
                for c2 in range(col + 1, min(ws.max_column, 30) + 1):
                    rot = ws.cell(row=cab, column=c2).value
                    if not isinstance(rot, str) or not rot.strip():
                        if titulo and c2 > col + 1:
                            break
                        continue
                    valores = {}
                    for r2, comp in corrida:
                        v = _numero(ws.cell(row=r2, column=c2).value)
                        if v:
                            valores[comp] = valores.get(comp, 0.0) + v
                    brutas.append({"linha": cab, "rotulo": rot.strip(), "negrito": False, "valores": valores,
                                   "acumulado": None, "local": f"{ws.title}!{ws.cell(row=cab, column=c2).column_letter}{cab}"})
                brutas.append({"linha": None, "rotulo": None, "negrito": False, "valores": {}, "acumulado": None,
                               "local": ""})
            corrida = []
    return brutas


def _estruturar(brutas: list[dict], mapa: dict[str, str]) -> tuple[list[LinhaGerencial], list[str]]:
    linhas: list[LinhaGerencial] = []
    alertas: list[str] = []
    grupo: LinhaGerencial | None = None
    filhos: dict[int, list[LinhaGerencial]] = {}
    titulos: set[int] = set()  # títulos de bloco (formato longo): agrupam, mas não têm valor próprio
    for b in brutas:
        if not b["rotulo"]:
            grupo = None  # linha em branco fecha o grupo
            continue
        chave = normalizar_texto(b["rotulo"])
        if chave in mapa:
            cat, origem = Categoria(mapa[chave]), "mapa"
        else:
            cat = classificar(b["rotulo"])
            origem = "regra" if cat else "pendente"
        eh_grupo = b["negrito"] and cat not in SEM_VALOR
        if not b["negrito"] and grupo is not None and (cat is None or origem == "pendente"):
            cat, origem = grupo.categoria, "grupo"
        linha = LinhaGerencial(rotulo=b["rotulo"], categoria=cat or Categoria.PENDENTE, origem=origem,
                               grupo=grupo.rotulo if grupo and not b["negrito"] else None, eh_grupo=eh_grupo,
                               valores=b["valores"], acumulado=b["acumulado"], localizacao=b["local"])
        linhas.append(linha)
        if b.get("so_titulo"):
            titulos.add(id(linha))
        if b["negrito"]:
            grupo = linha if eh_grupo else None
            if eh_grupo:
                filhos[id(linha)] = []
        elif grupo is not None:
            filhos[id(grupo)].append(linha)

    # grupo × soma das contas (mês a mês) e acumulado × soma dos meses
    for l in linhas:
        fs = filhos.get(id(l))
        if fs and id(l) not in titulos:
            meses_grupo = sorted(set(l.valores) | {c for f in fs for c in f.valores})
            divergentes = [c for c in meses_grupo
                           if abs(sum(f.valores.get(c, 0.0) for f in fs) - l.valores.get(c, 0.0)) > 1.0]
            if divergentes:
                faltando = [f.rotulo for f in fs if any(f.valores.get(c) for c in divergentes)]
                alertas.append(f"'{l.rotulo}': o valor do grupo não bate com a soma das contas em "
                               f"{len(divergentes)} mês(es) ({', '.join(divergentes[:4])}); verificar a fórmula — "
                               f"contas envolvidas: {', '.join(faltando[:4])}.")
        if l.acumulado is not None and l.valores and l.categoria not in SEM_VALOR | {Categoria.IGNORAR}:
            soma = sum(l.valores.values())
            if abs(soma - l.acumulado) > max(1.0, 0.005 * abs(soma)):
                alertas.append(f"'{l.rotulo}': total do ano na planilha R$ {brl(l.acumulado)} × soma dos meses "
                               f"R$ {brl(soma)} ({l.localizacao}).")
        if l.categoria == Categoria.SUBTOTAL and l.acumulado is not None and l.valores:
            soma = sum(l.valores.values())
            if abs(soma - l.acumulado) > max(1.0, 0.005 * abs(soma)):
                alertas.append(f"'{l.rotulo}' (subtotal): total do ano na planilha R$ {brl(l.acumulado)} × soma "
                               f"dos meses R$ {brl(soma)} — a planilha pode estar somando itens que não são "
                               "resultado (ex.: empréstimo recebido).")
    return linhas, alertas


def _aplicar_sinais(linhas: list[LinhaGerencial]) -> None:
    """Planilhas costumam lançar saídas como valores positivos: padroniza + entrada / − saída."""
    for l in linhas:
        if l.categoria in SEM_VALOR | {Categoria.PENDENTE}:
            continue
        positivos = sum(1 for v in l.valores.values() if v > 0)
        negativos = sum(1 for v in l.valores.values() if v < 0)
        if l.categoria not in ENTRADAS and positivos > negativos:
            l.valores = {c: -v for c, v in l.valores.items()}
            if l.acumulado is not None:
                l.acumulado = -l.acumulado


def eh_gerencial(caminho: str | Path) -> bool:
    from openpyxl import load_workbook

    try:
        wb = load_workbook(caminho, read_only=True, data_only=True)
    except Exception:  # noqa: BLE001
        return False
    for ws in wb.worksheets:
        for row in ws.iter_rows(max_row=40, max_col=30, values_only=True):
            if sum(1 for v in row if _mes(v, 2000)) >= 6:
                return True
        col_meses = 0
        for row in ws.iter_rows(max_row=60, max_col=3, values_only=True):
            col_meses += 1 if row and _mes(row[0], 2000) else 0
        if col_meses >= 6:
            return True
    return False


def ler_gerencial(caminho: str | Path, mapa: dict[str, str] | None = None) -> DREGerencial:
    """Lê a 1ª aba com estrutura mensal. `mapa` = {rótulo normalizado: categoria} salvo no case."""
    from openpyxl import load_workbook

    caminho = Path(caminho)
    mapa = {normalizar_texto(k): v for k, v in (mapa or {}).items()}
    wb = load_workbook(caminho, data_only=True)
    for ws in wb.worksheets:
        ano = _ano_padrao(ws, caminho)
        largo = _blocos_largos(ws, ano)
        brutas = _ler_largo(ws, *largo) if largo else _ler_longo(ws, ano)
        if any(b["valores"] for b in brutas):
            break
    else:
        raise GerencialNaoLido("nenhuma aba com meses nas linhas ou colunas")

    linhas, alertas = _estruturar(brutas, mapa)
    _aplicar_sinais(linhas)
    competencias = sorted({c for l in linhas for c in l.valores})
    d = DREGerencial(linhas=linhas, competencias=competencias, alertas=alertas,
                     proveniencia=Proveniencia(arquivo=caminho.name, localizacao=ws.title, metodo=Metodo.PARSER,
                                               confianca="media"))
    if d.pendentes():
        d.alertas.append(f"{len(d.pendentes())} conta(s) sem categoria: {', '.join(d.pendentes()[:6])}.")
    if not d.receita_mensal():
        d.alertas.append("Nenhuma linha reconhecida como receita operacional.")
    return d


def salvar_mapa(caminho: str | Path, novos: dict[str, str]) -> None:
    """Acrescenta classificações (do analista ou da IA) ao mapa do case, para os próximos anos."""
    caminho = Path(caminho)
    atual = json.loads(caminho.read_text(encoding="utf-8")) if caminho.exists() else {}
    atual.update({normalizar_texto(k): Categoria(v).value for k, v in novos.items()})
    caminho.write_text(json.dumps(atual, indent=2, ensure_ascii=False), encoding="utf-8")
