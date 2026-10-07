import test from 'node:test';
import assert from 'node:assert/strict';
import {tableView,compareDecimalText,uiIcon,statusBadge,statusPresentation,validatedTableState} from '../web/ui-foundation.js';
import {setLanguage,translateMarked} from '../web/i18n.js';

test('status badges add icon and text while preserving the exact protocol value',()=>{
  setLanguage('en');const raw='NOT VERIFIED';const badge=statusBadge(raw);
  assert.match(badge,/data-status="NOT VERIFIED"/);assert.match(badge,/ui-status--warning/);
  assert.match(badge,/<svg[^>]+aria-hidden="true"/);assert.match(badge,/<span data-i18n-status="NOT VERIFIED">NOT VERIFIED<\/span>/);
  setLanguage('zh-CN');assert.match(statusBadge(raw),/>未验证<\/span>/);assert.equal(raw,'NOT VERIFIED');setLanguage('en');
  assert.equal(statusPresentation('FAIL').tone,'danger');assert.equal(statusPresentation('PASS').tone,'success');assert.equal(statusPresentation('RUNNING').tone,'progress');
});
test('unrecognized status and icon inputs cannot inject HTML attributes or scripts',()=>{
  const raw='"><img src=x onerror=alert(1)>';
  const badge=statusBadge(raw);assert.ok(!badge.includes('<img'));assert.match(badge,/&lt;img/);
  const icon=uiIcon('<script>',{size:NaN,className:'" onload="alert(1)'});assert.ok(!icon.includes('<script'));assert.match(icon,/width="20"/);assert.ok(!icon.includes('class="ui-icon " onload="'));
});
test('in-place status translation has a text marker separate from the icon wrapper',()=>{
  const originalIcon={path:'warning',ariaHidden:true};
  const node={value:'NOT VERIFIED',textContent:'NOT VERIFIED',getAttribute:()=> 'NOT VERIFIED'};
  const root={querySelectorAll(selector){return selector==='[data-i18n-status]'?[node]:[];}};
  setLanguage('zh-CN');translateMarked(root);assert.equal(node.textContent,'未验证');assert.deepEqual(originalIcon,{path:'warning',ariaHidden:true});setLanguage('en');translateMarked(root);assert.equal(node.textContent,'NOT VERIFIED');
});
test('decimal sorting distinguishes integers beyond binary floating point precision',()=>{
  assert.equal(compareDecimalText('9007199254740993','9007199254740992'),1);
  assert.equal(compareDecimalText('-9007199254740993','-9007199254740992'),-1);
  assert.equal(compareDecimalText('1e-400','2e-400'),-1);
  assert.equal(compareDecimalText('1.0000000000000000002','1.0000000000000000001'),1);
  assert.equal(compareDecimalText('0.00012','1.2e-4'),0);
  assert.equal(compareDecimalText('-0','+0.000'),0);
  assert.equal(compareDecimalText('1.20e3','1200'),0);
  assert.equal(compareDecimalText('100 kN','100'),null);
});
test('local numeric sorting is stable in both directions and never changes frozen source rows',()=>{
  const rows=Object.freeze([Object.freeze(['A','2']),Object.freeze(['B','1']),Object.freeze(['C','2']),Object.freeze(['D','']),Object.freeze(['E','not a number'])]);
  const before=JSON.stringify(rows);
  assert.deepEqual(tableView(rows,{sortColumn:1,sortDirection:'ascending',columnTypes:['text','number']}).rowIndexes,[1,0,2,3,4]);
  assert.deepEqual(tableView(rows,{sortColumn:1,sortDirection:'descending',columnTypes:['text','number']}).rowIndexes,[0,2,1,3,4]);
  assert.deepEqual(tableView(rows,{sortColumn:1,sortDirection:'none'}).rowIndexes,[0,1,2,3,4]);assert.equal(JSON.stringify(rows),before);
});
test('auto numeric sort orders negative scientific values exactly rather than lexicographically',()=>{
  const rows=[['1e-400'],['2e-400'],['-0.5'],['-2'],['0'],['9007199254740993'],['9007199254740992']];
  assert.deepEqual(tableView(rows,{sortColumn:0,sortDirection:'ascending'}).rowIndexes,[3,2,4,0,1,6,5]);
});
test('filtering searches bilingual and raw field content without rewriting it',()=>{
  const rows=[['客户原文 -1.20 kN','NOT VERIFIED'],['客户原文 -1.20 kN','PASS'],['Client supplied','FAIL'],['ＡＢＣ','PASS']];
  const before=JSON.stringify(rows);
  assert.deepEqual(tableView(rows,{filter:'客户 NOT VERIFIED'}).rowIndexes,[0]);
  assert.deepEqual(tableView(rows,{filter:'client FAIL'}).rowIndexes,[2]);
  assert.deepEqual(tableView(rows,{filter:'abc'}).rowIndexes,[3]);assert.equal(JSON.stringify(rows),before);
});
test('pagination works on filtered and sorted rows with accurate empty-state counts',()=>{
  const rows=Array.from({length:13},(_,i)=>[String(i),i%2?'odd':'even']);
  const page=tableView(rows,{filter:'even',sortColumn:0,sortDirection:'descending',pageSize:3,page:2});
  assert.deepEqual(page.rowIndexes,[6,4,2]);assert.equal(page.total,13);assert.equal(page.filtered,7);assert.equal(page.start,4);assert.equal(page.end,6);assert.equal(page.pages,3);
  assert.deepEqual(tableView(rows,{filter:'none',page:4,pageSize:3}),{rowIndexes:[],allIndexes:[],total:13,filtered:0,page:1,pages:1,start:0,end:0});
  assert.equal(tableView(rows,{page:999,pageSize:5}).page,3);
});
test('invalid pagination/sort requests fail explicitly instead of silently coercing',()=>{
  assert.throws(()=>tableView([['a']],{pageSize:0}),RangeError);assert.throws(()=>tableView([['a']],{pageSize:501}),RangeError);
  assert.throws(()=>tableView([['a']],{page:0}),RangeError);assert.throws(()=>tableView([['a']],{sortDirection:'random'}),TypeError);
  assert.throws(()=>tableView([['a']],{sortColumn:-1}),RangeError);assert.throws(()=>tableView([{value:'a'}]),TypeError);
});


