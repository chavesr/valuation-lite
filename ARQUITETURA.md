# Arquitetura — Valuation Lite (tarantino_agent)

> Versão 0.1 · 2026-11-06 · Fase 1: desenho de arquitetura

## 1. Objetivo

Sistema que produz um **report de valuation em PDF** para PMEs brasileiras (faturamento até ~R$10 mi, majoritariamente Simples Nacional), com análise fundamentalista (Graham/Buffett), adaptado à metodologia da boutique, com **baixo custo de tokens** e **design fixo**.

## 2. Princípios de projeto

1. **A IA interpreta e escreve; o código calcula e diagrama.** Nenhum número do valuation é calculado por LLM. O PDF é gerado por template.
2. **Orquestração determinística.** O `tarantino_agent` é código Python com estados definidos; a IA é chamada apenas em fases que exigem julgamento.
3. **A confiabilidade da informação define o caminho da análise.** Antes de calcular qualquer valor, o sistema mede o Grau de Confiabilidade da Informação (GCI).
4. **Conservadorismo por padrão.** DCF sem perpetuidade, salvo justificativa aprovada no teste de perpetuidade; margem de segurança explícita; faixa de preço em vez de ponto único.
5. **Humano no circuito.** Checkpoints de aprovação nas etapas críticas, o que é obrigatório para uso por analistas e estagiários.
6. **Tudo auditável.** Cada case registra fontes, premissas, ajustes, decisões, modelo usado e custo.

## 3. Visão geral do fluxo

```
                    ┌──────────────────────────────────────┐
                    │          tarantino_agent             │
                    │  (orquestrador · estado · custos)    │
                    └──────────────────────────────────────┘
                                     │
 F0 Abertura do case ── cria pasta, ID, state.json
          │
 F1 Ingestão ─────────── classifica documentos recebidos      [código + Haiku]
          │
 F2 Extração ─────────── documentos → JSON padronizado        [Haiku]
          │
 F3 GCI ──────────────── triangulação de receitas, nível A/B/C [código]
          │                  ▶ CHECKPOINT 1: aprovar GCI e caminho
 F4 Normalização ─────── DRE econômica, ajustes, consolidação   [Sonnet + código]
          │                  ▶ CHECKPOINT 2: aprovar ajustes
 F5 Análise qualitativa ─ checklist Graham/Buffett, riscos      [Sonnet]
          │
 F6 Motor de valuation ── DCF finito, EPV, múltiplos, piso      [código]
          │
 F7 Revisão cética ────── coerência, outliers, red flags        [Opus]
          │                  ▶ CHECKPOINT 3: aprovar preço e textos
 F8 Redação + PDF ─────── textos curtos → template → PDF        [Sonnet + código]
          │
 F9 Fechamento ────────── arquiva, trilha de auditoria, custo    [código]
```

## 4. O orquestrador: tarantino_agent

**Responsabilidades**
- Abrir o case: gerar ID (`ND-AAAA-NNN`), criar a pasta e o `state.json`.
- Executar as fases em ordem, validar a saída de cada uma contra o esquema e permitir retomar de qualquer fase.
- Pausar nos checkpoints e aguardar aprovação ou correção humana.
- Registrar custo (tokens e US$) por fase e modelo.
- Fechar o case: gerar o PDF final, o log de auditoria e marcar o status como `fechado`.

**Estados do case:** `aberto → ingerido → extraído → gci_definido → normalizado → analisado → avaliado → revisado → emitido → fechado` (ou `pausado`/`rejeitado`, com o motivo).

**Regras**
- Uma fase só roda se a anterior passou na validação.
- Reexecutar uma fase invalida as fases seguintes, sem apagar o histórico.
- Toda chamada de LLM recebe apenas o JSON da fase anterior, nunca os documentos brutos novamente (exceto na F2).

## 5. Fases e agentes

| Fase | Executor | Modelo | Entrada | Saída |
|---|---|---|---|---|
| F1 Ingestão | código + agente classificador | Haiku 5.5 | arquivos brutos | `inventario.json` (tipo, período e CNPJ de cada documento) |
| F2 Extração | agente extrator | Haiku 5.5 | documentos | `dados_brutos.json` (DRE, BP, extratos, PGDAS, gerencial) |
| F3 GCI | código | nenhum | dados brutos | `gci.json` (índice, nível, divergências) |
| F4 Normalização | agente analista contábil + código | Sonnet 5.5 | dados + GCI | `dre_economica.json`, `ajustes.json` |
| F5 Qualitativa | agente analista fundamentalista | Sonnet 5.5 | dados normalizados + entrevista/briefing | `qualitativo.json` (fosso, gestão, riscos, notas) |
| F6 Valuation | motor Python | nenhum | normalizado + qualitativo + mercado | `valuation.json` (métodos, faixa, sensibilidade) |
| F7 Revisão | agente revisor cético | Opus 5.5 | resumo de todos os JSONs | `revisao.json` (alertas, severidade, sugestões) |
| F8 Redação | agente redator + renderizador | Sonnet 5.5 | todos os JSONs | `textos.json` → `report.pdf` |

