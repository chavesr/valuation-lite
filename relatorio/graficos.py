"""Gráficos SVG estáticos do relatório (impressão). Paleta validada contra o papel #FCFAF7:
cobre #C95D21 (série principal) e azul #3B6FB6 (segunda série). Textos sempre em tons de tinta, nunca na cor da série.
Barras finas (≤ 24 px), ponta arredondada de 4 px, base reta; grade fina e recessiva; legenda quando há 2 séries.
"""

from __future__ import annotations

from html import escape

# padrão do relatório da ND (07/11/2026): laranja #FF9900 destaca a série principal, cinza dá o contexto;
# o laranja tem pouco contraste sobre o branco, então todo valor leva rótulo direto
PAPEL, TINTA, TINTA_SUAVE, MUTED, LINHA = "#FFFFFF", "#1A1A1A", "#333333", "#6B6B6B", "#E6E6E6"
LARANJA, CINZA = "#FF9900", "#BFBFBF"
COBRE, AZUL, NEUTRO = LARANJA, CINZA, "#6B6B6B"
FONTE = "Helvetica,Arial,sans-serif"


def brl_compacto(v: float) -> str:
    """R$ 1,37 mi · R$ 703 mil · R$ 950 (pt-BR)."""
    s = "−" if v < 0 else ""
    a = abs(v)
    if a >= 1_000_000:
        txt = f"{a / 1_000_000:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") + " mi"
    elif a >= 1_000:
        txt = f"{a / 1_000:,.0f}".replace(",", ".") + " mil"
    else:
        txt = f"{a:,.0f}".replace(",", ".")
    return f"{s}R$ {txt}"


def faixa_compacta(a: float, b: float) -> str:
    """'0,93 – 1,82 mi' (mesma unidade) ou 'R$ 650 mil – 1,20 mi'."""
    if abs(a) >= 1_000_000 or abs(b) >= 1_000_000 and abs(a) >= 100_000:
        f = lambda v: f"{v / 1_000_000:.2f}".replace(".", ",")  # noqa: E731
        return f"R$ {f(a)} – {f(b)} mi"
    return f"{brl_compacto(a)} – {brl_compacto(b).replace('R$ ', '')}"


def _barra_v(x: float, y0: float, y1: float, w: float, cor: str) -> str:
    """Coluna da base y0 até y1, ponta arredondada (4 px) só na extremidade dos dados."""
    r = min(4.0, abs(y1 - y0) / 2, w / 2)
    if y1 < y0:  # positiva (cresce para cima)
        topo, base = y1, y0
        d = (f"M{x},{base} L{x},{topo + r} Q{x},{topo} {x + r},{topo} L{x + w - r},{topo} "
             f"Q{x + w},{topo} {x + w},{topo + r} L{x + w},{base} Z")
    else:  # negativa (cresce para baixo)
        topo, base = y0, y1
        d = (f"M{x},{topo} L{x},{base - r} Q{x},{base} {x + r},{base} L{x + w - r},{base} "
             f"Q{x + w},{base} {x + w},{base - r} L{x + w},{topo} Z")
    return f'<path d="{d}" fill="{cor}"/>'


def _barra_h(x0: float, x1: float, y: float, h: float, cor: str) -> str:
    r = min(4.0, abs(x1 - x0) / 2, h / 2)
    if x1 >= x0:
        d = (f"M{x0},{y} L{x1 - r},{y} Q{x1},{y} {x1},{y + r} L{x1},{y + h - r} Q{x1},{y + h} {x1 - r},{y + h} "
             f"L{x0},{y + h} Z")
    else:
        d = (f"M{x0},{y} L{x1 + r},{y} Q{x1},{y} {x1},{y + r} L{x1},{y + h - r} Q{x1},{y + h} {x1 + r},{y + h} "
             f"L{x0},{y + h} Z")
    return f'<path d="{d}" fill="{cor}"/>'


def _svg(largura: int, altura: int, corpo: str, titulo: str) -> str:
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {largura} {altura}" width="100%" role="img" '
            f'aria-label="{escape(titulo)}" style="font-family:{FONTE}">{corpo}</svg>')


def _ticks(minimo: float, maximo: float, n: int = 4) -> list[float]:
    import math

    span = (maximo - minimo) or 1.0
    bruto = span / n
    mag = 10 ** math.floor(math.log10(bruto))
    passo = min((m * mag for m in (1, 2, 2.5, 5, 10) if m * mag >= bruto), default=bruto)
    ini = math.floor(minimo / passo) * passo
    return [ini + i * passo for i in range(int((maximo - ini) / passo) + 2) if ini + i * passo <= maximo + passo * 0.01]


def receita_ebitda(periodos: list[tuple[str, float, float]]) -> str:
    """Colunas agrupadas por período: receita (azul) e EBITDA econômico (cobre). Mesma unidade, um eixo."""
    L, A, esq, dir_, topo, base = 640, 250, 64, 16, 34, 214
    vals = [v for _, r, e in periodos for v in (r, e)]
    vmin, vmax = min(0.0, *vals), max(0.0, *vals)
    ticks = _ticks(vmin, vmax)
    vmin, vmax = min(vmin, ticks[0]), max(vmax, ticks[-1])
    y = lambda v: topo + (vmax - v) / (vmax - vmin) * (base - topo)  # noqa: E731
    c = []
    for t in ticks:
        c.append(f'<line x1="{esq}" x2="{L - dir_}" y1="{y(t):.1f}" y2="{y(t):.1f}" stroke="{LINHA}" stroke-width="1"/>')
        c.append(f'<text x="{esq - 8}" y="{y(t) + 4:.1f}" font-size="11" fill="{MUTED}" text-anchor="end">'
                 f'{escape(brl_compacto(t).replace("R$ ", ""))}</text>')
    c.append(f'<line x1="{esq}" x2="{L - dir_}" y1="{y(0):.1f}" y2="{y(0):.1f}" stroke="{MUTED}" stroke-width="1"/>')
    banda = (L - esq - dir_) / max(len(periodos), 1)
    w = min(24.0, banda / 4)
    for i, (rot, rec, eb) in enumerate(periodos):
        cx = esq + banda * (i + 0.5)
        for j, (v, cor) in enumerate(((rec, AZUL), (eb, COBRE))):
            x = cx - w - 1 + j * (w + 2)  # 2 px de papel entre as colunas
            c.append(_barra_v(x, y(0), y(v), w, cor))
            ty = y(v) - 6 if v >= 0 else y(v) + 14
            c.append(f'<text x="{x + w / 2:.1f}" y="{ty:.1f}" font-size="10.5" fill="{TINTA_SUAVE}" text-anchor="middle">'
                     f'{escape(brl_compacto(v).replace("R$ ", ""))}</text>')
        c.append(f'<text x="{cx:.1f}" y="{A - 14}" font-size="11.5" fill="{TINTA}" text-anchor="middle">{escape(rot)}</text>')
    c.append(f'<rect x="{esq}" y="6" width="10" height="10" rx="2" fill="{AZUL}"/>'
             f'<text x="{esq + 15}" y="15" font-size="11.5" fill="{TINTA}">Receita bruta</text>'
             f'<rect x="{esq + 120}" y="6" width="10" height="10" rx="2" fill="{COBRE}"/>'
             f'<text x="{esq + 135}" y="15" font-size="11.5" fill="{TINTA}">EBITDA econômico</text>')
    return _svg(L, A, "".join(c), "Receita bruta e EBITDA econômico por período")


