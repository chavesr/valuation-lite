"""Resumo mensal da folha de pagamento (PDF do sistema de folha — layout "RESUMO DA FOLHA"). Zero tokens.

Só totais da empresa: nº de empregados, proventos, pró-labore, FGTS e INSS. Nunca dados por funcionário
(o "extrato mensal por funcionário" não é lido).
"""

from __future__ import annotations

import re
from pathlib import Path

from pydantic import BaseModel

from captacao.schemas import Metodo, Proveniencia
from captacao.util import apenas_digitos, normalizar_texto


class FolhaNaoLida(Exception):
    pass


class FolhaMes(BaseModel):
    cnpj: str | None
    competencia: str
    empregados: int | None
    proventos: float
    pro_labore: float = 0.0
    fgts: float = 0.0
    inss_total: float = 0.0  # empresa + RAT + terceiros + segurados
    inss_segurados: float = 0.0  # parte descontada do empregado
    proveniencia: Proveniencia

    @property
    def custo_empresa(self) -> float:
        """Proventos + FGTS + INSS patronal (sem a parte do empregado, que já está nos proventos)."""
        return round(self.proventos + self.fgts + self.inss_total - self.inss_segurados, 2)


def _n(txt: str | None) -> float:
    return float(txt.replace(".", "").replace(",", ".")) if txt else 0.0


def eh_resumo_folha(texto: str) -> bool:
    n = normalizar_texto(texto[:800])
    return "RESUMO DA FOLHA" in n and "COMPETENCIA" in n


def ler_resumo_folha(caminho: str | Path, paginas: list[str] | None = None) -> list[FolhaMes]:
    caminho = Path(caminho)
    if paginas is None:
        import pdfplumber

        with pdfplumber.open(caminho) as pdf:
            paginas = [p.extract_text() or "" for p in pdf.pages]
    if not paginas or not eh_resumo_folha(paginas[0]):
        raise FolhaNaoLida("não é resumo mensal da folha")
    meses: dict[tuple, FolhaMes] = {}
    for texto in paginas:
        comp = re.search(r"Compet\S+:\s*(\d{2})/(\d{4})", texto)
        if not comp or "PROVENTOS" not in texto.upper():
            continue
        cnpj = re.search(r"CNPJ:\s*([\d./-]+)", texto)
        bloco_prov = texto.upper().split("PROVENTOS", 1)[1].split("DESCONTOS", 1)[0]
        total_prov = re.search(r"TOTAL:\s*([\d.]+,\d{2})", bloco_prov)
        contagens = [int(m.group(1)) for m in re.finditer(r"^\d+\s+[^\n]*?\s(\d+)\s+[\d.]+,\d{2}\s+[\d.]+,\d{2}",
                                                          bloco_prov, flags=re.M)]
        normais = re.search(r"HORAS NORMAIS\s+(\d+)\s", bloco_prov)
        pro_lab = re.search(r"PRO-?LABORE\s+\d+\s+[\d.]+,\d{2}\s+([\d.]+,\d{2})", bloco_prov)
        fgts = re.search(r"F\.?G\.?T\.?S\.? DO M[EÊ]S\s+\d+\s+[\d.]+,\d{2}\s+([\d.]+,\d{2})", texto.upper())
        chave = (apenas_digitos(cnpj.group(1)) if cnpj else None, f"{comp.group(2)}-{comp.group(1)}")
        meses[chave] = FolhaMes(
            cnpj=chave[0], competencia=chave[1],
            empregados=int(normais.group(1)) if normais else (max(contagens) if contagens else None),
            proventos=_n(total_prov.group(1)) if total_prov else 0.0,
            pro_labore=_n(pro_lab.group(1)) if pro_lab else 0.0,
            fgts=_n(fgts.group(1)) if fgts else _n((re.search(r"Valor do FGTS:\s*([\d.]+,\d{2})", texto) or [0, None])[1]),
            inss_total=_n((re.search(r"Total INSS:\s*([\d.]+,\d{2})", texto) or [0, None])[1]),
            inss_segurados=_n((re.search(r"Segurados:\s*([\d.]+,\d{2})", texto) or [0, None])[1]),
            proveniencia=Proveniencia(arquivo=caminho.name, localizacao=f"competência {chave[1]}",
                                      metodo=Metodo.PARSER))
    if not meses:
        raise FolhaNaoLida("nenhuma competência reconhecida")
    return sorted(meses.values(), key=lambda f: (f.competencia, f.cnpj or ""))
