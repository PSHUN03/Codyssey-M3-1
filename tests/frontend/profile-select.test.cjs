const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

// A small DOM fixture exercises keyboard and selection behavior without a browser dependency.
function setup() {
  let document;
  class Element {
    constructor(tag) {
      Object.assign(this, { tag, children: [], attributes: {}, events: {}, style: {}, className: '',
        hidden: false, disabled: false, scrollTop: 0, scrollHeight: 220, clientHeight: 220,
        offsetTop: 0, offsetHeight: 44, textContent: '' });
      this.classList = {
        add: (...names) => { this.className = [...new Set([...this.className.split(' ').filter(Boolean), ...names])].join(' '); },
        remove: (...names) => { this.className = this.className.split(' ').filter(n => !names.includes(n)).join(' '); },
        toggle: (name, on) => { if (on) this.classList.add(name); else this.classList.remove(name); },
      };
    }
    append(...nodes) { this.children.push(...nodes); nodes.forEach(n => { n.parent = this; }); }
    after(node) { this.next = node; }
    contains(node) { return this === node || this.children.some(child => child.contains(node)); }
    setAttribute(name, value) { this.attributes[name] = String(value); }
    getAttribute(name) { return this.attributes[name] ?? null; }
    removeAttribute(name) { delete this.attributes[name]; }
    addEventListener(name, callback) { (this.events[name] ||= []).push(callback); }
    dispatchEvent(event) { (this.events[event.type] || []).forEach(fn => fn(event)); return true; }
    focus() { document.activeElement = this; document.dispatchEvent({ type: 'focusin', target: this }); }
    getBoundingClientRect() { return this.rect || { top: 200, bottom: 256 }; }
    get value() { return this.options ? this.options[this.selectedIndex]?.value : this._value; }
    set value(value) { this._value = value; }
  }
  document = new Element('document');
  document.createElement = tag => new Element(tag);
  const form = new Element('form');
  form.selects = ['company', 'region'].map((id, group) => {
    const select = new Element('select'), label = new Element('label');
    select.id = id;
    select.name = group ? 'region' : 'company_size';
    select.selectedIndex = 1;
    select.options = (group ? ['', '서울', '부산'] : ['', '중소기업', '중견기업', '대기업', '공공기관']).map(text => {
      const option = new Element('option');
      option.textContent = text || '해당 없음';
      option.value = text;
      return option;
    });
    select.label = label;
    return select;
  });
  document.querySelector = selector => form.selects.find(s => selector === `label[for="${s.id}"]`)?.label;
  const window = new Element('window');
  Object.assign(window, { innerHeight: 900, innerWidth: 1200 });
  const source = fs.readFileSync(path.join(__dirname, '../../app/static/js/app.js'), 'utf8');
  const implementation = source.slice(source.indexOf('function initProfileSelects('), source.indexOf('\nfunction initSettings('));
  vm.runInNewContext(`${implementation}\ninitProfileSelects(form);`, {
    document, window, form, $$: () => form.selects, Date, setTimeout,
    Event: class { constructor(type, options) { this.type = type; Object.assign(this, options); } },
  });
  const controls = form.selects.map(select => ({ select, trigger: select.next.children[0], menu: select.next.children[1] }));
  function key(control, key) {
    control.trigger.dispatchEvent({ type: 'keydown', key, preventDefault() {}, stopPropagation() {} });
  }
  function click(element) { element.dispatchEvent({ type: 'click', target: element }); }
  return { form, document, controls, key, click };
}

test('exposes one labelled combobox and selected check per native value', () => {
  const { controls } = setup();
  for (const { select, trigger, menu } of controls) {
    assert.equal(select.hidden, true);
    assert.equal(select.tabIndex, -1);
    assert.equal(trigger.type, 'button');
    assert.equal(trigger.getAttribute('role'), 'combobox');
    assert.equal(trigger.getAttribute('aria-controls'), menu.id);
    assert.equal(select.label.htmlFor, trigger.id);
    assert.equal(menu.children.filter(n => n.getAttribute('aria-selected') === 'true').length, 1);
    assert.equal(menu.children[select.selectedIndex].getAttribute('aria-selected'), 'true');
  }
});

test('Escape cancels keyboard navigation without changing the saved form value', () => {
  const { controls: [control], key } = setup();
  key(control, 'ArrowDown');
  key(control, 'ArrowDown');
  assert.equal(control.select.value, '중소기업');
  assert.equal(control.trigger.getAttribute('aria-activedescendant'), 'company-option-2');
  key(control, 'Escape');
  assert.equal(control.menu.hidden, true);
  assert.equal(control.select.value, '중소기업');
  assert.equal(control.trigger.getAttribute('aria-activedescendant'), null);
});

test('Enter commits the native form value exactly once and restores focus', () => {
  const { controls: [control], key, document } = setup();
  const events = [];
  for (const type of ['input', 'change']) control.select.addEventListener(type, () => events.push(type));
  key(control, 'ArrowDown');
  key(control, 'ArrowDown');
  key(control, 'Enter');
  assert.equal(control.select.value, '중견기업');
  assert.deepEqual(events, ['input', 'change']);
  assert.equal(control.trigger.children[0].textContent, '중견기업');
  assert.equal(control.menu.children[2].getAttribute('aria-selected'), 'true');
  assert.equal(document.activeElement, control.trigger);
  assert.equal(control.menu.hidden, true);
});

test('pointer selection and external value changes keep the label and check in sync', () => {
  const { controls: [control], click } = setup();
  click(control.trigger);
  click(control.menu.children[3]);
  assert.equal(control.select.value, '대기업');
  control.select.selectedIndex = 4;
  control.select.dispatchEvent({ type: 'change' });
  assert.equal(control.trigger.children[0].textContent, '공공기관');
  assert.equal(control.menu.children[4].getAttribute('aria-selected'), 'true');
});

test('only one menu opens and outside click or Tab closes it', () => {
  const { controls: [first, second], click, key, document } = setup();
  click(first.trigger);
  click(second.trigger);
  assert.equal(first.menu.hidden, true);
  assert.equal(second.menu.hidden, false);
  document.dispatchEvent({ type: 'pointerdown', target: document });
  assert.equal(second.menu.hidden, true);
  key(first, ' ');
  key(first, 'Tab');
  assert.equal(first.menu.hidden, true);
  assert.equal(first.select.value, '중소기업');
});

test('Home, End and typing navigate and commit the intended option', () => {
  const { controls: [control], key } = setup();
  key(control, 'End');
  key(control, 'Enter');
  assert.equal(control.select.value, '공공기관');
  key(control, 'Home');
  key(control, 'Enter');
  assert.equal(control.select.value, '');
  key(control, '대');
  key(control, 'Enter');
  assert.equal(control.select.value, '대기업');
});
