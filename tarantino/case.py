"""tarantino_agent — abertura do case e fases F1 (inventário), F2 (captação) e F3 (GCI).

Lê a pasta da empresa no padrão do Drive sem alterar os originais e grava tudo em `<pasta>/_valuation/`:

    state.json         estado do case e histórico de fases
    inventario.json    cada arquivo encontrado, tipo, duplicatas e o que não foi lido
    dados_brutos.json  tudo o que foi captado (extratos classificados, PGDAS/DRE manuais,
                       faturamento da Planilha ND, questionário) — entrada das fases seguintes
    gci.json           confiabilidade da informação (índice, nível A/B/C, divergências)
    pendencias.md      o que pedir ao cliente e o que levar para a entrevista

Enquanto não há parser de PGDAS/DRE/Balanço, esses dados podem ser digitados em
`_valuation/entrada_manual.json` (mesmos campos de DadosBrutos: pgdas, fiscal_mensal, dres, balancos).
"""

from __future__ import annotations

import json
import logging
import re
import zipfile
from datetime import date, datetime
from pathlib import Path

from pydantic import BaseModel, Field

from captacao.carregador import ExtratoNaoLido, ler_extrato, ler_mapa_contas
from captacao.classificacao import Classificador, deduplicar, pendentes_para_ia
from captacao.leitor_planilha_nd import PlanilhaND, ler_planilha_nd
from captacao.parsers.demonstracoes_pdf import DemonstracaoNaoLida, comparar_linhas, ler_demonstracao
from captacao.parsers.extrato_pdf import ExtratoPdfNaoLido, ler_extrato_pdf, mesma_conta
from captacao.parsers.gerencial_xlsx import DREGerencial, GerencialNaoLido, ler_gerencial
from captacao.parsers.emprestimos_pdf import Divida, EmprestimoNaoLido, consolidar_dividas, ler_emprestimos
from captacao.parsers.folha_pdf import FolhaMes, FolhaNaoLida, ler_resumo_folha
from captacao.parsers.pgdas_pdf import (ApuracaoPGDAS, DEFISAnual, SimplesNaoLido, ler_simples,
                                       pgdas_mensal)
from captacao.parsers.relatorios_erp import RelatorioERP, RelatorioNaoReconhecido, ler_relatorio_erp
from captacao.parsers.sped_efd import EFDMensal, EFDNaoLido, concentracao_clientes, consolidar, ler_efd
from captacao.questionario import RespostasQuestionario, carregar_catalogo, ler_respostas
from captacao.schemas import (BalancoAnual, Categoria, DadosBrutos, DREAnual, Empresa, EmpresaGrupo, ExtratoConta,
                              FiscalMes, PGDASMes, Socio)
from captacao.util import apenas_digitos, brl, mes, meses_entre, normalizar_texto
from engine.gci import ResultadoGCI, calcular_gci
from engine.risco import nota_gci
from tarantino.inventario import PASTA_SAIDA, Arquivo, Tipo, caminho_longo, inventariar

logging.getLogger("pdfminer").setLevel(logging.ERROR)  # avisos de fonte do PDF não interessam ao analista

MESES_PADRAO = 24
ESTADOS = ["aberto", "ingerido", "extraido", "gci_definido", "normalizado", "analisado", "avaliado",
           "revisado", "emitido", "fechado"]
REGISTRO = Path(__file__).resolve().parents[1] / "cases" / "registro.json"


# --------------------------------------------------------------------------- modelos


class Etapa(BaseModel):
    fase: str
    estado: str
    quando: str
    resumo: str


class EstadoCase(BaseModel):
    id: str
    empresa: str
    pasta: str
    estado: str = "aberto"
    criado_em: str
    atualizado_em: str
    periodo_inicio: str | None = None
    periodo_fim: str | None = None
    historico: list[Etapa] = Field(default_factory=list)

    def registrar(self, fase: str, estado: str, resumo: str) -> None:
        agora = _agora()
        self.estado, self.atualizado_em = estado, agora
        self.historico.append(Etapa(fase=fase, estado=estado, quando=agora, resumo=resumo))


class Entrevista(BaseModel):
    arquivo: str
    texto: str  # declarado pelo dono ou anotado pela ND na reunião inicial — não comprovado


class Trecho(BaseModel):
    arquivo: str
    texto: str  # começo do documento/planilha sem leitor estruturado (para a análise qualitativa)


class DadosCase(DadosBrutos):
    """dados_brutos.json: DadosBrutos + o que veio do questionário e da Planilha ND."""

    questionario: RespostasQuestionario | None = None
    planilha_nd: PlanilhaND | None = None
    gerenciais: list[DREGerencial] = Field(default_factory=list)  # DRE/fluxo gerencial do dono, por arquivo
    dres_gerenciais: list[DREAnual] = Field(default_factory=list)  # DRE gerencial em PDF (versão do dono)
    efd: list[EFDMensal] = Field(default_factory=list)  # SPED Fiscal por estabelecimento/mês (top 20 participantes)
    concentracao_clientes: dict | None = None
    erp: dict | None = None  # resumo dos relatórios do ERP (receber, pagar, faturamento por produto, estoque)
    dividas: list[Divida] = Field(default_factory=list)  # empréstimos/financiamentos por contrato (posição mais recente)
    folha: list[FolhaMes] = Field(default_factory=list)  # resumo mensal da folha (totais)
    defis: list[DEFISAnual] = Field(default_factory=list)  # declaração anual do Simples
    simples: dict | None = None  # resumo do PGDAS-D mais recente (RBT12, limites, atividades, DAS)
    entrevistas: list[Entrevista] = Field(default_factory=list)  # briefing / kick-off / entrevista (texto)
    outros_documentos: list[Trecho] = Field(default_factory=list)  # certidões, contratos, licenças, planilhas
    alertas: list[str] = Field(default_factory=list)


class Pendencias(BaseModel):
    pedir_ao_cliente: list[str] = Field(default_factory=list)
    arquivos_nao_lidos: list[str] = Field(default_factory=list)
    para_entrevista: list[str] = Field(default_factory=list)
    para_o_analista: list[str] = Field(default_factory=list)


class ResultadoAbertura(BaseModel):
    estado: EstadoCase
    dados: DadosCase
    gci: ResultadoGCI | None
    pendencias: Pendencias
    inventario: list[Arquivo]


# --------------------------------------------------------------------------- utilidades


def _agora() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _novo_id(pasta: Path) -> str:
    """ND-AAAA-NNN sequencial por ano, registrado em cases/registro.json (pasta → id)."""
    REGISTRO.parent.mkdir(parents=True, exist_ok=True)
    registro = json.loads(REGISTRO.read_text(encoding="utf-8")) if REGISTRO.exists() else {}
    chave = str(pasta.resolve())
    if chave in registro:
        return registro[chave]
    ano = datetime.now().year
    n = 1 + sum(1 for v in registro.values() if v.startswith(f"ND-{ano}-"))
    registro[chave] = f"ND-{ano}-{n:03d}"
    REGISTRO.write_text(json.dumps(registro, indent=2, ensure_ascii=False), encoding="utf-8")
    return registro[chave]


def _mes_menos(competencia: str, n: int) -> str:
    ano, m = map(int, competencia.split("-"))
    total = ano * 12 + m - 1 - n
    return f"{total // 12:04d}-{total % 12 + 1:02d}"


def _gravar(pasta: Path, nome: str, conteudo: BaseModel | list | str) -> None:
    alvo = pasta / nome
    if isinstance(conteudo, BaseModel):
        texto = conteudo.model_dump_json(indent=2)
    elif isinstance(conteudo, str):
        texto = conteudo
    else:
        texto = json.dumps([c.model_dump(mode="json") for c in conteudo], indent=2, ensure_ascii=False)
    alvo.write_text(texto, encoding="utf-8")


# --------------------------------------------------------------------------- F2: captação


