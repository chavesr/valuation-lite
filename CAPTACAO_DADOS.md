# Captação de Dados — Valuation Lite

> Versão 0.1 · 2026-11-06 · Fase 2: estrutura de captação de dados

## 1. Princípio: funil de captação (código primeiro, IA por último)

A maior parte do custo de tokens viria da leitura de documentos. A regra é: **todo documento passa primeiro por código, e só o que o código não resolve chega à IA**, e apenas na parte relevante.

| Nível | Tipo de arquivo | Tratamento | Custo em tokens |
|---|---|---|---|
| 0 | **Estruturados:** SPED ECD/ECF (.txt), extratos OFX/CSV, planilhas XLSX, XML de NF-e | parser Python | **zero** |
| 1 | **PDF com texto:** DRE/BP do contador, PGDAS-D, relatórios do sistema | extração de texto + regras de layout; IA só se a regra falhar, e só nas páginas relevantes | baixo |
| 2 | **PDF escaneado / foto** | OCR → Haiku com esquema fixo | médio |
| 3 | **Texto livre:** entrevista, transcrição, e-mails | Haiku condensa numa ficha estruturada | médio |

**Consequência prática:** pedir ao cliente **SPED, OFX e XLSX** em vez de PDF reduz o custo e aumenta a precisão. Isso deve constar na lista de documentos enviada ao cliente.

## 1.1 Lições do case A (protocolo antigo)

A auditoria do data-room do case A (out/2026) mostrou o problema típico: **muito documento, pouca informação decisiva**.
- **Organização:** arquivos duplicados entre pastas, Excel renomeado como PDF, documentos recebidos misturados com relatórios produzidos (v1…v10).
- **Faltava o essencial:** extratos bancários, PGDAS da empresa do Simples e faturamento mensal por CNPJ. Dos 3 CNPJs do grupo, só a Indústria tinha documentação completa.
- **O briefing contradizia os documentos** sem ser conferido:
  - estoque: R$ 0,7 mi declarado × R$ 6 mi no balanço;
  - fornecedores: "sem dívida" × R$ 2,8 mi;
  - lucro de 2025: três números diferentes;
  - imóvel: alugado × sem contrato.
- **Receita gerencial 28% acima da contábil**, e a sócia admitiu venda sem nota. No novo protocolo, o caso seria **GCI nível C** logo na F3.
- **Documentos inúteis ou sensíveis:** recibos e termos de ECD, CNH da sócia, lista nominal de funcionários com salário.

**Resposta do novo protocolo:** 4 entregas fechadas (kit em `kit_captacao/`), pasta única de entrada, pedido em duas ondas e conferência obrigatória de tudo o que for declarado contra os documentos.

## 1.2 Kit de captação (`kit_captacao/`)

| Entrega | Responsável | Arquivo |
|---|---|---|
| Documentos contábeis e fiscais | contador | `02_Email_Contador.md` |
| Extratos OFX (24 meses, todas as contas) | empreendedor | `01_Guia_Empreendedor.md` |
| Planilha ND de Captação (9 abas, lida por código) | empreendedor | `Planilha_ND_Captacao.xlsx`, gerada por `captacao/planilha_nd.py` |
| Questionário (núcleo + módulos indústria/serviços/comércio) e entrevista | sócios + analista | Google Form gerado por `formulario/criar_formulario.gs`; versão em texto `03_Questionario_Cliente.md`; `04_Roteiro_Entrevista.md` |

**Leitura sem tokens:**

| Entrada | Leitor | O que entrega |
|---|---|---|
| Planilha de respostas do Forms (CSV ou xlsx baixado) | `python -m captacao.questionario respostas.csv --cnpj <CNPJ>` | uma resposta por código (Q01, I02a…), valores convertidos ("4 mi" → 4.000.000), perguntas do caminho sem resposta, alertas de coerência (soma dos % da Parte 0, P03 × % informados) |
| Planilha ND preenchida | `python -m captacao.leitor_planilha_nd planilha.xlsx` | linhas de cada aba, faturamento mensal por CNPJ (vira fonte gerencial do GCI), alertas (CNPJ fora do grupo, meses faltando, participações ≠ 100%, Simples acima de R$ 4,8 mi) |

O catálogo de perguntas vem do próprio `criar_formulario.gs`: **textos de pergunta só se alteram no script**, nunca direto no Google Forms (o leitor reconhece a pergunta pelo título exato).

