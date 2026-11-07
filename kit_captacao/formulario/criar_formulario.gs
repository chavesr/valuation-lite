/**
 * Questionário do Empreendedor — Valuation Nova Direção
 * Gera o Google Form com seções condicionais por atividade + planilha de respostas.
 *
 * COMO USAR
 *  1. Acesse https://script.google.com com a conta da Nova Direção → "Novo projeto".
 *  2. Apague o conteúdo do editor, cole este arquivo inteiro e salve.
 *  3. (Opcional) Preencha PASTA_DESTINO_ID com o ID da pasta do Drive onde o formulário deve ficar.
 *  4. Selecione a função `criarFormulario` e clique em "Executar". Autorize o acesso na primeira vez.
 *  5. Os links (formulário para o cliente, edição e planilha de respostas) aparecem no "Registro de execução".
 *
 * Fonte do conteúdo: kit_captacao/03_Questionario_Cliente.md (v aprovada).
 * Cada pergunta tem um código interno (Q01, I01…) que NÃO aparece para o cliente. O leitor do sistema
 * identifica a pergunta pelo título exato (títulos são únicos) e converte para o código usando este arquivo.
 *
 * Por que 7 caminhos: o Google Forms só desvia o fluxo por pergunta de escolha ÚNICA.
 * Por isso a pergunta P03 lista as 7 combinações de atividades, e cada combinação tem sua sequência de módulos.
 */

const PASTA_DESTINO_ID = '';  // opcional
const VERSAO = '1.0';
const ANO_ATUAL = new Date().getFullYear();

// ------------------------------------------------------------------ tipos de pergunta
// t: 'texto' | 'paragrafo' | 'ano' | 'numero' | 'pct' | 'moeda' | 'unica' | 'multipla'
// e: true = pergunta essencial (★), também feita quando a atividade tem menos de 10% do faturamento

const IDENTIFICACAO = [
  { c: 'ID1', t: 'texto', titulo: 'Nome da empresa', req: true },
  { c: 'ID2', t: 'texto', titulo: 'CNPJ principal', req: true },
  { c: 'ID3', t: 'texto', titulo: 'Seu nome', req: true },
  { c: 'ID4', t: 'texto', titulo: 'Sua função na empresa', req: true },
  { c: 'ID5', t: 'texto', titulo: 'E-mail', req: true },
  { c: 'ID6', t: 'texto', titulo: 'Telefone / WhatsApp' },
];

const PARTE0 = [
  { c: 'P01', t: 'multipla', req: true, titulo: 'Em quais atividades a empresa atua? (considere todos os CNPJs do grupo)',
    op: ['Fabricação / produção — transforma matéria-prima em produto (inclui montagem e produção sob encomenda)',
         'Comércio / revenda — compra produtos prontos e revende (loja, distribuição, peças, atacado)',
         'Prestação de serviços — vende trabalho ou conhecimento (manutenção, instalação, consultoria, transporte, saúde…)'] },
  { c: 'P01a', t: 'pct', titulo: '% aproximado do faturamento — FABRICAÇÃO', ajuda: 'Deixe em branco se não atua. A soma das três atividades deve dar 100.' },
  { c: 'P01b', t: 'pct', titulo: '% aproximado do faturamento — COMÉRCIO / REVENDA' },
  { c: 'P01c', t: 'pct', titulo: '% aproximado do faturamento — SERVIÇOS' },
  { c: 'P01d', t: 'paragrafo', titulo: 'Qual CNPJ realiza cada atividade?', ajuda: 'Ex.: fabricação no CNPJ X; peças no CNPJ Y; manutenção no CNPJ Z.' },
  { c: 'P02', t: 'unica', titulo: 'As atividades dependem umas das outras?',
    ajuda: 'Ex.: a manutenção existe porque os clientes compraram o produto fabricado.',
    op: ['Sim, são complementares', 'Não, são negócios independentes', 'A empresa tem uma só atividade'] },
];

