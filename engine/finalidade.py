"""D7 — finalidade da transação: venda total, venda parcial ou entrada de sócio (com ou sem aporte).

Não muda o valor da empresa: muda como ele é apresentado (valor da participação, participação justa num aporte) e a
leitura do pedido do vendedor, que a ND sempre compara com o valor técnico.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from captacao.util import brl

Tipo = Literal["venda_total", "venda_parcial", "entrada_socio"]
NOMES = {"venda_total": "venda total", "venda_parcial": "venda parcial", "entrada_socio": "entrada de sócio"}
LEIA = ("tipo: venda_total | venda_parcial | entrada_socio · percentual: fração das cotas negociadas (0,30 = 30%) · "
        "aporte: dinheiro novo que entra na empresa (entrada de sócio), em R$ · pedido_vendedor: quanto o dono pede "
        "pela participação, em R$ · entrada_aceita / prazo_aceito_meses / aceita_earnout: forma de pagamento que o "
        "sócio aceita (reuniões; vazio = premissa ND de 25% + 24 meses) · custo_cotas: custo de aquisição das cotas "
        "na declaração do sócio, em R$ (para o IR sobre o ganho de capital)")


class Finalidade(BaseModel):
    tipo: Tipo = "venda_total"
    percentual: float = Field(1.0, gt=0, le=1)
    aporte: float | None = None
    pedido_vendedor: float | None = None
    entrada_aceita: float | None = Field(None, ge=0, le=1)  # fração do preço que o sócio aceita receber na entrada
    prazo_aceito_meses: int | None = Field(None, ge=0, le=120)
    aceita_earnout: bool | None = None
    custo_cotas: float | None = None  # custo de aquisição das cotas (capital integralizado), para o IR do sócio

    @property
    def descricao(self) -> str:
        partes = [NOMES[self.tipo]]
        if self.percentual < 1:
            partes.append(f"{self.percentual:.0%} das cotas")
        if self.aporte:
            partes.append(f"aporte de R$ {brl(self.aporte, 0)} na empresa")
        return ", ".join(partes)


def ler_finalidade(saida: Path) -> Finalidade:
    """Lê _valuation/finalidade.json; se não existir, grava o modelo (venda total de 100%) para o analista editar."""
    arq = saida / "finalidade.json"
    if arq.exists():
        dado = json.loads(arq.read_text(encoding="utf-8"))
        return Finalidade.model_validate({k: v for k, v in dado.items() if not k.startswith("_")})
    f = Finalidade()
    gravar_finalidade(saida, f)
    return f


def gravar_finalidade(saida: Path, f: Finalidade) -> None:
    (saida / "finalidade.json").write_text(json.dumps({"_leia": LEIA, **f.model_dump()}, indent=2, ensure_ascii=False),
                                           encoding="utf-8")


def leitura(f: Finalidade, preco: float, teto: float | None, fluxo: float) -> tuple[list[str], list[str]]:
    """→ (linhas para o relatório, alertas). `preco` = preço recomendado dos 100%; `teto` = valor de referência."""
    linhas, alertas = [f"Finalidade: **{f.descricao}**."], []
    if preco <= 0 and (f.percentual < 1 or f.aporte):
        linhas.append("Pelo nosso valor as cotas atuais valem zero (dívida e passivos acima do valor da empresa): "
                      "qualquer participação ou aporte precisa partir de um plano para a dívida.")
        alertas.append("Cotas sem valor pelo nosso cálculo: negociar participação só depois de tratar a dívida.")
    elif f.percentual < 1:
        linhas.append(f"Valor da participação ({f.percentual:.0%}) pelo preço recomendado: **R$ "
                      f"{brl(preco * f.percentual, 0)}** (sem desconto de minoritário).")
    if f.aporte and preco > 0:
        pos = preco + f.aporte
        justa = f.aporte / pos if pos > 0 else None
        if justa is not None:
            linhas.append(f"Com o aporte, a empresa passa a valer R$ {brl(pos, 0)} (pós-aporte): pelos R$ "
                          f"{brl(f.aporte, 0)} o investidor deveria receber **{justa:.0%}** das cotas.")
            if f.percentual < justa - 0.005:
                alertas.append(f"Participação oferecida ({f.percentual:.0%}) abaixo da justa ({justa:.0%}) para o aporte: "
                               "o pedido está caro para o investidor.")
    if f.pedido_vendedor:
        if f.aporte:  # aporte: o pedido define um valor pré-aporte implícito
            implicito = f.pedido_vendedor / f.percentual - f.pedido_vendedor
            base = "pré-aporte implícito"
        else:
            implicito = f.pedido_vendedor / f.percentual
            base = "implícito pelos 100%"
        linha = (f"Pedido do vendedor: R$ {brl(f.pedido_vendedor, 0)} → valor {base} de **R$ {brl(implicito, 0)}**")
        if preco > 0:
            linha += f", {implicito / preco:.1f}× o preço recomendado"
        if fluxo > 0:
            linha += f" e {implicito / fluxo:.1f} anos de fluxo"
        linhas.append(linha + ".")
        if teto and implicito > teto:
            alertas.append(f"Pedido do vendedor implica R$ {brl(implicito, 0)}, acima do valor de referência (teto) de "
                           f"R$ {brl(teto, 0)}: alinhar expectativa antes de ofertar.")
    return linhas, alertas