def faixa_valor(faixa: tuple[float, float], marcadores: list[tuple[str, float, bool]]) -> str:
    """Régua horizontal em R$: faixa conservador–otimista (faixa clara) e marcadores; destaque = preço recomendado."""
    L, esq, dir_ = 640, 24, 24
    vals = [faixa[0], faixa[1], *[v for _, v, _ in marcadores]]
    vmin, vmax = min(0.0, *vals), max(vals) * 1.04
    x = lambda v: esq + (v - vmin) / ((vmax - vmin) or 1) * (L - esq - dir_)  # noqa: E731
    linhas = len(marcadores)
    A = 80 + linhas * 22
    eixo_y = 44
    c = [f'<line x1="{esq}" x2="{L - dir_}" y1="{eixo_y}" y2="{eixo_y}" stroke="{LINHA}" stroke-width="1"/>',
         f'<rect x="{x(faixa[0]):.1f}" y="{eixo_y - 9}" width="{max(x(faixa[1]) - x(faixa[0]), 2):.1f}" height="18" '
         f'rx="3" fill="#EDEDED"/>',
         f'<text x="{x(faixa[0]):.1f}" y="{eixo_y - 16}" font-size="10.5" fill="{MUTED}">conservador</text>',
         f'<text x="{x(faixa[1]):.1f}" y="{eixo_y - 16}" font-size="10.5" fill="{MUTED}" text-anchor="end">otimista</text>']
    perto = [x(v) for _, v, _ in marcadores]
    for t in _ticks(vmin, vmax, 5):
        if vmin <= t <= vmax and all(abs(x(t) - px) > 22 for px in perto):
            c.append(f'<text x="{x(t):.1f}" y="{eixo_y + 20}" font-size="10" fill="{MUTED}" text-anchor="middle">'
                     f'{escape(brl_compacto(t).replace("R$ ", ""))}</text>')
    for i, (rot, v, destaque) in enumerate(sorted(marcadores, key=lambda m: m[1])):
        cor = TINTA if destaque else MUTED
        yy = eixo_y + 50 + i * 22
        c.append(f'<line x1="{x(v):.1f}" x2="{x(v):.1f}" y1="{eixo_y + 26}" y2="{yy - 4}" stroke="{cor}" '
                 f'stroke-width="1"/>')
        c.append(f'<circle cx="{x(v):.1f}" cy="{eixo_y}" r="{5 if destaque else 4}" fill="{cor}" stroke="{PAPEL}" '
                 f'stroke-width="2"/>')
        ancora = "end" if x(v) > L * 0.6 else "start"
        dx = -6 if ancora == "end" else 6
        peso = "600" if destaque else "400"
        c.append(f'<text x="{x(v) + dx:.1f}" y="{yy}" font-size="11.5" font-weight="{peso}" fill="{TINTA}" '
                 f'text-anchor="{ancora}">{escape(rot)} · {escape(brl_compacto(v))}</text>')
    return _svg(L, A, "".join(c), "Faixa de valor e referências")


def cascata(ponte: list[tuple[str, float]]) -> str:
    """Ponte horizontal: totais em tom neutro, deduções em cobre; valor ao fim de cada barra."""
    itens = [(n, v) for n, v in ponte if not n.startswith("(retido")]
    L, esq, dir_, h, passo = 640, 230, 110, 18, 30
    A = 16 + passo * len(itens)
    acum, barras = 0.0, []
    for i, (n, v) in enumerate(itens):
        total = i == 0 or n.startswith("=")
        ini, fim = (0.0, v) if total else (acum, acum + v)
        acum = v if total else acum + v
        barras.append((n, ini, fim, total, v))
    vals = [b for _, a, f, _, _ in barras for b in (a, f)]
    vmin, vmax = min(0.0, *vals), max(0.0, *vals)
    x = lambda v: esq + (v - vmin) / ((vmax - vmin) or 1) * (L - esq - dir_)  # noqa: E731
    c = [f'<line x1="{x(0):.1f}" x2="{x(0):.1f}" y1="6" y2="{A - 6}" stroke="{MUTED}" stroke-width="1"/>']
    for i, (n, ini, fim, total, v) in enumerate(barras):
        yy = 10 + i * passo
        c.append(f'<text x="{esq - 10}" y="{yy + 13}" font-size="11.5" fill="{TINTA}" text-anchor="end" '
                 f'font-weight="{600 if total else 400}">{escape(n.replace("(−) ", ""))}</text>')
        x0, x1 = (x(ini), x(fim)) if fim >= ini else (x(ini), x(fim))
        c.append(_barra_h(x0, x1, yy, h, NEUTRO if total else COBRE))
        c.append(f'<text x="{max(x0, x1) + 6:.1f}" y="{yy + 13}" font-size="11" fill="{TINTA_SUAVE}">'
                 f'{escape(brl_compacto(v))}</text>')
    return _svg(L, A, "".join(c), "Ponte do valor de referência ao que sobra para o dono")