const NUCLEO = [
  { titulo: 'A1. A empresa e a venda', perguntas: [
    { c: 'Q01', t: 'ano', titulo: 'Em que ano o negócio começou a operar (mesmo que com outro CNPJ)?' },
    { c: 'Q02', t: 'multipla', outro: true, titulo: 'Por que os sócios querem vender agora?',
      op: ['Aposentadoria', 'Sucessão sem herdeiros interessados', 'Conflito entre sócios', 'Saúde', 'Novo projeto', 'Dificuldade financeira'] },
    { c: 'Q03a', t: 'moeda', titulo: 'Qual valor os sócios esperam pela empresa? (R$)' },
    { c: 'Q03b', t: 'paragrafo', titulo: 'Como chegaram a esse valor?' },
    { c: 'Q04', t: 'unica', titulo: 'Após a venda, o sócio principal estaria disposto a permanecer na transição?',
      op: ['Não', 'Até 6 meses', 'De 6 a 12 meses', 'Mais de 12 meses'] },
    { c: 'Q05a', t: 'unica', titulo: 'O imóvel onde a empresa opera é:',
      op: ['Próprio da empresa', 'Dos sócios ou da família', 'Alugado de terceiros'] },
    { c: 'Q05b', t: 'moeda', titulo: 'Se alugado: valor do aluguel mensal (R$)' },
    { c: 'Q05c', t: 'texto', titulo: 'Se alugado: contrato válido até (mês/ano)' },
  ]},
  { titulo: 'A2. Dependência do dono', perguntas: [
    { c: 'Q06', t: 'numero', min: 0, max: 120, titulo: 'Quantas horas por semana o sócio principal trabalha na empresa?' },
    { c: 'Q07', t: 'multipla', titulo: 'Quais atividades SÓ o dono faz hoje?',
      op: ['Vender / fechar negócios', 'Relacionamento com os principais clientes', 'Negociar com fornecedores', 'Precificar',
           'Supervisionar a produção / operação', 'Controlar o financeiro', 'Parte técnica (projeto, receita, engenharia)'] },
    { c: 'Q08', t: 'unica', titulo: 'Se o dono se ausentasse por 3 meses, a empresa:',
      op: ['Funcionaria normalmente', 'Funcionaria com perda pequena', 'Perderia vendas relevantes', 'Pararia'] },
    { c: 'Q09a', t: 'unica', titulo: 'Existe gerente ou líder com autonomia para decidir?', op: ['Sim', 'Não'] },
    { c: 'Q09b', t: 'texto', titulo: 'Se sim: há quanto tempo essa pessoa está na empresa?' },
    { c: 'Q10', t: 'pct', titulo: 'Que % dos clientes compra principalmente por relacionamento pessoal com o dono?' },
  ]},
  { titulo: 'A3. Clientes e receita', perguntas: [
    { c: 'Q11', t: 'numero', min: 0, titulo: 'Quantos clientes compraram nos últimos 12 meses?' },
    { c: 'Q12a', t: 'pct', titulo: 'Que % do faturamento vem do MAIOR cliente?' },
    { c: 'Q12b', t: 'pct', titulo: 'Que % do faturamento vem dos 5 MAIORES clientes (somados)?' },
    { c: 'Q13', t: 'pct', titulo: 'Que % do faturamento é recorrente (contratos, clientes que compram todo mês)?' },
    { c: 'Q14', t: 'pct', titulo: 'Dos clientes que compravam há 2 anos, quantos % ainda compram?' },
    { c: 'Q15a', t: 'numero', min: 0, max: 720, titulo: 'Prazo médio que a empresa dá para os clientes pagarem (dias)' },
    { c: 'Q15b', t: 'pct', titulo: 'Inadimplência média (% do faturamento)' },
    { c: 'Q16', t: 'paragrafo', titulo: 'Existe sazonalidade? Quais os meses mais fortes e mais fracos?' },
  ]},
  { titulo: 'A4. Mercado e vantagem competitiva', perguntas: [
    { c: 'Q17', t: 'paragrafo', titulo: 'Quem são os 3 principais concorrentes?' },
    { c: 'Q18', t: 'multipla', max: 3, titulo: 'Por que os clientes escolhem a sua empresa? (até 3 opções)',
      op: ['Preço', 'Qualidade', 'Prazo de entrega', 'Atendimento / relacionamento', 'Marca conhecida', 'Produto exclusivo ou patenteado',
           'Localização', 'Assistência técnica', 'Condições de pagamento'] },
    { c: 'Q19', t: 'unica', titulo: 'Nos últimos 2 anos, a empresa conseguiu repassar aumentos de custo para o preço?',
      op: ['Integralmente', 'Parcialmente', 'Não conseguiu'] },
    { c: 'Q20', t: 'paragrafo', titulo: 'Quanto tempo e dinheiro um concorrente novo levaria para fazer o mesmo que vocês?' },
    { c: 'Q21', t: 'paragrafo', titulo: 'Como a empresa atravessou as últimas crises (2015–2016 e pandemia)? O faturamento caiu quanto?' },
  ]},
  { titulo: 'A5. Fornecedores e operação', perguntas: [
    { c: 'Q22a', t: 'pct', titulo: 'Que % das compras vem do MAIOR fornecedor?' },
    { c: 'Q22b', t: 'paragrafo', titulo: 'Existe fornecedor sem substituto? Qual?' },
    { c: 'Q23', t: 'paragrafo', titulo: 'A empresa depende de licença, alvará, certificação ou responsável técnico para operar? Estão em dia?' },
  ]},
  { titulo: 'A6. Finanças e passivos', ajuda: 'Respostas tratadas com sigilo, sob o acordo de confidencialidade.', perguntas: [
    { c: 'Q24', t: 'unica', titulo: 'Toda a receita da empresa é faturada com nota fiscal?',
      ajuda: 'Confidencial. Essa informação é essencial para um valor correto e defensável diante de compradores.',
      op: ['Sim', 'Não, parte é recebida sem nota'] },
    { c: 'Q25a', t: 'unica', titulo: 'A empresa paga despesas pessoais dos sócios?', op: ['Não', 'Sim'] },
    { c: 'Q25b', t: 'moeda', titulo: 'Se sim: valor aproximado por mês (R$)' },
    { c: 'Q26', t: 'paragrafo', titulo: 'Existem dívidas, impostos ou parcelamentos que NÃO aparecem na contabilidade? Quais?' },
    { c: 'Q27', t: 'paragrafo', titulo: 'Existem processos trabalhistas, cíveis ou fiscais? Quantos e qual o valor aproximado?' },
    { c: 'Q28', t: 'moeda', titulo: 'Quanto a empresa precisa investir POR ANO só para manter máquinas, veículos, equipamentos e instalações funcionando (sem crescer)? (R$)' },
    { c: 'Q29', t: 'paragrafo', titulo: 'Houve algum investimento ou gasto extraordinário recente que não vai se repetir?' },
  ]},
  { titulo: 'A7. Equipe', perguntas: [
    { c: 'Q30a', t: 'numero', min: 0, titulo: 'Quantos funcionários (CLT + terceiros)?' },
    { c: 'Q30b', t: 'numero', min: 0, titulo: 'Quantos têm mais de 3 anos de casa?' },
    { c: 'Q31', t: 'paragrafo', titulo: 'Há funcionários-chave cuja saída prejudicaria muito a empresa? Quantos e em que funções?' },
    { c: 'Q32', t: 'paragrafo', titulo: 'Há familiares dos sócios trabalhando na empresa? Em que funções?' },
  ]},
];