Os agentes são **chamadas únicas com saída estruturada** (JSON validado por esquema), e não agentes autônomos em loop. Isso reduz o custo e torna o resultado previsível.

**Como o agente é executado** (decisão de 07/11/2026; pacote `julgamento/`): o tarantino grava um pacote (`_valuation/f5_entrada.md`) com as instruções (`agents/`), os playbooks (`metodologia/playbooks/`), os fatos do case e o esquema da resposta. O pacote pode ser executado de três modos:
- `claude-code` (padrão): roda `claude -p` com a conta logada, numa pasta neutra, sem acesso aos arquivos do cliente.
- `manual`: Claude Code interativo, claude.ai ou o próprio analista gravam `f5_saida.json`, e depois roda-se `--importar`.
- `api`: reservado para quando houver chave da API.

O código só aceita JSON que passe na validação (`julgamento/esquemas.py`). As notas da F5 entram no Score como "F5 (proposta)", ainda pendentes, e o analista as aprova em `score_notas.json`.

## 6. Grau de Confiabilidade da Informação (GCI)

**Triangulação da receita** (por período e por CNPJ):

| Fonte | Representa |
|---|---|
| DRE / SPED | receita contábil |
| PGDAS (Simples) | receita declarada ao fisco |
| Créditos em extratos bancários (líquidos de transferências entre contas, empréstimos e aportes) | caixa real |
| Planilhas gerenciais | visão do dono |

**Índice:** é calculado por código a partir das divergências entre as fontes, da cobertura documental (meses disponíveis vs. período analisado) e da existência de documentos-chave.

| Nível | Critério (a calibrar nos cases) | Caminho de análise |
|---|---|---|
| **A** | fontes convergem (divergência < ~10%) | DRE contábil ajustada; DCF completo |
| **B** | divergência moderada; contabilidade parcial | DRE reconstruída a partir dos extratos + gerencial; prêmio de risco moderado |
| **C** | informalidade relevante (receita sem nota, CNPJs múltiplos, contabilidade inútil) | DRE econômica pelo caixa; faixa de preço mais larga; prêmio de risco alto; peso maior em EPV e no piso patrimonial |

**Regras de informalidade** (tratadas na F4):
- **Grupo econômico:** CNPJs com operação comum são consolidados numa única empresa econômica.
- **Carga tributária real:** se a receita consolidada ultrapassa o limite do Simples (R$ 4,8 mi), a projeção usa o regime que o comprador efetivamente teria (Lucro Presumido ou Real).
- **Receita não declarada:** entra no fluxo apenas na proporção formalizável. O passivo fiscal potencial é tratado como **contingência que reduz o preço**.

## 6.1 Normalização (F4) — implementada

`python -m tarantino normalizar "<pasta>"` (depois de `abrir`) grava `dre_economica.json`, `normalizacao.md` e `ajustes_decisoes.json` (Checkpoint 2). Parâmetros em `metodologia/parametros_normalizacao.json` (a calibrar).

- **Períodos:** LTM (12 meses de receita mensal) e os 2 últimos exercícios com DRE de 12 meses.
- **Receita econômica:** declarada (PGDAS/SPED/DRE) → gerencial se o caixa confirmar ≥ 90% → caixa se os extratos cobrirem ≥ 75% do período e mostrarem receita > 5% acima da declarada (a diferença vira contingência fiscal no valuation) → gerencial sem confirmação só quando não há outra fonte (confiança baixa).
- **Custos:** da mesma fonte da receita quando gerencial; senão DRE contábil (CMV proporcional à receita econômica, despesas fixas pelo valor contábil, juros/IOF e depreciação fora do EBITDA); sem DRE, caixa (confiança baixa). DRE reapresentada (comparativo do livro seguinte) prevalece sobre a original.
- **Tributos do comprador:** Simples (alíquota efetiva do PGDAS) até R$ 4,8 mi; acima, Lucro Presumido.
- **Ajustes:** metodologia (aplicados): pró-labore de mercado. Julgamento (propostos até aprovação): despesas pessoais (Q25), aba 9_Ajustes da Planilha ND, encargos sobre PJ.
- **Saída:** EBITDA, EBIT, lucro econômico, owner earnings (lucro + D&A − capex de manutenção).

## 7. Motor de valuation (código, zero tokens)

