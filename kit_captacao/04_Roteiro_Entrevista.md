# Roteiro de Entrevista — uso interno do analista

**Duração:** 60 a 75 minutos · **Gravar** (com autorização) · **Participantes:** sócio principal (+ financeiro, se houver)

## Preparação (antes da reunião)

1. Ler o **questionário respondido** e o **relatório de GCI** gerado pelo tarantino_agent.
2. Levar a **lista de divergências** do sistema (ex.: "receita em conta 28% acima da contábil", "briefing informa estoque de R$ 732 mil e o balanço mostra R$ 6 mi"). A entrevista serve para **explicar divergências**, não para repetir o questionário.
3. Marcar as perguntas do questionário com resposta vaga ou em branco.
4. Conferir a **Parte 0 (atuação)**: o mix declarado bate com o faturamento por CNPJ e com a curva de clientes? Se uma atividade tem 10% ou mais do faturamento e o módulo dela não foi respondido, cobrar no bloco 5.

## Princípios

- **Pedir número e exemplo:** "quanto?", "me dá um exemplo", "como você sabe?".
- **Ouvir mais do que falar.** Anotar frases literais sobre clientes, concorrentes e dificuldades.
- **Assuntos sensíveis no final**, depois de criada a confiança.
- **Não discutir valor durante a entrevista.** Registrar a expectativa e seguir.

## Blocos

| # | Bloco | Min | Perguntas-guia | Alimenta |
|---|---|---|---|---|
| 1 | **Abertura** | 5 | Objetivo da conversa, confidencialidade, autorização para gravar | — |
| 2 | **História e motivação** | 10 | Como o negócio começou e cresceu? Por que vender agora? O que você faria com o dinheiro? O que te faria desistir da venda? | Histórico; risco de desistência |
| 3 | **O dono e a gestão** | 10 | Descreva sua semana típica. Quem decide quando você não está? Qual foi a última vez que tirou 15 dias de férias, e o que aconteceu? Quem são as 3 pessoas mais importantes depois de você? | **Dependência do dono** |
| 4 | **Clientes e mercado** | 10 | Quem são os 3 maiores clientes e por que compram de você? Perdeu algum cliente grande recentemente? Por quê? O que o concorrente faz melhor? Se você aumentar o preço em 10% amanhã, o que acontece? | **Concentração, recorrência, posição competitiva (fosso)** |
| 5 | **Operação (módulos do setor)** | 10 | Aprofundar as respostas I/S/C dos módulos marcados na Parte 0: capacidade e máquinas (indústria), contratos e responsável técnico (serviços), exclusividades e ponto (comércio). Em empresas mistas: "qual atividade dá mais margem? Se tivesse que fechar uma, qual seria?" | Capex de manutenção; riscos operacionais; margem por atividade |
| 6 | **Números: conferência das divergências** | 15 | Para cada divergência do relatório de GCI: "os documentos mostram X e você informou Y. Como explica?" Revisar dívidas, parcelamentos e processos item a item | **Confiabilidade da informação; endividamento; contingências** |
| 7 | **Informalidade (sensível)** | 10 | "Muitas empresas do porte têm parte da receita sem nota. Isso acontece aqui? Que % aproximado? Por qual CNPJ passa?" · "Quais despesas pessoais passam pela empresa?" · "Por que existe mais de um CNPJ?" | Receita real; ajustes; **contingência fiscal**; grupo econômico |
| 8 | **Encerramento** | 5 | Recapitular as pendências documentais com prazo. Próximos passos | Lista de pendências |

**Como abordar o bloco 7:** explique que a receita sem nota **não some do valor**. Ela entra como receita com risco, e esconder isso gera surpresa na diligência do comprador, o que costuma derrubar o negócio ou o preço muito mais.

## Sinais de alerta (registrar na ficha)

- Respostas contraditórias com documentos, sem explicação plausível.
- "Não tenho concorrente" / "meu produto não tem igual" (excesso de otimismo).
- Recusa em enviar extratos bancários.
- Expectativa de valor muito acima do lucro (ex.: mais de 6× o lucro anual) sem justificativa.
- Dívidas, processos ou sócios ocultos que aparecem só no final.
- Dependência de um único contrato, cliente, licença ou pessoa.

## Mapa: perguntas → Score de Risco

| Dimensão do Score | Peso | Questionário | Entrevista | Documento que confirma |
|---|---|---|---|---|
| Confiabilidade da informação | 15 | Q24 | bloco 6–7 | GCI (extratos × PGDAS × contábil) |
| Dependência do dono | 15 | Q06–Q10, Q04 | bloco 3 | aba 2_Socios |
| Concentração de clientes | 10 | Q11–Q12 | bloco 4 | aba 5_Clientes, extratos |
| Recorrência de receita | 10 | Q13–Q14, S01–S02, I07 | bloco 4 | contratos, aba 5_Clientes |
| Histórico e tempo de mercado | 10 | Q01, Q21 | bloco 2 | Cartão CNPJ (consulta automática) |
| Estabilidade de resultados | 10 | Q16, Q21 | bloco 6 | aba 4_Faturamento, DREs |
| Endividamento e liquidez | 10 | Q15, Q26, C05 | bloco 6 | aba 6_Dividas, balanço |
| Contingências | 10 | Q24–Q27, I10 | bloco 6–7 | parcelamentos, processos |
| Setor e posição competitiva | 10 | Q17–Q20, Q22, I06, C02 | bloco 4 | — (julgamento, aprovação humana) |

## Mapa: perguntas → insumos do valuation

| Insumo | Fonte |
|---|---|
| **Owner earnings** (lucro do dono) | Q25, Q28, Q32, aba 9_Ajustes, aba 2_Socios |
| **Capex de manutenção** | Q28, I02 |
| **Capital de giro** | Q15, C04, C05, I08 |
| **Teste de perpetuidade** | Q01, Q09, Q13, S01, Q21 |
| **Ajuste do valor pela dependência do dono** | Q04, Q08, Q10 |
| **Contingências (reduzem o preço)** | Q24, Q26, Q27 |
| **Projeção por atividade** (empresas mistas) | P01–P02, bloco 5. Cada atividade com 10% ou mais é projetada separadamente, porque crescimento, margem e risco diferem. Ex.: serviço recorrente de manutenção tende a ter menos risco do que a venda de equipamento sob encomenda. |

## Após a entrevista

A transcrição é processada pelo sistema, que preenche a **ficha estruturada** (uma nota de 1 a 5 por dimensão, com a evidência literal). O analista **revisa e aprova** no Checkpoint 2. Não é preciso redigir ata.