def _consolidar(itens: list, tipo: str, alertas: list[str]) -> list:
    """Um registro por (CNPJ, exercício, período). Quando o livro seguinte traz o exercício como comparativo
    com outros números, prevalece essa versão REAPRESENTADA (a correção mais recente do contador) e o alerta
    mostra as duas — a reapresentação em si é ponto de diligência."""
    def chave(x):
        return (x.cnpj, x.exercicio, x.meses if tipo == "dre" else x.data_base)

    def comparativo(x) -> bool:
        return (x.proveniencia.localizacao or "").startswith("comparativo")

    campos = ("receita_bruta", "lucro_liquido") if tipo == "dre" else ("patrimonio_liquido", "estoques")
    grupos: dict = {}
    for x in itens:
        grupos.setdefault(chave(x), []).append(x)
    saida = []
    for (cnpj, exercicio, _), grupo in sorted(grupos.items(), key=lambda kv: (kv[0][0], kv[0][1])):
        grupo.sort(key=lambda x: not comparativo(x))  # reapresentado (livro mais recente) primeiro
        escolhido = grupo[0]
        for outro in grupo[1:]:
            for campo in campos:
                a, b = getattr(escolhido, campo), getattr(outro, campo)
                if a is not None and b is not None and abs(a - b) > max(1.0, 0.01 * abs(a)):
                    nome = "DRE" if tipo == "dre" else "Balanço"
                    alertas.append(
                        f"{nome} {exercicio} do CNPJ {cnpj} reapresentada: {campo} = {brl(a)} em "
                        f"{escolhido.proveniencia.arquivo} e {brl(b)} em {outro.proveniencia.arquivo} "
                        f"({outro.proveniencia.localizacao}).")
        saida.append(escolhido)
    return saida


def _resumo_simples(apuracoes: list[ApuracaoPGDAS], defis: list[DEFISAnual], pgdas: list[PGDASMes],
                    folha: list[FolhaMes]) -> tuple[dict | None, list[str]]:
    alertas: list[str] = []
    resumo: dict | None = None
    if apuracoes:
        ult = max(apuracoes, key=lambda a: a.competencia)
        resumo = {"pa_mais_recente": ult.competencia, "rbt12": ult.rbt12, "sublimite": ult.sublimite,
                  "aliquota_efetiva": ult.aliquota_efetiva, "atividades": ult.atividades,
                  "das_pagos": sum(1 for a in apuracoes if a.das_valor_pago), "das_apurados": len(apuracoes),
                  "abertura": min((a.abertura for a in apuracoes if a.abertura), default=None)}
        if ult.rbt12:
            alertas.append(f"Simples Nacional: RBT12 R$ {brl(ult.rbt12, 0)} em {ult.competencia} = "
                           f"{ult.rbt12 / 4_800_000:.0%} do limite (R$ 4,8 mi); alíquota efetiva "
                           f"{(ult.aliquota_efetiva or 0):.1%}.")
            if ult.sublimite and ult.rbt12 > 0.8 * ult.sublimite:
                alertas.append(f"RBT12 perto do sublimite estadual (R$ {brl(ult.sublimite, 0)}): acima dele o ICMS/ISS "
                               "sai do DAS — considerar no custo tributário projetado.")
    for d in sorted(defis, key=lambda d: d.ano):
        receita_ano = sum(p.receita_bruta for p in pgdas if p.competencia.startswith(f"{d.ano}-"))
        meses_ano = sum(1 for p in pgdas if p.competencia.startswith(f"{d.ano}-"))
        if d.estoque_final and receita_ano and meses_ano == 12:
            anos = d.estoque_final / receita_ano
            if anos > 0.5:
                alertas.append(f"DEFIS {d.ano}: estoque final R$ {brl(d.estoque_final, 0)} = {anos:.1f} ano(s) de "
                               f"receita (R$ {brl(receita_ano, 0)}) — estoque declarado muito alto para o giro; "
                               "possível estoque contábil/fictício: confirmar com inventário físico.")
        if d.distribuicao_socios:
            base = f" ({d.distribuicao_socios / receita_ano:.0%} da receita declarada)" if receita_ano and meses_ano == 12 else ""
            alertas.append(f"DEFIS {d.ano}: R$ {brl(d.distribuicao_socios, 0)} pagos aos sócios como lucro isento"
                           f"{base}; pró-labore declarado R$ {brl(d.pro_labore_socios, 0)}.")
        if d.empregados_fim == 0 and not folha:
            alertas.append(f"DEFIS {d.ano}: {d.empregados_inicio or 0} empregado(s) no início e 0 no fim do ano — "
                           "quem opera a empresa? (empregados em outro CNPJ, informais ou só os sócios).")
        if d.retificadora:
            alertas.append(f"DEFIS {d.ano} é retificadora: perguntar ao contador o que foi alterado.")
    return resumo, alertas


def _alertas_pessoal(folha: list[FolhaMes], relatorios: list[RelatorioERP]) -> list[str]:
    alertas = []
    if folha:
        meses = sorted({f.competencia for f in folha})
        por_mes = {m: sum(f.custo_empresa for f in folha if f.competencia == m) for m in meses}
        emp = [sum(f.empregados or 0 for f in folha if f.competencia == m) for m in meses]
        estab = {f.cnpj for f in folha}
        alertas.append(f"Folha CLT ({len(estab)} estabelecimento(s), {meses[0]} a {meses[-1]}): {emp[0]} → {emp[-1]} "
                       f"empregados; custo médio da empresa R$ {brl(sum(por_mes.values()) / len(meses), 0)}/mês "
                       f"(proventos + FGTS + INSS patronal); pró-labore R$ {brl(folha[-1].pro_labore, 0)}/mês.")
    pj = [r for r in relatorios if r.tipo == "colaboradores_pj"]
    if pj:
        qtd, total = sum(r.pj_quantidade for r in pj), sum(r.pj_total_mensal for r in pj)
        alertas.append(f"{qtd} colaborador(es) PJ recorrente(s), R$ {brl(total, 0)}/mês: custo de pessoal fora da folha e "
                       "risco trabalhista (vínculo de emprego) — avaliar como contingência e normalizar o custo.")
    return alertas


def _alertas_dividas(dividas: list[Divida], balancos: list[BalancoAnual]) -> list[str]:
    if not dividas:
        return []
    total = sum(d.saldo_devedor for d in dividas)
    bancos = {"001": "BB", "748": "Sicredi", "341": "Itaú", "237": "Bradesco", "033": "Santander", "104": "Caixa"}
    por_banco: dict[str, float] = {}
    for d in dividas:
        por_banco[bancos.get(d.banco, d.banco)] = por_banco.get(bancos.get(d.banco, d.banco), 0.0) + d.saldo_devedor
    datas = [d.data_posicao for d in dividas if d.data_posicao]
    alertas = [f"Dívida bancária: R$ {brl(total, 0)} em {len(dividas)} contrato(s) ("
               + ", ".join(f"{b} R$ {brl(v, 0)}" for b, v in sorted(por_banco.items(), key=lambda kv: -kv[1]))
               + (f"; posições de {min(datas):%d/%m/%Y} a {max(datas):%d/%m/%Y})." if datas else ").")]
    ultimo = max((b for b in balancos if b.data_base), key=lambda b: b.data_base, default=None)
    if ultimo:
        contabil = (ultimo.emprestimos_cp or 0.0) + (ultimo.emprestimos_lp or 0.0)
        anteriores = sum(d.saldo_devedor for d in dividas
                         if not d.contratacao or d.contratacao <= ultimo.data_base)
        if anteriores and abs(anteriores - contabil) > 0.15 * anteriores:
            alertas.append(f"Empréstimos contratados até {ultimo.data_base:%d/%m/%Y} somam R$ {brl(anteriores, 0)} nos "
                           f"extratos dos bancos (posição atual), mas o Balanço dessa data registra R$ {brl(contabil, 0)}"
                           " — dívida fora da contabilidade ou contabilizada em outra conta; conferir com o contador.")
    sem_taxa = [d.contrato for d in dividas if d.taxa_aa is None and d.taxa_am is None]
    if sem_taxa:
        alertas.append(f"Taxa de juros não informada em {len(sem_taxa)} contrato(s): {', '.join(sem_taxa[:4])}.")
    return alertas