def notas_score(notas: list[tuple[str, int, bool]]) -> str:
    """Notas 1–5 (5 = melhor) por dimensão, barras horizontais finas em cobre; pendente marcado no rótulo."""
    L, esq, dir_, h, passo = 640, 250, 40, 14, 24
    A = 30 + passo * len(notas)
    x = lambda v: esq + v / 5 * (L - esq - dir_)  # noqa: E731
    c = []
    for t in range(0, 6):
        c.append(f'<line x1="{x(t):.1f}" x2="{x(t):.1f}" y1="4" y2="{A - 22}" stroke="{LINHA}" stroke-width="1"/>'
                 f'<text x="{x(t):.1f}" y="{A - 8}" font-size="10" fill="{MUTED}" text-anchor="middle">{t}</text>')
    for i, (nome, nota, pendente) in enumerate(notas):
        yy = 8 + i * passo
        rot = nome + (" (proposta)" if pendente else "")
        c.append(f'<text x="{esq - 10}" y="{yy + 11}" font-size="11.5" fill="{TINTA}" text-anchor="end">{escape(rot)}</text>')
        c.append(_barra_h(x(0), x(nota), yy, h, COBRE))
        c.append(f'<text x="{x(nota) + 6:.1f}" y="{yy + 11}" font-size="11" fill="{TINTA_SUAVE}">{nota}</text>')
    return _svg(L, A, "".join(c), "Notas do Score de Risco por dimensão (5 = melhor)")


# --------------------------------------------------------------------------- capítulo 1 (padrão ND)


def colunas_mini(periodos: list[tuple[str, float, float]]) -> str:
    """Receita (cinza) e EBITDA econômico (laranja) por período, com margem no topo. Um eixo, rótulos diretos."""
    L, A, esq, dir_, topo, base = 330, 128, 6, 6, 26, 102
    vals = [v for _, r, e in periodos for v in (r, e)]
    vmin, vmax = min(0.0, *vals), max(0.0, *vals) or 1.0
    y = lambda v: topo + (vmax - v) / ((vmax - vmin) or 1) * (base - topo)  # noqa: E731
    banda = (L - esq - dir_) / max(len(periodos), 1)
    w = min(22.0, banda / 3)
    c = [f'<line x1="{esq}" x2="{L - dir_}" y1="{y(0):.1f}" y2="{y(0):.1f}" stroke="{MUTED}" stroke-width="1"/>']
    for i, (rot, rec, eb) in enumerate(periodos):
        cx = esq + banda * (i + 0.5)
        for j, (v, cor) in enumerate(((rec, CINZA), (eb, LARANJA))):
            x = cx - w - 1 + j * (w + 2)
            c.append(_barra_v(x, y(0), y(v), w, cor))
            ty = y(v) - 4 if v >= 0 else y(v) + 10
            c.append(f'<text x="{x + w / 2:.1f}" y="{ty:.1f}" font-size="8" fill="{TINTA_SUAVE}" text-anchor="middle">'
                     f'{escape(brl_compacto(v).replace("R$ ", "").replace(" mi", "M").replace(" mil", "k"))}</text>')
        if rec:
            margem = f"{eb / rec * 100:.1f}%".replace(".", ",")
            c.append(f'<text x="{cx:.1f}" y="{topo - 16}" font-size="8" fill="{MUTED}" text-anchor="middle">'
                     f'{margem}</text>')
        c.append(f'<text x="{cx:.1f}" y="{A - 14}" font-size="8.5" fill="{TINTA}" text-anchor="middle">{escape(rot)}</text>')
    c.append(f'<rect x="{esq}" y="{A - 7}" width="8" height="6" fill="{CINZA}"/><text x="{esq + 11}" y="{A - 1}" font-size="7.5" '
             f'fill="{MUTED}">Receita bruta</text><rect x="{esq + 74}" y="{A - 7}" width="8" height="6" fill="{LARANJA}"/>'
             f'<text x="{esq + 85}" y="{A - 1}" font-size="7.5" fill="{MUTED}">EBITDA econômico (margem no topo)</text>')
    return _svg(L, A, "".join(c), "Receita bruta e EBITDA econômico por período")


def radar(notas: list[tuple[str, int]]) -> str:
    """Radar das notas 1–5 (5 = mais sólido) por dimensão, com o valor em cada vértice."""
    import math

    L, A, cx, cy, R = 330, 158, 165, 82, 56
    n = len(notas)
    ang = lambda i: -math.pi / 2 + 2 * math.pi * i / n  # noqa: E731
    pt = lambda i, v: (cx + R * v / 5 * math.cos(ang(i)), cy + R * v / 5 * math.sin(ang(i)))  # noqa: E731
    c = []
    for nivel in range(1, 6):
        pts = " ".join(f"{pt(i, nivel)[0]:.1f},{pt(i, nivel)[1]:.1f}" for i in range(n))
        c.append(f'<polygon points="{pts}" fill="none" stroke="{LINHA}" stroke-width="1"/>')
    for i, (nome, v) in enumerate(notas):
        x2, y2 = pt(i, 5)
        c.append(f'<line x1="{cx}" y1="{cy}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="{LINHA}" stroke-width="1"/>')
        lx, ly = pt(i, 6.3)
        ancora = "middle" if abs(lx - cx) < 12 else ("start" if lx > cx else "end")
        c.append(f'<text x="{lx:.1f}" y="{ly + 3:.1f}" font-size="7.5" fill="{TINTA_SUAVE}" text-anchor="{ancora}">'
                 f'{escape(nome)}</text>')
    pts = " ".join(f"{pt(i, v)[0]:.1f},{pt(i, v)[1]:.1f}" for i, (_, v) in enumerate(notas))
    c.append(f'<polygon points="{pts}" fill="{LARANJA}" fill-opacity="0.18" stroke="{LARANJA}" stroke-width="2"/>')
    for i, (_, v) in enumerate(notas):
        x, yy = pt(i, v)
        c.append(f'<circle cx="{x:.1f}" cy="{yy:.1f}" r="3.5" fill="{LARANJA}" stroke="{PAPEL}" stroke-width="1.5"/>'
                 f'<text x="{x:.1f}" y="{yy - 6:.1f}" font-size="8" font-weight="700" fill="{TINTA}" '
                 f'text-anchor="middle">{v}</text>')
    return _svg(L, A, "".join(c), "Notas por dimensão do risco (5 = mais sólido)")


