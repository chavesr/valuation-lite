"""Planilha ND de Captação — definição única das abas e colunas.

A mesma definição gera o modelo em Excel enviado ao empreendedor e (próximo passo) serve de
contrato para o leitor que importa a planilha preenchida sem custo de tokens.

Uso:
    python -m captacao.planilha_nd --fim 2026-10 --meses 36 --saida kit_captacao/Planilha_ND_Captacao.xlsx
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from pathlib import Path

from openpyxl import Workbook
from openpyxl.comments import Comment
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.worksheet.datavalidation import DataValidation

from captacao.util import meses_entre

VERSAO = "1.0"
LINHAS_PADRAO = 60

LISTAS = {
    "regime": ["Simples Nacional", "Lucro Presumido", "Lucro Real", "MEI"],
    "sim_nao": ["Sim", "Não"],
    "permanencia": ["Sim, sem prazo", "Sim, por um período de transição", "Não"],
    "uso_conta": ["Recebimentos de clientes", "Pagamentos", "Recebimentos e pagamentos", "Aplicações", "Pouco usada"],
    "tipo_divida": ["Empréstimo bancário", "Financiamento de máquina/veículo", "Parcelamento de impostos",
                    "Mútuo/empréstimo de sócio", "Fornecedor em atraso", "Imposto em atraso", "Outro"],
    "area": ["Produção / operação", "Comercial / vendas", "Administrativo / financeiro", "Gestão / diretoria",
             "Logística / entrega", "Outros"],
    "tipo_ativo": ["Estoque de matéria-prima", "Estoque de produto acabado", "Estoque para revenda",
                   "Máquinas e equipamentos", "Veículos", "Imóvel", "Marca / patente", "Outros"],
    "tipo_ajuste": ["Despesa pessoal paga pela empresa", "Despesa que não vai se repetir",
                    "Receita que não vai se repetir", "Familiar na folha sem função na operação",
                    "Aluguel pago a sócio ou parente", "Despesa de outra empresa do sócio", "Outro"],
    "periodicidade": ["Mensal", "Anual", "Única"],
}


@dataclass
class Coluna:
    titulo: str
    ajuda: str = ""
    lista: str | None = None
    largura: int = 18
    formato: str | None = None  # '#,##0.00' para R$, '0.0%' para percentual


@dataclass
class Aba:
    nome: str
    titulo: str
    instrucao: str
    colunas: list[Coluna] = field(default_factory=list)


R = "#,##0.00"
ABAS: list[Aba] = [
    Aba("1_Grupo", "Empresas do grupo",
        "Liste TODOS os CNPJs ligados ao negócio, inclusive os que só emitem nota, só registram funcionários "
        "ou só têm conta bancária.",
        [Coluna("CNPJ", largura=22), Coluna("Razão social", largura=40), Coluna("Nome fantasia", largura=24),
         Coluna("Regime tributário", lista="regime", largura=20),
         Coluna("O que esta empresa faz no grupo", "Ex.: fábrica, loja, prestação de serviço, emissão de notas",
                largura=40),
         Coluna("Ano de abertura", largura=14)]),
    Aba("2_Socios", "Sócios e remuneração",
        "Uma linha por sócio. Valores médios dos últimos 12 meses.",
        [Coluna("Nome", largura=30), Coluna("% de participação", formato="0.0%", largura=14),
         Coluna("Em quais CNPJs é sócio", largura=24), Coluna("Função no dia a dia", largura=28),
         Coluna("Horas por semana na empresa", largura=14),
         Coluna("Pró-labore mensal (R$)", formato=R),
         Coluna("Outras retiradas mensais (R$)", "Distribuição de lucro, PIX para conta pessoal, etc.",
                formato=R),
         Coluna("Permanece após a venda?", lista="permanencia", largura=30)]),
    Aba("3_Contas", "Contas bancárias",
        "Todas as contas de todos os CNPJs (e contas pessoais usadas para receber da empresa).",
        [Coluna("CNPJ ou CPF titular", largura=22), Coluna("Banco", largura=18), Coluna("Agência", largura=10),
         Coluna("Conta", largura=14), Coluna("Uso principal", lista="uso_conta", largura=28),
         Coluna("Extrato enviado?", lista="sim_nao", largura=14)]),
    Aba("4_Faturamento", "Faturamento mensal por empresa",
        "Na linha 1, troque 'CNPJ empresa N' pelo CNPJ de cada empresa (mesmos CNPJs da aba 1_Grupo). "
        "Informe o faturamento bruto de cada mês. Se não souber o valor exato, use o valor do sistema "
        "ou da maquininha e explique na coluna Observação.",
        []),  # colunas geradas com os meses
    Aba("5_Clientes", "Principais clientes",
        "Os 20 maiores clientes de cada um dos últimos 3 anos. Um cliente = uma linha por ano "
        "(some todas as compras/parcelas do mesmo cliente).",
        [Coluna("Ano", largura=8), Coluna("Cliente", largura=36), Coluna("CNPJ/CPF do cliente", largura=22),
         Coluna("Faturamento no ano (R$)", formato=R), Coluna("Tem contrato?", lista="sim_nao", largura=14),
         Coluna("Duração do contrato (meses)", largura=14), Coluna("Cliente desde (ano)", largura=14)]),
    Aba("6_Dividas", "Dívidas e parcelamentos",
        "Todas as dívidas de todos os CNPJs, inclusive parcelamentos de impostos, empréstimos de sócios "
        "e contas em atraso.",
        [Coluna("CNPJ devedor", largura=22), Coluna("Credor", largura=24),
         Coluna("Tipo", lista="tipo_divida", largura=30), Coluna("Valor contratado (R$)", formato=R),
         Coluna("Saldo devedor hoje (R$)", formato=R), Coluna("Parcela mensal (R$)", formato=R),
         Coluna("Taxa de juros (% ao mês)", formato="0.00%", largura=14),
         Coluna("Parcelas restantes", largura=12), Coluna("Garantias", largura=24)]),
    Aba("7_Pessoal", "Equipe (resumo, sem nomes)",
        "Uma linha por área em cada CNPJ. Não informe nomes nem salários individuais.",
        [Coluna("CNPJ", largura=22), Coluna("Área", lista="area", largura=26),
         Coluna("Funcionários CLT", largura=12), Coluna("Terceiros / PJ", largura=12),
         Coluna("Folha bruta mensal (R$)", formato=R),
         Coluna("Encargos e benefícios mensais (R$)", "INSS, FGTS, vale-transporte, alimentação, plano de saúde",
                formato=R)]),
    Aba("8_Ativos", "Estoques e bens relevantes",
        "Estoque e bens de maior valor. Use valor de mercado estimado (quanto venderia hoje).",
        [Coluna("Tipo", lista="tipo_ativo", largura=28), Coluna("Descrição", largura=36),
         Coluna("CNPJ ou pessoa proprietária", largura=24), Coluna("Valor de mercado estimado (R$)", formato=R),
         Coluna("Data de referência", largura=14), Coluna("Observação", largura=30)]),
    Aba("9_Ajustes", "Ajustes (receitas e despesas fora do normal)",
        "Gastos ou receitas que passam pela empresa mas não fazem parte da operação, ou que não vão se repetir. "
        "Isso AUMENTA o lucro ajustado e pode valorizar a empresa.",
        [Coluna("Descrição", largura=40), Coluna("Tipo", lista="tipo_ajuste", largura=36),
         Coluna("Valor (R$)", formato=R), Coluna("Periodicidade", lista="periodicidade", largura=14),
         Coluna("Observação", largura=30)]),
]

AZUL = PatternFill("solid", fgColor="1F3864")
CINZA = PatternFill("solid", fgColor="F2F2F2")
BORDA = Border(bottom=Side(style="thin", color="BFBFBF"))


def _colunas_faturamento(n_empresas: int = 4) -> list[Coluna]:
    cols = [Coluna("Mês (AAAA-MM)", largura=14)]
    cols += [Coluna(f"CNPJ empresa {i}", "Substitua pelo CNPJ", formato=R, largura=20)
             for i in range(1, n_empresas + 1)]
    cols += [Coluna("Total (R$)", formato=R, largura=18), Coluna("Observação", largura=40)]
    return cols


def _aba_instrucoes(wb: Workbook) -> None:
    ws = wb.active
    ws.title = "Instrucoes"
    linhas = [
        ("Planilha de Captação — Nova Direção", Font(bold=True, size=16, color="1F3864")),
        (f"Versão {VERSAO}", Font(italic=True, color="808080")),
        ("", None),
        ("Para que serve", Font(bold=True, size=12)),
        ("Reúne em um só lugar as informações que usamos para avaliar a empresa. Quanto mais completa, "
         "mais preciso o valuation e menor o desconto de risco aplicado.", None),
        ("", None),
        ("Como preencher", Font(bold=True, size=12)),
        ("1. Preencha as abas na ordem (1 a 9). Campos com lista: clique na célula e escolha a opção.", None),
        ("2. Valores em reais, sem o símbolo R$. Use estimativas quando não tiver o número exato e indique na "
         "observação.", None),
        ("3. Considere TODOS os CNPJs do grupo, mesmo os que parecem secundários.", None),
        ("4. Não altere os nomes das abas nem os títulos das colunas (exceto os CNPJs na aba 4).", None),
        ("5. Deixe em branco o que não se aplica. Não apague linhas de meses.", None),
        ("", None),
        ("Confidencialidade", Font(bold=True, size=12)),
        ("As informações são usadas exclusivamente para a avaliação, sob o acordo de confidencialidade "
         "assinado. Não envie documentos pessoais nem dados individuais de funcionários.", None),
    ]
    for i, (texto, fonte) in enumerate(linhas, start=1):
        c = ws.cell(row=i, column=1, value=texto)
        c.alignment = Alignment(wrap_text=True, vertical="top")
        if fonte:
            c.font = fonte
    ws.column_dimensions["A"].width = 110
    ws.sheet_view.showGridLines = False


def gerar_modelo(caminho: str | Path, fim: str, meses: int = 36) -> Path:
    caminho = Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    ano, mes = map(int, fim.split("-"))
    total = ano * 12 + mes - 1 - (meses - 1)
    inicio = f"{total // 12:04d}-{total % 12 + 1:02d}"
    lista_meses = meses_entre(inicio, fim)

    wb = Workbook()
    _aba_instrucoes(wb)
    listas_ws = wb.create_sheet("_listas")
    for j, (nome, valores) in enumerate(LISTAS.items(), start=1):
        listas_ws.cell(row=1, column=j, value=nome)
        for i, v in enumerate(valores, start=2):
            listas_ws.cell(row=i, column=j, value=v)
    listas_ws.sheet_state = "hidden"
    coluna_lista = {nome: j for j, nome in enumerate(LISTAS, start=1)}

    for aba in ABAS:
        ws = wb.create_sheet(aba.nome)
        colunas = aba.colunas or _colunas_faturamento()
        ws.cell(row=1, column=1, value=aba.titulo).font = Font(bold=True, size=13, color="1F3864")
        instr = ws.cell(row=2, column=1, value=aba.instrucao)
        instr.font = Font(italic=True, color="595959")
        instr.alignment = Alignment(wrap_text=True, vertical="top")
        ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=max(len(colunas), 4))
        ws.row_dimensions[2].height = 45

        cab = 4  # linha de cabeçalho
        for j, col in enumerate(colunas, start=1):
            c = ws.cell(row=cab, column=j, value=col.titulo)
            c.font, c.fill = Font(bold=True, color="FFFFFF"), AZUL
            c.alignment = Alignment(wrap_text=True, vertical="center", horizontal="center")
            if col.ajuda:
                c.comment = Comment(col.ajuda, "Nova Direção")
            ws.column_dimensions[c.column_letter].width = col.largura
        ws.row_dimensions[cab].height = 36
        ws.freeze_panes = ws.cell(row=cab + 1, column=1)

        n_linhas = len(lista_meses) if aba.nome == "4_Faturamento" else LINHAS_PADRAO
        for j, col in enumerate(colunas, start=1):
            letra = ws.cell(row=cab, column=j).column_letter
            faixa = f"{letra}{cab + 1}:{letra}{cab + n_linhas}"
            if col.lista:
                k = coluna_lista[col.lista]
                ref_col = listas_ws.cell(row=1, column=k).column_letter
                dv = DataValidation(type="list", allow_blank=True,
                                    formula1=f"=_listas!${ref_col}$2:${ref_col}${len(LISTAS[col.lista]) + 1}")
                ws.add_data_validation(dv)
                dv.add(faixa)
            for i in range(cab + 1, cab + n_linhas + 1):
                cel = ws.cell(row=i, column=j)
                cel.border = BORDA
                if col.formato:
                    cel.number_format = col.formato

        if aba.nome == "4_Faturamento":
            n_emp = len(colunas) - 3
            ultima_emp = ws.cell(row=cab, column=1 + n_emp).column_letter
            col_total = 2 + n_emp
            for i, m in enumerate(lista_meses, start=cab + 1):
                ws.cell(row=i, column=1, value=m).fill = CINZA
                ws.cell(row=i, column=col_total, value=f"=SUM(B{i}:{ultima_emp}{i})").fill = CINZA

    wb.save(caminho)
    return caminho


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Gera o modelo da Planilha ND de Captação")
    ap.add_argument("--fim", required=True, help="último mês do período, AAAA-MM")
    ap.add_argument("--meses", type=int, default=36)
    ap.add_argument("--saida", default="kit_captacao/Planilha_ND_Captacao.xlsx")
    args = ap.parse_args()
    print(gerar_modelo(args.saida, args.fim, args.meses))