**Métodos**
1. **DCF de horizonte finito** (padrão: 5–7 anos), com valor terminal igual a zero ou ao valor de liquidação dos ativos.
2. **DCF com perpetuidade**, apenas se aprovado no teste de perpetuidade (abaixo).
3. **EPV (Earnings Power Value):** lucro sustentável sem crescimento, como âncora conservadora.
4. **Owner earnings (Buffett):** lucro líquido ajustado + D&A − capex de manutenção ± variação de capital de giro.
5. **Múltiplos de mercado** como checagem cruzada, nunca como método principal.
6. **Piso patrimonial:** valor de liquidação ordenada dos ativos.

**Teste de perpetuidade** (pontuação com critérios escritos; os pesos serão definidos com você):
- contratos de longo prazo / receita recorrente;
- estrutura organizacional que independe do dono;
- anos de mercado e histórico de resiliência;
- diversificação de clientes;
- GCI nível A ou B.

**Taxa de desconto (metodologia da boutique):** `taxa total = Selic + prêmio de risco`, com a **taxa total entre 20% e 35% a.a.** (revisado em 06/11/2026; antes 20–50%), definida pelo **Score de Risco do Negócio** (abaixo). O prêmio é a diferença entre a taxa total e a Selic vigente. O CAPM com beta Damodaran fica apenas como referência comparativa no anexo, sem entrar no cálculo.

**Score de Risco do Negócio (0 = menor risco, 100 = maior risco).** Pesos e faixas iniciais, a calibrar nos cases:

| Dimensão | Peso | Como é medida |
|---|---|---|
| Confiabilidade da informação (GCI) | 15 | código (F3) |
| Dependência do dono (key-person) | 15 | ficha de entrevista + agente, com aprovação humana |
| Concentração de clientes (top 1 / top 5) | 10 | código (gerencial / extratos) |
| Recorrência de receita e contratos | 10 | código + agente (contratos) |
| Histórico e tempo de mercado | 10 | código (data de abertura do CNPJ, série histórica) |
| Estabilidade de resultados (volatilidade de receita e margem) | 10 | código |
| Endividamento e liquidez | 10 | código (BP, parcelamentos) |
| Contingências (fiscal, trabalhista, informalidade) | 10 | código + agente |
| Setor e posição competitiva (fosso) | 10 | agente, com aprovação humana |

Cada dimensão recebe nota de 1 a 5 na **escala da ND: 5 = melhor (risco mínimo), 1 = pior (risco máximo)** (adotada em 07/11/2026). A nota é convertida em pontos de risco: peso × (5 − nota) / 4. Dimensões objetivas são calculadas por código. Nas subjetivas, o agente propõe a nota com evidências e o humano aprova no Checkpoint 2.

**Do score para a taxa e o horizonte:**
- `taxa total = 20% + 15% × (score / 100)` (faixa em `metodologia/parametros_valuation.json`), com piso de `Selic + 5 p.p.`.
- Dimensão sem informação recebe nota neutra (3), marcada como pendente; o relatório mostra a **taxa provisória** (faixa se as pendentes forem 1 ou 5).
- `prêmio implícito = taxa total − Selic`. O report mostra os dois.
- Horizonte do DCF: score ≤ 35 → **5 anos** · 35–65 → **4 anos** · > 65 → **3 anos**.
- Perpetuidade: somente com score ≤ 30 **e** aprovação no teste de perpetuidade.

**Checagem de sanidade:** com taxas de 20–35% e horizontes de 3–5 anos, o valor fica em torno de **1,7× a 3,0× o fluxo de caixa anual** (fator de anuidade). Isso é coerente com a prática de mercado para PMEs e serve como alerta automático: se o resultado sair dessa faixa sem perpetuidade, alguma premissa precisa ser revista.

**Saída:** a faixa de preço justo (conservador, base, otimista), o **preço com margem de segurança**, a sensibilidade das premissas e a reconciliação entre os métodos com os pesos usados.

## 7.1 Implementação (F6)

`python -m tarantino avaliar "<pasta>"` (depois de `normalizar`) grava `score_notas.json`, `valuation.json` e `valuation.md`. Parâmetros em `metodologia/parametros_valuation.json` (a calibrar); Selic do Banco Central (SGS 432) com cache em `market_data/cache/`.

- **Score:** dimensões objetivas por código (GCI, concentração pelo SPED/ERP/questionário, tempo de mercado, estabilidade da margem, dívida líquida/EBITDA, sinais de contingência); de julgamento pelo questionário ou padrão conservador marcado ⚠ até o analista decidir (`"origem": "analista"` em `score_notas.json` prevalece).
- **Fluxo:** owner earnings sustentável = média dos períodos (até 3, sem os de confiança baixa), limitada ao mais recente.
- **DCF finito** 3–5 anos; terminal 0 (conservador) ou liquidação dos ativos operacionais (base/otimista); perpetuidade só com Score ≤ 30 + teste.
- **Patrimônio** = valor da empresa − dívida líquida (contratos bancários quando houver, senão Balanço) − contingências × probabilidade. Preço recomendado = máx(base × (1 − margem de segurança), piso patrimonial, 0).
- Referências: EPV, múltiplo de EBITDA 3–5×, sensibilidade taxa × crescimento.