**Pedido em duas ondas:** a 1ª onda é o kit. Depois da F3 (GCI), o tarantino_agent gera uma **lista de pendências específica do case**. Nada de pedido genérico.

**Não pedir:** documentos pessoais, Cartão CNPJ e certidões (consulta automática pelo CNPJ), notas fiscais individuais, recibos e termos de SPED, dados nominais de funcionários.

## 2. Estrutura padrão da pasta da empresa no Drive

```
Drives compartilhados/<drive da boutique>/Empresas/<NOME_EMPRESA>/
├── 00_recebidos/     ← ÚNICA pasta em que o empreendedor/contador deposita (sem organizar)
├── 01_Contabil/      DRE, Balanço, Balancetes, SPED ECD/ECF
├── 02_Fiscal/        PGDAS-D, DAS, parcelamentos, certidões (CND)
├── 03_Bancario/      extratos (OFX/CSV preferencialmente), por conta e CNPJ
├── 04_Gerencial/     planilhas de faturamento, clientes, custos
├── 05_Societario/    contrato social, alterações, CNPJs do grupo
├── 06_Comercial/     contratos com clientes, carteira, top clientes
├── 07_Passivos/      empréstimos, financiamentos, processos
├── 08_Entrevista/    ficha de entrevista, gravações/transcrições
└── _valuation/       ← criada pelo tarantino_agent (saídas do case)
```

A F1 (ingestão) lê `00_recebidos/` e classifica cada arquivo pelo nome e conteúdo, primeiro por regra e, se necessário, com Haiku. Em seguida:
- copia o arquivo para a pasta 01–08 correta, com nome padronizado (`AAAA_tipo_CNPJ.ext`);
- descarta duplicatas pelo hash do conteúdo;
- registra no inventário os arquivos inúteis (recibos de SPED, documentos pessoais).

Os originais nunca são alterados, e as saídas ficam em `_valuation/`.

## 3. Período de análise

- **Histórico:** últimos 3 exercícios fechados (anual) + ano corrente (mensal).
- **Extratos e PGDAS:** mensal, nos últimos 24 meses no mínimo (base da triangulação do GCI).

## 4. Dicionário de dados: o que captar (e o que ignorar)

### DRE (por exercício)
Receita bruta · deduções/impostos sobre venda · receita líquida · CMV/CSP · despesas com pessoal · **pró-labore** · despesas administrativas · comerciais · aluguel · D&A · outras receitas e despesas · resultado financeiro · IR/CS · lucro líquido.

### Balanço Patrimonial (por exercício)
Caixa e aplicações · contas a receber · estoques · imobilizado (bruto e líquido) · fornecedores · obrigações trabalhistas · obrigações fiscais · **parcelamentos fiscais** · empréstimos CP e LP · mútuos com sócios · patrimônio líquido.

### PGDAS-D (mensal, por CNPJ)
Receita bruta declarada no mês · RBT12 · anexo · alíquota efetiva · valor do DAS.

### Extratos bancários (por transação)
Data · valor · descrição · contraparte (quando houver) · conta · CNPJ titular → **classificação** (seção 5).

### Gerencial
Faturamento mensal · faturamento por cliente (para concentração) · por produto/linha · custos diretos.

### Comercial
Top 10 clientes (% da receita) · contratos: **prazo, valor, renovação, multa de rescisão**. Do contrato, extrair só esses campos, não o texto inteiro.

### Societário
CNPJs do grupo econômico · sócios e participações · data de abertura · CNAE.

### Passivos
Saldo, taxa e prazo de cada dívida · parcelamentos · processos (valor e probabilidade, se informados).

### O que NÃO ler
- Notas fiscais individuais: usar totais (relatório do emissor ou XML agregado por código).
- Contratos na íntegra: só as cláusulas da lista acima.
- Documentos fora do período de análise.
- Páginas de PDF sem números relevantes (capas, notas explicativas genéricas), filtradas por código antes de qualquer chamada à IA.

## 5. Extratos bancários: a base dos casos nível B e C

Os extratos são o maior volume de dados e, nas empresas informais, a fonte mais confiável. Pipeline:

1. **Leitura:** OFX/CSV por parser. PDF de extrato por regras de layout por banco (Itaú, Bradesco, BB, Caixa, Santander, Inter, Nubank, Sicoob…).
2. **Classificação por regras (código):**
   - transferências entre contas do próprio grupo, identificadas por CNPJ/CPF dos sócios e contas cadastradas → **excluir da receita**;
   - empréstimos recebidos, resgates de aplicação, aportes de sócios → **excluir da receita**;
   - tarifas, impostos (DAS), folha, fornecedores recorrentes → categorias de despesa.
3. **IA só para o que sobrar:** as descrições não classificadas são **deduplicadas** (ex.: "PIX RECEBIDO FULANO" aparece 200 vezes e é classificado uma vez só) e enviadas em lote ao Haiku. As novas regras aprendidas são salvas e reaproveitadas nos próximos cases.
4. **Saída:** receita de caixa mensal, despesas por categoria e retiradas dos sócios, que alimentam a triangulação do GCI e a DRE econômica.

## 6. Ficha de entrevista (insumo qualitativo)

Em vez de a IA ler horas de transcrição, o analista preenche (ou o Haiku condensa a partir da transcrição) uma **ficha estruturada**, que alimenta diretamente o Score de Risco:

| Bloco | Perguntas-chave |
|---|---|
| Dono | Quantas horas por semana dedica? Quem decide na sua ausência? Clientes compram por causa dele? |
| Equipe | Há gerentes ou líderes? Tempo médio de casa? |
| Clientes | Top 5 e % da receita? Contratos ou compra avulsa? Taxa de perda de clientes? |
| Receita | Quanto é faturado sem nota (estimativa)? Por que há mais de um CNPJ? |
| Operação | Fornecedores críticos? Ponto comercial próprio ou alugado? Licenças essenciais? |
| Mercado | Principais concorrentes? Por que o cliente escolhe a empresa? |
| Passivos | Dívidas fora do balanço? Processos? Parcelamentos? |
| Venda | Motivo da venda? O dono fica na transição? Por quanto tempo? |

## 7. Saída da captação: `dados_brutos.json`

Todo número captado guarda a sua **proveniência** (arquivo, página/linha, método: parser/regra/IA). Isso permite auditoria e mostrar no report de onde veio cada dado.

```json
{
  "receita_bruta": {
    "2025": { "valor": 4320000.00,
              "fonte": "01_Contabil/DRE_2025.pdf", "pagina": 1,
              "metodo": "regra_layout", "confianca": "alta" }
  }
}
```

## 8. Lista de documentos para o cliente (por prioridade)

| Prioridade | Documento | Formato preferido |
|---|---|---|
| Essencial | Extratos bancários de todas as contas (24 meses) | OFX ou CSV |
| Essencial | PGDAS-D (24 meses) de todos os CNPJs | PDF do portal |
| Essencial | DRE e Balanço (3 exercícios) | PDF ou SPED ECD |
| Essencial | Faturamento mensal e por cliente | XLSX |
| Importante | Contrato social e CNPJs relacionados | PDF |
| Importante | Relação de dívidas e parcelamentos | XLSX / PDF |
| Importante | Contratos com principais clientes | PDF |
| Desejável | SPED ECD/ECF · XML de NF-e · balancetes mensais | arquivo original |

Com só os documentos essenciais já é possível chegar a GCI nível B ou C. Os demais elevam a confiabilidade e reduzem o prêmio de risco, **o que é um argumento comercial para o cliente entregar mais informação**.

## 9. Próximos passos desta fase