test('explicit sort values do not replace the displayed text used by the filter',()=>{
  const sortValues=[['1760000000000'],['1760000000001']];
  const displayed=[['7 Oct, 10:36 pm'],['7 Oct, 10:37 pm']];
  assert.deepEqual(tableView(sortValues,{searchRows:displayed,filter:'10:36',sortColumn:0,sortDirection:'descending'}).rowIndexes,[0]);
  assert.deepEqual(tableView(sortValues,{searchRows:displayed,filter:'1760000000000'}).rowIndexes,[]);
  assert.throws(()=>tableView(sortValues,{searchRows:[]}),TypeError);
});


test('saved table state restores filter, stable sort and page without retaining customer records',()=>{
  const snapshot=Object.freeze({filter:'客户',sortColumn:1,sortDirection:'descending',page:2,pageSize:2});
  const restored=validatedTableState(snapshot,{columnCount:3,sortableColumns:[0,1]});
  const rows=[['客户 A','1'],['客户 B','2'],['Other','3'],['客户 C','4']];
  const view=tableView(rows,restored);assert.deepEqual(view.rowIndexes,[0]);assert.equal(view.page,2);
  restored.filter='changed';assert.equal(snapshot.filter,'客户');
  assert.deepEqual(Object.keys(restored).sort(),['filter','page','pageSize','sortColumn','sortDirection']);
  assert.deepEqual(validatedTableState({}),{filter:'',sortColumn:null,sortDirection:'none',page:1,pageSize:10});
});
test('invalid saved state is rejected before DOM preferences can be applied',()=>{
  const original={filter:'safe',sortColumn:0,sortDirection:'ascending',page:1,pageSize:10};
  for(const bad of [{filter:7},{page:0},{pageSize:501},{sortDirection:'random'},{sortColumn:4}]){
    assert.throws(()=>validatedTableState({...original,...bad},{columnCount:3,sortableColumns:[0,1]}));
  }
  assert.throws(()=>validatedTableState({...original,sortColumn:2},{columnCount:3,sortableColumns:[0,1]}),RangeError);
  assert.throws(()=>validatedTableState(null),TypeError);assert.equal(original.filter,'safe');
});
