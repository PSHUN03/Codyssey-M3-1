const { test } = require('node:test');
const assert = require('node:assert/strict');
const { parseMan, summarize, createSampleStore } = require('../../app/static/js/fe01.js');
const config = {
  scope: 'test-user-a', month: '2026-11', week: '2026-W45', goal: { amount: 30000000 },
  records: [40, 45, 50, 60, 60, 65].map((value, index) => ({ month: `2026-${String(index + 6).padStart(2, '0')}`, amount: value * 10000 })),
};
function storage() {
  const entries = new Map();
  return { getItem: key => entries.get(key) ?? null, setItem: (key, value) => entries.set(key, value), entries };
}
test('money entered in ten-thousand-won units becomes integer won and zero is accepted', () => {
  assert.equal(parseMan('65'), 650000);
  assert.equal(parseMan('0'), 0);
  for (const value of ['', '-1', '0.5', '1e3', '1000001', 'not a number']) assert.throws(() => parseMan(value));
});
test('same-month sample update replaces the record instead of double counting', () => {
  const store = createSampleStore(config, storage());
  store.recordSavings(700000);
  const next = store.recordSavings(700000);
  assert.equal(next.records.length, 6);
  assert.equal(summarize(next.records, config.goal.amount).total, 3250000);
  assert.equal(next.records.at(-1).amount, 700000);
  store.recordSavings(0);
  assert.equal(summarize(store.read().records, config.goal.amount).total, 2550000);
});
test('weekly check is independent from monthly savings and accepts false explicitly', () => {
  const store = createSampleStore(config, storage());
  assert.equal(store.read().paid, null);
  store.recordWeekly(false);
  assert.equal(store.read().paid, false);
  assert.equal(summarize(store.read().records, config.goal.amount).total, 3200000);
  assert.throws(() => store.recordWeekly('false'));
});
test('sample updates survive page navigation within a browser tab', () => {
  const session = storage(), first = createSampleStore(config, session);
  first.recordSavings(700000); first.recordWeekly(true);
  const second = createSampleStore(config, session);
  assert.equal(second.read().paid, true);
  assert.equal(second.read().records.at(-1).amount, 700000);
  first.recordSavings(800000);
  assert.equal(second.reload().records.at(-1).amount, 800000);
});
test('different users and sample months cannot share each other\'s sample edits', () => {
  const session = storage();
  createSampleStore(config, session).recordSavings(700000);
  assert.equal(createSampleStore({ ...config, scope: 'test-user-b' }, session).read().records.at(-1).amount, 650000);
  assert.equal(createSampleStore({ ...config, month: '2026-12' }, session).read().records.at(-1).amount, 650000);
});
test('a new ISO week resets the weekly answer without losing the same month\'s savings', () => {
  const session = storage(), first = createSampleStore(config, session);
  first.recordWeekly(true); first.recordSavings(700000);
  const nextWeek = createSampleStore({ ...config, week: '2026-W46' }, session);
  assert.equal(nextWeek.read().paid, null);
  assert.equal(nextWeek.read().records.at(-1).amount, 700000);
});
test('malformed or invalid cached values cannot create invalid totals', () => {
  const session = storage(), key = 'sadari:fe01:sample:v1:test-user-a:2026-11';
  session.setItem(key, '{broken');
  assert.equal(createSampleStore(config, session).read().records.at(-1).amount, 650000);
  session.setItem(key, JSON.stringify({ version: 1, paid: 'yes', records: [{ month: '2026-11', amount: -100 }] }));
  const store = createSampleStore(config, session);
  assert.equal(store.read().paid, null);
  assert.equal(store.read().records.at(-1).amount, 650000);
  store.recordSavings(700000);
  assert.equal(store.isPersistent(), true);
  for (const amount of [-1, .5, NaN, Infinity, 10000000001]) assert.throws(() => store.recordSavings(amount));
});
test('blocked browser storage keeps interactions usable without claiming persistence', () => {
  const blocked = { getItem() { throw new Error('blocked'); }, setItem() { throw new Error('blocked'); } };
  const store = createSampleStore(config, blocked);
  store.recordSavings(700000);
  assert.equal(store.read().records.at(-1).amount, 700000);
  assert.equal(store.isPersistent(), false);
});
test('over-goal amounts keep their real sample total while the visual bar stops at 100%', () => {
  const result = summarize([{ month: '2026-11', amount: 40000000 }], 30000000);
  assert.equal(result.total, 40000000);
  assert.equal(result.cappedPercent, 100);
  assert.equal(result.remaining, 0);
  assert.ok(result.percent > 100);
});
test('reading sample state returns a copy and does not mutate the configuration', () => {
  const store = createSampleStore(config, storage()), result = store.read();
  result.records[0].amount = 999;
  assert.equal(store.read().records[0].amount, 400000);
  store.recordSavings(700000);
  assert.equal(config.records.at(-1).amount, 650000);
});