def barras_valor(itens: list[tuple[str, float, str, bool]]) -> str:
    """Barras horizontais de valor (rótulo, valor, observação, destaque). Destaque em laranja, demais em cinza."""
    L, esq, dir_, h, passo = 330, 112, 8, 13, 22
    A = 8 + passo * len(itens)
    vmax = max([v for _, v, _, _ in itens] + [1.0])
    x = lambda v: esq + max(v, 0) / vmax * (L - esq - dir_ - 90)  # noqa: E731
    c = []
    for i, (rot, v, obs, dest) in enumerate(itens):
        yy = 4 + i * passo
        c.append(f'<text x="{esq - 6}" y="{yy + 10}" font-size="8.5" fill="{TINTA}" text-anchor="end" '
                 f'font-weight="{700 if dest else 400}">{escape(rot)}</text>')
        c.append(_barra_h(esq, x(v), yy, h, LARANJA if dest else CINZA))
        c.append(f'<text x="{x(v) + 5:.1f}" y="{yy + 10}" font-size="8.5" fill="{TINTA}" font-weight="{700 if dest else 400}">'
                 f'{escape(brl_compacto(v))}</text><text x="{x(v) + 5:.1f}" y="{yy + 19}" font-size="7" fill="{MUTED}">'
                 f'{escape(obs)}</text>')
    return _svg(L, A, "".join(c), "Quanto vale")


# --------------------------------------------------------------------------- capítulo 2 (padrão ND, sóbrio)


def _quebrar(texto: str, largura: int) -> list[str]:
    linhas, atual = [], ""
    for palavra in texto.split():
        if len(atual) + len(palavra) + 1 > largura and atual:
            linhas.append(atual)
            atual = palavra
        else:
            atual = f"{atual} {palavra}".strip()
    return linhas + ([atual] if atual else [])


def _cortar(texto: str, largura: int, linhas: int) -> list[str]:
    """Quebra em até `linhas` linhas; se sobrar texto, termina a última com reticências."""
    partes = _quebrar(texto, largura)
    if len(partes) <= linhas:
        return partes
    ultima = partes[linhas - 1]
    return partes[:linhas - 1] + [(ultima[:largura - 1].rstrip() + "…")]


def _tspans(x: float, y: float, linhas: list[str], tam: float, cor: str, ancora: str = "middle", peso: int = 400) -> str:
    return (f'<text x="{x:.1f}" y="{y:.1f}" font-size="{tam}" fill="{cor}" text-anchor="{ancora}" font-weight="{peso}" '
            f'font-family="Helvetica,Arial,sans-serif">'
            + "".join(f'<tspan x="{x:.1f}" dy="{0 if i == 0 else tam * 1.25:.1f}">{escape(l)}</tspan>'
                      for i, l in enumerate(linhas)) + "</text>")


def linha_do_tempo(eventos: list[tuple[int, str]]) -> str:
    """Marcos em ordem de ano, alternando acima e abaixo da linha; o mais recente em laranja."""
    eventos = sorted(eventos)[:8]
    L, A, esq, dir_, cy = 540, 168, 62, 62, 84
    n = len(eventos)
    passo = (L - esq - dir_) / max(n - 1, 1)
    c = [f'<line x1="{esq - 20}" x2="{L - dir_ + 20}" y1="{cy}" y2="{cy}" stroke="{CINZA}" stroke-width="2"/>']
    for i, (ano, ev) in enumerate(eventos):
        x = esq + passo * i if n > 1 else L / 2
        ultimo = i == n - 1
        cima = i % 2 == 0
        c.append(f'<line x1="{x:.1f}" x2="{x:.1f}" y1="{cy}" y2="{cy - 14 if cima else cy + 14}" stroke="{CINZA}" stroke-width="1"/>')
        c.append(f'<circle cx="{x:.1f}" cy="{cy}" r="5" fill="{LARANJA if ultimo else TINTA}" stroke="{PAPEL}" stroke-width="2"/>')
        linhas = _cortar(ev, 24, 3)
        if cima:
            y0 = cy - 24 - 10.5 * len(linhas)
            c.append(_tspans(x, y0 - 3, [str(ano)], 9.5, TINTA, peso=700))
            c.append(_tspans(x, y0 + 9, linhas, 8.2, TINTA_SUAVE))
        else:
            c.append(_tspans(x, cy + 30, [str(ano)], 9.5, TINTA, peso=700))
            c.append(_tspans(x, cy + 42, linhas, 8.2, TINTA_SUAVE))
    return _svg(L, A, "".join(c), "Linha do tempo da empresa")


def organograma(nos: list[dict]) -> str:
    """Árvore a partir de id/superior: folhas espaçadas por igual, cada chefe centralizado sobre a equipe."""
    por_id = {n["id"]: n for n in nos}
    filhos: dict[str | None, list[str]] = {}
    for n in nos:
        pai = n.get("superior") if n.get("superior") in por_id else None
        filhos.setdefault(pai, []).append(n["id"])
    nivel, pos, cont = {}, {}, [0]

    def visitar(i: str, d: int) -> None:
        nivel[i] = d
        fs = filhos.get(i, [])
        for f in fs:
            visitar(f, d + 1)
        if fs:
            pos[i] = (pos[fs[0]] + pos[fs[-1]]) / 2
        else:
            pos[i] = cont[0]
            cont[0] += 1

    for raiz in filhos.get(None, []):
        visitar(raiz, 0)
    folhas = max(cont[0], 1)
    bw, bh, gy = 112, 38, 24
    L = max(520, int(folhas * (bw + 12)))
    esp = L / folhas
    prof = max(nivel.values(), default=0) + 1
    A = prof * (bh + gy) + 4
    xy = {i: (esp * (pos[i] + 0.5), 4 + nivel[i] * (bh + gy)) for i in pos}
    c = []
    for pai, fs in filhos.items():
        if pai is None or pai not in xy:
            continue
        px, py = xy[pai]
        meio = py + bh + gy / 2
        c.append(f'<line x1="{px:.1f}" x2="{px:.1f}" y1="{py + bh}" y2="{meio}" stroke="{CINZA}" stroke-width="1"/>')
        xs = [xy[f][0] for f in fs]
        c.append(f'<line x1="{min(xs):.1f}" x2="{max(xs):.1f}" y1="{meio}" y2="{meio}" stroke="{CINZA}" stroke-width="1"/>')
        for x in xs:
            c.append(f'<line x1="{x:.1f}" x2="{x:.1f}" y1="{meio}" y2="{meio + gy / 2}" stroke="{CINZA}" stroke-width="1"/>')
    for i, (x, y) in xy.items():
        n = por_id[i]
        topo = nivel[i] == 0
        c.append(f'<rect x="{x - bw / 2:.1f}" y="{y}" width="{bw}" height="{bh}" rx="6" '
                 f'fill="{TINTA if topo else "#F2F2F2"}"/>')
        cor1, cor2 = ("#FFFFFF", "#D9D9D9") if topo else (TINTA, MUTED)
        cargo = _cortar(n["cargo"], 22, 2)
        yc = y + (15 if len(cargo) == 1 else 12)
        c.append(_tspans(x, yc, cargo, 8.4, cor1, peso=700))
        if n.get("nome"):
            c.append(_tspans(x, y + bh - 6, _cortar(n["nome"], 24, 1), 7.8, cor2))
    return _svg(L, A, "".join(c), "Organograma")