const MODULOS = {
  I: { nome: 'INDÚSTRIA', perguntas: [
    { c: 'I01a', e: true, t: 'texto', titulo: 'Capacidade máxima de produção por mês (unidades, toneladas…)' },
    { c: 'I01b', e: true, t: 'texto', titulo: 'Produção média atual por mês' },
    { c: 'I02a', e: true, t: 'numero', min: 0, max: 100, titulo: 'Idade média das principais máquinas (anos)' },
    { c: 'I02b', e: true, t: 'paragrafo', titulo: 'Alguma máquina precisa ser substituída nos próximos 2 anos? Custo estimado?' },
    { c: 'I03', t: 'paragrafo', titulo: 'Principais matérias-primas e que % do custo representam. Os preços acompanham alguma commodity (aço, resina, grãos…)?' },
    { c: 'I04', t: 'texto', titulo: 'Carteira de pedidos hoje (vendido e ainda não entregue): R$ ou meses de produção' },
    { c: 'I05', t: 'numero', min: 0, max: 720, titulo: 'Prazo médio entre o pedido e a entrega (dias)' },
    { c: 'I06', t: 'paragrafo', titulo: 'A empresa tem produto próprio, projeto, patente ou registro? Quais? (ou produz sob projeto do cliente?)' },
    { c: 'I07', t: 'pct', titulo: 'Que % da receita vem de pós-venda (peças, manutenção, reforma)?' },
    { c: 'I08a', e: true, t: 'moeda', titulo: 'Estoque de matéria-prima — valor aproximado (R$)' },
    { c: 'I08b', e: true, t: 'moeda', titulo: 'Estoque em produção — valor aproximado (R$)' },
    { c: 'I08c', e: true, t: 'moeda', titulo: 'Estoque de produto acabado — valor aproximado (R$)' },
    { c: 'I08d', e: true, t: 'paragrafo', titulo: 'Há estoque parado há mais de 1 ano? Valor aproximado?' },
    { c: 'I09', t: 'paragrafo', titulo: 'Certificações (ISO, Inmetro, homologações de clientes)?' },
    { c: 'I10', t: 'paragrafo', titulo: 'Há passivo ambiental, licença ambiental pendente ou destinação de resíduos irregular?' },
  ]},
  S: { nome: 'SERVIÇOS', perguntas: [
    { c: 'S01a', e: true, t: 'pct', titulo: 'Que % da receita de serviços vem de contratos com prazo definido?' },
    { c: 'S01b', e: true, t: 'numero', min: 0, max: 600, titulo: 'Duração média dos contratos (meses)' },
    { c: 'S01c', e: true, t: 'unica', titulo: 'Os contratos têm multa de rescisão?', op: ['Sim', 'Não', 'Varia', 'Não há contratos'] },
    { c: 'S02', t: 'pct', titulo: 'Taxa de renovação de contratos no último ano' },
    { c: 'S03', e: true, t: 'paragrafo', titulo: 'O serviço depende de responsável técnico ou profissional habilitado (engenheiro, médico, contador…)? É o próprio sócio?' },
    { c: 'S04', t: 'paragrafo', titulo: 'Quantos profissionais entregam o serviço? Quantos clientes cada um atende?' },
    { c: 'S05', t: 'pct', titulo: 'Taxa de ocupação da equipe (horas faturadas ÷ horas disponíveis)' },
    { c: 'S06a', t: 'pct', titulo: 'Que % da receita vem de órgãos públicos / licitações?' },
    { c: 'S06b', t: 'paragrafo', titulo: 'Há atrasos de pagamento de órgãos públicos?' },
    { c: 'S07', t: 'unica', titulo: 'O conhecimento do serviço está documentado (processos, manuais, sistemas)?',
      op: ['Sim, bem documentado', 'Parcialmente', 'Não, está na cabeça das pessoas'] },
    { c: 'S08', t: 'texto', titulo: 'Quanto tempo leva para treinar um novo profissional até ele ser produtivo?' },
    { c: 'S09', t: 'paragrafo', titulo: 'Usa sistema/software próprio ou licenciado essencial para a entrega? Qual?' },
  ]},
  C: { nome: 'COMÉRCIO', perguntas: [
    { c: 'C01a', t: 'pct', titulo: 'Canais de venda — % loja física' },
    { c: 'C01b', t: 'pct', titulo: 'Canais de venda — % atacado / representantes' },
    { c: 'C01c', t: 'pct', titulo: 'Canais de venda — % online / marketplace' },
    { c: 'C01d', t: 'pct', titulo: 'Canais de venda — % outros' },
    { c: 'C02', e: true, t: 'paragrafo', titulo: 'A empresa tem exclusividade ou representação de alguma marca/fornecedor? Há contrato? É transferível para um novo dono?' },
    { c: 'C03a', t: 'pct', titulo: 'Margem bruta média (preço de venda − custo da mercadoria), em %' },
    { c: 'C03b', t: 'paragrafo', titulo: 'A margem varia muito entre linhas de produto? Quais as mais e menos rentáveis?' },
    { c: 'C04', e: true, t: 'numero', min: 0, max: 1000, titulo: 'Giro do estoque: em média, quantos dias um produto fica parado antes de ser vendido?' },
    { c: 'C05a', e: true, t: 'numero', min: 0, max: 720, titulo: 'Prazo médio de pagamento aos fornecedores (dias)' },
    { c: 'C05b', e: true, t: 'numero', min: 0, max: 720, titulo: 'Prazo médio de recebimento dos clientes (dias)' },
    { c: 'C06a', t: 'pct', titulo: 'Que % das vendas é paga com cartão / maquininha?' },
    { c: 'C06b', t: 'multipla', outro: true, titulo: 'Quais adquirentes / maquininhas usa?',
      op: ['Cielo', 'Stone', 'Rede', 'Getnet', 'PagSeguro / PagBank', 'Mercado Pago', 'SumUp', 'Não usa'] },
    { c: 'C07', t: 'paragrafo', titulo: 'Ponto comercial: o movimento depende da localização? Há luvas, contrato longo ou risco de despejo?' },
    { c: 'C08', t: 'texto', titulo: 'Há estoque obsoleto, avariado ou com validade vencendo? Valor aproximado (R$)' },
    { c: 'C09', t: 'texto', titulo: 'Quantas lojas/filiais? Todas são lucrativas?' },
  ]},
};

