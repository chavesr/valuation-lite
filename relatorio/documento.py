"""Relatório em Word (.docx) para abrir no Google Docs, a partir do mesmo relatorio.html que vira o PDF (13/11/2026).

Uma fonte só: o HTML montado por relatorio.render é lido e traduzido para elementos que o Google Docs entende
(títulos, parágrafos, listas, tabelas, células sombreadas e imagens). O que o Docs não tem vira o equivalente:
- gráficos e ícones (SVG) → PNG desenhado pelo próprio Chrome/Edge headless, em lotes;
- cartões e colunas lado a lado (grid/flex) → tabelas sem borda, com células cinza e borda branca no lugar do espaço;
- capa preta de página inteira → bloco preto em uma tabela de 1 célula.
Assim o PDF e o Doc sempre dizem a mesma coisa: nada aqui escreve texto ou número próprio.
"""

from __future__ import annotations

import io
import re
import subprocess
import tempfile
from base64 import b64decode
from pathlib import Path

from bs4 import BeautifulSoup, NavigableString, Tag
from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_ROW_HEIGHT_RULE
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK, WD_TAB_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Mm, Pt, RGBColor

from relatorio.render import ASSETS, navegador

FONTE = "Arial"
INK, INK2, GRAY, GRAY2, LINE = "000000", "1A1A1A", "6B6B6B", "8C8C8C", "E6E6E6"
CINZA, LARANJA, LARANJA_CLARO, PRETO_CAPA = "F2F2F2", "FF9900", "FFF4E3", "111111"
LARGURA_UTIL = 182.0  # mm: A4 (210) menos margens de 14 mm, como no PDF
CORPO, TABELA, PEQUENO = 8.5, 7.5, 7.0
GAP_PT = 6  # borda branca entre cartões: faz o papel do "gap" do CSS

BLOCOS = {"div", "p", "table", "ul", "ol", "h1", "h2", "h3", "section", "img"}


# ───────────────────────── SVG → PNG pelo navegador ─────────────────────────

def _caixa_svg(svg: Tag) -> tuple[float, float]:
    vb = svg.get("viewbox") or svg.get("viewBox")
    if vb:
        _, _, w, h = (float(x) for x in re.split(r"[ ,]+", vb.strip()))
        return w, h
    return float(svg.get("width") or 24), float(svg.get("height") or 24)


def _e_icone(svg: Tag) -> bool:
    w = svg.get("width") or ""
    return w.isdigit() and int(w) <= 32


def rasterizar(svgs: list[str], caixas: list[tuple[float, float]], larguras_px: list[int],
               exe: str | None = None, lote_px: int = 3600, timeout: int = 120) -> list[bytes]:
    """Desenha cada SVG num PNG com o Chrome/Edge headless: os SVGs são empilhados numa página, uma captura de tela
    por lote e o Pillow recorta cada um. Devolve os PNGs na mesma ordem."""
    from PIL import Image

    exe = exe or navegador()
    if not exe:
        raise RuntimeError("Edge/Chrome não encontrado: os gráficos do Word são desenhados por ele.")
    itens = []
    for svg, (w, h), lp in zip(svgs, caixas, larguras_px):
        itens.append((svg, lp, max(1, round(lp * h / w))))
    saida: list[bytes] = [b""] * len(itens)
    lotes, atual, alt = [], [], 0
    for i, (_, lp, hp) in enumerate(itens):
        if atual and alt + hp + 4 > lote_px:
            lotes.append(atual)
            atual, alt = [], 0
        atual.append(i)
        alt += hp + 4
    if atual:
        lotes.append(atual)
    with tempfile.TemporaryDirectory(prefix="tarantino_docx_") as tmp:
        tmp = Path(tmp)
        for n, lote in enumerate(lotes):
            y, pos, partes = 0, {}, []
            larg = max(itens[i][1] for i in lote)
            for i in lote:
                svg, lp, hp = itens[i]
                svg = re.sub(r"<svg\b", '<svg style="display:block;width:100%;height:100%"', svg, count=1)
                partes.append(f'<div style="position:absolute;left:0;top:{y}px;width:{lp}px;height:{hp}px">{svg}</div>')
                pos[i] = (y, lp, hp)
                y += hp + 4
            html = tmp / f"lote{n}.html"
            html.write_text("<!doctype html><html><head><meta charset='utf-8'><style>html,body{margin:0;"
                            "background:#fff;overflow:hidden}svg{display:block;width:100%;height:100%}</style></head><body>" + "".join(partes)
                            + "</body></html>", encoding="utf-8")
            png = tmp / f"lote{n}.png"
            cmd = [exe, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--force-device-scale-factor=1",
                   f"--user-data-dir={tmp / 'perfil'}", f"--window-size={larg},{y}", f"--screenshot={png}",
                   html.resolve().as_uri()]
            subprocess.run(cmd, capture_output=True, timeout=timeout)
            if not png.exists():
                raise RuntimeError("o navegador não gerou as imagens dos gráficos.")
            with Image.open(png) as im:
                im = im.convert("RGB")
                for i in lote:
                    y0, lp, hp = pos[i]
                    buf = io.BytesIO()
                    im.crop((0, y0, lp, y0 + hp)).save(buf, "PNG", optimize=True)
                    saida[i] = buf.getvalue()
    return saida


