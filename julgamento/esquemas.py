"""Esquemas das saídas dos agentes de julgamento (F5, F7, F8).

O agente (Claude Code, manual ou API) devolve JSON; o código só aceita o que valida aqui. Nenhum número do
valuation vem daqui — só notas propostas (1–5) para as dimensões de julgamento do Score, que o analista aprova.
"""

from __future__ import annotations

from typing import Annotated, Literal

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


# dados estruturados e curtos para os visuais do relatório (desenhados pelo código: zero tokens no desenho)
Curto = Annotated[str, Field(max_length=110)]


class Perfil(BaseModel):
    cidade_uf: str | None = None
    fundacao: int | None = Field(None, ge=1900, le=2100)
    funcionarios: str | None = Field(None, max_length=30, description="número ou faixa declarada (ex.: '7 a 9')")
    setor: str | None = Field(None, max_length=80, description="setor em poucas palavras (ex.: etiquetas adesivas)")


class EventoHistorico(BaseModel):
    ano: int = Field(ge=1900, le=2100)
    evento: str = Field(max_length=80)


class ModeloNegocio(BaseModel):
    operacao: list[Curto] = Field(default_factory=list, max_length=4, description="o que faz e como produz/entrega")
    venda: list[Curto] = Field(default_factory=list, max_length=4, description="para quem vende e por quais canais")
    receita: list[Curto] = Field(default_factory=list, max_length=4, description="como ganha dinheiro, preço, recorrência")


class NoOrganograma(BaseModel):
    id: str = Field(pattern=r"^[a-z0-9_]{1,30}$")
    cargo: str = Field(max_length=40)
    nome: str | None = Field(None, max_length=40, description="nome ou quantidade (ex.: 'equipe de 6')")
    superior: str | None = Field(None, description="id do superior; vazio no topo")


class Decisao(BaseModel):
    decisao: str = Field(max_length=50)
    quem: str = Field(max_length=40)
    como: str = Field(max_length=110)


class ItemMix(BaseModel):
    item: str = Field(max_length=40)
    percentual: float = Field(ge=0, le=100)


class EtapaCadeia(BaseModel):
    etapa: str = Field(max_length=32, description="ex.: fornecedores de papel, gráficas, indústria cliente")
    quem: str = Field("", max_length=60, description="exemplos de quem atua nessa etapa")
    empresa_atua: bool = False


class Concorrente(BaseModel):
    nome: str = Field(max_length=40, description="nome ou tipo (ex.: gráficas pequenas da região)")
    perfil: str = Field("", max_length=60)
    preco: int = Field(ge=1, le=5, description="1 = preço baixo … 5 = preço alto")
    especializacao: int = Field(ge=1, le=5, description="1 = produto padrão … 5 = muito especializado")
    comparacao: str = Field("", max_length=110, description="como a empresa se compara")


class PosicaoEmpresa(BaseModel):
    preco: int = Field(ge=1, le=5)
    especializacao: int = Field(ge=1, le=5)


class ValorAno(BaseModel):
    ano: int = Field(ge=1990, le=2100)
    valor: float = Field(ge=0)


class Indicador(BaseModel):
    nome: str = Field(max_length=40, description="ex.: milheiros de etiquetas vendidos; diária média")
    unidade: str = Field("", max_length=24, description="ex.: milheiros; R$ por milheiro; diárias")
    valores: list[ValorAno] = Field(min_length=1, max_length=4)


class Operacional(BaseModel):
    """Os dois números que explicam a receita (volume × preço), como declarados — nunca calculados pelo agente."""

    volume: Indicador
    preco: Indicador
    preco_mensal: bool = Field(False, description="true se o preço/ticket declarado é por mês (a receita do ano = volume × preço × 12)")
    fonte: str = Field(max_length=90, description="quem declarou e onde (ex.: dono, entrevista B2 31:40)")


class LinhaReceita(BaseModel):
    nome: str = Field(max_length=40)
    valores: list[ValorAno] = Field(min_length=1, max_length=4, description="receita da linha em R$ no ano")


class ClienteDeclarado(BaseModel):
    cliente: str = Field(max_length=40, description="nome ou tipo (ex.: 'hospitais da região')")
    setor: str = Field("", max_length=30)
    receita_anual: float | None = Field(None, ge=0, description="R$ no ano, como declarado ou anualizado (60 mil/mês → 720 mil)")
    percentual: float | None = Field(None, ge=0, le=100, description="% da receita, se declarado")


