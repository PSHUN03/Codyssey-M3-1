const { test } = require('node:test');
const assert = require('node:assert/strict');
const { MAX_FILE_BYTES, validateFile, parseWon, validDate, validateDraft, sampleResult, toDraft } = require('../../app/static/js/receipts.js');

test('file selection accepts JPEG and PNG at the documented size boundary', () => {
  for (const type of ['image/jpeg','image/png']) assert.doesNotThrow(() => validateFile({ type, size: MAX_FILE_BYTES }));
});
test('unsupported, empty, and oversized files are rejected before preview', () => {
  for (const file of [null,{type:'application/pdf',size:100},{type:'image/heic',size:100},{type:'image/png',size:0},{type:'image/png',size:MAX_FILE_BYTES+1}]) assert.throws(()=>validateFile(file));
});
test('amounts remain integer won and accept a correctly grouped pasted amount', () => {
  assert.equal(parseWon('15500'),15500); assert.equal(parseWon(' 15,500 '),15500);
});
test('invalid amounts never become a different amount by stripping their signs or decimals', () => {
  for(const value of ['',null,'-10','10.5','1e3','1,2,3','0','9007199254740992']) assert.throws(()=>parseWon(value));
});
test('receipt dates must be real calendar dates', () => {
  assert.equal(validDate('2024-02-29'),true);
  for(const value of ['2026-02-29','2026-02-30','2026-13-01','2026/11/03','']) assert.equal(validDate(value),false);
});
test('a valid correction returns exactly the values the user confirmed', () => {
  assert.deepEqual(validateDraft({date:'2026-11-02',merchant:' 샘플 가게 ',amount:'20,000'}),{errors:{},record:{date:'2026-11-02',merchant:'샘플 가게',amount:20000}});
});
test('all required missing values produce errors without creating a record', () => {
  const result=validateDraft({date:'',merchant:'  ',amount:''});
  assert.deepEqual(Object.keys(result.errors),['date','merchant','amount']); assert.equal(result.record,null);
  assert.equal(validateDraft({date:'2026-11-03',merchant:'가'.repeat(81),amount:'1'}).record,null);
});
test('unread amounts stay blank for user confirmation instead of being guessed', () => {
  const result=sampleResult({sample_date:'2026-11-03',example:'missing'});
  assert.equal(result.amount,null); assert.equal(toDraft(result).amount,'');
  assert.equal(validateDraft(toDraft(result)).record,null);
});
test('null or malformed result fields stay blank and the adapter does not mutate results', () => {
  const original={date:null,merchant:null,amount:null};
  assert.deepEqual(toDraft(original),{date:'',merchant:'',amount:''});
  assert.deepEqual(original,{date:null,merchant:null,amount:null});
  assert.deepEqual(toDraft({date:'2026-99-99',merchant:'샘플',amount:-1}),{date:'',merchant:'샘플',amount:''});
});
test('sample data is deterministic, fictional, and independent of a selected image', () => {
  assert.deepEqual(sampleResult({sample_date:'2026-11-03',example:'complete'}),{date:'2026-11-03',merchant:'사다리 커피',amount:15500});
});
