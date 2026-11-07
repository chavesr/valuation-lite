"""SPED Fiscal (EFD ICMS/IPI) — arquivos sintéticos no layout oficial (sem dados de clientes)."""

import zipfile

from captacao.parsers.sped_efd import concentracao_clientes, consolidar, eh_efd_icms, ler_efd, ler_efd_texto
from captacao.schemas import (DadosBrutos, Empresa, EmpresaGrupo, ExtratoConta, FiscalMes, Metodo, Proveniencia,
                              Transacao, Categoria)
from engine.gci import calcular_gci


def _efd(cnpj="11222333000181", mes="01", finalidade="0"):
    linhas = [
        f"|0000|020|{finalidade}|01{mes}2026|31{mes}2026|EMPRESA TESTE LTDA|{cnpj}||SC|123|4204608|||B|0|",
        "|0150|C001|CLIENTE A &amp; FILHOS LTDA|1058|22333444000100||1||||||",
        "|0150|C002|FULANO DE TAL|1058||12345678909|||||||",
        "|0150|F001|FORNECEDOR CHINA|5860|||||||||",
        "|0150|FIL|EMPRESA TESTE LTDA - FILIAL|1058|11222333000262||||||||",
        # venda a empresa (1.000) + venda a consumidor final interestadual (600)
        "|C100|1|0|C001|55|00|1|1|chave1|05012026|05012026|1000|0|0|0|1000|0|0|0|0|1000|0|0|0|0|0|0|0|0|",
        "|C190|000|5102|18|1000|1000|180|0|0|0|0||",
        "|C100|1|0|C002|55|00|1|2|chave2|06012026|06012026|600|0|0|0|600|0|0|0|0|600|0|0|0|0|0|0|0|0|",
        "|C190|000|6108|12|600|600|72|0|0|0|0||",
        # nota cancelada: não conta
        "|C100|1|0|C001|55|02|1|3|chave3|07012026|07012026|5000|0|0|0|5000|0|0|0|0|5000|0|0|0|0|0|0|0|0|",
        "|C190|000|5102|18|5000|5000|900|0|0|0|0||",
        # transferência para a filial: não é receita
        "|C100|1|0|FIL|55|00|1|4|chave4|08012026|08012026|3000|0|0|0|3000|0|0|0|0|3000|0|0|0|0|0|0|0|0|",
        "|C190|000|5152|18|3000|3000|540|0|0|0|0||",
        # devolução de venda (entrada) e importação
        "|C100|0|1|C001|55|00|1|5|chave5|09012026|09012026|100|0|0|0|100|0|0|0|0|100|0|0|0|0|0|0|0|0|",
        "|C190|000|1202|18|100|100|18|0|0|0|0||",
        "|C100|0|0|F001|55|00|1|6|chave6|10012026|10012026|2000|0|0|0|2000|0|0|0|0|2000|0|0|0|0|0|0|0|0|",
        "|C190|000|3102|4|2000|2000|80|0|0|0|0||",
        "|E110|1000|0|0|0|500|0|0|0|0|500|0|420,50|0|0|",
        "|9999|20|",
    ]
    return "\n".join(linhas)


def test_le_efd_separa_venda_transferencia_devolucao_e_importacao():
    e = ler_efd_texto(_efd(), "efd.txt")
    assert (e.cnpj, e.competencia, e.substituto) == ("11222333000181", "2026-01", False)
    assert e.vendas == 1600 and e.devolucoes_venda == 100 and e.venda_liquida == 1500
    assert e.transferencias_saida == 3000 and e.compras == 2000 and e.importacoes == 2000
    assert (e.notas_saida, e.notas_canceladas) == (4, 1)
    assert e.icms_a_recolher == 420.50
    assert e.clientes[0].nome == "CLIENTE A & FILHOS LTDA" and e.clientes[1].pessoa_fisica


def test_concentracao_separa_pessoa_fisica_e_ignora_o_proprio_grupo():
    c = concentracao_clientes([ler_efd_texto(_efd(), "efd.txt")], raiz_cnpj_grupo={"11222333"})
    assert c["pessoas_fisicas"] == 0.375  # 600 de 1.600
    assert c["maior"] == 0.625 and c["clientes_pj"] == 1
    assert c["ranking"][0]["cliente"] == "CLIENTE A & FILHOS LTDA"


def test_zip_e_substituto_prevalece(tmp_path):
    arq = tmp_path / "Sped Matriz.zip"
    with zipfile.ZipFile(arq, "w") as zf:
        zf.writestr("Sped/original-jan.txt", _efd(finalidade="0").encode("latin-1"))
        zf.writestr("Sped/substituto-jan.txt", _efd(finalidade="1").replace("|1000|0|0|0|1000|", "|1200|0|0|0|1200|")
                    .replace("|5102|18|1000|1000|", "|5102|18|1200|1200|").encode("latin-1"))
        zf.writestr("__MACOSX/Sped/._original-jan.txt", b"lixo")
        zf.writestr("leia-me.txt", b"nao e sped")
    efds = consolidar(ler_efd(arq))
    assert len(efds) == 1 and efds[0].substituto and efds[0].vendas == 1800
    assert eh_efd_icms(_efd().splitlines()[0]) and not eh_efd_icms("|0000|LECD|01012025|31122025|X|")


def test_gci_usa_efd_como_receita_declarada():
    prov = Proveniencia(arquivo="x", metodo=Metodo.PARSER)
    caixa = [Transacao(data=__import__("datetime").date(2026, m, 10), valor=500_000, descricao="PIX RECEBIDO",
                       categoria=Categoria.RECEITA_OPERACIONAL) for m in range(1, 4)]
    fiscal = [FiscalMes(cnpj=c, competencia=f"2026-0{m}", receita_bruta=600_000, devolucoes=100_000,
                        fonte="EFD ICMS/IPI", proveniencia=prov) for m in range(1, 4) for c in ("1", "2")]
    dados = DadosBrutos(empresa=Empresa(nome="X", cnpjs=[EmpresaGrupo(cnpj="11222333000181", razao_social="X"),
                                                          EmpresaGrupo(cnpj="11222333000262", razao_social="X")]),
                        periodo_inicio="2026-01", periodo_fim="2026-03",
                        extratos=[ExtratoConta(transacoes=caixa, proveniencia=prov)], fiscal_mensal=fiscal)
    g = calcular_gci(dados)
    assert g.receita_fiscal_12m == 3_000_000  # 2 estabelecimentos × 3 meses × (600 mil − 100 mil)
    assert g.metricas["gap_fiscal"] == -1.0  # declarado (1 mi/mês) é o dobro do caixa (500 mil/mês)
    texto = " | ".join(g.alertas)
    assert "(EFD ICMS/IPI)" in texto and "1 empresa" not in texto and "2 estabelecimentos" in texto