def _resumo_erp(relatorios: list[RelatorioERP], efds: list[EFDMensal],
                balancos: list[BalancoAnual]) -> tuple[dict, list[str]]:
    """Consolida os relatórios do ERP e confere com o SPED (faturamento) e com o Balanço (estoque)."""
    alertas: list[str] = []
    resumo: dict = {}

    # faturamento por mês × estabelecimento (normal + fulfillment) × SPED
    fat: dict[tuple, dict] = {}
    produtos: dict[str, float] = {}
    for r in (r for r in relatorios if r.tipo == "faturamento_produto" and r.competencia):
        d = fat.setdefault((r.competencia, r.estabelecimento), {"vendas": 0.0, "devolucoes": 0.0, "fulfillment": 0.0})
        d["vendas"] += r.vendas_total
        d["devolucoes"] += r.devolucoes_total
        d["fulfillment"] += r.vendas_total if r.fulfillment else 0.0
        for nome, v in r.produtos.items():
            produtos[nome] = produtos.get(nome, 0.0) + v
    if fat:
        vendas = sum(d["vendas"] for d in fat.values())
        full = sum(d["fulfillment"] for d in fat.values())
        top = sorted(produtos.items(), key=lambda kv: -kv[1])
        resumo["faturamento"] = {f"{c} {e or ''}".strip(): {k: round(v, 2) for k, v in d.items()} for (c, e), d in sorted(fat.items())}
        resumo["produtos"] = {"quantidade": len(produtos), "top10": round(sum(v for _, v in top[:10]) / vendas, 4) if vendas else 0,
                              "maiores": [{"produto": n, "valor": round(v, 2)} for n, v in top[:10]]}
        if vendas and full / vendas > 0.10:
            alertas.append(f"Marketplace (fulfillment) = {full / vendas:.0%} das vendas no ERP: dependência do canal "
                           "(taxas, regras e prazo de repasse do marketplace).")
        # conferência com o SPED: estabelecimento pelo sufixo do CNPJ (0001 = matriz)
        efd_por = {}
        for e in efds:
            estab = "Matriz" if e.cnpj[8:12] == "0001" else "Filial"
            efd_por[(e.competencia, estab)] = efd_por.get((e.competencia, estab), 0.0) + e.vendas
        conferidos, divergentes = 0, []
        for (c, estab), d in fat.items():
            if (c, estab) in efd_por and efd_por[(c, estab)]:
                conferidos += 1
                dif = d["vendas"] / efd_por[(c, estab)] - 1
                if abs(dif) > 0.03:
                    divergentes.append(f"{c} {estab}: ERP R$ {brl(d['vendas'], 0)} × SPED R$ {brl(efd_por[(c, estab)], 0)} ({dif:+.0%})")
        if conferidos and not divergentes:
            alertas.append(f"Faturamento do ERP confere com o SPED nos {conferidos} mês(es)/estabelecimento(s) comparados.")
        alertas += [f"Faturamento ERP × SPED diverge — {d}" for d in divergentes]

    # estoque × balanço
    estoques = [r for r in relatorios if r.tipo == "estoque"]
    if estoques:
        total = sum(r.estoque_total for r in estoques)
        sem_custo = sum(r.estoque_sem_custo for r in estoques)
        resumo["estoque"] = {"total": round(total, 2), "itens": sum(r.estoque_itens for r in estoques),
                             "sem_custo": sem_custo, "negativos": sum(r.estoque_negativos for r in estoques),
                             "por_estabelecimento": {r.estabelecimento or r.proveniencia.arquivo: r.estoque_total for r in estoques}}
        ultimo = max((b for b in balancos if b.estoques), key=lambda b: b.data_base or date.min, default=None)
        if ultimo and ultimo.estoques:
            dif = total / ultimo.estoques - 1
            if abs(dif) > 0.15:
                alertas.append(f"Estoque no ERP R$ {brl(total, 0)} × Balanço de {ultimo.data_base:%d/%m/%Y} R$ "
                               f"{brl(ultimo.estoques, 0)} ({dif:+.0%})"
                               + (f"; e {sem_custo} item(ns) do ERP estão sem custo" if sem_custo else "")
                               + " — confirmar qual reflete o estoque real (inventário físico).")

    # contas a receber: saldo, atraso e prazo médio (PMR) sobre as vendas do último mês do ERP/SPED
    receber = [r for r in relatorios if r.tipo == "contas_receber"]
    if receber:
        datas = [t.emissao for r in receber for t in r.titulos if t.emissao]
        base = max(datas) if datas else date.today()
        aberto = sum(r.saldo_aberto() for r in receber)
        aging: dict[str, float] = {}
        for r in receber:
            for k, v in r.aging(base).items():
                aging[k] = round(aging.get(k, 0.0) + v, 2)
        resumo["contas_receber"] = {"data_base": base.isoformat(), "aberto": round(aberto, 2), "aging": aging}
        vendas_mes = sorted(((c, v) for c, v in _vendas_mensais(efds, fat).items()), reverse=True)
        if vendas_mes and vendas_mes[0][1]:
            pmr = aberto / (vendas_mes[0][1] / 30)
            resumo["contas_receber"]["pmr_dias"] = round(pmr)
            alertas.append(f"Contas a receber R$ {brl(aberto, 0)} em {base:%d/%m/%Y} ≈ {pmr:.0f} dias de venda "
                           f"(vendas de {vendas_mes[0][0]}); vencido R$ {brl(aging.get('vencido', 0), 0)}.")

    for r in (r for r in relatorios if r.tipo == "ranking_clientes" and r.ranking):
        total = sum(x["valor"] for x in r.ranking)
        pj = [x for x in r.ranking if not x["pessoa_fisica"]]
        if total:
            resumo["ranking_clientes"] = {"arquivo": r.proveniencia.arquivo, "clientes": len(r.ranking),
                                          "maior": round(pj[0]["valor"] / total, 4) if pj else 0.0,
                                          "top5": round(sum(x["valor"] for x in pj[:5]) / total, 4),
                                          "maiores": pj[:10]}
            if pj and pj[0]["valor"] / total > 0.10:
                alertas.append(f"Concentração (ranking de clientes do ERP, período do relatório): maior cliente "
                               f"{pj[0]['nome']} = {pj[0]['valor'] / total:.0%}; 5 maiores = "
                               f"{sum(x['valor'] for x in pj[:5]) / total:.0%} — confirmar o período do relatório.")
    pj = [r for r in relatorios if r.tipo == "colaboradores_pj"]
    if pj:
        resumo["pj_quantidade"] = sum(r.pj_quantidade for r in pj)
        resumo["pj_total_mensal"] = round(sum(r.pj_total_mensal for r in pj), 2)
    pagar = [r for r in relatorios if r.tipo == "contas_pagar"]
    if pagar:
        pagos: dict[str, float] = {}
        for r in pagar:
            for t in r.titulos:
                if t.vencimento:
                    m = f"{t.vencimento:%Y-%m}"
                    pagos[m] = round(pagos.get(m, 0.0) + t.valor - t.saldo, 2)
        resumo["contas_pagar"] = {"aberto": round(sum(r.saldo_aberto() for r in pagar), 2), "pagos_por_mes": dict(sorted(pagos.items()))}
        from captacao.parsers.relatorios_erp import ALERTA_PASSIVO

        vistos, por_mes = set(), {}
        for r in pagar:
            for t in r.titulos:
                chave = (t.vencimento, round(t.valor, 2), t.contraparte)
                if chave in vistos or not ALERTA_PASSIVO.search(normalizar_texto(f"{t.contraparte} {t.historico}")):
                    continue
                vistos.add(chave)
                m = f"{t.vencimento:%Y-%m}" if t.vencimento else "?"
                por_mes[m] = por_mes.get(m, 0.0) + t.valor
        if por_mes:
            resumo["contas_pagar"]["passivo_fiscal_pago"] = {k: round(v, 2) for k, v in sorted(por_mes.items())}
            reais = {m: v for m, v in por_mes.items() if v >= 100}  # parcelas futuras vêm com valor simbólico
            media = sum(reais.values()) / len(reais) if reais else 0.0
            ultimo = max(por_mes)
            alertas.append(f"Parcelamento de dívida ativa/fiscal: {len(reais)} parcela(s) de ~R$ {brl(media, 0)} no ERP e "
                           f"parcelas programadas até {ultimo} — passivo fiscal que reduz o preço. Pedir o extrato do "
                           "parcelamento (PGFN/Receita/Estado) com saldo devedor e nº de parcelas restantes.")
    return resumo, alertas


