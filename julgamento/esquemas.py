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