# ───────────────────────── utilitários de formatação ─────────────────────────

_ORDEM_TCPR = ["cnfStyle", "tcW", "gridSpan", "hMerge", "vMerge", "tcBorders", "shd", "noWrap", "tcMar",
               "textDirection", "tcFitText", "vAlign", "hideMark"]


def _no_tcpr(celula, el) -> None:
    """Põe `el` no tcPr na ordem do schema (o Word e o Google Docs ignoram o que vem fora de ordem)."""
    tcPr = celula._tc.get_or_add_tcPr()
    nome = el.tag.split("}")[1]
    for velho in tcPr.findall(qn(f"w:{nome}")):
        tcPr.remove(velho)
    pos = _ORDEM_TCPR.index(nome)
    for i, filho in enumerate(tcPr):
        outro = filho.tag.split("}")[1]
        if outro in _ORDEM_TCPR and _ORDEM_TCPR.index(outro) > pos:
            tcPr.insert(i, el)
            return
    tcPr.append(el)


def _sombra(celula, cor: str) -> None:
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), cor)
    _no_tcpr(celula, shd)


def _bordas_celula(celula, **lados: tuple[str, int] | None) -> None:
    """lados: top/left/bottom/right = (cor, espessura em oitavos de pt) ou None (sem borda)."""
    tcPr = celula._tc.get_or_add_tcPr()
    b = tcPr.find(qn("w:tcBorders"))
    if b is None:
        b = OxmlElement("w:tcBorders")
        _no_tcpr(celula, b)
    for lado, spec in lados.items():
        el = b.find(qn(f"w:{lado}"))
        if el is None:
            el = OxmlElement(f"w:{lado}")
            b.append(el)
        if spec is None:
            el.set(qn("w:val"), "nil")
        else:
            el.set(qn("w:val"), "single")
            el.set(qn("w:sz"), str(spec[1]))
            el.set(qn("w:color"), spec[0])
            el.set(qn("w:space"), "0")


def _sem_bordas(tabela) -> None:
    tblPr = tabela._tbl.tblPr
    b = OxmlElement("w:tblBorders")
    for lado in ("top", "left", "bottom", "right", "insideH", "insideV"):
        el = OxmlElement(f"w:{lado}")
        el.set(qn("w:val"), "nil")
        b.append(el)
    tblPr.append(b)


def _margens_celula(celula, mm: float, vert: float | None = None, esq: float | None = None,
                    dir_: float | None = None) -> None:
    m = OxmlElement("w:tcMar")
    v = mm if vert is None else vert
    for lado, val in (("top", v), ("bottom", v), ("left", mm if esq is None else esq),
                      ("right", mm if dir_ is None else dir_)):
        el = OxmlElement(f"w:{lado}")
        el.set(qn("w:w"), str(int(val * 56.7)))
        el.set(qn("w:type"), "dxa")
        m.append(el)
    _no_tcpr(celula, m)


def _borda_paragrafo(par, lado: str, cor: str = LINE, sz: int = 6, espaco: int = 3) -> None:
    pPr = par._p.get_or_add_pPr()
    b = pPr.find(qn("w:pBdr"))
    if b is None:
        b = OxmlElement("w:pBdr")
        pPr.append(b)
    el = OxmlElement(f"w:{lado}")
    el.set(qn("w:val"), "single")
    el.set(qn("w:sz"), str(sz))
    el.set(qn("w:space"), str(espaco))
    el.set(qn("w:color"), cor)
    b.append(el)