def barras_percentual(itens: list[tuple[str, float]]) -> str:
    """Participação (%) por item; o maior em laranja, demais em cinza; valor ao fim da barra."""
    itens = sorted(itens, key=lambda x: -x[1])[:6]
    L, esq, h, passo = 330, 120, 12, 20
    A = 6 + passo * len(itens)
    x = lambda v: esq + v / 100 * (L - esq - 40)  # noqa: E731
    c = []
    for i, (rot, v) in enumerate(itens):
        yy = 3 + i * passo
        c.append(f'<text x="{esq - 6}" y="{yy + 9.5}" font-size="8" fill="{TINTA}" text-anchor="end">{escape(rot)}</text>')
        c.append(_barra_h(esq, x(v), yy, h, LARANJA if i == 0 else CINZA))
        c.append(f'<text x="{x(v) + 5:.1f}" y="{yy + 9.5}" font-size="8" fill="{TINTA}">{v:.0f}%</text>')
    return _svg(L, A, "".join(c), "Participação na receita")


def linhas_rentabilidade(anos: list[int], series: list[tuple[str, list[float], str]]) -> str:
    """Rentabilidade anual (% a.a.) por ano: uma linha por alternativa, 2 px, marcador com anel branco, valor no fim.
    `series` = (nome, valores em %, cor). Um eixo só (todas em % a.a.)."""
    L, A, esq, dir_, topo, base = 330, 140, 30, 74, 12, 114
    vals = [v for _, vs, _ in series for v in vs if v is not None]
    if not vals:
        return '<div class="nota">Sem expectativas de mercado disponíveis.</div>'
    vmin, vmax = min(0.0, *vals), max(vals) * 1.12
    ticks = _ticks(vmin, vmax, 4)
    vmax = max(vmax, ticks[-1])
    n = len(anos)
    x = lambda i: esq + (L - esq - dir_) * (i / max(n - 1, 1))  # noqa: E731
    y = lambda v: topo + (vmax - v) / ((vmax - vmin) or 1) * (base - topo)  # noqa: E731
    c = []
    for t in ticks:
        c.append(f'<line x1="{esq}" x2="{L - dir_}" y1="{y(t):.1f}" y2="{y(t):.1f}" stroke="{LINHA}" stroke-width="1"/>'
                 f'<text x="{esq - 5}" y="{y(t) + 3:.1f}" font-size="7.5" fill="{MUTED}" text-anchor="end">{t:.0f}%</text>')
    for i, ano in enumerate(anos):
        c.append(f'<text x="{x(i):.1f}" y="{base + 13}" font-size="8" fill="{TINTA}" text-anchor="middle">{ano}</text>')
    rotulos = []
    for nome, vs, cor in series:
        pts = [(x(i), y(v)) for i, v in enumerate(vs) if v is not None]
        if not pts:
            continue
        c.append(f'<polyline points="{" ".join(f"{a:.1f},{b:.1f}" for a, b in pts)}" fill="none" stroke="{cor}" '
                 f'stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>')
        for a, b in pts:
            c.append(f'<circle cx="{a:.1f}" cy="{b:.1f}" r="3.2" fill="{cor}" stroke="{PAPEL}" stroke-width="1.5"/>')
        rotulos.append([pts[-1][1], nome, vs[-1], cor])
    rotulos.sort()
    for i in range(1, len(rotulos)):  # evita sobreposição dos rótulos no fim das linhas
        if rotulos[i][0] - rotulos[i - 1][0] < 11:
            rotulos[i][0] = rotulos[i - 1][0] + 11
    for yy, nome, v, cor in rotulos:
        c.append(f'<text x="{L - dir_ + 7}" y="{yy + 3:.1f}" font-size="8" fill="{TINTA}">'
                 f'<tspan font-weight="700">{v:.1f}%</tspan> {escape(nome)}</text>'.replace(f"{v:.1f}%", f"{v:.1f}%".replace(".", ",")))
    return _svg(L, A, "".join(c), "Rentabilidade anual por alternativa")


