// Valida offline a lógica do criar_formulario.gs: simula o FormApp, percorre os 7 caminhos e confere módulos.
// Uso: node kit_captacao/formulario/validar_formulario.js
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const assert = require('assert');

function builder() {
  const b = {};
  ['setHelpText', 'requireNumberBetween', 'requireNumberGreaterThanOrEqualTo', 'requireSelectAtMost']
    .forEach((m) => { b[m] = () => b; });
  b.build = () => ({});
  return b;
}

function novoItem(tipo, form) {
  const it = { tipo, titulo: '', obrigatoria: false, goTo: null, escolhas: [] };
  const chain = (fn) => (...a) => { fn(...a); return it; };
  it.setTitle = chain((t) => { it.titulo = t; });
  it.setHelpText = chain(() => {});
  it.setRequired = chain((r) => { it.obrigatoria = r; });
  it.setValidation = chain(() => {});
  it.setChoiceValues = chain((v) => { it.escolhas = v.map((x) => ({ valor: x, pagina: null })); });
  it.showOtherOption = chain(() => {});
  it.createChoice = (valor, pagina) => ({ valor, pagina });
  it.setChoices = chain((c) => { it.escolhas = c; });
  it.setGoToPage = chain((p) => { it.goTo = p; });
  form.itens.push(it);
  return it;
}

const form = { itens: [] };
['setDescription', 'setProgressBar', 'setAllowResponseEdits', 'setCollectEmail', 'setConfirmationMessage', 'setDestination']
  .forEach((m) => { form[m] = () => form; });
form.addTextItem = () => novoItem('texto', form);
form.addParagraphTextItem = () => novoItem('paragrafo', form);
form.addMultipleChoiceItem = () => novoItem('unica', form);
form.addCheckboxItem = () => novoItem('multipla', form);
form.addSectionHeaderItem = () => novoItem('cabecalho', form);
form.addPageBreakItem = () => novoItem('quebra', form);
form.getId = () => 'f'; form.getPublishedUrl = () => 'url'; form.getEditUrl = () => 'edit';

const sandbox = {
  FormApp: {
    create: () => form, createTextValidation: builder, createCheckboxValidation: builder,
    PageNavigationType: { SUBMIT: 'SUBMIT' }, DestinationType: { SPREADSHEET: 'SS' },
  },
  SpreadsheetApp: { create: () => ({ getId: () => 's', getUrl: () => 'sheet' }) },
  DriveApp: {}, Logger: { log: () => {} }, Date,
};
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync(path.join(__dirname, 'criar_formulario.gs'), 'utf8') + '\nthis.__COMBOS = COMBOS; this.__MODULOS = MODULOS;' +
  ' this.__TODAS = [].concat(IDENTIFICACAO, PARTE0, ...NUCLEO.map(s => s.perguntas), ...Object.values(MODULOS).map(m => m.perguntas));', sandbox);
sandbox.criarFormulario();

// páginas: página 0 = itens antes da 1ª quebra; cada quebra inicia uma página
const paginas = [{ quebra: null, itens: [] }];
for (const it of form.itens) {
  if (it.tipo === 'quebra') paginas.push({ quebra: it, itens: [] });
  else paginas[paginas.length - 1].itens.push(it);
}
const indicePorQuebra = new Map(paginas.map((p, i) => [p.quebra, i]));
const porTitulo = new Map(sandbox.__TODAS.map((q) => [q.titulo, q.c]));
porTitulo.set('Quais atividades representam 10% ou mais do faturamento?', 'P03');
assert.strictEqual(porTitulo.size, sandbox.__TODAS.length + 1, 'títulos duplicados');
const codigo = (it) => {
  assert(!/^[A-Z]+[0-9]+[a-z]? · /.test(it.titulo), 'código visível no título: ' + it.titulo);
  assert(porTitulo.has(it.titulo), 'título sem código: ' + it.titulo);
  return porTitulo.get(it.titulo);
};

function percorrer(rotuloCombo) {
  let p = 0; const visitadas = []; const codigos = [];
  for (let passos = 0; passos < 100; passos++) {
    const pag = paginas[p];
    visitadas.push(pag.quebra ? pag.quebra.titulo : '(início)');
    pag.itens.filter((i) => i.tipo !== 'cabecalho').forEach((i) => codigos.push(codigo(i)));
    const nav = pag.itens.find((i) => i.tipo === 'unica' && i.escolhas.some((e) => e.pagina));
    if (nav) { p = indicePorQuebra.get(nav.escolhas.find((e) => e.valor === rotuloCombo).pagina); continue; }
    const prox = paginas[p + 1];
    if (!prox || prox.quebra.goTo === 'SUBMIT') return { visitadas, codigos };
    p = prox.quebra.goTo ? indicePorQuebra.get(prox.quebra.goTo) : p + 1;
  }
  throw new Error('laço infinito no caminho ' + rotuloCombo);
}

const MOD = sandbox.__MODULOS;
for (const combo of sandbox.__COMBOS) {
  const { visitadas, codigos } = percorrer(combo.rotulo);
  for (const m of ['I', 'C', 'S']) {
    const todos = MOD[m].perguntas.map((q) => q.c);
    const essenciais = MOD[m].perguntas.filter((q) => q.e).map((q) => q.c);
    const vistos = codigos.filter((c) => todos.includes(c));
    const esperado = combo.mods.includes(m) ? todos : essenciais;
    assert.strictEqual(JSON.stringify(vistos), JSON.stringify(esperado), `${combo.rotulo}: módulo ${m}`);
  }
  assert.strictEqual(new Set(codigos).size, codigos.length, `${combo.rotulo}: pergunta repetida no caminho`);
  ['ID1', 'P01', 'Q01', 'Q32', 'P03'].forEach((c) => assert(codigos.includes(c), `${combo.rotulo}: falta ${c}`));
  console.log(`OK  ${combo.rotulo.padEnd(34)} ${String(codigos.length).padStart(3)} perguntas · ` +
    visitadas.slice(9).join(' → '));
}
console.log(`\nTotal de itens no formulário: ${form.itens.length} · páginas: ${paginas.length}`);
