const { test } = require('node:test');
const assert = require('node:assert/strict');
const { normalizePreview, buildPreviewRequest, createPreviewClient, createSampleSource } = require('../../app/static/js/spending-contract.js');
const mapping={date:0,merchant:1,withdrawal:2,deposit:3};
const response=()=>({needs_mapping:false,mapping,header_row:0,transactions:[{date:'2026-10-01',merchant:'예시 카페',amount:-5000,category:'식비'},{date:'2026-10-02',merchant:'급여 예시',amount:2450000,category:'수입'}],errors:[]});
const file=(name='fake.csv',text='fictional rows')=>Object.assign(new Blob([text],{type:'text/csv'}),{name});

test('withdrawals become positive chart values while deposits stay outside spending',()=>{
  const original=response(),before=JSON.stringify(original),result=normalizePreview(original);
  assert.equal(result.totalSpending,5000);assert.equal(result.totalDeposits,2450000);assert.equal(result.expenses.length,1);
  assert.equal(result.expenses[0].amount,5000);assert.equal(result.expenses[0].signedAmount,-5000);
  assert.equal(result.fixedTotal,null);assert.equal(result.variableTotal,null);assert.equal(result.expenses[0].fixed,null);
  assert.equal('id'in result.expenses[0],false);assert.equal(JSON.stringify(original),before);
});
test('mapping-required previews preserve zero-based columns and do not invent transactions',()=>{
  const result=normalizePreview({needs_mapping:true,preview:[['날짜','예시 거래','출금']],transactions:[],errors:[]});
  assert.equal(result.status,'mapping-required');assert.equal(result.needsConfirmation,true);assert.deepEqual(result.preview,[['날짜','예시 거래','출금']]);assert.equal(result.expenses.length,0);
});
test('partial failures preserve one-based source row numbers for user confirmation',()=>{
  const payload=response();payload.errors=[{row:4,reason:'날짜 확인'}];
  const result=normalizePreview(payload);assert.equal(result.status,'partial');assert.equal(result.errors[0].row,4);assert.equal(result.needsConfirmation,true);
});
test('empty result remains explicit',()=>{
  const payload=response();payload.transactions=[];const result=normalizePreview(payload);
  assert.equal(result.status,'empty');assert.equal(result.totalSpending,0);assert.equal(result.fixedTotal,null);
});
test('malformed dates, unsafe amounts, unknown categories and malformed errors are rejected',()=>{
  for(const change of [{date:'2026-02-30'},{amount:'-5000'},{amount:1.5},{amount:Infinity},{category:'구독'}]){const payload=response();Object.assign(payload.transactions[0],change);assert.throws(()=>normalizePreview(payload));}
  const bad=response();bad.errors=[{row:0,reason:'bad'}];assert.throws(()=>normalizePreview(bad));
  for(const payload of [null,{},[],{needs_mapping:'false',transactions:[],errors:[]}])assert.throws(()=>normalizePreview(payload));
});
test('oversized responses and overflowing sums are rejected',()=>{
  const payload=response();payload.transactions=Array(10001).fill(payload.transactions[0]);assert.throws(()=>normalizePreview(payload));
  const sums=response();sums.transactions=Array(2).fill({...sums.transactions[0],amount:-Number.MAX_SAFE_INTEGER});assert.throws(()=>normalizePreview(sums));
});
test('preview request uses multipart file and lets the browser choose its boundary',()=>{
  const request=buildPreviewRequest(file());assert.equal(request.url,'/api/transactions/preview');assert.equal(request.method,'POST');assert.equal(request.credentials,'same-origin');
  assert.equal(request.body.get('file').name,'fake.csv');assert.equal('headers'in request,false);assert.equal(request.body.has('mapping'),false);
  const retry=buildPreviewRequest(file('fake.XLSX'),{mapping,headerRow:0});assert.deepEqual(JSON.parse(retry.body.get('mapping')),mapping);assert.equal(retry.body.get('header_row'),'0');
});
test('request rejects unsupported files and malformed mapping/header indices before transport',()=>{
  for(const input of [null,file('fake.xls'),file('fake.csv',''),{name:'large.xlsx',size:2*1024*1024+1}])assert.throws(()=>buildPreviewRequest(input));
  for(const options of [{mapping,headerRow:-1},{mapping,headerRow:20},{mapping:{date:-1},headerRow:0},{mapping:{unknown:1},headerRow:0},{mapping:{date:100},headerRow:0}])assert.throws(()=>buildPreviewRequest(file(),options));
});
test('transport is opt-in and can be exercised with a fake response before any real API exists',async()=>{
  assert.throws(()=>createPreviewClient());let calls=0;
  const preview=createPreviewClient(async(url,options)=>{calls++;assert.equal(url,'/api/transactions/preview');assert.equal(options.body.get('file').name,'fake.csv');return{ok:true,json:async()=>response()};});
  const result=await preview(file());assert.equal(calls,1);assert.equal(result.totalSpending,5000);
  await assert.rejects(preview(file('bad.pdf')));assert.equal(calls,1);
});
test('auth, consent, onboarding, validation and server failures remain errors',async()=>{
  for(const status of [401,403,409,422,500]){const preview=createPreviewClient(async()=>({ok:false,status}));await assert.rejects(preview(file()),error=>error.status===status&&error.message.length>0);}
});
test('sample source stays independent of API categories and cannot mutate its seed',()=>{
  const source=createSampleSource({rows:[{id:1,amount:100,category:'카페',fixed:false}],categories:['카페']});
  const first=source.read();first.rows[0].amount=999;first.categories.push('구독');assert.equal(source.read().rows[0].amount,100);assert.deepEqual(source.read().categories,['카페']);
});