def _larguras(tabela, mm: list[float]) -> None:
    tabela.autofit = False
    tblPr = tabela._tbl.tblPr
    lay = OxmlElement("w:tblLayout")
    lay.set(qn("w:type"), "fixed")
    tblPr.append(lay)
    tw = tblPr.find(qn("w:tblW"))
    if tw is None:
        tw = OxmlElement("w:tblW")
        tblPr.append(tw)
    tw.set(qn("w:w"), str(int(sum(mm) * 56.7)))
    tw.set(qn("w:type"), "dxa")
    grid = tabela._tbl.tblGrid
    for gc, w in zip(grid.findall(qn("w:gridCol")), mm):
        gc.set(qn("w:w"), str(int(w * 56.7)))
    for linha in tabela.rows:
        for cel, w in zip(linha.cells, mm):
            cel.width = Mm(w)


def _recuo_tabela(tabela, mm: float = 0) -> None:
    tblPr = tabela._tbl.tblPr
    ind = OxmlElement("w:tblInd")
    ind.set(qn("w:w"), str(int(mm * 56.7)))
    ind.set(qn("w:type"), "dxa")
    tblPr.append(ind)


def _fmt(par, tam: float | None = None, depois: float = 2, antes: float = 0, alinha=None, entre: float = 1.15):
    pf = par.paragraph_format
    pf.space_after, pf.space_before, pf.line_spacing = Pt(depois), Pt(antes), entre
    if alinha is not None:
        par.alignment = alinha
    return par


def _run(par, texto: str, tam: float | None = None, cor: str | None = None, negrito: bool | None = None,
         italico: bool | None = None):
    r = par.add_run(texto)
    if tam:
        r.font.size = Pt(tam)
    if cor:
        r.font.color.rgb = RGBColor.from_string(cor)
    if negrito is not None:
        r.font.bold = negrito
    if italico is not None:
        r.font.italic = italico
    return r


def _classes(no: Tag) -> set[str]:
    return set(no.get("class") or [])


def _texto(no) -> str:
    return re.sub(r"\s+", " ", no.get_text(" ") if isinstance(no, Tag) else str(no)).strip()


# ───────────────────────── conversor ─────────────────────────