def _vendas_mensais(efds: list[EFDMensal], fat: dict) -> dict[str, float]:
    if efds:
        out: dict[str, float] = {}
        for e in efds:
            out[e.competencia] = out.get(e.competencia, 0.0) + e.venda_liquida
        return out
    out = {}
    for (c, _), d in fat.items():
        out[c] = out.get(c, 0.0) + d["vendas"] - d["devolucoes"]
    return out


def _resumir_efd(e: EFDMensal) -> EFDMensal:
    """Guarda só os 20 maiores participantes e nunca o nome de pessoa física."""
    def limpar(ps):
        return [p.model_copy(update={"nome": "Pessoa física", "documento": None}) if p.pessoa_fisica else p
                for p in ps[:20]]
    return e.model_copy(update={"clientes": limpar(e.clientes), "fornecedores": limpar(e.fornecedores)})


def _alertas_efd(efds: list[EFDMensal], conc: dict) -> list[str]:
    alertas = []
    meses = sorted({e.competencia for e in efds})
    if not meses:
        return alertas
    vendas = sum(e.vendas for e in efds)
    estab = sorted({e.cnpj for e in efds})
    alertas.append(f"SPED Fiscal: {len(estab)} estabelecimento(s), {meses[0]} a {meses[-1]}, vendas R$ {brl(vendas, 0)}"
                   f", devoluções R$ {brl(sum(e.devolucoes_venda for e in efds), 0)}.")
    transf = sum(e.transferencias_saida for e in efds)
    if transf > 0.05 * vendas:
        alertas.append(f"Transferências entre estabelecimentos R$ {brl(transf, 0)} (fora da receita): a receita de "
                       "cada estabelecimento deve ser analisada consolidada.")
    if conc.get("maior", 0) > 0.10:
        top = conc["ranking"][0]
        alertas.append(f"Concentração: maior cliente ({top['cliente']}) = {conc['maior']:.0%} das vendas; "
                       f"5 maiores = {conc['top5']:.0%}.")
    if conc.get("pessoas_fisicas", 0) > 0.30:
        alertas.append(f"{conc['pessoas_fisicas']:.0%} das vendas a consumidor final (pessoa física: varejo/e-commerce)"
                       f" — receita pulverizada; maior cliente empresa = {conc['maior']:.1%}.")
    compras = sum(e.compras for e in efds)
    imp = sum(e.importacoes for e in efds)
    if compras and imp / compras > 0.30:
        alertas.append(f"Importação = {imp / compras:.0%} das compras (R$ {brl(imp, 0)}): exposição ao câmbio e a "
                       "prazos de importação no custo e no capital de giro.")
    emitidas = sum(e.notas_saida for e in efds)
    canceladas = sum(e.notas_canceladas for e in efds)
    if emitidas and canceladas / emitidas > 0.05:
        alertas.append(f"{canceladas / emitidas:.0%} das notas de saída canceladas ({canceladas} de {emitidas}).")
    return alertas


def _resumo_gerencial_x_contabil(contabil, gerencial) -> str:
    """Uma linha para o analista: o que a versão gerencial do dono muda em relação à contábil."""
    c, g = contabil.dres[0], gerencial.dres[0]
    difs = comparar_linhas(contabil, gerencial)
    redondas = [d for d in difs if d.redonda]
    partes = [f"DRE gerencial {g.exercicio} × contábil: receita R$ {brl(c.receita_bruta or 0, 0)} → "
              f"R$ {brl(g.receita_bruta or 0, 0)}, lucro R$ {brl(c.lucro_liquido or 0, 0)} → "
              f"R$ {brl(g.lucro_liquido or 0, 0)}; {len(difs)} linha(s) diferentes"]
    if redondas:
        exemplos = ", ".join(f"{d.conta.title()} {brl(d.diferenca, 0)}" for d in redondas[:4])
        partes.append(f"{len(redondas)} em valores redondos ({exemplos}) — sinal de ajuste manual, pedir a "
                      "justificativa de cada um")
    elif (g.receita_bruta or 0) > (c.receita_bruta or 0) * 1.05:
        partes.append("diferença concentrada na receita/CMV — indício de venda sem nota: confirmar pelos extratos")
    return "; ".join(partes) + "."


def _pdfs_sem_ofx(lidos_pdf: list[tuple[Arquivo, ExtratoConta]], ofx: list[ExtratoConta]) -> list[ExtratoConta]:
    """O OFX é a fonte preferida. Do PDF fica só o que nenhum OFX da mesma conta cobre (mês a mês),
    para não contar o mesmo lançamento duas vezes."""
    saida = []
    for item, pdf in lidos_pdf:
        cobertos = {mes(t.data) for o in ofx if mesma_conta(o, pdf) for t in o.transacoes}
        resto = [t for t in pdf.transacoes if mes(t.data) not in cobertos]
        if not resto and pdf.transacoes:
            item.status, item.detalhe = "duplicado", "mesmo período e conta de um OFX (o OFX foi usado)"
            continue
        if len(resto) < len(pdf.transacoes):
            item.detalhe = f"usados só os meses sem OFX ({len(resto)} de {len(pdf.transacoes)} lançamentos)"
        saida.append(pdf.model_copy(update={"transacoes": resto}))
    return saida


def _juntar_por_conta(extratos: list[ExtratoConta]) -> list[ExtratoConta]:
    """Arquivos da mesma conta (mensais, OFX e PDF) viram um só extrato. O número da conta é comparado
    tolerando zeros e agência/cooperativa à esquerda, porque OFX e PDF escrevem a conta de jeitos diferentes."""
    contas: list[ExtratoConta] = []
    arquivos: list[int] = []
    for e in extratos:
        alvo = next((i for i, c in enumerate(contas)
                     if mesma_conta(c, e) and (not c.cnpj_titular or not e.cnpj_titular
                                               or c.cnpj_titular == e.cnpj_titular)), None)
        if alvo is None:
            contas.append(e.model_copy(deep=True))
            arquivos.append(1)
        else:
            contas[alvo].transacoes += e.transacoes
            contas[alvo].cnpj_titular = contas[alvo].cnpj_titular or e.cnpj_titular
            arquivos[alvo] += 1
    for e, n in zip(contas, arquivos):
        e.transacoes.sort(key=lambda t: t.data)
        if n > 1:
            e.proveniencia.localizacao = f"{n} arquivos"
    return contas


def _receita_gerencial(gerenciais: list[DREGerencial]) -> dict[str, float]:
    """Receita operacional mensal das DREs gerenciais (se dois arquivos cobrem o mesmo mês, vale o 1º)."""
    receita: dict[str, float] = {}
    for d in gerenciais:
        for c, v in d.receita_mensal().items():
            receita.setdefault(c, v)
    return dict(sorted(receita.items()))


