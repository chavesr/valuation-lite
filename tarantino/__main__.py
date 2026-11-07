"""Linha de comando do tarantino_agent.

    python -m tarantino abrir "<pasta da empresa>" [--fim 2026-10] [--meses 24] [--cnpj ...]
    python -m tarantino qualitativo "<pasta>" [--modo claude-code|manual] [--importar]
    python -m tarantino calibrar "<pasta de trabalho>" [--so R1 R2]
    python -m tarantino revisar "<pasta>" [--modo claude-code|manual] [--importar] [--forcar]
    python -m tarantino finalidade "<pasta>" [--tipo entrada_socio] [--percentual 0.3] [--aporte ...] [--pedido ...]
    python -m tarantino mercado [--forcar]
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

    r = avaliar_case(args.pasta, selic=args.selic, atualizar_mercado=args.atualizar_mercado)
    b = r.base
    print(f"Score {r.risco.score:.0f} · taxa {r.risco.taxa_desconto:.1%} · horizonte {r.risco.horizonte_anos} anos · "
          f"fluxo base {_brl(r.fluxo_base)}/ano")
    print("  " + " · ".join(f"{c.nome} {_brl(c.valor_patrimonio)}" for c in r.cenarios))
    print(f"  preço recomendado (margem de segurança): {_brl(r.preco_recomendado)}")
    print(f"Detalhes: {args.pasta}/{PASTA_SAIDA}/valuation.md · notas do Score: score_notas.json")
    for linha in r.leitura_finalidade[1:]:
        print(f"  {linha.replace('**', '')}")
    if r.aviso_mercado:
        print(f"\n⚠ {r.aviso_mercado}")


def cmd_qualitativo(args: argparse.Namespace) -> None:
    from julgamento.executor import ErroJulgamento
    from tarantino.qualitativo import importar_f5, rodar_f5

    try:
        r = importar_f5(args.pasta) if args.importar else rodar_f5(args.pasta, modo=args.modo, modelo=args.modelo)
    except ErroJulgamento as erro:
        sys.exit(f"F5: {erro}")
    if not hasattr(r, "notas_score"):
        print(f"Pacote da F5 gravado em: {r}")
        print("Peça ao Claude Code (ou cole no claude.ai): 'leia esse arquivo e grave a resposta em "
              f"{PASTA_SAIDA}/f5_saida.json'. Depois rode: python -m tarantino qualitativo \"{args.pasta}\" --importar")
        return
    print(f"F5 · fosso {r.fosso.forca} · {len(r.riscos)} risco(s) · {len(r.perguntas_entrevista)} pergunta(s) para a entrevista")
    for n in r.notas_score:
        print(f"  {n.dimensao:28} nota {n.nota} ({n.confianca})")
    if r.funcoes_do_dono:
        eixos = ", ".join(f.eixo for f in r.funcoes_do_dono)
        print(f"Funções do dono sem substituto ({eixos}): custo proposto em {PASTA_SAIDA}/ajustes_decisoes.json — "
              "aprove/rejeite e rode 'normalizar' de novo antes de 'avaliar'.")
    print(f"Detalhes: {args.pasta}/{PASTA_SAIDA}/qualitativo.md · rode 'avaliar' para levar as notas ao Score")


def cmd_calibrar(args: argparse.Namespace) -> None:
    import json
    from pathlib import Path

    from julgamento.calibracao import MAPA, rodar_calibracao

    mapa = json.loads(Path(args.mapa or MAPA).read_text(encoding="utf-8"))
    r = rodar_calibracao(mapa, Path(args.destino), so=args.so)
    for l in r["linhas"]:
        marca = "=" if l["diferenca"] == 0 else ("~" if abs(l["diferenca"]) == 1 else "X")
        print(f"  {marca} {l['caso']} {l['dimensao']:28} ND {l['gabarito']} · agente {l['agente']}")
    for caso, erro in r["erros"].items():
        print(f"  ! {caso}: {erro}")
    if r["notas"]:
        print(f"Concordância: {r['exatas']}/{r['notas']} exatas · {r['ate_1_ponto']}/{r['notas']} até 1 ponto · "
              f"erro médio {r['erro_medio']} · viés {r['vies_medio']:+} (positivo = agente mais otimista)")


def cmd_mercado(args: argparse.Namespace) -> None:
    from market_data.painel import PASTA, atualizar_painel
    from tarantino.mercado import selic_por_horizonte

    p = atualizar_painel(forcar=args.forcar)
    print(f"Painel de mercado ({PASTA}) · conferido em {p['coletado_em']} · "
          f"atualizados agora: {', '.join(p['atualizados']) or 'nenhum (nada venceu)'}")
    for nome, s in p["sgs"].items():
        print(f"  {s.get('descricao', nome):70} {s['valor']:>8} {s.get('unidade', '')} ({s['data']})")
    for nome, f in p["focus"].items():
        anos = ' · '.join(f"{a}: {v:g}" for a, v in sorted(f['medianas'].items()))
        print(f"  Focus {nome:8} ({f['data']}) {anos}")
    valores, _ = selic_por_horizonte(p)
    print("  Selic de referência: " + " · ".join(f"{h} anos {v:.2%}" for h, v in valores.items()))
    for a in p["avisos"]:
        print(f"  ! {a}")


def cmd_revisar(args: argparse.Namespace) -> None:
    from julgamento.executor import ErroJulgamento
    from tarantino.revisao import importar_f7, pendentes_graves, rodar_f7

    try:
        if args.importar:
            r, reaproveitada = importar_f7(args.pasta), False
        else:
            r, reaproveitada = rodar_f7(args.pasta, modo=args.modo, modelo=args.modelo, forcar=args.forcar)
    except ErroJulgamento as erro:
        sys.exit(f"F7: {erro}")
    if not hasattr(r, "parecer"):
        print(f"Pacote da F7 gravado em: {r}")
        print(f"Peça ao Claude Code: 'leia esse arquivo e grave a resposta em {PASTA_SAIDA}/f7_saida.json'. "
              f"Depois rode: python -m tarantino revisar \"{args.pasta}\" --importar")
        return
    if reaproveitada:
        print("Nada mudou desde a última revisão: resposta reaproveitada (sem nova chamada ao agente).")
    rot = {"aprovado": "APROVADO", "aprovado_com_ressalvas": "APROVADO COM RESSALVAS", "refazer": "REFAZER"}
    print(f"F7 · parecer {rot[r.parecer]} · {len(r.alertas)} alerta(s)")
    for a in r.alertas:
        print(f"  [{a.severidade:5}] {a.fase:12} {a.id}")
    from pathlib import Path

    graves = pendentes_graves(Path(args.pasta) / PASTA_SAIDA)
    if graves:
        print(f"⚠ {len(graves)} alerta(s) grave(s) sem decisão: decida em {PASTA_SAIDA}/revisao_decisoes.json")
    print(f"Detalhes: {args.pasta}/{PASTA_SAIDA}/revisao.md")


def cmd_finalidade(args: argparse.Namespace) -> None:
    from pathlib import Path

    from engine.finalidade import Finalidade, gravar_finalidade, ler_finalidade

    saida = Path(args.pasta) / PASTA_SAIDA
    if not saida.exists():
        sys.exit("Rode antes: python -m tarantino abrir")
    atual = ler_finalidade(saida).model_dump()
    novos = {k: v for k, v in {"tipo": args.tipo, "percentual": args.percentual, "aporte": args.aporte,
                               "pedido_vendedor": args.pedido}.items() if v is not None}
    f = Finalidade.model_validate({**atual, **novos})
    gravar_finalidade(saida, f)
    print(f"Finalidade: {f.descricao}" + (f" · pedido do vendedor R$ {f.pedido_vendedor:,.0f}".replace(",", ".")
                                         if f.pedido_vendedor else "") + " · rode 'avaliar' para ver a leitura")


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
    v.add_argument("--selic", type=float, help="Selic de referência a.a. em fração (padrão: média Focus no horizonte)")
    v.add_argument("--atualizar-mercado", action="store_true",
                   help="coleta nova fotografia do mercado (padrão: usa _valuation/mercado.json do case)")
    v.set_defaults(func=cmd_avaliar)
    q = sub.add_parser("qualitativo", help="F5: análise qualitativa pelo agente (rodar depois de 'normalizar')")
    q.add_argument("pasta")
    q.add_argument("--modo", choices=["claude-code", "manual", "api"], default="claude-code")
    q.add_argument("--modelo", help="modelo do Claude Code (padrão: o da conta)")
    q.add_argument("--importar", action="store_true", help="só valida e importa _valuation/f5_saida.json")
    q.set_defaults(func=cmd_qualitativo)
    c = sub.add_parser("calibrar", help="mede a concordância da F5 com o gabarito da ND (casos de referência)")
    c.add_argument("destino", help="pasta de trabalho para as cópias (fora do Drive)")
    c.add_argument("--mapa", help="JSON caso → pasta (padrão: cases/calibracao.json)")
    c.add_argument("--so", nargs="*", help="rodar só estes casos (ex.: R1 R2)")
    c.set_defaults(func=cmd_calibrar)
    rv = sub.add_parser("revisar", help="F7: revisão cética pelo agente (rodar depois de 'avaliar')")
    rv.add_argument("pasta")
    rv.add_argument("--modo", choices=["claude-code", "manual", "api"], default="claude-code")
    rv.add_argument("--modelo", help="modelo do Claude Code (padrão: o da conta)")
    rv.add_argument("--importar", action="store_true", help="só valida e importa _valuation/f7_saida.json")
    rv.add_argument("--forcar", action="store_true", help="roda o agente mesmo se nada mudou")
    rv.set_defaults(func=cmd_revisar)
    f = sub.add_parser("finalidade", help="D7: venda total/parcial ou entrada de sócio, % das cotas, aporte, pedido")
    f.add_argument("pasta")
    f.add_argument("--tipo", choices=["venda_total", "venda_parcial", "entrada_socio"])
    f.add_argument("--percentual", type=float, help="fração das cotas (0.3 = 30%%)")
    f.add_argument("--aporte", type=float, help="dinheiro novo que entra na empresa, em R$")
    f.add_argument("--pedido", type=float, help="quanto o dono pede pela participação, em R$")
    f.set_defaults(func=cmd_finalidade)
    m = sub.add_parser("mercado", help="mostra o painel de mercado (BCB/Focus) e atualiza o que venceu")
    m.add_argument("--forcar", action="store_true", help="busca tudo de novo, mesmo o que não venceu")
    m.set_defaults(func=cmd_mercado)
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
