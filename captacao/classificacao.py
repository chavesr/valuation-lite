"""Classificação de transações bancárias por regras (custo zero de tokens).

Ordem de aplicação:
  1. Contexto do grupo econômico — CNPJs/razões sociais do grupo e nomes/CPFs dos sócios.
  2. Regras aprendidas — padrões já classificados em cases anteriores (por IA ou humano).
  3. Palavras-chave — tabela abaixo, das mais específicas para as mais genéricas.
O que sobrar vai, deduplicado, para a IA (`pendentes_para_ia`).
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path

from captacao.schemas import Categoria, Empresa, ExtratoConta, Metodo, Transacao
from captacao.util import apenas_digitos, mes, normalizar_texto

C = Categoria

# (categoria, sinal: +1 crédito / -1 débito, regex, confiança)
_REGRAS_PALAVRA_CHAVE: list[tuple[Categoria, int, str, str]] = [
    # ---- créditos
    (C.ESTORNO, +1, r"\bESTORNO|\bDEVOL", "alta"),
    (C.ESTORNO, +1, r"PIX REJEITADO|REJEITAD|DEVOLVID", "alta"),
    (C.TRANSFERENCIA_INTERNA, +1, r"\bTBI\b|ENTRE CONTAS|MESMA TITULARIDADE", "alta"),
    (C.RESGATE_APLICACAO, +1, r"\bRESGATE|\bRESG\b|RENDE FACIL|BRASILCAP|CAPITALIZ|AUT MAIS", "alta"),
    (C.RECEITA_FINANCEIRA, +1, r"RENDIMENTO|REND\w* PAGO|JUROS CREDITADOS", "alta"),
    (C.EMPRESTIMO_RECEBIDO, +1,
     r"EMPRESTIMO|CAPITAL DE GIRO|PRONAMPE|FINANCIAMENTO|LIBERACAO (DE )?(CREDITO|CONTRATO)", "alta"),
    (C.RECEITA_OPERACIONAL, +1,
     r"CIELO|\bREDE\b|STONE|GETNET|PAGSEGURO|SUMUP|MERCADO ?PAGO|SAFRAPAY|VENDAS? (CARTAO|DEBITO|CREDITO)"
     r"|LIQUIDACAO (DE )?COBRANCA|COBRANCA|BOLETO|SISPAG (VISA|MAST|ELO|AMEX|HIPER)|RECEBIMENTO FORNECEDOR"
     r"|CONFIRMING", "alta"),
    (C.RECEITA_OPERACIONAL, +1, r"PIX RECEB|RECEBIMENTO PIX|PIX_CRED|TED RECEB|DOC RECEB|DEPOSITO|TRANSF\w* RECEB"
                                r"|^TED .*BANCO|CREDITO TED|^RECEBIMENTOS? |^ENTRADA PIX|PIX TRANSF", "media"),
    # ---- débitos
    (C.RETIRADA_SOCIO, -1, r"PRO.?LABORE|DISTRIB\w* (DE )?LUCROS?", "alta"),
    (C.ENCARGOS_FOLHA, -1, r"\bFGTS|\bGPS\b|\bINSS|\bGRF\b|ESOCIAL", "alta"),
    (C.IMPOSTO, -1, r"\bDAS\b|SIMPLES NACIONAL|\bDARF|\bICMS|\bISS\b|\bISSQN|RECEITA FEDERAL|PGFN"
                    r"|PARCELAMENTO|\bIPTU|\bIPVA|PAGAMENTOS? (DE )?TRIB|TRIBUTOS? COD BARRAS", "alta"),
    (C.FOLHA, -1, r"FOLHA|SALARIO|FERIAS|RESCISAO|13 ?SAL|ADIANT\w* SAL", "alta"),
    (C.TARIFA_BANCARIA, -1, r"TARIFA|\bTAR\b|CESTA|MANUT\w* (DE )?CONTA|\bIOF\b|ANUIDADE", "alta"),
    (C.PAGAMENTO_EMPRESTIMO, -1,
     r"AMORTIZ|PRESTACAO|PARC\w* (DE )?(EMPREST|FINANC|CONTRATO)|DEB\w* (EMPREST|FINANC)|CAPITAL (DE )?GIRO"
     r"|\bPEAC\b|\bFGI\b|PRONAMPE|LIQUIDACAO DE PARCELA|JUROS CONTR|PAGTO JUROS|^JUROS\b|FINANCEIRA|\bCFI\b"
     r"|LEASING|CONSORCIO|CONTR ROTATIVO|CONC GARANTIA", "alta"),
    (C.APLICACAO_FINANCEIRA, -1, r"APLICACAO|\bAPLIC\b|\bCDB\b|RENDE FACIL|BRASILCAP|CAPITALIZ", "alta"),
    (C.DESPESA_OPERACIONAL, -1,
     r"ALUGUEL|ENERGIA|\bLUZ\b|AGUA|TELEFON|INTERNET|COMBUSTIVEL|POSTO|FORNECEDOR|COMPRA|CAMBIO|IMPORTACAO"
     r"|SISCOMEX|PUCOMEX|TERMO DE MOEDA|FATURA|CARTAO (DE )?CREDITO|SEGURO|DEBITO CONVENIO", "alta"),
    (C.DESPESA_OPERACIONAL, -1,
     r"PAG\w* (DE )?(BOLETO|TITULO)|BOLETO PAGO|PIX ENVIADO|PIX EMITIDO|TED ENVIADA|DOC ENVIADO"
     r"|DEBITO AUTOMATICO|DEB AUT|LIQUIDACAO BOLETO|PAGAMENTOS? PIX|PIX_DEB|SISPAG|PIX AGENDAMENTO|^SAIDA PIX", "media"),
]

_SUFIXOS_SOCIETARIOS = {"LTDA", "ME", "EPP", "EIRELI", "SA", "S/A", "MEI", "SLU"}


def padrao_descricao(descricao: str) -> str:
    """Remove números, datas e pontuação para agrupar descrições equivalentes."""
    texto = normalizar_texto(descricao)
    texto = re.sub(r"[\d/\-.:*#,]+", " ", texto)
    return re.sub(r"\s+", " ", texto).strip()


_PALAVRAS_GENERICAS = {"COMERCIO", "INDUSTRIA", "SERVICOS", "DISTRIBUIDORA", "TRANSPORTES", "TRANSPORTE",
                       "CONSTRUTORA", "COMERCIAL", "INDUSTRIAL", "BRASIL", "BRASILEIRA", "NACIONAL", "GRUPO",
                       "EMPRESA", "MERCADO", "SUPERMERCADO", "FARMACIA", "CENTRO", "SOLUCOES", "TECNOLOGIA",
                       "ALIMENTOS", "IMPORTACAO", "EXPORTACAO", "LOGISTICA"}


def _chave_empresa(razao_social: str) -> str | None:
    """Trecho que identifica a empresa do grupo num histórico bancário. Usa a 1ª palavra quando ela é
    distintiva (ex.: 'ALFAPRESS' casa com 'ALFAPRESS COMERCIO' e 'ALFAPRESS IND'); senão, as duas primeiras."""
    palavras = [p for p in normalizar_texto(razao_social).split() if p not in _SUFIXOS_SOCIETARIOS]
    if not palavras:
        return None
    if len(palavras[0]) >= 6 and palavras[0] not in _PALAVRAS_GENERICAS:
        return palavras[0]
    chave = " ".join(palavras[:2])
    return chave if len(chave) >= 5 else None


class Classificador:
    def __init__(self, empresa: Empresa, caminho_regras_aprendidas: str | Path | None = None):
        self.empresa = empresa
        self.caminho_regras = Path(caminho_regras_aprendidas) if caminho_regras_aprendidas else None
        self.regras_aprendidas: dict[str, str] = {}
        if self.caminho_regras and self.caminho_regras.exists():
            self.regras_aprendidas = json.loads(self.caminho_regras.read_text(encoding="utf-8"))

        # só documentos completos (CNPJ/CPF): números curtos casariam com datas e horas do histórico
        self._docs_grupo = {d for e in empresa.cnpjs if len(d := apenas_digitos(e.cnpj)) >= 11}
        self._nomes_grupo = {k for e in empresa.cnpjs
                             for k in (_chave_empresa(e.razao_social),
                                       _chave_empresa(e.nome_fantasia or "")) if k}
        self._docs_socios = {d for s in empresa.socios if s.cpf and len(d := apenas_digitos(s.cpf)) >= 11}
        self._nomes_socios = []
        for s in empresa.socios:
            tokens = normalizar_texto(s.nome).split()
            if len(tokens) >= 2:
                self._nomes_socios.append((tokens[0], tokens[-1]))

    # ------------------------------------------------------------------ regras

    def _por_contexto(self, t: Transacao) -> Categoria | None:
        desc = normalizar_texto(t.descricao)
        digitos = apenas_digitos(t.descricao) + apenas_digitos(t.contraparte_doc)
        tokens = set(desc.split())
        credito = t.valor > 0

        if any(d and d in digitos for d in self._docs_grupo) or any(n in desc for n in self._nomes_grupo):
            return C.TRANSFERENCIA_INTERNA
        eh_socio = any(d and d in digitos for d in self._docs_socios) or any(
            primeiro in tokens and ultimo in tokens for primeiro, ultimo in self._nomes_socios
        )
        if eh_socio:
            return C.APORTE_SOCIO if credito else C.RETIRADA_SOCIO
        return None

    def _por_palavra_chave(self, t: Transacao) -> tuple[Categoria, str] | None:
        desc = normalizar_texto(t.descricao)
        # 'PIX - ENVIADO - 24/02 15:40 FORNECEDOR' (BB) → 'PIX ENVIADO FORNECEDOR': sem pontuação, data e hora
        limpa = re.sub(r"\s+", " ", re.sub(r"\b\d{1,2}[/:]\d{2}\b|[^A-Z0-9_ ]", " ", desc)).strip()
        sinal = 1 if t.valor > 0 else -1
        for categoria, sinal_regra, regex, confianca in _REGRAS_PALAVRA_CHAVE:
            if sinal == sinal_regra and (re.search(regex, desc) or re.search(regex, limpa)):
                return categoria, confianca
        return None

    def classificar_transacao(self, t: Transacao) -> Transacao:
        if t.metodo_classificacao in (Metodo.MANUAL, Metodo.IA):
            return t  # não sobrescreve decisões humanas ou da IA
        categoria = self._por_contexto(t)
        if categoria:
            t.categoria, t.metodo_classificacao, t.confianca = categoria, Metodo.REGRA, "alta"
            return t
        aprendida = self.regras_aprendidas.get(padrao_descricao(t.descricao))
        if aprendida:
            t.categoria, t.metodo_classificacao, t.confianca = Categoria(aprendida), Metodo.REGRA, "media"
            return t
        resultado = self._por_palavra_chave(t)
        if resultado:
            t.categoria, t.confianca = resultado
            t.metodo_classificacao = Metodo.REGRA
        else:
            t.categoria, t.metodo_classificacao, t.confianca = C.NAO_CLASSIFICADO, None, None
        return t

    def classificar(self, extratos: list[ExtratoConta]) -> list[ExtratoConta]:
        for extrato in extratos:
            for t in extrato.transacoes:
                self.classificar_transacao(t)
        return extratos

    # ------------------------------------------------------------------ aprendizado

    def aprender(self, padroes: dict[str, Categoria | str], salvar: bool = True) -> None:
        """Registra classificações (vindas da IA ou de pessoa) para reaproveitar nos próximos cases."""
        for padrao, categoria in padroes.items():
            self.regras_aprendidas[padrao] = Categoria(categoria).value
        if salvar and self.caminho_regras:
            self.caminho_regras.parent.mkdir(parents=True, exist_ok=True)
            self.caminho_regras.write_text(
                json.dumps(self.regras_aprendidas, ensure_ascii=False, indent=2, sort_keys=True),
                encoding="utf-8",
            )


# ---------------------------------------------------------------------- consultas


def pendentes_para_ia(extratos: list[ExtratoConta], limite: int = 200) -> list[dict]:
    """Transações não classificadas agrupadas por padrão — o lote enviado à IA (Haiku).

    Ordenado por valor absoluto: os padrões que mais pesam no resultado vêm primeiro.
    """
    grupos: dict[tuple[str, int], dict] = {}
    for extrato in extratos:
        for t in extrato.transacoes:
            if t.categoria != C.NAO_CLASSIFICADO:
                continue
            sinal = 1 if t.valor > 0 else -1
            chave = (padrao_descricao(t.descricao), sinal)
            g = grupos.setdefault(chave, {"padrao": chave[0], "tipo": "credito" if sinal > 0 else "debito",
                                          "ocorrencias": 0, "valor_total": 0.0, "exemplo": t.descricao})
            g["ocorrencias"] += 1
            g["valor_total"] = round(g["valor_total"] + t.valor, 2)
    ordenados = sorted(grupos.values(), key=lambda g: abs(g["valor_total"]), reverse=True)
    return ordenados[:limite]


def resumo_por_categoria(extratos: list[ExtratoConta]) -> dict[str, float]:
    totais: dict[str, float] = defaultdict(float)
    for extrato in extratos:
        for t in extrato.transacoes:
            totais[t.categoria.value] += t.valor
    return {k: round(v, 2) for k, v in sorted(totais.items())}


def pct_creditos_nao_classificados(extratos: list[ExtratoConta]) -> float:
    total = nao_class = 0.0
    for extrato in extratos:
        for t in extrato.transacoes:
            if t.valor > 0:
                total += t.valor
                if t.categoria == C.NAO_CLASSIFICADO:
                    nao_class += t.valor
    return nao_class / total if total else 0.0


def receita_caixa_mensal(extratos: list[ExtratoConta]) -> dict[str, float]:
    """Receita operacional recebida em conta, por competência (consolidada no grupo)."""
    receita: dict[str, float] = defaultdict(float)
    for extrato in extratos:
        for t in extrato.transacoes:
            if t.categoria == C.RECEITA_OPERACIONAL and t.valor > 0:
                receita[mes(t.data)] += t.valor
    return {k: round(v, 2) for k, v in sorted(receita.items())}


def deduplicar(extratos: list[ExtratoConta]) -> list[ExtratoConta]:
    """Remove transações repetidas quando arquivos do mesmo banco/conta se sobrepõem no período.

    Transações idênticas dentro do MESMO arquivo são mantidas (ex.: dois PIX iguais no mesmo dia);
    só é descartado o que excede a contagem já vista em arquivos anteriores.
    """
    ja_incluidas: dict[tuple, int] = defaultdict(int)
    for extrato in extratos:
        locais: dict[tuple, int] = defaultdict(int)
        unicas = []
        for t in extrato.transacoes:
            if t.id_banco and not t.id_banco.startswith("linha-"):
                chave = (extrato.banco, extrato.conta, t.id_banco, t.data, t.valor)
            else:
                chave = (extrato.banco, extrato.conta, t.data, t.valor, normalizar_texto(t.descricao))
            locais[chave] += 1
            if locais[chave] > ja_incluidas[chave]:
                unicas.append(t)
        for chave, n in locais.items():
            ja_incluidas[chave] = max(ja_incluidas[chave], n)
        extrato.transacoes = unicas
    return extratos
