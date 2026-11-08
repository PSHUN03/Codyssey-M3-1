const { test } = require('node:test');
const assert = require('node:assert/strict');
const { weeklyRequest, savingsRequest, validWeek } = require('../../app/static/js/checkin-contract.js');
const { parseMan, createSampleStore } = require('../../app/static/js/fe01.js');

test('weekly writes match the current BE-04 route and boolean paid field', () => {
  assert.deepEqual(weeklyRequest('2026-W45', false), {url:'/api/savings/weekly-check',method:'PUT',body:{week:'2026-W45',paid:false}});
  for (const value of ['false', 0, null]) assert.throws(() => weeklyRequest('2026-W45', value));
});
test('ISO weeks respect year boundaries and reject path injection', () => {
  assert.equal(validWeek('2026-W53'), true);
  for (const value of ['2025-W53','2026-W00','2026-W54','2026-W1','2026-W45/other']) assert.throws(()=>weeklyRequest(value,true));
});
test('65 manwon becomes 650000 integer won without double conversion', () => {
  assert.deepEqual(savingsRequest('2026-11',parseMan('65')), {url:'/api/savings/monthly',method:'POST',body:{month:'2026-11',amount:650000}});
  assert.equal(savingsRequest('2026-11',0).body.amount,0);
});

const live=require('../../app/static/js/checkin-contract.js');
test('real amounts preserve integer won precision and enforce current backend upper bound',()=>{
  assert.equal(live.parseMan('1.2345'),12345);assert.equal(live.parseMan('0.0001'),1);assert.equal(live.parseMan('1000'),10000000);assert.equal(live.parseMan('0'),0);
  for(const value of ['','-1','1e2','0.00001','1000.0001','NaN'])assert.throws(()=>live.parseMan(value));
  assert.throws(()=>savingsRequest('2026-11',10000001));
});
test('weekly reads normalize deposited or paid while preserving false and rejecting conflicts',()=>{
  assert.deepEqual(live.normalizeCheckins({checkins:[{week:'2026-W45',deposited:false}]}),[{week:'2026-W45',paid:false}]);
  assert.deepEqual(live.normalizeCheckins({checkins:[{week:'2026-W45',paid:true}]}),[{week:'2026-W45',paid:true}]);
  for(const row of [{week:'2026-W45',paid:'false'},{week:'2025-W53',paid:true},{week:'2026-W45',paid:false,deposited:true}])assert.throws(()=>live.normalizeCheckins({checkins:[row]}));
});
test('reads validate unique periods and never infer missing months or cumulative progress',()=>{
  const result=live.normalizeSavings({savings:[{month:'2026-11',amount:0},{month:'2026-09',amount:500000}]});
  assert.deepEqual(result,[{month:'2026-09',amount:500000},{month:'2026-11',amount:0}]);assert.equal('progress' in result,false);
  for(const row of [{month:'2026-13',amount:1},{month:'2026-11',amount:-1},{month:'2026-11',amount:'100'}])assert.throws(()=>live.normalizeSavings({savings:[row]}));
  assert.throws(()=>live.normalizeSavings({savings:[result[0],result[0]]}));assert.throws(()=>live.normalizeCheckins({checkins:[{week:'2026-W45',paid:true},{week:'2026-W45',paid:false}]}));
});
test('display window spans twelve calendar months across years without inventing zero records',()=>{
  const records=['2025-12','2026-01','2026-12','2027-01','2027-02'].map(month=>({month,amount:0}));
  assert.deepEqual(live.recentRecords(records,'2027-01').map(row=>row.month),['2026-12','2027-01']);
});
test('live transport uses authenticated no-store reads and current JSON writes',async()=>{
  const calls=[],responses=[{checkins:[]},{savings:[]},{ok:true,week:'2026-W45',paid:false},{ok:true,month:'2026-11',amount:12345}];
  const client=live.createClient(async(url,init)=>{calls.push({url,...init});return {ok:true,json:async()=>responses.shift()};});
  assert.deepEqual(await client.loadWeekly(),[]);assert.deepEqual(await client.loadSavings(),[]);assert.equal((await client.saveWeekly('2026-W45',false)).paid,false);assert.equal((await client.saveSavings('2026-11',12345)).amount,12345);
  assert.deepEqual(calls.map(call=>[call.url,call.method]),[['/api/checkins','GET'],['/api/savings','GET'],['/api/savings/weekly-check','PUT'],['/api/savings/monthly','POST']]);
  assert.ok(calls.every(call=>call.credentials==='same-origin'&&call.cache==='no-store'));assert.deepEqual(JSON.parse(calls[2].body),{week:'2026-W45',paid:false});
});
test('HTTP errors, malformed JSON and mismatched write acknowledgements never become success',async()=>{
  for(const status of [401,403,404,409,422,500]){const client=live.createClient(async()=>({ok:false,status}));await assert.rejects(client.loadWeekly(),error=>error.status===status);}
  const malformed=live.createClient(async()=>({ok:true,json:async()=>{throw new SyntaxError();}}));await assert.rejects(malformed.loadSavings(),/응답/);
  const wrong=live.createClient(async()=>({ok:true,json:async()=>({ok:true,month:'2026-10',amount:10000})}));await assert.rejects(wrong.saveSavings('2026-11',10000),/저장 결과/);
});
test('invalid writes are rejected before transport and abort signal is propagated',async()=>{
  let calls=0;const controller=new AbortController();const client=live.createClient(async(url,init)=>{calls++;assert.equal(init.signal,controller.signal);return{ok:true,json:async()=>({savings:[]})};});
  await assert.rejects(client.saveWeekly('2025-W53',true));await assert.rejects(client.saveSavings('2026-11',-1));assert.equal(calls,0);await client.loadSavings({signal:controller.signal});assert.equal(calls,1);
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
test('server progress is accepted only when it matches the GET /api/savings contract',async()=>{
  assert.deepEqual(live.normalizeProgress({progress:{saved_amount:3500000,target_amount:30000000,percentage:11.7}}),{saved:3500000,target:30000000,percentage:11.7});
  assert.deepEqual(live.normalizeProgress({progress:{saved_amount:0,target_amount:null,percentage:null}}),{saved:0,target:null,percentage:null});
  for(const progress of [undefined,{saved_amount:-1,target_amount:1,percentage:0},{saved_amount:1,target_amount:0,percentage:0},{saved_amount:1,target_amount:10,percentage:101},{saved_amount:1,target_amount:10,percentage:null},{saved_amount:'1',target_amount:10,percentage:10}])assert.equal(live.normalizeProgress({progress}),null);
  const client=live.createClient(async()=>({ok:true,json:async()=>({savings:[{month:'2026-11',amount:500000}],progress:{saved_amount:3500000,target_amount:30000000,percentage:11.7}})}));
  assert.deepEqual(await client.loadSavingsWithProgress(),{records:[{month:'2026-11',amount:500000}],progress:{saved:3500000,target:30000000,percentage:11.7}});
});