class Conversor:
    def __init__(self, html: str, exe: str | None = None):
        self.soup = BeautifulSoup(html, "html.parser")
        self.exe = exe
        self.png: dict[str, bytes] = {}
        self.doc = Document()
        self._estilos()

    # estilos e página ------------------------------------------------------
    def _estilos(self) -> None:
        st = self.doc.styles
        normal = st["Normal"]
        normal.font.name, normal.font.size = FONTE, Pt(CORPO)
        normal.font.color.rgb = RGBColor.from_string(INK2)
        rpr = normal.element.get_or_add_rPr()
        fonts = rpr.find(qn("w:rFonts"))
        for att in ("w:ascii", "w:hAnsi", "w:cs", "w:eastAsia"):
            fonts.set(qn(att), FONTE)
        normal.paragraph_format.space_after, normal.paragraph_format.line_spacing = Pt(2), 1.15
        for nome, tam in (("Title", 30), ("Heading 1", 15), ("Heading 2", 9.5), ("Heading 3", 9)):
            s = st[nome]
            s.font.name, s.font.size, s.font.bold = FONTE, Pt(tam), True
            s.font.color.rgb = RGBColor.from_string(INK)
            s.font.italic = False
            rf = s.element.get_or_add_rPr().find(qn("w:rFonts"))
            if rf is not None:
                for att in ("w:ascii", "w:hAnsi", "w:cs", "w:eastAsia", "w:asciiTheme", "w:hAnsiTheme",
                            "w:eastAsiaTheme", "w:cstheme"):
                    if rf.get(qn(att)) is not None:
                        del rf.attrib[qn(att)]
                for att in ("w:ascii", "w:hAnsi", "w:cs", "w:eastAsia"):
                    rf.set(qn(att), FONTE)
            s.paragraph_format.space_before, s.paragraph_format.space_after = Pt(0), Pt(2)
            s.paragraph_format.keep_with_next = True
        lb = st["List Bullet"]
        lb.font.name, lb.font.size = FONTE, Pt(CORPO)
        lb.paragraph_format.space_after = Pt(1.5)

        sec = self.doc.sections[0]
        sec.page_width, sec.page_height = Mm(210), Mm(297)
        sec.top_margin, sec.bottom_margin = Mm(18), Mm(16)
        sec.left_margin = sec.right_margin = Mm(14)
        sec.header_distance, sec.footer_distance = Mm(7), Mm(7)
        sec.different_first_page_header_footer = True
        logo = ASSETS / "logo_nd.png"
        cab = sec.header.paragraphs[0]
        cab.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        if logo.exists():
            cab.add_run().add_picture(str(logo), width=Mm(25))
        rod = sec.footer.paragraphs[0]
        for pos in (Inches(3.25), Inches(6.5)):
            rod.paragraph_format.tab_stops.add_tab_stop(pos, WD_TAB_ALIGNMENT.CLEAR)
        rod.paragraph_format.tab_stops.add_tab_stop(Mm(LARGURA_UTIL), WD_TAB_ALIGNMENT.RIGHT)
        _run(rod, "NOVA DIREÇÃO  ·  Relatório de valuation  ·  confidencial\tPág. ", 7, GRAY2)
        fld = OxmlElement("w:fldSimple")
        fld.set(qn("w:instr"), "PAGE")
        r = OxmlElement("w:r")
        rpr = OxmlElement("w:rPr")
        for tag, val in (("w:color", GRAY2), ("w:sz", "14")):
            e = OxmlElement(tag)
            e.set(qn("w:val"), val)
            rpr.append(e)
        r.append(rpr)
        t = OxmlElement("w:t")
        t.text = "1"
        r.append(t)
        fld.append(r)
        rod._p.append(fld)

    # imagens ---------------------------------------------------------------
    def _preparar_imagens(self) -> None:
        unicos: dict[str, Tag] = {}
        for svg in self.soup.find_all("svg"):
            unicos.setdefault(str(svg), svg)
        chaves = list(unicos)
        caixas = [_caixa_svg(unicos[k]) for k in chaves]
        larg = [64 if _e_icone(unicos[k]) else 1400 for k in chaves]
        for k, png in zip(chaves, rasterizar(chaves, caixas, larg, self.exe)):
            self.png[k] = png

    def _imagem(self, par, svg: Tag, largura_mm: float):
        w, h = _caixa_svg(svg)
        if _e_icone(svg):
            lado = float(svg.get("width")) * 0.26  # px → mm, mesmo tamanho do PDF
            return par.add_run().add_picture(io.BytesIO(self.png[str(svg)]), width=Mm(lado), height=Mm(lado))
        return par.add_run().add_picture(io.BytesIO(self.png[str(svg)]), width=Mm(largura_mm))

    # texto corrido ----------------------------------------------------------
    def _inline(self, par, no, tam: float | None = None, cor: str | None = None, negrito=None, italico=None,
                inicio: list | None = None) -> None:
        inicio = inicio if inicio is not None else [True]
        for f in (no.children if isinstance(no, Tag) else [no]):
            if isinstance(f, NavigableString):
                if f.__class__.__name__ in ("Comment", "Doctype"):
                    continue
                t = re.sub(r"\s+", " ", str(f))
                if inicio[0]:
                    t = t.lstrip()
                if t:
                    _run(par, t, tam, cor, negrito, italico)
                    inicio[0] = False
            elif f.name == "svg":
                self._imagem(par, f, 3.5)
                _run(par, " ", tam)
            elif f.name == "br":
                par.add_run().add_break()
                inicio[0] = True
            elif f.name in ("b", "strong"):
                self._inline(par, f, tam, cor, True, italico, inicio)
            elif f.name in ("i", "em"):
                self._inline(par, f, tam, cor, negrito, True, inicio)
            elif f.name == "small":
                self._inline(par, f, PEQUENO - 0.5 if (tam or CORPO) <= TABELA else PEQUENO, GRAY2, negrito,
                             italico, inicio)
            else:
                self._inline(par, f, tam, cor, negrito, italico, inicio)

    def _paragrafo(self, cont, no, tam=None, cor=None, negrito=None, italico=None, alinha=None,
                   depois: float = 3, antes: float = 0):
        par = cont.add_paragraph()
        _fmt(par, depois=depois, antes=antes, alinha=alinha)
        self._inline(par, no, tam, cor, negrito, italico)
        return par

    # blocos -----------------------------------------------------------------
    def _tem_bloco(self, no: Tag) -> bool:
        for f in no.children:
            if isinstance(f, Tag) and (f.name in BLOCOS or (f.name == "svg" and not _e_icone(f))):
                return True
        return False

    def blocos(self, cont, no: Tag, largura: float) -> None:
        for f in no.children:
            if isinstance(f, NavigableString):
                if _texto(f):
                    self._paragrafo(cont, f)
                continue
            self.bloco(cont, f, largura)

    def bloco(self, cont, no: Tag, largura: float, dentro_secao: bool = False) -> None:
        cl, tag = _classes(no), no.name
        if tag == "section" and "capa" in cl:
            return self.capa(no)
        if tag == "section":
            if "capitulo" in cl:
                self._quebra()
            return self.blocos(cont, no, largura)
        if tag == "svg":
            if _e_icone(no):
                return
            par = _fmt(cont.add_paragraph(), depois=3, alinha=WD_ALIGN_PARAGRAPH.CENTER)
            self._imagem(par, no, largura)
            return
        if tag == "img":
            src = no.get("src") or ""
            if src.startswith("data:image"):
                par = _fmt(cont.add_paragraph(), depois=3)
                par.add_run().add_picture(io.BytesIO(b64decode(src.split(",", 1)[1])), width=Mm(min(largura, 60)))
            return
        if tag in ("h1", "h2", "h3"):
            return self.titulo(cont, no, tag, largura, dentro_secao or "sec" in cl)
        if tag == "p":
            par = self._paragrafo(cont, no, alinha=WD_ALIGN_PARAGRAPH.JUSTIFY, depois=4,
                                  antes=4 if "fosso" in cl else 0)
            return
        if tag in ("ul", "ol"):
            for li in no.find_all("li", recursive=False):
                if tag == "ol":
                    par = cont.add_paragraph(style="List Number")
                else:  # 13/11/2026 (usuário): marcador "▎" no lugar da bolinha, como no Word editado da Vedis
                    par = cont.add_paragraph()
                    _run(par, "▎ ")
                _fmt(par, depois=2, alinha=WD_ALIGN_PARAGRAPH.LEFT if largura < 100 else WD_ALIGN_PARAGRAPH.JUSTIFY)
                self._inline(par, li)
            return
        if tag == "table":
            return self.tabela(cont, no, largura)
        if tag != "div":
            return self.blocos(cont, no, largura) if self._tem_bloco(no) else self._paragrafo(cont, no)

        # divs com papel visual
        if "cab" in cl:
            h2, sub = no.find("h2"), no.find(class_="sub")
            par = self.doc.add_paragraph(style="Heading 1") if cont is self.doc else cont.add_paragraph(style="Heading 1")
            _fmt(par, depois=1)
            self._inline(par, h2)
            if sub is not None:
                ps = self._paragrafo(cont, sub, 7.5, GRAY, depois=10)
                _borda_paragrafo(ps, "bottom", LINE, 6, 5)
            return
        if "kpis" in cl or "kpis3" in cl or "kpis4" in cl:
            n = 3 if "kpis3" in cl else 4 if "kpis4" in cl else 5
            return self.grade(cont, [k for k in no.children if isinstance(k, Tag)], n, largura, kpi=True)
        if "duas" in cl or "tres" in cl:
            n = 3 if "tres" in cl else 2
            return self.grade(cont, [k for k in no.children if isinstance(k, Tag)], n, largura)
        if "perfil" in cl:
            return self.perfil(cont, no, largura)
        if "quadro" in cl or cl & {"formula", "aviso", "ficha", "coluna-modelo", "kpi"}:
            return self.caixa(cont, no, largura, cinza="destaque" in cl or "quadro" not in cl)
        if "tit" in cl:
            par = self._paragrafo(cont, no, negrito=True, cor=INK, depois=3)
            par.paragraph_format.keep_with_next = True
            return
        if "nota" in cl:
            return self._paragrafo(cont, no, PEQUENO, GRAY if "nd" in cl else GRAY2,
                                   italico=True if "nd" in cl else None, depois=5)
        if "legenda-graf" in cl:
            par = self._paragrafo(cont, no, 7.2, GRAY, depois=1, antes=2)
            par.paragraph_format.keep_with_next = True
            return
        if "disclaimer" in cl:
            par = self._paragrafo(cont, no, PEQUENO, GRAY2, antes=14, alinha=WD_ALIGN_PARAGRAPH.JUSTIFY)
            _borda_paragrafo(par, "top", LINE, 6, 5)
            return
        if "secao" in cl:
            for f in no.children:
                if isinstance(f, Tag):
                    self.bloco(cont, f, largura, dentro_secao=True)
                elif _texto(f):
                    self._paragrafo(cont, f)
            _fmt(cont.add_paragraph(), depois=0, entre=0.5)
            return
        if self._tem_bloco(no):
            return self.blocos(cont, no, largura)
        if _texto(no) or no.find("svg"):
            self._paragrafo(cont, no)

    def _quebra(self) -> None:
        corpo = self.doc.element.body
        ultimo = corpo[-2] if len(corpo) > 1 else None  # [-1] é o sectPr
        if ultimo is not None and ultimo.tag == qn("w:p") and not ultimo.xpath(".//w:t") and not ultimo.xpath(".//w:br"):
            par = self.doc.paragraphs[-1]
        else:
            par = self.doc.add_paragraph()
        _fmt(par, depois=0)
        par.add_run().add_break(WD_BREAK.PAGE)

    def titulo(self, cont, no: Tag, tag: str, largura: float, sublinhado: bool) -> None:
        estilo = {"h1": "Heading 1", "h2": "Heading 1", "h3": "Heading 2"}[tag]
        par = cont.add_paragraph(style=estilo)
        _fmt(par, depois=4 if sublinhado else 3, antes=2)
        par.paragraph_format.keep_with_next = True
        self._inline(par, no)
        if sublinhado:
            _borda_paragrafo(par, "bottom", LINE, 6, 2)

    # caixas e grades --------------------------------------------------------
    def _tabela_caixa(self, cont, colunas: list[float]):
        t = cont.add_table(rows=1, cols=len(colunas))
        _sem_bordas(t)
        _larguras(t, colunas)
        return t

    def _preencher_caixa(self, cel, no: Tag, largura: float, cinza: bool, kpi: bool = False) -> None:
        if cinza:
            _sombra(cel, CINZA)
        _margens_celula(cel, 2.8 if not kpi else 2.4, 2.2 if not kpi else 1.8)
        primeiro = cel.paragraphs[0]
        if kpi:
            self._kpi(cel, no)
        else:
            self.blocos(cel, no, largura - 6)
        if len(cel.paragraphs) > 1 and not primeiro.text and not primeiro._p.xpath(".//w:drawing"):
            primeiro._p.getparent().remove(primeiro._p)
        if cel.paragraphs:
            cel.paragraphs[-1].paragraph_format.space_after = Pt(0)

    def caixa(self, cont, no: Tag, largura: float, cinza: bool) -> None:
        t = self._tabela_caixa(cont, [largura])
        cel = t.cell(0, 0)
        self._preencher_caixa(cel, no, largura, cinza, kpi="kpi" in _classes(no))
        if not cinza:
            for lado in ("top", "left", "bottom", "right"):
                _bordas_celula(cel, **{lado: (LINE, 6)})
        _fmt(cont.add_paragraph(), depois=0, entre=0.6)

    def _kpi(self, cel, no: Tag) -> None:
        mini = "mini" in _classes(no)
        rot, val, obs = no.find(class_="rot"), no.find(class_="val"), no.find(class_="obs")
        if rot is not None:
            self._paragrafo(cel, rot, 6.8, GRAY, depois=1)
        if val is not None:
            pequeno = "pequeno" in _classes(val)
            self._paragrafo(cel, val, 9.5 if (mini or pequeno) else 12, INK, negrito=True, depois=1)
        if obs is not None and _texto(obs):
            self._paragrafo(cel, obs, 6.5, GRAY2, depois=0)

    def grade(self, cont, filhos: list[Tag], n: int, largura: float, kpi: bool = False) -> None:
        """Colunas lado a lado (grid do CSS) → tabela sem borda; cartões cinza ganham borda branca como espaço."""
        n = min(n, len(filhos)) or 1
        col = largura / n
        linhas = [filhos[i:i + n] for i in range(0, len(filhos), n)]
        t = cont.add_table(rows=len(linhas), cols=n)
        _sem_bordas(t)
        _larguras(t, [col] * n)
        branco = ("FFFFFF", GAP_PT * 4)
        for r, linha in enumerate(linhas):
            for c in range(n):
                cel = t.cell(r, c)
                if c >= len(linha):
                    continue
                f = linha[c]
                cl = _classes(f)
                caixa_cinza = kpi or bool(cl & {"coluna-modelo", "kpi"}) or ("quadro" in cl and "destaque" in cl)
                if caixa_cinza:
                    self._preencher_caixa(cel, f, col, True, kpi=kpi or "kpi" in cl)
                    _bordas_celula(cel, top=branco if r else None, bottom=branco if r < len(linhas) - 1 else None,
                                   left=branco if c else None, right=branco if c < n - 1 else None)
                elif "quadro" in cl:
                    self._preencher_caixa(cel, f, col, False)
                    for lado in ("top", "left", "bottom", "right"):
                        _bordas_celula(cel, **{lado: (LINE, 6)})
                else:
                    _margens_celula(cel, 0, 0, esq=0 if c == 0 else 2.0, dir_=0 if c == n - 1 else 2.0)
                    primeiro = cel.paragraphs[0]
                    self.bloco(cel, f, col - 4)
                    if len(cel.paragraphs) > 1 and not primeiro.text and not primeiro._p.xpath(".//w:drawing"):
                        primeiro._p.getparent().remove(primeiro._p)
        _fmt(cont.add_paragraph(), depois=0, entre=0.6)

    def perfil(self, cont, no: Tag, largura: float) -> None:
        colunas = [c for c in no.children if isinstance(c, Tag)]
        lins = [c.find_all(class_="lin") for c in colunas]
        nl = max((len(x) for x in lins), default=0)
        larg = [27.0, largura / 2 - 27.0] * len(colunas)
        t = cont.add_table(rows=nl, cols=2 * len(colunas))
        _sem_bordas(t)
        _larguras(t, larg)
        for r in range(nl):
            for k, col in enumerate(lins):
                ce, cv = t.cell(r, 2 * k), t.cell(r, 2 * k + 1)
                for cel in (ce, cv):
                    _sombra(cel, CINZA)
                    _margens_celula(cel, 2.4, 0.9)
                if r < len(col):
                    rot, val = col[r].find(class_="rot"), col[r].find(class_="val")
                    p = _fmt(ce.paragraphs[0], depois=0)
                    self._inline(p, rot, 7.5, GRAY)
                    p = _fmt(cv.paragraphs[0], depois=0)
                    self._inline(p, val, 7.5, INK)
        _fmt(cont.add_paragraph(), depois=0, entre=0.6)

    # capa --------------------------------------------------------------------
    def capa(self, no: Tag) -> None:
        t = self.doc.add_table(rows=1, cols=1)
        _sem_bordas(t)
        _larguras(t, [LARGURA_UTIL])
        t.alignment = WD_TABLE_ALIGNMENT.CENTER
        linha = t.rows[0]
        linha.height, linha.height_rule = Mm(205), WD_ROW_HEIGHT_RULE.AT_LEAST
        cel = t.cell(0, 0)
        _sombra(cel, PRETO_CAPA)
        _margens_celula(cel, 12, 14)
        img = no.find("img")
        p = _fmt(cel.paragraphs[0], depois=0)
        if img is not None and (img.get("src") or "").startswith("data:image"):
            p.add_run().add_picture(io.BytesIO(b64decode(img["src"].split(",", 1)[1])), width=Mm(55))
        _fmt(cel.add_paragraph(), depois=0, antes=150)
        rot = no.find(class_="rotulo")
        if rot is not None:
            p = _fmt(cel.add_paragraph(), depois=6)
            r = _run(p, _texto(rot), 9, LARANJA, True)
            sp = OxmlElement("w:spacing")
            sp.set(qn("w:val"), "50")
            r._r.get_or_add_rPr().append(sp)
        h1 = no.find("h1")
        if h1 is not None:
            p = _fmt(cel.add_paragraph(), depois=6, entre=1.0)
            _run(p, _texto(h1), 32, "FFFFFF", True)
        razao = no.find(class_="razao")
        if razao is not None:
            _run(_fmt(cel.add_paragraph(), depois=18), _texto(razao), 10, "BFBFBF")
        p = _fmt(cel.add_paragraph(), depois=18)
        p.add_run().add_picture(io.BytesIO(_barra_laranja()), width=Mm(24), height=Mm(1.4))
        dados = no.find(class_="dados")
        if dados is not None:
            itens = [c for c in dados.children if isinstance(c, Tag)]
            for rotulo, valor in zip(itens[::2], itens[1::2]):
                p = _fmt(cel.add_paragraph(), depois=5)
                p.paragraph_format.tab_stops.add_tab_stop(Mm(34))
                _run(p, _texto(rotulo) + "\t", 9.5, GRAY2)
                _run(p, _texto(valor), 9.5, "FFFFFF")
        rod = no.find(class_="rodape")
        if rod is not None:
            p = _fmt(cel.add_paragraph(), depois=0, antes=120, entre=1.4)
            _borda_paragrafo(p, "top", "333333", 6, 8)
            _run(p, _texto(rod), 7.6, GRAY2)
        self._quebra()

    # tabelas -----------------------------------------------------------------
    def tabela(self, cont, no: Tag, largura: float) -> None:
        trs = no.find_all("tr")
        if not trs:
            return
        grade = [[c for c in tr.find_all(["td", "th"], recursive=False)] for tr in trs]
        ncol = max(sum(int(c.get("colspan") or 1) for c in linha) for linha in grade)
        t = cont.add_table(rows=len(trs), cols=ncol)
        _sem_bordas(t)
        _larguras(t, self._larguras_tabela(no, grade, ncol, largura))
        compacta = "compacta" in _classes(no)
        for r, (tr, linha) in enumerate(zip(trs, grade)):
            lcl = _classes(tr)
            c = 0
            for i, celh in enumerate(linha):
                span = int(celh.get("colspan") or 1)
                cel = t.cell(r, c)
                if span > 1:
                    cel = cel.merge(t.cell(r, c + span - 1))
                c += span
                ccl = _classes(celh)
                _margens_celula(cel, 1.6, 0.5 if compacta else 1.0)
                cab = celh.name == "th"
                cor, neg, ita, tam = INK2, None, None, TABELA
                if cab:
                    if "col" in ccl:
                        _sombra(cel, LARANJA_CLARO)
                        cor = INK
                    else:
                        _sombra(cel, INK2)
                        cor = "FFFFFF"
                    neg = True
                else:
                    _bordas_celula(cel, bottom=(LINE, 6))
                    if "total" in lcl:
                        _sombra(cel, CINZA)
                        neg = True
                    elif "col" in ccl:
                        _sombra(cel, LARANJA_CLARO)
                    if "sub" in lcl:
                        neg = True
                    if "margem" in lcl:
                        cor, ita = GRAY, True
                    if "obs-cel" in ccl:
                        cor, tam = GRAY, 7.0
                alinha = WD_ALIGN_PARAGRAPH.RIGHT if "n" in ccl else WD_ALIGN_PARAGRAPH.LEFT
                p = _fmt(cel.paragraphs[0], depois=0, alinha=alinha, entre=1.05)
                if self._tem_bloco(celh):
                    self.blocos(cel, celh, 30)
                else:
                    self._inline(p, celh, tam, cor, neg, ita)
            # linha de cabeçalho repete se a tabela quebrar de página
            if all(x.name == "th" for x in linha) and r == 0:
                trPr = t.rows[0]._tr.get_or_add_trPr()
                h = OxmlElement("w:tblHeader")
                trPr.append(h)
            trPr = t.rows[r]._tr.get_or_add_trPr()
            cs = OxmlElement("w:cantSplit")
            trPr.append(cs)
        _fmt(cont.add_paragraph(), depois=0, entre=0.8)

    def _larguras_tabela(self, no: Tag, grade, ncol: int, largura: float) -> list[float]:
        cl = _classes(no)
        fixas = {"verticais-larga": [24, 6, 42, 28], "riscos": [62, 9, 29], "ativos": [27, 9, 9]}
        for nome, pcts in fixas.items():
            if nome in cl and len(pcts) <= ncol:
                resto = 100 - sum(pcts)
                pcts = pcts + [resto / (ncol - len(pcts))] * (ncol - len(pcts)) if ncol > len(pcts) else pcts
                return [largura * p / 100 for p in pcts]
        pesos = [0.0] * ncol
        for linha in grade:
            c = 0
            for celh in linha:
                span = int(celh.get("colspan") or 1)
                if span == 1:
                    n = len(_texto(celh))
                    pesos[c] = max(pesos[c], min(max(n, 4), 48) if "n" not in _classes(celh) else min(max(n, 6), 16))
                c += span
        pesos = [max(p, 4) for p in pesos]
        tot = sum(pesos)
        return [largura * p / tot for p in pesos]

    # montagem ------------------------------------------------------------
    def converter(self, destino: Path) -> Path:
        self._preparar_imagens()
        corpo = self.soup.body
        primeiro = self.doc.paragraphs[0] if self.doc.paragraphs else None
        self.blocos(self.doc, corpo, LARGURA_UTIL)
        if primeiro is not None and not primeiro.text:
            primeiro._p.getparent().remove(primeiro._p)
        self.doc.core_properties.title = (self.soup.title.get_text() if self.soup.title else "Relatório de valuation")
        self.doc.core_properties.author = "Nova Direção"
        self.doc.save(destino)
        return destino


def _barra_laranja() -> bytes:
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (240, 14), "#FF9900").save(buf, "PNG")
    return buf.getvalue()


def html_para_docx(html: Path, docx: Path, exe: str | None = None) -> Path:
    """relatorio.html → relatorio.docx (abre no Word e importa no Google Docs)."""
    return Conversor(Path(html).read_text(encoding="utf-8"), exe).converter(Path(docx))
