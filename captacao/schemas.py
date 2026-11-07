"""Modelo de dados padronizado da captação (`dados_brutos.json`).

Todo dado guarda sua proveniência: de qual arquivo veio, onde, por qual método e com que confiança.
"""

from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field

Competencia = str  # 'AAAA-MM'
Confianca = Literal["alta", "media", "baixa"]


class Metodo(str, Enum):
    PARSER = "parser"  # arquivo estruturado lido por código
    REGRA = "regra"  # regra determinística (layout, palavra-chave, contexto)
    IA = "ia"  # extraído/classificado por modelo de linguagem
    MANUAL = "manual"  # informado ou corrigido por pessoa


class Proveniencia(BaseModel):
    arquivo: str
    localizacao: str | None = None  # página, linha, registro
    metodo: Metodo
    confianca: Confianca = "alta"


# --------------------------------------------------------------------------- empresa


class Socio(BaseModel):
    nome: str
    cpf: str | None = None


class EmpresaGrupo(BaseModel):
    """Um CNPJ do grupo econômico."""

    cnpj: str
    razao_social: str
    nome_fantasia: str | None = None


class Empresa(BaseModel):
    nome: str
    cnpjs: list[EmpresaGrupo]
    socios: list[Socio] = Field(default_factory=list)


# --------------------------------------------------------------------------- extratos


class Categoria(str, Enum):
    # créditos
    RECEITA_OPERACIONAL = "receita_operacional"
    RECEITA_FINANCEIRA = "receita_financeira"
    TRANSFERENCIA_INTERNA = "transferencia_interna"  # entre contas/CNPJs do grupo
    EMPRESTIMO_RECEBIDO = "emprestimo_recebido"
    RESGATE_APLICACAO = "resgate_aplicacao"
    APORTE_SOCIO = "aporte_socio"
    ESTORNO = "estorno"
    # débitos
    DESPESA_OPERACIONAL = "despesa_operacional"
    FOLHA = "folha"
    ENCARGOS_FOLHA = "encargos_folha"
    IMPOSTO = "imposto"
    TARIFA_BANCARIA = "tarifa_bancaria"
    PAGAMENTO_EMPRESTIMO = "pagamento_emprestimo"
    APLICACAO_FINANCEIRA = "aplicacao_financeira"
    RETIRADA_SOCIO = "retirada_socio"  # inclui pró-labore e distribuição
    # pendente
    NAO_CLASSIFICADO = "nao_classificado"


class Transacao(BaseModel):
    data: date
    valor: float  # positivo = crédito, negativo = débito
    descricao: str
    id_banco: str | None = None
    contraparte_doc: str | None = None
    categoria: Categoria = Categoria.NAO_CLASSIFICADO
    metodo_classificacao: Metodo | None = None
    confianca: Confianca | None = None


class ExtratoConta(BaseModel):
    cnpj_titular: str | None = None
    banco: str | None = None
    conta: str | None = None
    transacoes: list[Transacao]
    proveniencia: Proveniencia


# --------------------------------------------------------------------------- fiscal / contábil / gerencial


class PGDASMes(BaseModel):
    cnpj: str
    competencia: Competencia
    receita_bruta: float
    rbt12: float | None = None
    aliquota_efetiva: float | None = None
    valor_das: float | None = None
    proveniencia: Proveniencia


class FiscalMes(BaseModel):
    """Venda declarada ao fisco no mês, por estabelecimento, fora do Simples (ex.: EFD ICMS/IPI)."""

    cnpj: str
    competencia: Competencia
    receita_bruta: float  # vendas (sem transferências entre estabelecimentos)
    devolucoes: float = 0.0
    fonte: str
    proveniencia: Proveniencia


class GerencialMes(BaseModel):
    competencia: Competencia
    receita: float
    cliente: str | None = None  # None = total do mês
    proveniencia: Proveniencia


class DREAnual(BaseModel):
    """Valores com o sinal da demonstração: receitas positivas, custos e despesas negativos."""

    cnpj: str
    exercicio: int
    meses: int = 12  # < 12 em balancete/DRE parcial do ano corrente
    receita_bruta: float | None = None
    deducoes: float | None = None
    receita_liquida: float | None = None
    custo_vendas: float | None = None
    despesas_pessoal: float | None = None
    pro_labore: float | None = None
    despesas_administrativas: float | None = None
    despesas_comerciais: float | None = None
    aluguel: float | None = None
    depreciacao_amortizacao: float | None = None
    outras_receitas_despesas: float | None = None
    resultado_financeiro: float | None = None
    financeiras_nas_operacionais: float | None = None  # juros/IOF lançados dentro de adm./comerciais
    despesas_operacionais_total: float | None = None  # grupo 'Despesas operacionais' inteiro, sem as financeiras
    atividade_receita: str | None = None  # industria | comercio | servicos, pelo nome das contas de receita
    ir_csll: float | None = None
    lucro_liquido: float | None = None
    proveniencia: Proveniencia


class BalancoAnual(BaseModel):
    cnpj: str
    exercicio: int
    data_base: date | None = None  # 31/12 ou a data do balancete
    caixa_aplicacoes: float | None = None
    contas_receber: float | None = None
    estoques: float | None = None
    imobilizado_liquido: float | None = None
    fornecedores: float | None = None
    obrigacoes_trabalhistas: float | None = None
    obrigacoes_fiscais: float | None = None
    parcelamentos_fiscais: float | None = None
    emprestimos_cp: float | None = None
    emprestimos_lp: float | None = None
    mutuos_socios: float | None = None
    patrimonio_liquido: float | None = None
    proveniencia: Proveniencia


# --------------------------------------------------------------------------- agregado do case


class DadosBrutos(BaseModel):
    """Saída da fase F2 — tudo o que foi captado de um case."""

    empresa: Empresa
    periodo_inicio: Competencia
    periodo_fim: Competencia
    extratos: list[ExtratoConta] = Field(default_factory=list)
    pgdas: list[PGDASMes] = Field(default_factory=list)
    fiscal_mensal: list[FiscalMes] = Field(default_factory=list)  # EFD/notas, empresas fora do Simples
    gerencial: list[GerencialMes] = Field(default_factory=list)
    dres: list[DREAnual] = Field(default_factory=list)
    balancos: list[BalancoAnual] = Field(default_factory=list)