class OperacaoAtivos(BaseModel):
    nota: int = Field(ge=1, le=5, description="5 = operação e ativos sólidos … 1 = frágeis (máquinas, capacidade, imóvel)")
    justificativa: str = Field(max_length=700)
    evidencias: list[str] = Field(default_factory=list, max_length=4)


VERTICAIS_RISCO = ("Receita e clientes", "Mercado e concorrência", "Diferencial e intangíveis",
                   "Gestão e dependência do dono", "Governança e informação", "Saúde financeira",
                   "Operação e ativos físicos", "Contingências")
VerticalRisco = Literal["Receita e clientes", "Mercado e concorrência", "Diferencial e intangíveis",
                        "Gestão e dependência do dono", "Governança e informação", "Saúde financeira",
                        "Operação e ativos físicos", "Contingências"]


class LeituraVertical(BaseModel):
    vertical: VerticalRisco
    leitura: str = Field(max_length=140, description="o principal ponto da vertical, numa frase")
    tratamento: str = Field(max_length=110, description="como o risco é tratado: na taxa, no preço, retenção, diligência")


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
    perfil: Perfil = Field(default_factory=Perfil)
    linha_do_tempo: list[EventoHistorico] = Field(default_factory=list, max_length=8)
    modelo: ModeloNegocio = Field(default_factory=ModeloNegocio)
    organograma: list[NoOrganograma] = Field(default_factory=list, max_length=14)
    quem_decide: list[Decisao] = Field(default_factory=list, max_length=6)
    mix_receita: list[ItemMix] = Field(default_factory=list, max_length=6,
                                       description="% da receita por produto, serviço ou canal (se o pacote informar)")
    cadeia_valor: list[EtapaCadeia] = Field(default_factory=list, max_length=6)
    concorrentes: list[Concorrente] = Field(default_factory=list, max_length=6)
    posicao_empresa: PosicaoEmpresa | None = None
    # capítulo 4 (usados só quando a planilha da ND não traz o dado)
    operacional: Operacional | None = None
    linhas_receita: list[LinhaReceita] = Field(default_factory=list, max_length=6)
    clientes_principais: list[ClienteDeclarado] = Field(default_factory=list, max_length=10)
    operacao_ativos: OperacaoAtivos | None = None
    leitura_verticais: list[LeituraVertical] = Field(default_factory=list, max_length=8)

    @field_validator("funcoes_do_dono")
    @classmethod
    def _um_por_eixo(cls, v: list[FuncaoDono]) -> list[FuncaoDono]:
        eixos = [f.eixo for f in v]
        if len(eixos) != len(set(eixos)):
            raise ValueError("funcoes_do_dono com eixo repetido")
        return v

    @field_validator("leitura_verticais")
    @classmethod
    def _uma_por_vertical(cls, v: list[LeituraVertical]) -> list[LeituraVertical]:
        if len({x.vertical for x in v}) != len(v):
            raise ValueError("leitura_verticais com vertical repetida")
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


# --------------------------------------------------------------------------- F8 (redator)


class TextosRelatorio(BaseModel):
    """textos.json — saída da F8 (redator). Só texto: números e gráficos vêm do sistema."""

    case_id: str
    tese: str = Field(min_length=40, max_length=450, description="2 a 3 frases: o que é a empresa e quanto vale, por quê")
    por_que_olhar: list[Annotated[str, Field(max_length=170)]] = Field(
        min_length=2, max_length=4, description="forças: até 4 itens de no máximo 2 linhas, com o número que prova")
    o_que_pesa_contra: list[Annotated[str, Field(max_length=170)]] = Field(
        min_length=2, max_length=4, description="fragilidades: até 4 itens de no máximo 2 linhas, com a ação que resolve")
    sobre_empresa: str = Field(min_length=80, max_length=700,
                               description="o negócio em 3 a 4 frases (linha do tempo, modelo e organograma são gráficos)")
    gestao_pessoas: str = Field(min_length=40, max_length=500, description="papel do dono, equipe, sucessão: 2 a 3 frases")
    mercado_setor: str = Field(min_length=80, max_length=700,
                               description="setor, concorrência e fosso em 3 a 4 frases (cadeia e mapa são gráficos)")
    leitura_financeira: str = Field(min_length=80, max_length=1400, description="o que os números mostram e o que foi ajustado")
    leitura_riscos: str = Field(min_length=60, max_length=1200, description="principais riscos e contingências")
    leitura_valuation: str = Field(min_length=60, max_length=1200, description="como chegamos ao valor, em linguagem simples")
    estrutura_transacao: str = Field(min_length=60, max_length=1200, description="como a operação pode ser feita")
    proximos_passos: list[str] = Field(min_length=2, max_length=7, description="o que o dono e a ND fazem a seguir")