def _comparar_gerenciais(planilha_nd: dict[str, float], dre_ger: dict[str, float]) -> list[str]:
    comuns = [m for m in planilha_nd if m in dre_ger]
    a, b = sum(planilha_nd[m] for m in comuns), sum(dre_ger[m] for m in comuns)
    if comuns and b and abs(a - b) / b > 0.10:
        return [f"Faturamento da Planilha ND (R$ {brl(a, 0)}) difere {abs(a - b) / b:.0%} da DRE gerencial "
                f"(R$ {brl(b, 0)}) nos mesmos {len(comuns)} meses."]
    return []


def _comparar_contabil(receita_ger: dict[str, float], dres: list[DREAnual]) -> list[str]:
    """Receita gerencial × contábil por ano fechado: a diferença é o principal indício de venda sem nota."""
    alertas = []
    contabil: dict[int, float] = {}
    for d in dres:
        if d.meses == 12 and d.receita_bruta:
            contabil[d.exercicio] = contabil.get(d.exercicio, 0.0) + d.receita_bruta
    for ano, rec_cont in sorted(contabil.items()):
        meses = [m for m in receita_ger if m.startswith(f"{ano}-")]
        if len(meses) < 12:
            continue
        rec_ger = sum(receita_ger[m] for m in meses)
        dif = (rec_ger - rec_cont) / rec_cont
        if abs(dif) > 0.05:
            alertas.append(f"Receita {ano}: gerencial R$ {brl(rec_ger, 0)} × contábil R$ {brl(rec_cont, 0)} "
                           f"({dif:+.0%}). " + ("Indício de receita sem nota: confirmar pelos extratos."
                                                if dif > 0 else "Gerencial abaixo do contábil: verificar se a "
                                                "planilha cobre todos os CNPJs/atividades."))
    return alertas


def _empresa(nome_pasta: str, planilha: PlanilhaND | None, quest: RespostasQuestionario | None,
             manual: dict, entidades: dict[str, str] | None = None) -> Empresa:
    if manual.get("empresa"):
        return Empresa.model_validate(manual["empresa"])
    cnpjs, socios = [], []
    if planilha:
        for l in planilha.abas.get("1_Grupo", []):
            if l.get("cnpj"):
                cnpjs.append(EmpresaGrupo(cnpj=l["cnpj"], razao_social=l.get("razao_social") or l["cnpj"],
                                          nome_fantasia=l.get("nome_fantasia")))
        socios = [Socio(nome=s["nome"]) for s in planilha.abas.get("2_Socios", []) if s.get("nome")]
    if not cnpjs and quest and quest.cnpj:
        cnpjs = [EmpresaGrupo(cnpj=quest.cnpj, razao_social=quest.empresa or quest.cnpj)]
    conhecidos = {apenas_digitos(c.cnpj) for c in cnpjs}
    for cnpj, entidade in (entidades or {}).items():  # CNPJs que só aparecem nas demonstrações contábeis
        if cnpj not in conhecidos:
            cnpjs.append(EmpresaGrupo(cnpj=cnpj, razao_social=entidade))
    nome = (quest.empresa if quest and quest.empresa else None) or \
        (cnpjs[0].nome_fantasia or cnpjs[0].razao_social if cnpjs else None) or nome_pasta
    return Empresa(nome=nome, cnpjs=cnpjs, socios=socios)


def _periodo(extratos: list[ExtratoConta], pgdas: list[PGDASMes], planilha: PlanilhaND | None,
             fim: str | None, meses: int, balancos: list[BalancoAnual] | None = None,
             gerenciais: list[DREGerencial] | None = None) -> tuple[str, str]:
    if not fim:
        candidatos = [mes(t.data) for e in extratos for t in e.transacoes]
        candidatos += [p.competencia for p in pgdas]
        if planilha:
            candidatos += [f.competencia for f in planilha.faturamento]
        candidatos += [c for g in gerenciais or [] for c in g.receita_mensal()]
        if not candidatos:  # sem dados mensais: termina na data do último balanço/balancete
            candidatos = [mes(b.data_base) for b in balancos or [] if b.data_base]
        fim = max(candidatos) if candidatos else mes(datetime.now().date().replace(day=1))
    return _mes_menos(fim, meses - 1), fim


_RE_PESSOAL = re.compile(r"\bCNH\b|\bRG\b|\bCPF\b|IRPF|HOLERITE|CONTRACHEQUE|FUNCIONARI|COLABORADOR|"
                         r"EMPREGADO|FOLHA DE PAGAMENTO|DECLARACAO DE AJUSTE|CERTIDAO DE (NASCIMENTO|CASAMENTO)")
LIMITE_TRECHO = 2000


def _trecho(arquivo: Path) -> str | None:
    """Começo do texto de um PDF ou das primeiras linhas de uma planilha; None se não houver texto."""
    try:
        if arquivo.suffix.lower() == ".pdf":
            import pdfplumber

            with pdfplumber.open(arquivo) as pdf:
                texto = "\n".join((p.extract_text() or "") for p in pdf.pages[:2])
        elif arquivo.suffix.lower() in {".xlsx", ".xlsm"}:
            from openpyxl import load_workbook

            wb = load_workbook(arquivo, read_only=True, data_only=True)
            linhas = []
            for ws in wb.worksheets[:3]:
                linhas.append(f"[aba {ws.title}]")
                for row in ws.iter_rows(max_row=40, values_only=True):
                    vals = [str(v) for v in row if v not in (None, "")]
                    if vals:
                        linhas.append(" | ".join(vals))
            texto = "\n".join(linhas)
        else:
            return None
    except Exception:  # noqa: BLE001 — arquivo protegido ou corrompido: fica só como não lido
        return None
    texto = re.sub(r"\n{3,}", "\n\n", texto).strip()
    return texto[:LIMITE_TRECHO] if len(texto) >= 80 else None


def _no_periodo(itens: list, inicio: str, fim: str, campo: str = "competencia") -> list:
    return [i for i in itens if inicio <= getattr(i, campo) <= fim]