const COMBOS = [
  { rotulo: 'Somente fabricação', mods: ['I'] },
  { rotulo: 'Somente comércio / revenda', mods: ['C'] },
  { rotulo: 'Somente serviços', mods: ['S'] },
  { rotulo: 'Fabricação + comércio', mods: ['I', 'C'] },
  { rotulo: 'Fabricação + serviços', mods: ['I', 'S'] },
  { rotulo: 'Comércio + serviços', mods: ['C', 'S'] },
  { rotulo: 'Fabricação + comércio + serviços', mods: ['I', 'C', 'S'] },
];

// ------------------------------------------------------------------ construção

function _rotulo(p) { return p.titulo; }

function _adicionar(form, p, forcarOpcional) {
  let item;
  const num = FormApp.createTextValidation().setHelpText('Informe apenas números.');
  switch (p.t) {
    case 'paragrafo':
      item = form.addParagraphTextItem();
      break;
    case 'unica':
      item = form.addMultipleChoiceItem().setChoiceValues(p.op);
      if (p.outro) item.showOtherOption(true);
      break;
    case 'multipla':
      item = form.addCheckboxItem().setChoiceValues(p.op);
      if (p.outro) item.showOtherOption(true);
      if (p.max) item.setValidation(FormApp.createCheckboxValidation().requireSelectAtMost(p.max)
        .setHelpText('Escolha no máximo ' + p.max + ' opções.').build());
      break;
    case 'ano':
      item = form.addTextItem().setValidation(num.requireNumberBetween(1900, ANO_ATUAL).build());
      break;
    case 'pct':
      item = form.addTextItem().setValidation(FormApp.createTextValidation()
        .setHelpText('Informe um número entre 0 e 100, sem o símbolo %.').requireNumberBetween(0, 100).build());
      break;
    case 'numero':
      item = form.addTextItem();
      if (p.max !== undefined) item.setValidation(num.requireNumberBetween(p.min || 0, p.max).build());
      else item.setValidation(num.requireNumberGreaterThanOrEqualTo(p.min || 0).build());
      break;
    case 'moeda':  // sem validação: o cliente costuma escrever "1,5 mi" ou "R$ 20.000"
    case 'texto':
    default:
      item = form.addTextItem();
  }
  item.setTitle(_rotulo(p));
  const ajuda = p.ajuda || (p.t === 'moeda' ? 'Valor aproximado em reais.' : '');
  if (ajuda) item.setHelpText(ajuda);
  if (p.req && !forcarOpcional) item.setRequired(true);
  return item;
}

