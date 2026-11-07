"""Gerador de cases fictícios para teste.

- ALFA: distribuidora formal, 1 CNPJ, receita ~R$300 mil/mês, declara ~99% → esperado GCI nível A.
- CHARLIE: alimentos, 2 CNPJs no Simples, receita real ~R$600 mil/mês, declara 60%,
  transferências entre CNPJs, empréstimo e aporte do sócio → esperado GCI nível C.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from captacao.schemas import (DadosBrutos, DREAnual, Empresa, EmpresaGrupo, GerencialMes, Metodo,
                              PGDASMes, Proveniencia, Socio)
from captacao.util import meses_entre

PERIODO = ("2024-01", "2025-12")

CLIENTES = ["MERCADO BOM PRECO", "PADARIA SAO JOSE", "RESTAURANTE SABOR DA TERRA", "HOTEL BEIRA MAR",
            "LANCHONETE DO ZE", "EMPORIO CENTRAL", "CANTINA ITALIA", "BUFFET ALEGRIA",
            "SUPERMERCADO UNIAO", "CAFE DA PRACA"]
FORNECEDORES = ["ATACADAO DISTRIB", "LATICINIOS SERRA", "EMBALAGENS PLASTPAC", "FRIGORIFICO BOI GORDO"]


@dataclass
class Perfil:
    nome: str
    cnpjs: list[tuple[str, str]]
    socios: list[tuple[str, str]]
    contas: list[tuple[int, str, str, float]]  # (índice do CNPJ, banco, conta, participação na receita)
    receita_mensal: float
    fracao_declarada: float
    eventos: dict = field(default_factory=dict)


PERFIS = {
    "alfa": Perfil(
        nome="Alfa Distribuidora",
        cnpjs=[("11.111.111/0001-11", "ALFA DISTRIBUIDORA DE BEBIDAS LTDA")],
        socios=[("CARLOS EDUARDO MENDES", "111.222.333-44")],
        contas=[(0, "341", "1111-1", 1.0)],
        receita_mensal=300_000,
        fracao_declarada=0.99,
    ),
    "charlie": Perfil(
        nome="Charlie Alimentos",
        cnpjs=[("22.222.222/0001-22", "CHARLIE COMERCIO DE ALIMENTOS LTDA"),
               ("33.333.333/0001-33", "CHARLIE SERVICOS ALIMENTARES LTDA")],
        socios=[("MARIA APARECIDA OLIVEIRA", "555.666.777-88")],
        contas=[(0, "237", "2222-2", 0.7), (1, "001", "3333-3", 0.3)],
        receita_mensal=600_000,
        fracao_declarada=0.60,
        eventos={"emprestimo": ("2024-06", 150_000), "aporte": ("2024-03", 30_000), "transferencia": 20_000},
    ),
}


def _ofx(banco: str, conta: str, transacoes: list[tuple[date, float, str]], virgula: bool) -> str:
    linhas = ["OFXHEADER:100", "DATA:OFXSGML", "VERSION:102", "CHARSET:1252", "", "<OFX>",
              "<BANKMSGSRSV1><STMTTRNRS><STMTRS><CURDEF>BRL",
              f"<BANKACCTFROM><BANKID>{banco}<ACCTID>{conta}<ACCTTYPE>CHECKING</BANKACCTFROM>",
              "<BANKTRANLIST>"]
    for i, (d, valor, memo) in enumerate(transacoes, start=1):
        valor_txt = f"{valor:.2f}".replace(".", ",") if virgula else f"{valor:.2f}"
        linhas += ["<STMTTRN>", f"<TRNTYPE>{'CREDIT' if valor > 0 else 'DEBIT'}",
                   f"<DTPOSTED>{d:%Y%m%d}120000[-3:BRT]", f"<TRNAMT>{valor_txt}",
                   f"<FITID>{conta}-{i:06d}", f"<MEMO>{memo}", "</STMTTRN>"]
    linhas += ["</BANKTRANLIST>", "</STMTRS></STMTTRNRS></BANKMSGSRSV1>", "</OFX>"]
    return "\n".join(linhas)


def gerar_case(pasta: Path, chave: str, semente: int = 42) -> DadosBrutos:
    perfil = PERFIS[chave]
    rnd = random.Random(semente)
    meses = meses_entre(*PERIODO)
    bancario = pasta / "03_Bancario"
    bancario.mkdir(parents=True, exist_ok=True)

    socio = perfil.socios[0][0]
    pgdas, gerencial = [], []
    prov = lambda arq: Proveniencia(arquivo=arq, metodo=Metodo.MANUAL)  # noqa: E731
    transacoes_por_conta: dict[int, list] = {i: [] for i in range(len(perfil.contas))}

    for m in meses:
        ano, mm = map(int, m.split("-"))
        receita_real_mes = perfil.receita_mensal * rnd.uniform(0.9, 1.1)
        gerencial.append(GerencialMes(competencia=m, receita=round(receita_real_mes * rnd.uniform(0.98, 1.02), 2),
                                      proveniencia=prov("04_Gerencial/faturamento.xlsx")))
        for i, (idx_cnpj, _banco, _conta, part) in enumerate(perfil.contas):
            tx = transacoes_por_conta[i]
            receita_conta = receita_real_mes * part
            # recebimentos: 60% PIX de clientes, 40% maquininha
            n = 12
            for k in range(n):
                dia = date(ano, mm, rnd.randint(1, 28))
                valor = round(receita_conta / n, 2)
                memo = (f"PIX RECEBIDO {rnd.choice(CLIENTES)}" if k < 7 else "CRED CIELO VENDAS CARTAO")
                tx.append((dia, valor, memo))
            declarado = round(receita_conta * perfil.fracao_declarada, 2)
            cnpj = perfil.cnpjs[idx_cnpj][0]
            pgdas.append(PGDASMes(cnpj=cnpj, competencia=m, receita_bruta=declarado,
                                  proveniencia=prov("02_Fiscal/pgdas.pdf")))
            # despesas
            tx += [
                (date(ano, mm, 20), -round(declarado * 0.08, 2), "PAGAMENTO DAS SIMPLES NACIONAL"),
                (date(ano, mm, 5), -round(receita_conta * 0.15, 2), "PAGAMENTO FOLHA SALARIOS"),
                (date(ano, mm, 10), -round(receita_conta * 0.45, 2), f"PIX ENVIADO {rnd.choice(FORNECEDORES)}"),
                (date(ano, mm, 10), -8_000.0 * part, "BOLETO PAGO ALUGUEL LOJA"),
                (date(ano, mm, 1), -150.0, "TARIFA CESTA SERVICOS"),
                (date(ano, mm, 28), -25_000.0 * part, f"PIX ENVIADO {socio}"),
                (date(ano, mm, 15), round(rnd.uniform(100, 900), 2), f"CR DIVERSOS {rnd.randint(1000, 9999)}"),
                (date(ano, mm, 16), -round(rnd.uniform(100, 400), 2), f"DEB DIVERSOS {rnd.randint(1000, 9999)}"),
                (date(ano, mm, 25), round(rnd.uniform(50, 300), 2), "RENDIMENTO APLICACAO AUTOMATICA"),
            ]

        ev = perfil.eventos
        if "transferencia" in ev:
            destino = perfil.cnpjs[1][1]
            origem = perfil.cnpjs[0][1]
            transacoes_por_conta[0].append((date(ano, mm, 12), -ev["transferencia"], f"TED ENVIADA {destino}"))
            transacoes_por_conta[1].append((date(ano, mm, 12), ev["transferencia"], f"TED RECEBIDA {origem}"))
        if ev.get("emprestimo", ("",))[0] == m:
            transacoes_por_conta[0].append((date(ano, mm, 8), ev["emprestimo"][1], "LIBERACAO CAPITAL DE GIRO"))
        if ev.get("aporte", ("",))[0] == m:
            transacoes_por_conta[0].append((date(ano, mm, 9), ev["aporte"][1], f"PIX RECEBIDO {socio}"))

    for i, (_idx, banco, conta, _part) in enumerate(perfil.contas):
        tx = sorted(transacoes_por_conta[i])
        (bancario / f"extrato_{banco}_{conta}.ofx").write_text(_ofx(banco, conta, tx, virgula=(i == 1)),
                                                               encoding="cp1252")

    dres = []
    for idx, (cnpj, _rs) in enumerate(perfil.cnpjs):
        for ano in (2024, 2025):
            total = sum(p.receita_bruta for p in pgdas if p.cnpj == cnpj and p.competencia.startswith(str(ano)))
            dres.append(DREAnual(cnpj=cnpj, exercicio=ano, receita_bruta=round(total, 2),
                                 proveniencia=prov(f"01_Contabil/DRE_{ano}.pdf")))

    empresa = Empresa(
        nome=perfil.nome,
        cnpjs=[EmpresaGrupo(cnpj=c, razao_social=r) for c, r in perfil.cnpjs],
        socios=[Socio(nome=n, cpf=cpf) for n, cpf in perfil.socios],
    )
    return DadosBrutos(empresa=empresa, periodo_inicio=PERIODO[0], periodo_fim=PERIODO[1],
                       pgdas=pgdas, gerencial=gerencial, dres=dres)
