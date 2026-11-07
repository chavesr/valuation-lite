"""Linha de comando do tarantino_agent.

    python -m tarantino abrir "<pasta da empresa>" [--fim 2026-10] [--meses 24] [--cnpj ...]
    python -m tarantino status "<pasta da empresa>"
"""

from __future__ import annotations

import argparse
import sys

from tarantino.case import abrir_case, ler_estado
from tarantino.inventario import PASTA_SAIDA


def _brl(v: float) -> str:
    return f"R$ {v:,.0f}".replace(",", ".")


def cmd_abrir(args: argparse.Namespace) -> None:
    r = abrir_case(args.pasta, fim=args.fim, meses=args.meses, cnpj=args.cnpj)
    e, d, g, p = r.estado, r.dados, r.gci, r.pendencias
    print(f"Case {e.id} · {e.empresa} · {len(d.empresa.cnpjs)} CNPJ(s) · período {e.periodo_inicio} a {e.periodo_fim}")
    for etapa in e.historico[-3:]:
        print(f"  {etapa.fase:3} {etapa.estado:13} {etapa.resumo}")
    if g:
        print(f"\nGCI {g.indice:.1f} · nível {g.nivel} · caixa 12m {_brl(g.receita_caixa_12m)} · "
              f"fiscal 12m {_brl(g.receita_fiscal_12m)} · não declarada 12m {_brl(g.receita_nao_declarada_12m)}")
    print(f"\nPedir ao cliente: {len(p.pedir_ao_cliente)} · não lidos: {len(p.arquivos_nao_lidos)} · "
          f"entrevista: {len(p.para_entrevista)} · alertas: {len(p.para_o_analista)}")
    print(f"Saídas em: {args.pasta}/{PASTA_SAIDA}/ (pendencias.md, dados_brutos.json, gci.json, inventario.json)")


def cmd_normalizar(args: argparse.Namespace) -> None:
    from tarantino.normalizar import normalizar_case

    dres = normalizar_case(args.pasta)
    for d in dres:
        m = f"{d.margem_ebitda:.1%}" if d.margem_ebitda is not None else "—"
        print(f"{d.periodo:24} receita {_brl(d.valor('Receita bruta')):>16} ({d.receita_fonte}) · EBITDA "
              f"{_brl(d.ebitda):>14} ({m}) · lucro {_brl(d.lucro_economico)} · confiança {d.confianca}")
    print(f"Detalhes: {args.pasta}/{PASTA_SAIDA}/normalizacao.md · decisões do analista: ajustes_decisoes.json")


def cmd_avaliar(args: argparse.Namespace) -> None:
    from tarantino.avaliar import avaliar_case

    r = avaliar_case(args.pasta, selic=args.selic)
    b = r.base
    print(f"Score {r.risco.score:.0f} · taxa {r.risco.taxa_desconto:.1%} · horizonte {r.risco.horizonte_anos} anos · "
          f"fluxo base {_brl(r.fluxo_base)}/ano")
    print("  " + " · ".join(f"{c.nome} {_brl(c.valor_patrimonio)}" for c in r.cenarios))
    print(f"  preço recomendado (margem de segurança): {_brl(r.preco_recomendado)}")
    print(f"Detalhes: {args.pasta}/{PASTA_SAIDA}/valuation.md · notas do Score: score_notas.json")


def cmd_status(args: argparse.Namespace) -> None:
    e = ler_estado(args.pasta)
    print(f"Case {e.id} · {e.empresa} · estado: {e.estado} · atualizado em {e.atualizado_em}")
    for etapa in e.historico:
        print(f"  {etapa.quando}  {etapa.fase:8} {etapa.estado:13} {etapa.resumo}")


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="tarantino", description="Orquestrador dos cases de valuation")
    sub = ap.add_subparsers(dest="comando", required=True)
    a = sub.add_parser("abrir", help="abre/reabre o case e roda inventário, captação e GCI")
    a.add_argument("pasta")
    a.add_argument("--fim", help="último mês do período (AAAA-MM); padrão: último mês com dados")
    a.add_argument("--meses", type=int, default=24)
    a.add_argument("--cnpj", help="CNPJ para escolher a resposta do questionário")
    a.set_defaults(func=cmd_abrir)
    n = sub.add_parser("normalizar", help="F4: monta a DRE econômica (rodar depois de 'abrir')")
    n.add_argument("pasta")
    n.set_defaults(func=cmd_normalizar)
    v = sub.add_parser("avaliar", help="F6: Score de Risco + valuation (rodar depois de 'normalizar')")
    v.add_argument("pasta")
    v.add_argument("--selic", type=float, help="Selic a.a. em fração (padrão: Banco Central)")
    v.set_defaults(func=cmd_avaliar)
    s = sub.add_parser("status", help="mostra o estado e o histórico do case")
    s.add_argument("pasta")
    s.set_defaults(func=cmd_status)
    args = ap.parse_args(argv)
    try:
        args.func(args)
    except FileNotFoundError as erro:
        sys.exit(str(erro))


if __name__ == "__main__":
    main()