1. Definir os esquemas de dados (Pydantic) de `dados_brutos.json`.
2. Implementar os parsers de nível 0: OFX/CSV, XLSX, SPED.
3. Implementar a classificação de extratos por regras.
4. Implementar a triangulação e o cálculo do GCI.
5. Testar com um conjunto fictício (empresa nível A e empresa nível C).
6. ✅ Leitores do questionário (Forms) e da Planilha ND.
6a. ✅ Montagem do case: `python -m tarantino abrir "<pasta da empresa>"` → inventário, `dados_brutos.json`, GCI e `pendencias.md` em `_valuation/` (originais não são movidos; PGDAS/DRE digitados em `_valuation/entrada_manual.json` até existirem os parsers).
7. ✅ DRE e Balanço em PDF com texto (`captacao/parsers/demonstracoes_pdf.py`): layout do visualizador SPED/ECD e de sistemas contábeis (D/C); hierarquia pela indentação, conferência de somas, comparativo do ano anterior e alerta de contabilidade reapresentada. Validado em 5 PDFs reais do case A. PDFs escaneados viram pendência.
8. ✅ DRE gerencial em Excel (`captacao/parsers/gerencial_xlsx.py`): formatos largo (meses nas colunas) e longo (meses nas linhas); grupos por negrito; contas classificadas em categorias econômicas por regras, herança do grupo ou `_valuation/mapa_gerencial.json` (analista/IA, só os nomes das contas); separa operação × financeiro × investimento × financiamento; confere grupo × contas e acumulado × meses; no case, compara receita gerencial × contábil por ano e vira fonte gerencial do GCI quando não há Planilha ND. Validado nas 4 DREs gerenciais do case A.
9. ✅ Aprendizados do case B (fora do Simples, 3 bancos): OFX do Itaú traz linhas de SALDO como lançamento (ignoradas); históricos BB/Sicredi/Itaú nas regras (créditos não classificados 87% → 0,7%); arquivos mensais juntados por conta; empresa do grupo reconhecida pelo nome distintivo; layout contábil "Código | Classificação | Saldo | Total"; "DRE gerencial" em PDF comparada linha a linha com a contábil (valores redondos = ajuste manual); GCI sem PGDAS compara o caixa com a DRE contábil do período dos extratos; pendência de contas não enviadas quando há transferências líquidas relevantes de contas próprias.
10. ✅ Extrato bancário em PDF (`captacao/parsers/extrato_pdf.py`): Banco do Brasil, Sicredi e Itaú (detalhado). Autoconferência pelos saldos do próprio extrato; ignora "Lançamentos Futuros" e lançamentos fora do período; usa a data do movimento (como o OFX). Validado contra os OFX do case B: 9 meses BB, 9 Sicredi e 9 Itaú batem lançamento a lançamento (≈3.800 saldos conferidos). No case, o OFX tem prioridade: PDF do mesmo mês/conta vira duplicata; só PDF → mesmo resultado (GCI idêntico).
11. ✅ SPED Fiscal — EFD ICMS/IPI (`captacao/parsers/sped_efd.py`), lido direto do .zip: venda por CFOP separada de transferência entre estabelecimentos, devolução, compra, importação e remessas; retificadora prevalece sobre a original; concentração de clientes só entre empresas (pessoa física = varejo/e-commerce, sem nome); vira a receita declarada do GCI para empresas fora do Simples (`FiscalMes`). Validado no case B (matriz + filial, jan–set/2026): vendas do 1º semestre batem com a DRE contábil.
12. ✅ Relatórios do ERP em .xls/.xlsx (`captacao/parsers/relatorios_erp.py`), reconhecidos pelas colunas: contas a receber (aberto, atraso, prazo médio), contas a pagar/pagas (parcelamentos e dívida ativa), faturamento por produto (normal × fulfillment; confere com o SPED por mês e estabelecimento), estoque com custo (confere com o Balanço; itens negativos/sem custo), colaboradores PJ (só quantidade e total).
13. ✅ Posições de empréstimo em PDF (`captacao/parsers/emprestimos_pdf.py`: BB consolidado/operação/histórico, Sicredi descritivo/consulta) → dívida por contrato, conferida com o Balanço. Resumo da folha em PDF (`captacao/parsers/folha_pdf.py`, só totais). Inventário: caminhos longos do Windows, DANFE avulsa (coberta pelo SPED), dados individuais de funcionário (não lidos), zips já extraídos (comparação por conteúdo, inclusive zip dentro de zip).
14. ✅ Simples Nacional em PDF (`captacao/parsers/pgdas_pdf.py`): Extrato do PGDAS-D (receita do PA + até 18 meses anteriores, RBT12, sublimite, tributos, DAS e pagamento; retificação detectada quando um extrato posterior cita outro valor) e DEFIS (estoque, caixa, compras, empregados, rendimentos dos sócios). Validado no case C (1 extrato = 19 meses de receita). Extrato bancário exportado em planilha (`captacao/parsers/extrato_planilha.py`) e rankings de clientes/produtos do ERP.
15. Próximos: ECD (.txt, aguardando amostra), EFD-Contribuições, novos layouts de banco (case D), certidões/relatório de situação fiscal (CND, débitos).