def captar(pasta: Path, inventario: list[Arquivo], fim: str | None = None, meses: int = MESES_PADRAO,
           cnpj: str | None = None) -> DadosCase:
    alertas: list[str] = []
    saida = pasta / PASTA_SAIDA

    manual = {}
    if (saida / "entrada_manual.json").exists():
        manual = json.loads((saida / "entrada_manual.json").read_text(encoding="utf-8"))

    ativos = [a for a in inventario if a.status != "duplicado"]

    planilhas = [a for a in ativos if a.tipo == Tipo.PLANILHA_ND]
    planilha = None
    if planilhas:
        escolhida = max(planilhas, key=lambda a: (pasta / a.caminho).stat().st_mtime)
        planilha = ler_planilha_nd(pasta / escolhida.caminho)
        escolhida.status = "lido"
        for a in planilhas:
            if a is not escolhida:
                a.status, a.detalhe = "não lido", f"versão mais antiga; usada {escolhida.caminho}"

    quest = None
    for a in [a for a in ativos if a.tipo == Tipo.QUESTIONARIO]:
        try:
            quest = ler_respostas(pasta / a.caminho, cnpj=cnpj)
            a.status = "lido"
            break
        except ValueError as erro:
            a.status, a.detalhe = "erro", str(erro)

    extratos: list[ExtratoConta] = []
    mapas: dict[Path, dict] = {}
    lidos_pdf: list[tuple[Arquivo, ExtratoConta]] = []
    for a in [a for a in ativos if a.tipo == Tipo.EXTRATO]:
        arq = pasta / a.caminho
        mapa = mapas.setdefault(arq.parent, ler_mapa_contas(arq.parent))
        try:
            if arq.suffix.lower() == ".pdf":
                extrato, avisos = ler_extrato_pdf(arq)
                alertas += [f"{a.caminho}: {x}" for x in avisos]
                lidos_pdf.append((a, extrato))
            else:
                extratos.append(ler_extrato(arq, mapa.get(arq.name)))
            a.status = "lido"
        except (ExtratoNaoLido, ExtratoPdfNaoLido) as erro:
            a.status, a.detalhe = "erro", str(erro)
    extratos += _pdfs_sem_ofx(lidos_pdf, extratos)
    extratos = deduplicar(_juntar_por_conta(extratos))

    efds: list[EFDMensal] = []
    for a in [a for a in ativos if a.tipo in (Tipo.SPED, Tipo.COMPACTADO)]:
        try:
            lidos = ler_efd(pasta / a.caminho)
        except (EFDNaoLido, zipfile.BadZipFile) as erro:
            if a.tipo == Tipo.SPED:
                a.status, a.detalhe = "erro", str(erro)
            continue
        a.status, a.detalhe = "lido", f"{len(lidos)} EFD ICMS/IPI ({lidos[0].competencia} a {lidos[-1].competencia})"
        efds += lidos
    efds = consolidar(efds)

    dividas: list[Divida] = []
    for a in [a for a in ativos if a.tipo == Tipo.EMPRESTIMO]:
        try:
            lidas = ler_emprestimos(pasta / a.caminho)
        except (EmprestimoNaoLido, AttributeError, ValueError) as erro:
            a.status, a.detalhe = "erro", str(erro)
            continue
        a.status, a.detalhe = "lido", f"{len(lidas)} contrato(s), saldo R$ {brl(sum(d.saldo_devedor for d in lidas), 0)}"
        dividas += lidas
    dividas = consolidar_dividas(dividas)

    folha: list[FolhaMes] = []
    for a in [a for a in ativos if a.tipo == Tipo.FOLHA]:
        try:
            meses_folha = ler_resumo_folha(pasta / a.caminho)
        except FolhaNaoLida as erro:
            a.status, a.detalhe = "erro", str(erro)
            continue
        a.status, a.detalhe = "lido", f"folha {meses_folha[0].competencia} a {meses_folha[-1].competencia}"
        folha += meses_folha

    entrevistas: list[Entrevista] = []
    for a in [a for a in ativos if a.tipo == Tipo.ENTREVISTA]:
        from captacao.parsers.entrevista import EntrevistaNaoLida, extrair_texto

        try:
            texto = extrair_texto(pasta / a.caminho)
        except (EntrevistaNaoLida, OSError) as erro:
            a.status, a.detalhe = "erro", str(erro)
            continue
        a.status, a.detalhe = "lido", f"entrevista/briefing: {len(texto):,} caracteres".replace(",", ".")
        entrevistas.append(Entrevista(arquivo=a.caminho, texto=texto))

    outros: list[Trecho] = []
    for a in [a for a in ativos if a.tipo in (Tipo.PDF, Tipo.PLANILHA_OUTRA) and a.status == "não lido"]:
        if _RE_PESSOAL.search(normalizar_texto(a.caminho)):
            continue  # documento pessoal ou de funcionários: não sai da pasta (privacidade)
        texto = _trecho(pasta / a.caminho)
        if texto:
            outros.append(Trecho(arquivo=a.caminho, texto=texto))
            a.detalhe = f"{a.detalhe} (trecho enviado à análise qualitativa)"

    apuracoes: list[ApuracaoPGDAS] = []
    defis: list[DEFISAnual] = []
    for a in [a for a in ativos if a.tipo == Tipo.SIMPLES]:
        try:
            doc = ler_simples(pasta / a.caminho)
        except (SimplesNaoLido, ValueError) as erro:
            a.status, a.detalhe = "erro", str(erro)
            continue
        a.status = "lido"
        if isinstance(doc, ApuracaoPGDAS):
            a.detalhe = f"PGDAS-D PA {doc.competencia} (+{len(doc.receitas_anteriores)} meses anteriores)"
            apuracoes.append(doc)
        else:
            a.detalhe = f"DEFIS {doc.ano}{' retificadora' if doc.retificadora else ''}"
            defis.append(doc)

    relatorios: list[RelatorioERP] = []
    for a in [a for a in ativos if a.tipo == Tipo.RELATORIO_ERP]:
        try:
            rel = ler_relatorio_erp(pasta / a.caminho)
        except (RelatorioNaoReconhecido, ValueError) as erro:
            a.status, a.detalhe = "erro", str(erro)
            continue
        a.status = "lido"
        a.detalhe = " ".join(x for x in (rel.tipo, rel.estabelecimento, rel.competencia,
                                         "fulfillment" if rel.fulfillment else None) if x)
        # passivo fiscal é consolidado em _resumo_erp (os relatórios repetem os mesmos títulos)
        alertas += [f"{a.caminho}: {x}" for x in rel.alertas if not x.startswith("Pagamento de passivo fiscal")]
        relatorios.append(rel)

    pgdas = [PGDASMes.model_validate(p) for p in manual.get("pgdas", [])]
    if apuracoes:
        lidos_pgdas, alertas_pgdas = pgdas_mensal(apuracoes)
        manuais = {p.competencia for p in pgdas}
        pgdas += [p for p in lidos_pgdas if p.competencia not in manuais]  # o digitado à mão prevalece
        alertas += alertas_pgdas
    dres = [DREAnual.model_validate(d) for d in manual.get("dres", [])]
    balancos = [BalancoAnual.model_validate(b) for b in manual.get("balancos", [])]

    entidades: dict[str, str] = {}
    for e in efds:  # estabelecimentos do SPED entram no grupo (ex.: filial)
        entidades.setdefault(e.cnpj, e.nome)
    lidos_dre, lidos_bp = [], []
    # DRE gerencial digitada pelo analista (11/11/2026, Intermoldes: operação com a receita sem nota estimada)
    docs_gerenciais, docs_contabeis = [], {}
    dres_gerenciais = [DREAnual.model_validate(d) for d in manual.get("dres_gerenciais", [])]
    for a in [a for a in ativos if a.tipo == Tipo.DEMONSTRACAO]:
        try:
            doc = ler_demonstracao(pasta / a.caminho)
        except DemonstracaoNaoLida as erro:
            a.status, a.detalhe = "erro", str(erro)
            continue
        a.status = "lido"
        a.detalhe = f"{doc.tipo}{' gerencial' if doc.gerencial else ''} {doc.data_fim:%d/%m/%Y} ({doc.layout})"
        if doc.cnpj and doc.entidade:
            entidades.setdefault(doc.cnpj, doc.entidade)
        alertas += [f"{a.caminho}: {x}" for x in doc.alertas]
        if doc.gerencial:  # versão do dono: não entra como contábil; é comparada linha a linha
            docs_gerenciais.append(doc)
            dres_gerenciais += doc.dres[:1]
            continue
        if doc.tipo == "dre":
            docs_contabeis[(doc.cnpj, doc.data_fim)] = doc
        lidos_dre += doc.dres
        lidos_bp += doc.balancos
    # o digitado à mão prevalece (11/11/2026, WM): exercício com DRE/balanço na entrada manual não recebe a versão do
    # parser — a manual é a reclassificada pelo analista e somar as duas contaria o ano em dobro
    anos_dre = {(d.exercicio, d.meses) for d in dres}
    datas_bp = {b.data_base for b in balancos}
    dres += [d for d in _consolidar(lidos_dre, "dre", alertas) if (d.exercicio, d.meses) not in anos_dre]
    balancos += [b for b in _consolidar(lidos_bp, "balanco", alertas) if b.data_base not in datas_bp]
    for g in docs_gerenciais:
        contabil = docs_contabeis.get((g.cnpj, g.data_fim))
        if contabil:
            alertas.append(_resumo_gerencial_x_contabil(contabil, g))

    mapa_ger = saida / "mapa_gerencial.json"
    mapa = json.loads(mapa_ger.read_text(encoding="utf-8")) if mapa_ger.exists() else {}
    gerenciais: list[DREGerencial] = []
    for a in [a for a in ativos if a.tipo == Tipo.GERENCIAL]:
        try:
            g = ler_gerencial(pasta / a.caminho, mapa)
        except GerencialNaoLido as erro:
            a.status, a.detalhe = "erro", str(erro)
            continue
        a.status, a.detalhe = "lido", f"gerencial {g.competencias[0]} a {g.competencias[-1]}" if g.competencias else "gerencial"
        gerenciais.append(g)
        alertas += [f"{a.caminho}: {x}" for x in g.alertas]

    empresa = _empresa(pasta.name, planilha, quest, manual, entidades)
    if not empresa.socios and defis:
        ultima = max(defis, key=lambda d: d.ano)
        empresa.socios = [Socio(nome=x["nome"], cpf=x.get("cpf")) for x in ultima.socios if x.get("nome")]
    if apuracoes and not empresa.cnpjs:
        a0 = max(apuracoes, key=lambda x: x.competencia)
        empresa.cnpjs = [EmpresaGrupo(cnpj=a0.cnpj, razao_social=a0.nome or a0.cnpj)]
    if apuracoes and empresa.nome == pasta.name and max(apuracoes, key=lambda x: x.competencia).nome:
        empresa.nome = max(apuracoes, key=lambda x: x.competencia).nome
    inicio, fim = _periodo(extratos, pgdas, planilha, fim, meses, balancos, gerenciais)

    regras = saida / "regras_aprendidas.json"
    Classificador(empresa, regras if regras.exists() else None).classificar(extratos)

    if quest:
        alertas += [f"Questionário: {x}" for x in quest.alertas]
    if planilha:
        alertas += [f"Planilha ND: {x}" for x in planilha.alertas]
    cnpjs_grupo = {apenas_digitos(e.cnpj) for e in empresa.cnpjs}
    if quest and quest.cnpj and cnpjs_grupo and quest.cnpj not in cnpjs_grupo:
        alertas.append(f"CNPJ do questionário ({quest.cnpj}) não está entre os CNPJs da Planilha ND.")

    fiscal = [FiscalMes(cnpj=e.cnpj, competencia=e.competencia, receita_bruta=e.vendas,
                        devolucoes=e.devolucoes_venda, fonte="EFD ICMS/IPI", proveniencia=e.proveniencia)
              for e in efds]
    manuais_fiscal = [FiscalMes.model_validate(f) for f in manual.get("fiscal_mensal", [])]
    if manuais_fiscal:  # receita mensal digitada (ex.: relatório de faturamento do contador); prevalece sobre a EFD
        meses_manuais = {(f.cnpj, f.competencia) for f in manuais_fiscal}
        fiscal = manuais_fiscal + [f for f in fiscal if (f.cnpj, f.competencia) not in meses_manuais]
    concentracao = None
    if efds:
        efds_periodo = [e for e in efds if inicio <= e.competencia <= fim]
        raiz = {apenas_digitos(c.cnpj)[:8] for c in empresa.cnpjs} | {e.cnpj[:8] for e in efds}
        concentracao = concentracao_clientes(efds_periodo, raiz)
        alertas += _alertas_efd(efds_periodo, concentracao)
    alertas += _alertas_dividas(dividas, balancos)
    alertas += _alertas_pessoal(folha, relatorios)
    resumo_simples, alertas_simples = _resumo_simples(apuracoes, defis, pgdas, folha)
    alertas += alertas_simples
    erp = None
    if relatorios:
        erp, alertas_erp = _resumo_erp(relatorios, efds, balancos)
        alertas += alertas_erp
    receita_ger = _receita_gerencial(gerenciais)
    if planilha and planilha.faturamento:
        fonte_gerencial = planilha.gerencial()
        alertas += _comparar_gerenciais(planilha.faturamento_mensal_total(), receita_ger)
    else:  # sem Planilha ND: a receita da DRE gerencial é a visão do dono
        fonte_gerencial = [g for d in gerenciais for g in d.gerencial_mensal() if g.competencia in receita_ger]
        vistos = set()
        fonte_gerencial = [g for g in fonte_gerencial if not (g.competencia in vistos or vistos.add(g.competencia))]
    alertas += _comparar_contabil(receita_ger, dres)

    return DadosCase(
        empresa=empresa, periodo_inicio=inicio, periodo_fim=fim,
        extratos=extratos,
        pgdas=_no_periodo(pgdas, inicio, fim),
        gerencial=_no_periodo(fonte_gerencial, inicio, fim),
        fiscal_mensal=_no_periodo(fiscal, inicio, fim),
        dres=dres, balancos=balancos,
        questionario=quest, planilha_nd=planilha, gerenciais=gerenciais, dres_gerenciais=dres_gerenciais,
        efd=[_resumir_efd(e) for e in efds], concentracao_clientes=concentracao,
        erp=erp,
        dividas=dividas,
        folha=folha,
        defis=defis, simples=resumo_simples,
        entrevistas=entrevistas, outros_documentos=outros,
        alertas=alertas,
    )