def linhas_evolucao(anos: list[int], series: list[tuple[str, list[float], str]]) -> str:
    """Quanto o investimento vira ao longo dos anos (R$ acumulados), uma linha por alternativa; valor no fim."""
    L, A, esq, dir_, topo, base = 330, 140, 34, 86, 12, 114
    vals = [v for _, vs, _ in series for v in vs if v is not None]
    vmin = min(vals) * 0.9 if vals else 0.0
    vmax = max(vals) * 1.06 if vals else 1.0
    ticks = [t for t in _ticks(vmin, vmax, 4) if vmin <= t <= vmax]
    n = len(anos)
    x = lambda i: esq + (L - esq - dir_) * (i / max(n - 1, 1))  # noqa: E731
    y = lambda v: topo + (vmax - v) / ((vmax - vmin) or 1) * (base - topo)  # noqa: E731
    c = []
    for t in ticks:
        c.append(f'<line x1="{esq}" x2="{L - dir_}" y1="{y(t):.1f}" y2="{y(t):.1f}" stroke="{LINHA}" stroke-width="1"/>'
                 f'<text x="{esq - 5}" y="{y(t) + 3:.1f}" font-size="7.5" fill="{MUTED}" text-anchor="end">'
                 f'{escape(brl_compacto(t).replace("R$ ", "").replace(" mi", "M").replace(" mil", "k"))}</text>')
    for i, ano in enumerate(anos):
        c.append(f'<text x="{x(i):.1f}" y="{base + 13}" font-size="8" fill="{TINTA}" text-anchor="middle">'
                 f'{"hoje" if i == 0 else ano}</text>')
    rotulos = []
    for nome, vs, cor in series:
        pts = [(x(i), y(v)) for i, v in enumerate(vs) if v is not None]
        if not pts:
            continue
        c.append(f'<polyline points="{" ".join(f"{a:.1f},{b:.1f}" for a, b in pts)}" fill="none" stroke="{cor}" '
                 f'stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>')
        for a, b in pts[1:]:
            c.append(f'<circle cx="{a:.1f}" cy="{b:.1f}" r="3.2" fill="{cor}" stroke="{PAPEL}" stroke-width="1.5"/>')
        rotulos.append([pts[-1][1], nome, vs[-1]])
    c.append(f'<circle cx="{x(0):.1f}" cy="{y(series[0][1][0]):.1f}" r="3.5" fill="{TINTA}" stroke="{PAPEL}" stroke-width="1.5"/>'
             if series and series[0][1] else "")
    rotulos.sort()
    for i in range(1, len(rotulos)):
        if rotulos[i][0] - rotulos[i - 1][0] < 11:
            rotulos[i][0] = rotulos[i - 1][0] + 11
    for yy, nome, v in rotulos:
        c.append(f'<text x="{L - dir_ + 7}" y="{yy + 3:.1f}" font-size="8" fill="{TINTA}"><tspan font-weight="700">'
                 f'{escape(brl_compacto(v).replace("R$ ", ""))}</tspan> {escape(nome)}</text>')
    return _svg(L, A, "".join(c), "Quanto vira o investimento recomendado")


# --------------------------------------------------------------------------- capítulo 3 (padrão ND, sóbrio)


def cadeia_valor(etapas: list[dict]) -> str:
    """Fluxograma em setas: etapas do setor da matéria-prima ao cliente; onde a empresa atua fica em preto."""
    etapas = etapas[:6]
    n = max(len(etapas), 1)
    L, A, h, ponta, gap = 660, 86, 38, 12, 4
    w = (L - gap * (n - 1)) / n
    c = []
    for i, e in enumerate(etapas):
        x0 = i * (w + gap)
        x1 = x0 + w
        ent = ponta if i > 0 else 0
        pts = f"{x0:.1f},4 {x1 - ponta:.1f},4 {x1:.1f},{4 + h / 2:.1f} {x1 - ponta:.1f},{4 + h} {x0:.1f},{4 + h} {x0 + ent:.1f},{4 + h / 2:.1f}"
        if i == n - 1:
            pts = f"{x0:.1f},4 {x1:.1f},4 {x1:.1f},{4 + h} {x0:.1f},{4 + h} {x0 + ent:.1f},{4 + h / 2:.1f}"
        atua = e.get("empresa_atua")
        c.append(f'<polygon points="{pts}" fill="{TINTA if atua else "#F2F2F2"}"/>')
        cx = x0 + (w + ent - ponta) / 2 + (ponta / 2 if i == n - 1 else 0)
        rot = _cortar(e["etapa"], 18, 2)
        c.append(_tspans(cx, 4 + h / 2 + (3 if len(rot) == 1 else -2), rot, 8.4, "#FFFFFF" if atua else TINTA, peso=700))
        if e.get("quem"):
            c.append(_tspans(cx, 4 + h + 13, _cortar(e["quem"], 26, 2), 7.4, MUTED))
    return _svg(L, A, "".join(c), "Cadeia de valor do setor")


def mapa_posicionamento(concorrentes: list[dict], empresa: tuple[str, int, int] | None) -> str:
    """Preço (x) × especialização (y), notas 1–5; quadrantes nomeados; empresa em laranja, concorrentes em cinza."""
    L, A, esq, dir_, topo, base = 330, 206, 30, 12, 10, 178
    x = lambda v: esq + (v - 0.5) / 5 * (L - esq - dir_)  # noqa: E731
    y = lambda v: topo + (5.5 - v) / 5 * (base - topo)  # noqa: E731
    c = [f'<rect x="{esq}" y="{topo}" width="{L - esq - dir_}" height="{base - topo}" fill="none" stroke="{LINHA}"/>',
         f'<line x1="{x(3):.1f}" x2="{x(3):.1f}" y1="{topo}" y2="{base}" stroke="{LINHA}"/>',
         f'<line x1="{esq}" x2="{L - dir_}" y1="{y(3):.1f}" y2="{y(3):.1f}" stroke="{LINHA}"/>']
    for txt, qx, qy, anc in (("especialista acessível", x(0.7), y(5.25), "start"), ("nicho de valor", x(5.3), y(5.25), "end"),
                             ("produto padrão", x(0.7), y(0.8), "start"), ("caro sem diferencial", x(5.3), y(0.8), "end")):
        c.append(f'<text x="{qx:.1f}" y="{qy:.1f}" font-size="7.2" fill="#A6A6A6" text-anchor="{anc}">{escape(txt)}</text>')
    c.append(f'<text x="{(esq + L - dir_) / 2:.1f}" y="{base + 14}" font-size="7.6" fill="{MUTED}" text-anchor="middle">'
             'preço →</text>')
    c.append(f'<text x="10" y="{(topo + base) / 2:.1f}" font-size="7.6" fill="{MUTED}" text-anchor="middle" '
             f'transform="rotate(-90 10 {(topo + base) / 2:.1f})">especialização →</text>')
    usados: dict[tuple[int, int], int] = {}
    pontos = [(k["nome"], k["preco"], k["especializacao"], False) for k in concorrentes[:6]]
    if empresa:
        pontos.append((empresa[0], empresa[1], empresa[2], True))
    for nome, pr, es, eh in pontos:
        k = usados.get((pr, es), 0)
        usados[(pr, es)] = k + 1
        px, py = x(pr) + k * 9, y(es) - k * 9  # afasta pontos repetidos
        c.append(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="{6 if eh else 4.5}" fill="{LARANJA if eh else CINZA}" '
                 f'stroke="{PAPEL}" stroke-width="1.5"/>')
        rot = _cortar(nome, 18, 2)
        dy = -9 - 9 * (len(rot) - 1) if es <= 1 else (14 if eh else 12)  # na borda de baixo, rótulo acima do ponto
        c.append(_tspans(px, py + dy, rot, 8.2 if eh else 7.2, TINTA, peso=700 if eh else 400))
    return _svg(L, A, "".join(c), "Mapa de posicionamento competitivo")


