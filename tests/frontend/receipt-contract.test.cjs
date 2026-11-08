const { test } = require('node:test');
const assert = require('node:assert/strict');
const { fromScanResponse } = require('../../app/static/js/receipt-contract.js');
const { toDraft, validateDraft } = require('../../app/static/js/receipts.js');

test('AI-02 field names populate the existing confirmation fields',()=>{
  const response={date:'2026-06-07',merchant_name:'예시 카페',total_amount:14000,currency:'KRW',items:[{name:'예시',price:14000}],masked_card_number:'****-****-****-1234'};
  const before=JSON.stringify(response),result=fromScanResponse(response);
  assert.deepEqual(toDraft(result),{date:'2026-06-07',merchant:'예시 카페',amount:'14000'});
  assert.deepEqual(Object.keys(result),['date','merchant','amount']);assert.equal(JSON.stringify(response),before);
});
test('null amounts stay blank even when item prices could suggest a value',()=>{
  const draft=toDraft(fromScanResponse({date:'2026-11-04',merchant_name:'예시',total_amount:null,items:[{price:9999}]}));
  assert.equal(draft.amount,'');assert.equal(validateDraft(draft).record,null);
});
test('missing, string, fractional, negative and unsafe amounts are never guessed',()=>{
  for(const total_amount of [undefined,'14000',1.5,-1,0,NaN,Number.MAX_SAFE_INTEGER+1])assert.equal(fromScanResponse({total_amount}).amount,null);
  assert.deepEqual(toDraft(fromScanResponse({})),{date:'',merchant:'',amount:''});
});
test('malformed payloads and non-KRW results cannot silently become a record',()=>{
  for(const value of [null,[],false,'bad'])assert.throws(()=>fromScanResponse(value));
  assert.throws(()=>fromScanResponse({currency:'USD',total_amount:14}));
  assert.equal(toDraft(fromScanResponse({date:'2026-02-30'})).date,'');
});
test('user corrections remain the source of the confirmed record',()=>{
  const draft=toDraft(fromScanResponse({date:'2026-11-04',merchant_name:'예시',total_amount:null}));
  draft.merchant='수정한 예시';draft.amount='20,000';
  assert.deepEqual(validateDraft(draft).record,{date:'2026-11-04',merchant:'수정한 예시',amount:20000});
});
