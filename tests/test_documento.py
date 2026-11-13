"""Relatório em Word (relatorio.html → relatorio.docx para o Google Docs): mesmo conteúdo do PDF, sem texto próprio."""

import io

from docx import Document
from PIL import Image

from relatorio import documento
from relatorio.icones import icone

HTML = f"""<!doctype html><html><head><title>Valuation — Teste</title></head><body>
<section class="capa"><div class="meio"><div class="rotulo">RELATÓRIO DE VALUATION</div><h1>Empresa Teste</h1>
<div class="razao">EMPRESA TESTE LTDA</div><div class="traco"></div>
<div class="dados"><b>Setor</b><span>Serviços</span><b>Data</b><span>novembro de 2026</span></div></div>
<div class="rodape">Documento confidencial.</div></section>
<div class="cab"><h2>01. Visão geral | Empresa Teste</h2><div class="sub">Setor: Serviços</div></div>
<div class="quadro destaque"><h3>{icone("empresa")} A empresa</h3><p>Texto com <b>negrito</b> e <small>nota</small>.</p></div>
<div class="kpis"><div class="kpi"><div class="rot">{icone("receita", tam=11)} Receita</div><div class="val">R$ 8,81 mi</div>
<div class="obs">LTM</div></div><div class="kpi"><div class="rot">EBITDA</div><div class="val">R$ 307 mil</div></div></div>
<div class="duas"><div class="secao"><h3>Por que olhar</h3><ul class="marcador"><li>Ponto um</li><li>Ponto dois</li></ul>
<svg viewBox="0 0 600 200" width="100%"><rect width="600" height="200" fill="#FF9900"/></svg></div>
<div class="secao"><h3>Tabela</h3><table class="compacta"><tr><th>R$ mil</th><th class="n">2025</th></tr>
<tr><td>Receita</td><td class="n">10.352</td></tr><tr class="total"><td>Total</td><td class="n">10.352</td></tr></table></div></div>
<section class="capitulo"><div class="cab"><h2>02. Sobre a empresa | Empresa Teste</h2></div>
<div class="nota">Nota de rodapé.</div></section></body></html>"""


def _falso_rasterizar(svgs, caixas, larguras, exe=None, **_):
    saida = []
    for (w, h), lp in zip(caixas, larguras):
        buf = io.BytesIO()
        Image.new("RGB", (lp, max(1, round(lp * h / w))), "white").save(buf, "PNG")
        saida.append(buf.getvalue())
    return saida


def test_html_vira_docx_com_o_mesmo_conteudo(tmp_path, monkeypatch):
    monkeypatch.setattr(documento, "rasterizar", _falso_rasterizar)
    html = tmp_path / "relatorio.html"
    html.write_text(HTML, encoding="utf-8")
    destino = documento.html_para_docx(html, tmp_path / "relatorio.docx")
    doc = Document(destino)

    def textos(tabelas, acc):
        for t in tabelas:
            for linha in t.rows:
                for c in linha.cells:
                    acc.extend(p.text for p in c.paragraphs)
                    textos(c.tables, acc)
        return acc

    tudo = " | ".join([p.text for p in doc.paragraphs] + textos(doc.tables, []))
    for trecho in ("Empresa Teste", "01. Visão geral", "A empresa", "Texto com negrito e nota.", "R$ 8,81 mi",
                   "R$ 307 mil", "Ponto um", "10.352", "02. Sobre a empresa", "Nota de rodapé."):
        assert trecho in tudo, trecho
    assert [p.text for p in doc.paragraphs if p.style.name == "Heading 1"] == [
        "01. Visão geral | Empresa Teste", "02. Sobre a empresa | Empresa Teste"]
    # gráfico e ícones viram imagens; capa preta e cartões cinza viram células sombreadas
    assert len(doc.inline_shapes) >= 1
    xml = doc.element.xml
    assert 'w:fill="111111"' in xml and 'w:fill="F2F2F2"' in xml and 'w:fill="1A1A1A"' in xml
    assert "PAGE" in doc.sections[0].footer._element.xml


def test_icone_e_grafico_sao_separados():
    from bs4 import BeautifulSoup
    s = BeautifulSoup(icone("empresa") + '<svg viewBox="0 0 600 200" width="100%"></svg>', "html.parser")
    ic, gr = s.find_all("svg")
    assert documento._e_icone(ic) and not documento._e_icone(gr)
    assert documento._caixa_svg(gr) == (600.0, 200.0)