# --------------------------------------------------------------------------- capítulo 4 (análise financeira)


def _curto(v: float) -> str:
    """1,37M · 703k · 950 (rótulo de coluna)."""
    return brl_compacto(v).replace("R$ ", "").replace(" mil", "k").replace(" mi", "M")


def colunas_serie(itens: list[tuple[str, float, str]], destaques: set[int] | None = None, altura: int = 128,
                  rotulo_valor: bool = True, titulo: str = "Série por período") -> str:
    """Colunas de uma série (cinza), destaque em laranja; `itens` = (rótulo do eixo, valor, texto extra no topo)."""
    destaques = destaques or set()
    n = max(len(itens), 1)
    L, esq, dir_, topo, base = 330, 4, 4, 24, altura - 22
    vals = [v for _, v, _ in itens]
    vmin, vmax = min(0.0, *vals), max(0.0, *vals) or 1.0
    y = lambda v: topo + (vmax - v) / ((vmax - vmin) or 1) * (base - topo)  # noqa: E731
    banda = (L - esq - dir_) / n
    w = min(26.0, banda * 0.62)
    fonte = 8 if n <= 8 else 6.4
    c = [f'<line x1="{esq}" x2="{L - dir_}" y1="{y(0):.1f}" y2="{y(0):.1f}" stroke="{MUTED}" stroke-width="1"/>']
    for i, (rot, v, extra) in enumerate(itens):
        cx = esq + banda * (i + 0.5)
        c.append(_barra_v(cx - w / 2, y(0), y(v), w, LARANJA if i in destaques else CINZA))
        if rotulo_valor:
            ty = y(v) - 4 if v >= 0 else y(v) + 10
            c.append(f'<text x="{cx:.1f}" y="{ty:.1f}" font-size="{fonte}" fill="{TINTA_SUAVE}" text-anchor="middle">'
                     f'{escape(_curto(v))}</text>')
        if extra:
            c.append(f'<text x="{cx:.1f}" y="{topo - 14}" font-size="{fonte}" fill="{MUTED}" text-anchor="middle">'
                     f'{escape(extra)}</text>')
        c.append(f'<text x="{cx:.1f}" y="{altura - 8}" font-size="{fonte + 0.5}" fill="{TINTA}" text-anchor="middle">'
                 f'{escape(rot)}</text>')
    return _svg(L, altura, "".join(c), titulo)


def empilhadas_100(anos: list[str], segmentos: dict[str, list[float]]) -> str:
    """Cada ano = 100% da receita bruta, empilhado de baixo para cima; o último segmento (EBITDA) em laranja,
    os demais em tons de cinza. Percentual dentro do segmento quando cabe; legenda à direita."""
    L, A, esq, topo, base = 330, 150, 4, 8, 128
    nomes = list(segmentos)
    tons = ["#E3E3E3", "#BFBFBF", "#9A9A9A", "#6B6B6B"]
    cores = {n: (LARANJA if i == len(nomes) - 1 else tons[i % len(tons)]) for i, n in enumerate(nomes)}
    larg_graf = 200
    banda = larg_graf / max(len(anos), 1)
    w = min(34.0, banda * 0.6)
    teto = max(100.0, *(sum(max(segmentos[n][i], 0.0) for n in nomes) for i in range(len(anos))))
    y = lambda p: base - p / teto * (base - topo)  # noqa: E731
    c = []
    if teto > 100.5:  # custos acima da receita: linha de 100% marca onde a receita acaba
        c.append(f'<line x1="{esq}" x2="{esq + larg_graf}" y1="{y(100):.1f}" y2="{y(100):.1f}" stroke="{TINTA}" '
                 f'stroke-width="0.8" stroke-dasharray="3 2"/><text x="{esq + larg_graf}" y="{y(100) - 2:.1f}" '
                 f'font-size="6.8" fill="{MUTED}" text-anchor="end">100% da receita</text>')
    for i, ano in enumerate(anos):
        cx = esq + banda * (i + 0.5)
        acum = 0.0
        for n in nomes:
            p = max(segmentos[n][i], 0.0)
            if p <= 0:
                continue
            y1, y0 = y(acum + p), y(acum)
            c.append(f'<rect x="{cx - w / 2:.1f}" y="{y1:.1f}" width="{w:.1f}" height="{y0 - y1:.1f}" fill="{cores[n]}" '
                     f'stroke="{PAPEL}" stroke-width="0.8"/>')
            if y0 - y1 >= 9:
                cor_txt = PAPEL if cores[n] == "#6B6B6B" else TINTA
                peso = 700 if n == nomes[-1] else 400
                c.append(f'<text x="{cx:.1f}" y="{(y0 + y1) / 2 + 3:.1f}" font-size="7.2" fill="{cor_txt}" '
                         f'text-anchor="middle" font-weight="{peso}">{p:.0f}%</text>')
            acum += p
        ult = segmentos[nomes[-1]][i]
        if ult < 0:  # EBITDA negativo: não empilha, vai escrito acima da barra
            c.append(f'<text x="{cx:.1f}" y="{y(acum) - 3:.1f}" font-size="7.2" font-weight="700" fill="{TINTA}" '
                     f'text-anchor="middle">{escape(nomes[-1])} {ult:.0f}%</text>')
        c.append(f'<text x="{cx:.1f}" y="{A - 8}" font-size="8.5" fill="{TINTA}" text-anchor="middle">{escape(ano)}</text>')
    lx = esq + larg_graf + 14
    for j, n in enumerate(reversed(nomes)):
        yy = topo + 8 + j * 16
        c.append(f'<rect x="{lx}" y="{yy - 7}" width="8" height="8" rx="1.5" fill="{cores[n]}"/>'
                 f'<text x="{lx + 12}" y="{yy}" font-size="8" fill="{TINTA}">{escape(n)}</text>')
    return _svg(L, A, "".join(c), "Composição da receita bruta: tributos, custos, despesas e EBITDA")


