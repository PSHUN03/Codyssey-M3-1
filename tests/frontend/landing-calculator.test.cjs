const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

// Exercise submission and request boundaries; the browser supplies field validity.
async function setup() {
  class Element {
    constructor(value = '') {
      Object.assign(this, { value, textContent: '', innerHTML: '', disabled: false, hidden: false,
        customError: '', attributes: {}, events: {}, classes: new Set() });
      this.classList = {
        add: name => this.classes.add(name), remove: name => this.classes.delete(name),
        toggle: (name, active) => active ? this.classes.add(name) : this.classes.delete(name),
      };
    }
    setCustomValidity(message) { this.customError = message; }
    get willValidate() { return this.required && !this.disabled; }
    get validity() { return { valid: !this.willValidate || (this.value !== '' && !this.customError) }; }
    setAttribute(name, value) { this.attributes[name] = String(value); }
    addEventListener(name, callback) { (this.events[name] ||= []).push(callback); }
    emit(type) { (this.events[type] || []).forEach(fn => fn({ preventDefault() {} })); }
  }
  const nodes = Object.fromEntries(['calc-form', 'calc-rent', 'calc-row', 'calc-amount', 'calc-bar',
    'calc-legend', 'calc-extra', 'calc-result', 'calc-status', 'calc-apply', 'label', 'card']
    .map(id => [id, new Element()]));
  const form = nodes['calc-form'];
  const fields = Object.fromEntries(Object.entries({ monthly_income: '245', rent: '50', fixed_costs: '35', living: 'alone' })
    .map(([name, value]) => { const el = new Element(value); el.required = name !== 'living'; return [name, el]; }));
  form.elements = Object.assign(Object.values(fields), fields);
  form.checkValidity = () => form.elements.every(el => el.validity.valid);
  form.reportValidity = () => { throw new Error('Native validation popups must not be requested'); };
  form.closest = () => nodes.card;
  const requests = [];
  const source = fs.readFileSync(path.join(__dirname, '../../app/static/js/app.js'), 'utf8');
  const implementation = source.slice(source.indexOf('function initLanding()'), source.indexOf('function initOnboarding()'));
  vm.runInNewContext(`${implementation}\ninitLanding();`, {
    $: selector => nodes[selector === '.calc-label' ? 'label' : selector.slice(1)],
    window: { matchMedia: () => ({ matches: true, addEventListener() {} }), addEventListener() {} },
    AbortController, digits: value => String(value).replace(/[^\d]/g, ''),
    toWon: value => Number(value) * 10000, won: String, escapeHtml: String,
    setFeedback: (node, message) => { node.textContent = message; },
    api: async (_, { body }) => {
      requests.push(body);
      return { total_saving: 720000, groups: [{ key: 'saving', amount: 720000, label: '저축' }] };
    },
  });
  const flush = () => new Promise(resolve => setImmediate(resolve));
  await flush();
  const apply = async () => { form.emit('submit'); await flush(); };
  const edit = (name, value) => { fields[name].value = value; form.emit('input'); };
  return { fields, nodes, requests, apply, edit };
}

test('blank visible costs block a request and clear the old result; explicit zero can be applied', async () => {
  const { nodes, requests, apply, edit } = await setup();
  assert.equal(requests.length, 1);
  edit('fixed_costs', '');
  await apply();
  assert.equal(requests.length, 1);
  assert.equal(nodes['calc-result'].hidden, true);
  assert.equal(nodes['calc-status'].classes.has('ob-error'), true);
  assert.equal(nodes['calc-apply'].disabled, false);
  edit('fixed_costs', '0');
  await apply();
  assert.equal(requests.length, 2);
  assert.equal(requests[1].fixed_costs, 0);
  assert.equal(nodes['calc-result'].hidden, false);
});

test('blank rent is invalid alone but is skipped while its field is hidden for parents', async () => {
  const { fields, requests, apply, edit } = await setup();
  edit('rent', '');
  await apply();
  assert.equal(requests.length, 1);
  edit('living', 'parents');
  assert.equal(fields.rent.disabled, true);
  await apply();
  assert.equal(requests.length, 2);
  assert.equal(requests[1].rent, 0);
  edit('living', 'alone');
  assert.equal(fields.rent.disabled, false);
  await apply();
  assert.equal(requests.length, 2);
});

test('blank and zero income do not calculate, and a corrected income recovers submission', async () => {
  const { requests, apply, edit } = await setup();
  for (const value of ['', '0']) {
    edit('monthly_income', value);
    await apply();
    assert.equal(requests.length, 1);
  }
  edit('monthly_income', '245');
  await apply();
  assert.equal(requests.length, 2);
  assert.equal(requests[1].monthly_income, 2450000);
});

function setupPlan() {
  const fields = Object.fromEntries(Object.entries({ product: 'general', monthly_amount: '30', months: '24' })
    .map(([name, value]) => [name, { value, focus() { state.focus = name; } }]));
  const state = { focus: '', events: {}, requests: [] };
  const form = { elements: fields, setAttribute() {},
    addEventListener(type, handler) { state.events[type] = handler; } };
  const out = { innerHTML: '', setAttribute() {} };
  const months = { hidden: false }, help = {}, button = { disabled: false, textContent: '계산하기' };
  const nodes = { '#simulate-form': form, '#simulate-result': out, '#sim-months-field': months,
    '#sim-help': help, 'button[type="submit"]': button };
  const source = fs.readFileSync(path.join(__dirname, '../../app/static/js/app.js'), 'utf8');
  const implementation = source.slice(source.indexOf('function initPlan()'), source.indexOf('async function regenerate('));
  vm.runInNewContext(`${implementation}\ninitPlan();`, {
    $: selector => nodes[selector], digits: value => String(value).replace(/[^\d]/g, ''),
    toWon: value => Number(value) * 10000, escapeHtml: String, renderMd: String,
    api: async (_, { body }) => { state.requests.push(body); return { months: 24, contribution: 0,
      readable: { '원금': '72만 원', '세전 이자': '3만 원', '세금': '1만 원', '만기 수령액': '74만 원' }, notes: [] }; },
  });
  return { fields, out, months, state,
    product(value) { fields.product.value = value; state.events.change(); },
    async apply() { await state.events.submit({ preventDefault() {} }); },
  };
}

test('both plan products distinguish a missing monthly amount from a range error', async () => {
  const plan = setupPlan();
  for (const product of ['general', 'youth_future_savings']) {
    plan.product(product);
    plan.fields.monthly_amount.value = '';
    await plan.apply();
    assert.match(plan.out.innerHTML, /매달 넣을 돈을 입력해 주세요/);
    assert.equal(plan.state.focus, 'monthly_amount');
    assert.equal(plan.state.requests.length, 0);
  }
});

test('general savings requires a period and recovers when it is filled', async () => {
  const plan = setupPlan();
  plan.fields.months.value = '';
  await plan.apply();
  assert.match(plan.out.innerHTML, /기간을 입력해 주세요/);
  assert.equal(plan.state.focus, 'months');
  assert.equal(plan.state.requests.length, 0);
  plan.fields.months.value = '24';
  await plan.apply();
  assert.equal(plan.state.requests.length, 1);
  assert.equal(plan.state.requests[0].months, 24);
});

test('youth savings can calculate without the hidden period field', async () => {
  const plan = setupPlan();
  plan.product('youth_future_savings');
  plan.fields.months.value = '';
  await plan.apply();
  assert.equal(plan.months.hidden, true);
  assert.equal(plan.state.requests.length, 1);
  assert.equal('months' in plan.state.requests[0], false);
});