# --------------------------------------------------------------------------- pendências


def montar_pendencias(dados: DadosCase, gci: ResultadoGCI | None, inventario: list[Arquivo]) -> Pendencias:
    p = Pendencias()
    meses = meses_entre(dados.periodo_inicio, dados.periodo_fim)

    meses_extrato = {mes(t.data) for e in dados.extratos for t in e.transacoes}
    if not dados.extratos:
        p.pedir_ao_cliente.append(f"Extratos bancários em OFX de todas as contas, de {meses[0]} a {meses[-1]}.")
    else:
        faltam = [m for m in meses if m not in meses_extrato]
        if faltam:
            p.pedir_ao_cliente.append(f"Extratos de {len(faltam)} mês(es) sem movimento recebido: "
                                      f"{', '.join(faltam[:6])}{'…' if len(faltam) > 6 else ''}.")
    fora_do_simples = any(d.deducoes and d.receita_bruta and abs(d.deducoes) / d.receita_bruta > 0.15
                          for d in dados.dres)  # PIS/COFINS/ICMS cheios nas deduções
    if dados.fiscal_mensal:
        faltam_efd = [m for m in meses if m not in {f.competencia for f in dados.fiscal_mensal}]
        if faltam_efd:
            p.pedir_ao_cliente.append(f"SPED Fiscal (EFD ICMS/IPI) de {len(faltam_efd)} mês(es) do período ainda não "
                                      f"recebido(s): {', '.join(faltam_efd[:6])}{'…' if len(faltam_efd) > 6 else ''} "
                                      "— todos os estabelecimentos.")
    elif dados.pgdas:
        faltam_pgdas = [m for m in meses if m not in {p.competencia for p in dados.pgdas}]
        if faltam_pgdas:
            p.pedir_ao_cliente.append(f"PGDAS-D de {len(faltam_pgdas)} mês(es) sem receita declarada no período "
                                      f"({', '.join(faltam_pgdas[:6])}{'…' if len(faltam_pgdas) > 6 else ''}) — um "
                                      "extrato do PGDAS-D de um mês posterior traz os 18 meses anteriores.")
    elif not dados.pgdas and fora_do_simples:
        p.pedir_ao_cliente.append("SPED Fiscal (EFD ICMS/IPI e EFD Contribuições) em .txt dos últimos 24 meses — "
                                  "a empresa parece fora do Simples; pedir ao contador.")
    elif not dados.pgdas:
        p.pedir_ao_cliente.append("PGDAS-D (ou declarações do regime) dos últimos 24 meses de todos os CNPJs "
                                  "— pedir ao contador.")
    internas = sum(t.valor for e in dados.extratos for t in e.transacoes
                   if t.categoria == Categoria.TRANSFERENCIA_INTERNA)
    receita_caixa = sum(t.valor for e in dados.extratos for t in e.transacoes
                        if t.categoria == Categoria.RECEITA_OPERACIONAL)
    if receita_caixa and internas > 0.10 * receita_caixa:
        p.pedir_ao_cliente.append(
            f"Extratos de TODAS as contas da empresa e das outras empresas/filiais do grupo: entraram R$ "
            f"{brl(internas, 0)} líquidos vindos de contas próprias que não estão na pasta (a receita pode estar "
            "sendo recebida nelas).")
    if not dados.dres:
        p.pedir_ao_cliente.append("DRE e Balanço dos últimos 3 exercícios (ou SPED ECD/ECF) — pedir ao contador.")
    if dados.planilha_nd is None:
        p.pedir_ao_cliente.append("Planilha ND de Captação preenchida.")
    if dados.questionario is None:
        p.pedir_ao_cliente.append("Questionário do Empreendedor (enviar o link do formulário).")

    nao_lidos = [a for a in inventario if a.status in {"não lido", "erro"}]
    pdfs = [a for a in nao_lidos if a.tipo == Tipo.PDF]
    if pdfs and len(meses_extrato) < len(meses):
        p.pedir_ao_cliente.append(f"Há {len(pdfs)} PDF(s) na pasta que o sistema ainda não lê. Se forem extratos, "
                                  "pedir os mesmos períodos em OFX (exportação do internet banking).")
    grupos: dict[str, list[Arquivo]] = {}
    for a in nao_lidos:
        grupos.setdefault(a.detalhe or a.tipo.value, []).append(a)
    for detalhe, arqs in grupos.items():
        if len(arqs) > 3:  # muitos arquivos do mesmo tipo (ex.: notas avulsas): uma linha com a pasta
            pastas = sorted({str(Path(a.caminho).parent) for a in arqs})
            p.arquivos_nao_lidos.append(f"{len(arqs)} arquivo(s) em {', '.join(pastas[:3])} — {detalhe}")
        else:
            p.arquivos_nao_lidos += [f"{a.caminho} — {detalhe}" for a in arqs]
    passivo_fiscal = (dados.erp or {}).get("contas_pagar", {}).get("passivo_fiscal_pago")
    if passivo_fiscal:
        p.pedir_ao_cliente.append("Extrato do parcelamento/dívida ativa (PGFN, Receita ou Estado) com saldo devedor e "
                                  f"parcelas restantes — há pagamentos mensais até {max(passivo_fiscal)}.")
    if dados.dividas and dados.balancos:
        p.pedir_ao_cliente.append("Ao contador: conciliação dos empréstimos bancários (extratos dos bancos × conta de "
                                  "empréstimos do Balanço) e posição de TODAS as dívidas, inclusive de sócios.")
    duplicados = [a for a in inventario if a.status == "duplicado"]
    if duplicados:
        p.para_o_analista.append(f"{len(duplicados)} arquivo(s) duplicado(s) ignorado(s) (mesmo conteúdo de outro).")

    if dados.questionario:
        cat = carregar_catalogo()
        pend = dados.questionario.pendentes(cat)
        p.para_entrevista = [f"{c} · {cat.perguntas[c].titulo}" for c in pend if not c.startswith("ID")]

    for g in dados.gerenciais:
        if g.pendentes():
            p.para_o_analista.append(
                f"Classificar {len(g.pendentes())} conta(s) da DRE gerencial {g.proveniencia.arquivo} "
                f"({', '.join(g.pendentes()[:5])}) em _valuation/mapa_gerencial.json (analista ou IA).")
    p.para_o_analista += dados.alertas
    if gci:
        p.para_o_analista += [f"GCI: {a}" for a in gci.alertas]
    ia = pendentes_para_ia(dados.extratos)
    if ia:
        p.para_o_analista.append(f"{len(ia)} padrão(ões) de lançamento sem classificação "
                                 "(revisar ou enviar à IA na próxima fase).")
    return p