def cascata_ponte(itens: list[tuple[str, float]]) -> str:
    """Ponte vertical do EBITDA contábil ao econômico: totais em grafite (o final em laranja), acréscimos em cinza
    claro, reduções em cinza escuro; conectores finos entre as barras e valor sobre cada uma."""
    n = len(itens)
    L, A, esq, dir_, topo, base = 660, 150, 10, 10, 20, 108
    acum, barras = 0.0, []
    for i, (rot, v) in enumerate(itens):
        total = i == 0 or rot.startswith("=")
        ini, fim = (0.0, v) if total else (acum, acum + v)
        acum = v if total else acum + v
        barras.append((rot.lstrip("= "), ini, fim, total, v, i == n - 1))
    vals = [b for _, a, f, *_ in barras for b in (a, f)]
    vmin, vmax = min(0.0, *vals), max(vals) * 1.08
    y = lambda v: topo + (vmax - v) / ((vmax - vmin) or 1) * (base - topo)  # noqa: E731
    banda = (L - esq - dir_) / n
    w = min(46.0, banda * 0.58)
    c = [f'<line x1="{esq}" x2="{L - dir_}" y1="{y(0):.1f}" y2="{y(0):.1f}" stroke="{MUTED}" stroke-width="1"/>']
    for i, (rot, ini, fim, total, v, ultimo) in enumerate(barras):
        cx = esq + banda * (i + 0.5)
        cor = LARANJA if ultimo else (TINTA_SUAVE if total else (CINZA if v >= 0 else NEUTRO))
        y0, y1 = sorted((y(ini), y(fim)))
        c.append(f'<rect x="{cx - w / 2:.1f}" y="{y0:.1f}" width="{w:.1f}" height="{max(y1 - y0, 1.2):.1f}" rx="2" '
                 f'fill="{cor}"/>')
        if i < n - 1:
            nx = esq + banda * (i + 1.5) - w / 2
            c.append(f'<line x1="{cx + w / 2:.1f}" x2="{nx:.1f}" y1="{y(fim):.1f}" y2="{y(fim):.1f}" stroke="{MUTED}" '
                     f'stroke-width="0.8" stroke-dasharray="2 2"/>')
        txt = _curto(v) if total else ("+" if v >= 0 else "") + _curto(v)
        c.append(f'<text x="{cx:.1f}" y="{y0 - 4:.1f}" font-size="9" fill="{TINTA}" text-anchor="middle" '
                 f'font-weight="{700 if total else 400}">{escape(txt)}</text>')
        c.append(_tspans(cx, base + 14, _cortar(rot, 16, 3), 8.2, TINTA, peso=700 if total else 400))
    return _svg(L, A, "".join(c), "Ponte do EBITDA contábil ao EBITDA econômico")


def radar_verticais(notas: list[tuple[str, float | None]]) -> str:
    """Teia das verticais de risco (nota 1–5, 5 = mais sólido). Sem nota = vértice vazio marcado 'n/d'."""
    import math

    L, A, cx, cy, R = 330, 210, 165, 106, 72
    n = len(notas)
    ang = lambda i: -math.pi / 2 + 2 * math.pi * i / n  # noqa: E731
    pt = lambda i, v: (cx + R * v / 5 * math.cos(ang(i)), cy + R * v / 5 * math.sin(ang(i)))  # noqa: E731
    c = []
    for nivel in range(1, 6):
        pts = " ".join(f"{pt(i, nivel)[0]:.1f},{pt(i, nivel)[1]:.1f}" for i in range(n))
        c.append(f'<polygon points="{pts}" fill="none" stroke="{LINHA}" stroke-width="1"/>')
    for i, (nome, v) in enumerate(notas):
        x2, y2 = pt(i, 5)
        c.append(f'<line x1="{cx}" y1="{cy}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="{LINHA}" stroke-width="1"/>')
        lx, ly = pt(i, 5.75)
        ancora = "middle" if abs(lx - cx) < 12 else ("start" if lx > cx else "end")
        linhas = _quebrar(nome, 17)
        if abs(ly - cy) < 40:
            y0 = ly + 3 - (len(linhas) - 1) * 4.5
        elif ly < cy:
            y0 = ly - (len(linhas) - 1) * 9 + 3
        else:
            y0 = ly + 6
        c.append(_tspans(lx, y0, linhas, 7.6, TINTA_SUAVE, ancora=ancora))
    validos = [(i, v) for i, (_, v) in enumerate(notas) if v is not None]
    pts = " ".join(f"{pt(i, v)[0]:.1f},{pt(i, v)[1]:.1f}" for i, v in validos)
    c.append(f'<polygon points="{pts}" fill="{LARANJA}" fill-opacity="0.18" stroke="{LARANJA}" stroke-width="2"/>')
    for i, (_, v) in enumerate(notas):
        if v is None:
            x, yy = pt(i, 0.9)
            c.append(f'<text x="{x:.1f}" y="{yy + 3:.1f}" font-size="7.5" fill="{MUTED}" text-anchor="middle">n/d</text>')
            continue
        x, yy = pt(i, v)
        txt = f"{v:.1f}".rstrip("0").rstrip(".").replace(".", ",")
        c.append(f'<circle cx="{x:.1f}" cy="{yy:.1f}" r="3.5" fill="{LARANJA}" stroke="{PAPEL}" stroke-width="1.5"/>'
                 f'<text x="{x:.1f}" y="{yy - 6:.1f}" font-size="8" font-weight="700" fill="{TINTA}" '
                 f'text-anchor="middle">{txt}</text>')
    return _svg(L, A, "".join(c), "Mapa de risco por vertical (5 = mais sólido)")
