const {test}=require('node:test');
const assert=require('node:assert/strict');
const {normalizePreview}=require('../../app/static/js/spending-contract.js');
const {summarizePreview,PAGE_SIZE}=require('../../app/static/js/spending-preview.js');
function preview(){return normalizePreview({needs_mapping:false,mapping:{date:0,merchant:1,amount:2},header_row:0,errors:[],transactions:[
  {date:'2026-10-01',merchant:'예시 카페',amount:-5000,category:'식비'},
  {date:'2026-10-02',merchant:'급여',amount:2450000,category:'수입'},
  {date:'2026-10-03',merchant:'모의 버스',amount:-1500,category:'교통'}]});}
test('real chart and top spending exclude deposits and do not invent fixed costs',()=>{
  const data=preview(),result=summarizePreview(data);assert.equal(result.total,6500);assert.deepEqual(result.groups.map(row=>row.category),['식비','교통']);assert.equal(result.top.length,2);assert.equal(data.fixedTotal,null);assert.equal(PAGE_SIZE,20);
});
test('local reclassification changes preview chart without changing upload response',()=>{
  const data=preview(),before=JSON.stringify(data),result=summarizePreview(data,{0:'쇼핑',2:'쇼핑'});
  assert.equal(result.groups[0].amount,6500);assert.equal(result.groups[0].category,'쇼핑');assert.equal(result.total,6500);assert.equal(JSON.stringify(data),before);
});
test('API category list rejects sample-only or income overrides for expenses',()=>{
  const data=preview();for(const category of ['카페','구독','수입','unknown'])assert.equal(summarizePreview(data,{0:category}).top[0].category,'식비');
});
test('income-only and empty previews produce an explicit zero spending summary',()=>{
  const data=preview();data.expenses=[];data.totalSpending=0;assert.deepEqual(summarizePreview(data),{total:0,groups:[],top:[]});
});