def pendencias_md(estado: EstadoCase, gci: ResultadoGCI | None, p: Pendencias) -> str:
    def secao(titulo: str, itens: list[str], vazio: str) -> str:
        corpo = "\n".join(f"- {i}" for i in itens) if itens else f"_{vazio}_"
        return f"## {titulo}\n\n{corpo}\n"

    gci_txt = (f"**GCI:** {gci.indice:.1f} · nível **{gci.nivel}** · nota de risco {nota_gci(gci.indice, gci.nivel)}/5"
               if gci else "**GCI:** não calculado (sem extratos nem PGDAS)")
    partes = [
        f"# Pendências — {estado.empresa} ({estado.id})",
        f"Período analisado: {estado.periodo_inicio} a {estado.periodo_fim} · {gci_txt} · gerado em {estado.atualizado_em}\n",
        secao("Pedir ao cliente", p.pedir_ao_cliente, "nada pendente"),
        secao("Arquivos que o sistema não leu", p.arquivos_nao_lidos, "todos lidos"),
        secao("Levar para a entrevista (sem resposta no questionário)", p.para_entrevista, "nada"),
        secao("Para o analista", p.para_o_analista, "sem alertas"),
    ]
    return "\n".join(partes)


# --------------------------------------------------------------------------- orquestração


def abrir_case(pasta_empresa: str | Path, fim: str | None = None, meses: int = MESES_PADRAO,
               cnpj: str | None = None) -> ResultadoAbertura:
    """Abre (ou reabre) o case e roda F1 → F3. Reexecutar refaz as fases sem apagar o histórico."""
    pasta = Path(pasta_empresa)
    if not pasta.is_dir():
        raise FileNotFoundError(f"Pasta da empresa não encontrada: {pasta}")
    saida = pasta / PASTA_SAIDA
    saida.mkdir(exist_ok=True)

    arq_estado = saida / "state.json"
    if arq_estado.exists():
        estado = EstadoCase.model_validate_json(arq_estado.read_text(encoding="utf-8"))
    else:
        agora = _agora()
        estado = EstadoCase(id=_novo_id(pasta), empresa=pasta.name, pasta=str(pasta), criado_em=agora,
                            atualizado_em=agora)
        estado.registrar("abertura", "aberto", "case aberto")

    inventario = inventariar(pasta)
    contagem = {t.value: sum(1 for a in inventario if a.tipo == t and a.status != "duplicado") for t in Tipo}
    estado.registrar("F1", "ingerido",
                     f"{len(inventario)} arquivo(s); " + ", ".join(f"{k}: {v}" for k, v in contagem.items() if v))

    dados = captar(caminho_longo(pasta), inventario, fim=fim, meses=meses, cnpj=cnpj)
    estado.empresa, estado.periodo_inicio, estado.periodo_fim = dados.empresa.nome, dados.periodo_inicio, dados.periodo_fim
    n_tx = sum(len(e.transacoes) for e in dados.extratos)
    estado.registrar("F2", "extraido",
                     f"{len(dados.extratos)} conta(s), {n_tx} lançamento(s), {len(dados.pgdas)} PGDAS, "
                     f"{len(dados.dres)} DRE, questionário {'sim' if dados.questionario else 'não'}, "
                     f"Planilha ND {'sim' if dados.planilha_nd else 'não'}")

    gci = None
    if dados.extratos or dados.pgdas:
        gci = calcular_gci(dados)
        estado.registrar("F3", "gci_definido", f"GCI {gci.indice:.1f}, nível {gci.nivel}")
        _gravar(saida, "gci.json", gci)

    pendencias = montar_pendencias(dados, gci, inventario)
    _gravar(saida, "inventario.json", inventario)
    _gravar(saida, "dados_brutos.json", dados)
    _gravar(saida, "pendencias.md", pendencias_md(estado, gci, pendencias))
    _gravar(saida, "state.json", estado)
    return ResultadoAbertura(estado=estado, dados=dados, gci=gci, pendencias=pendencias, inventario=inventario)


def ler_estado(pasta_empresa: str | Path) -> EstadoCase:
    arq = Path(pasta_empresa) / PASTA_SAIDA / "state.json"
    if not arq.exists():
        raise FileNotFoundError(f"Nenhum case aberto em {pasta_empresa}.")
    return EstadoCase.model_validate_json(arq.read_text(encoding="utf-8"))