## 8. Estratégia de economia de tokens

1. **Metodologia em cache:** um documento fixo (`metodologia/`), carregado como prefixo estável com prompt caching. Ele é lido uma vez e reaproveitado entre fases e cases.
2. **JSON entre fases:** cada agente recebe só o necessário da fase anterior.
3. **Dados de mercado em cache local:** BCB e Damodaran são atualizados periodicamente, não a cada case.
4. **Modelo por tarefa:** Haiku para extração em volume, Sonnet para julgamento e Opus apenas na revisão final.
5. **Saídas curtas e estruturadas:** a IA nunca gera layout, só textos com tamanho máximo por campo.
6. **Medição:** custo por fase registrado no `state.json`. Meta inicial: < US$ 1 por case.

## 9. Estrutura de pastas

```
project_valuation_lite/
├── ARQUITETURA.md
├── tarantino/            # orquestrador: estados, checkpoints, custos
├── captacao/             # F1–F2: esquemas, parsers (OFX/CSV/…), classificação de extratos
├── agents/               # prompts + esquemas de cada agente
├── engine/               # motor de valuation (DCF, EPV, GCI, múltiplos)
├── market_data/          # conectores BCB, Damodaran + cache
├── metodologia/          # filosofia da boutique (prefixo em cache)
├── templates/            # template HTML/CSS do report → PDF
├── interface/            # CLI e, depois, interface web
├── tests/                # testes do motor + cases de referência
└── cases/                # um diretório por case (fora do versionamento)
    └── ND-2026-001/
        ├── state.json
        ├── 00_docs/      # documentos recebidos
        ├── 01_extracao/  ... 08_report/
        └── audit.log
```

## 10. Disponibilização (operador → equipe)

| Etapa | Quem usa | Como | Quando |
|---|---|---|---|
| 1. Validação | você | linha de comando local (`tarantino abrir`, `tarantino rodar`, `tarantino aprovar`) | fases 2–5 |
| 2. Piloto interno | você + 1 analista | interface web simples (Streamlit): upload de documentos, telas de checkpoint, download do PDF | após 3–5 cases validados |
| 3. Equipe | analistas e estagiários | mesma interface hospedada num servidor com login; chave da API só no servidor; perfis (estagiário prepara, analista aprova) | após o piloto |

A CLI e a interface web usam o **mesmo núcleo** (`tarantino` + `engine`), então a interface é só uma camada a mais, sem retrabalho.

**Segurança e LGPD:** os dados financeiros de clientes são sensíveis.
- A chave da API nunca fica no código nem nas máquinas dos analistas.
- Os cases ficam em armazenamento controlado pela boutique.
- Cada ação no case é registrada no log, com quem fez e quando.
- Política de retenção e descarte por case.

## 11. Stack técnica

- Python 3.12 + Anthropic SDK (Messages API, saída estruturada, prompt caching)
- Pydantic (esquemas e validação entre fases)
- pdfplumber / OCR (leitura de PDFs), pandas (extratos, planilhas)
- Jinja2 + WeasyPrint (HTML → PDF)
- Typer (CLI) → Streamlit (interface web, etapa 2)

## 12. Roadmap

1. ✅ **Desenho da arquitetura** (este documento)
2. **Captação de dados:** esquemas JSON, extratores por tipo de documento, conectores BCB/Damodaran, cálculo do GCI
3. **Agentes:** Tarantino + agentes F1–F8, prompts e metodologia em cache
4. **Output:** estrutura do report e template do PDF
5. **Cases de teste:** um fictício (nível A e nível C) e um real
6. **Aprimoramento:** calibrar GCI, pesos do teste de perpetuidade e prompts com cases diversos

## 13. Decisões em aberto

- [ ] Conta e chave da API da Anthropic (console.anthropic.com), de preferência em nome da empresa
- [ ] Pesos do teste de perpetuidade e limites do GCI
- [x] Horizonte do DCF: 3 a 5 anos, definido pelo Score de Risco
- [x] Taxa de desconto: Selic + prêmio de 20–50 p.p., definido pelo Score de Risco
- [x] Taxa total (Selic + prêmio) entre 20% e 50% a.a.
- [x] Pesos e faixas do Score de Risco validados (recalibrar com os cases)
- [ ] Estrutura e identidade visual do report (seções, tamanho, logo)
- [x] Cases ficam no Google Drive da empresa (lidos localmente pelo Google Drive para computador). Captação detalhada em `CAPTACAO_DADOS.md`
- [ ] Versionamento do código (Git/GitHub) e se o código deve sair do Google Drive (sincronização + Git costumam conflitar)
