"""Esquemas das saídas dos agentes de julgamento (F5, F7, F8).

O agente (Claude Code, manual ou API) devolve JSON; o código só aceita o que valida aqui. Nenhum número do
valuation vem daqui — só notas propostas (1–5) para as dimensões de julgamento do Score, que o analista aprova.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

# dimensões do Score que dependem de julgamento (as demais são calculadas por código)
DIMENSOES_JULGAMENTO = ("dependencia_dono", "recorrencia_receita", "contingencias", "setor_posicao_competitiva")
DimensaoJulgamento = Literal["dependencia_dono", "recorrencia_receita", "contingencias", "setor_posicao_competitiva"]
Nivel = Literal["alta", "media", "baixa"]


class NotaProposta(BaseModel):
    dimensao: DimensaoJulgamento
    nota: int = Field(ge=1, le=5, description="escala da ND: 5 = melhor (risco mínimo) … 1 = pior (risco máximo)")
    justificativa: str = Field(min_length=10)
    evidencias: list[str] = Field(min_length=1, description="fatos do pacote que sustentam a nota")
    confianca: Nivel


class Risco(BaseModel):
    descricao: str
    severidade: Nivel
    evidencia: str
    mitigante: str | None = None


class Fosso(BaseModel):
    forca: Literal["nenhum", "estreito", "amplo"]
    fontes: list[str] = Field(default_factory=list, description="ex.: custo, marca, localização, troca, contrato")
    justificativa: str


class Gestao(BaseModel):
    avaliacao: str
    pontos_atencao: list[str] = Field(default_factory=list)


class FuncaoDono(BaseModel):
    """Função que o dono exerce sem substituto (além da gestão geral) e que o comprador terá de contratar."""

    eixo: Literal["comercial", "tecnico", "financeiro"]
    descricao: str = Field(description="o que o dono faz nesse eixo")
    evidencia: str


class Qualitativo(BaseModel):
    """qualitativo.json — saída da F5 (analista fundamentalista)."""

    case_id: str
    playbook: str
    resumo: str = Field(description="3 a 6 frases para o relatório")
    modelo_negocio: str
    fosso: Fosso
    gestao: Gestao
    notas_score: list[NotaProposta]
    riscos: list[Risco] = Field(default_factory=list)
    pontos_fortes: list[str] = Field(default_factory=list)
    perguntas_entrevista: list[str] = Field(default_factory=list)
    lacunas_informacao: list[str] = Field(default_factory=list)
    funcoes_do_dono: list[FuncaoDono] = Field(default_factory=list,
                                              description="funções sem substituto além da gestão geral (D1)")

    @field_validator("funcoes_do_dono")
    @classmethod
    def _um_por_eixo(cls, v: list[FuncaoDono]) -> list[FuncaoDono]:
        eixos = [f.eixo for f in v]
        if len(eixos) != len(set(eixos)):
            raise ValueError("funcoes_do_dono com eixo repetido")
        return v

    @field_validator("notas_score")
    @classmethod
    def _uma_por_dimensao(cls, v: list[NotaProposta]) -> list[NotaProposta]:
        dims = [n.dimensao for n in v]
        if len(dims) != len(set(dims)):
            raise ValueError("notas_score com dimensão repetida")
        faltam = set(DIMENSOES_JULGAMENTO) - set(dims)
        if faltam:
            raise ValueError(f"notas_score sem as dimensões: {', '.join(sorted(faltam))}")
        return v


# --------------------------------------------------------------------------- F7 (revisor)

Fase = Literal["captacao", "normalizacao", "qualitativo", "valuation", "finalidade"]


class AlertaRevisao(BaseModel):
    id: str = Field(pattern=r"^[a-z0-9_]{3,60}$", description="snake_case estável, para registrar a decisão")
    fase: Fase
    severidade: Nivel
    achado: str = Field(min_length=10)
    evidencia: str = Field(min_length=5)
    sugestao: str = Field(min_length=5, description="o que fazer e onde (arquivo de decisão ou documento a pedir)")


class Revisao(BaseModel):
    """revisao.json — saída da F7 (revisor cético)."""

    case_id: str
    parecer: Literal["aprovado", "aprovado_com_ressalvas", "refazer"]
    resumo: str = Field(description="2 a 4 frases: o valuation se sustenta? o que mais pesa?")
    alertas: list[AlertaRevisao] = Field(default_factory=list)
    perguntas_ao_dono: list[str] = Field(default_factory=list)

    @field_validator("alertas")
    @classmethod
    def _ids_unicos(cls, v: list[AlertaRevisao]) -> list[AlertaRevisao]:
        ids = [a.id for a in v]
        if len(ids) != len(set(ids)):
            raise ValueError("alertas com id repetido")
        return v
