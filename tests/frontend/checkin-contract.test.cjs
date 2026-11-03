const { test } = require('node:test');
const assert = require('node:assert/strict');
const { weeklyRequest, savingsRequest, validWeek } = require('../../app/static/js/checkin-contract.js');
const { parseMan, createSampleStore } = require('../../app/static/js/fe01.js');

test('weekly writes use the week in the URL and a boolean body', () => {
  assert.deepEqual(weeklyRequest('2026-W45', false), {url:'/api/checkins/2026-W45',method:'PUT',body:{paid:false}});
  for (const value of ['false', 0, null]) assert.throws(() => weeklyRequest('2026-W45', value));
});
test('ISO weeks respect year boundaries and reject path injection', () => {
  assert.equal(validWeek('2026-W53'), true);
  for (const value of ['2025-W53','2026-W00','2026-W54','2026-W1','2026-W45/other']) assert.throws(()=>weeklyRequest(value,true));
});
test('65 manwon becomes 650000 integer won without double conversion', () => {
  assert.deepEqual(savingsRequest('2026-11',parseMan('65')), {url:'/api/savings/2026-11',method:'PUT',body:{amount:650000}});
  assert.equal(savingsRequest('2026-11',0).body.amount,0);
});
test('malformed month, string, fractional and negative amounts are rejected', () => {
  for (const month of ['2026-00','2026-13','2026-1','../savings']) assert.throws(()=>savingsRequest(month,1));
  for (const amount of ['650000',-1,1.5,Infinity,Number.MAX_SAFE_INTEGER]) assert.throws(()=>savingsRequest('2026-11',amount));
});
test('same-period corrections replace the sample value and never append records', () => {
  const config={scope:'contract-test',week:'2026-W45',month:'2026-11',records:[{month:'2026-11',amount:0}]};
  const store=createSampleStore(config,null);
  store.recordWeekly(true);store.recordWeekly(false);store.recordSavings(parseMan('65'));store.recordSavings(parseMan('70'));
  assert.equal(store.read().paid,false);assert.deepEqual(store.read().records,[{month:'2026-11',amount:700000}]);
  assert.equal(config.records[0].amount,0);
});