function _adicionarTodas(form, perguntas, forcarOpcional) {
  perguntas.forEach(function (p) { _adicionar(form, p, forcarOpcional); });
}

function criarFormulario() {
  const form = FormApp.create('Questionário do Empreendedor — Valuation Nova Direção');
  form.setDescription(
    'Tempo estimado: 25 a 35 minutos. Responda com a melhor estimativa possível — números aproximados ' +
    'são melhores que nenhum número. As informações são confidenciais e usadas exclusivamente para a avaliação. ' +
    'Você pode editar suas respostas depois de enviar.  (v' + VERSAO + ')');
  form.setProgressBar(true);
  form.setAllowResponseEdits(true);
  form.setCollectEmail(false);
  form.setConfirmationMessage('Obrigado! Suas respostas serão conferidas com os documentos e aprofundadas na conversa com o analista.');

  // Página 1: identificação + Parte 0
  _adicionarTodas(form, IDENTIFICACAO);
  form.addSectionHeaderItem().setTitle('Parte 0 — Em que a empresa atua?')
    .setHelpText('Define quais perguntas específicas do seu setor aparecerão no final.');
  _adicionarTodas(form, PARTE0);

  // Parte A — núcleo comum
  NUCLEO.forEach(function (secao, i) {
    const pb = form.addPageBreakItem().setTitle((i === 0 ? 'Parte A — ' : '') + secao.titulo);
    if (secao.ajuda) pb.setHelpText(secao.ajuda);
    _adicionarTodas(form, secao.perguntas);
  });

  // Parte B — seletor de caminho
  form.addPageBreakItem().setTitle('Parte B — Perguntas do seu setor')
    .setHelpText('Agora, perguntas específicas das atividades da empresa.');
  const seletor = form.addMultipleChoiceItem()
    .setTitle('Quais atividades representam 10% ou mais do faturamento?')
    .setHelpText('Use os percentuais que você informou na Parte 0. Atividades menores que 10% terão apenas algumas perguntas essenciais.')
    .setRequired(true);

  // Um caminho por combinação. As seções de cada caminho ficam contíguas; o fim de cada caminho envia o formulário.
  const inicioCaminho = [];
  COMBOS.forEach(function (combo, k) {
    let primeira = null;
    combo.mods.forEach(function (m, j) {
      const pb = form.addPageBreakItem().setTitle('Módulo ' + MODULOS[m].nome)
        .setHelpText(combo.rotulo + (combo.mods.length > 1 ? ' — parte ' + (j + 1) + ' de ' + combo.mods.length : ''));
      if (!primeira) primeira = pb;
      _adicionarTodas(form, MODULOS[m].perguntas);
    });
    const secundarios = ['I', 'C', 'S'].filter(function (m) { return combo.mods.indexOf(m) < 0; });
    if (secundarios.length) {
      form.addPageBreakItem().setTitle('Atividades secundárias (menos de 10% do faturamento)')
        .setHelpText('Responda SOMENTE os blocos das atividades que a empresa exerce em menor escala. Se não exerce, deixe em branco e envie.');
      secundarios.forEach(function (m) {
        form.addSectionHeaderItem().setTitle('Se também atua com ' + MODULOS[m].nome.toLowerCase());
        _adicionarTodas(form, MODULOS[m].perguntas.filter(function (p) { return p.e; }), true);
      });
    }
    inicioCaminho.push(primeira);
  });

  seletor.setChoices(COMBOS.map(function (combo, k) { return seletor.createChoice(combo.rotulo, inicioCaminho[k]); }));
  // Ao terminar o caminho k, a progressão linear chegaria ao início do caminho k+1: força o envio.
  for (let k = 1; k < inicioCaminho.length; k++) {
    inicioCaminho[k].setGoToPage(FormApp.PageNavigationType.SUBMIT);
  }

  const planilha = SpreadsheetApp.create('Respostas — Questionário do Empreendedor (ND)');
  form.setDestination(FormApp.DestinationType.SPREADSHEET, planilha.getId());

  if (PASTA_DESTINO_ID) {
    const pasta = DriveApp.getFolderById(PASTA_DESTINO_ID);
    DriveApp.getFileById(form.getId()).moveTo(pasta);
    DriveApp.getFileById(planilha.getId()).moveTo(pasta);
  }

  Logger.log('Link para o CLIENTE responder: ' + form.getPublishedUrl());
  Logger.log('Link de EDIÇÃO (interno):    ' + form.getEditUrl());
  Logger.log('Planilha de respostas:       ' + planilha.getUrl());
  return form;
}

// Remove o prefixo "CÓDIGO · " dos títulos de um formulário já criado (mantém links e respostas).
function removerCodigosDoFormulario() {
  const FORM_ID = '1a1ogqXT-KsXMJnpBfdLZe7F-358l6xtQXJS_HttmiRE';
  const form = FormApp.openById(FORM_ID);
  let n = 0;
  form.getItems().forEach(function (item) {
    const t = item.getTitle();
    const novo = t.replace(/^[A-Z]+[0-9]+[a-z]? · /, '');
    if (novo !== t) { item.setTitle(novo); n++; }
  });
  Logger.log('Títulos ajustados: ' + n);
}
