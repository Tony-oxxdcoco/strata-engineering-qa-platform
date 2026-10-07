import test from 'node:test';
import assert from 'node:assert/strict';
import {capturePageState,restorePageState,enhanceFormAccessibility,controlKey} from '../web/ui-page-state.js';

// Deliberately small DOM fixtures exercise state transfer, not browser layout,
// native focus, file selection or event propagation. Root GUI acceptance covers
// those separately; these tests must not be reported as real browser evidence.
const draftSelector='form input,form textarea,form select,#resume-snapshot,#resume-target,[name="benchmark-case"]';
const focusSelector='input,textarea,select,button,summary';
const tableSelector='input[data-table-control],select[data-table-control]';
function control({id='',name='',value='',type='text',tagName='INPUT',checked=false,options=[],dataset={},formId='test-form',disabled=false}={}) {
  const attributes={};
  return {id,name,value,type,tagName,checked,options:options.map(value=>({value})),dataset:{...dataset},disabled,
    form:{id:formId,getAttribute:key=>key==='id'?formId:null},selectionStart:0,selectionEnd:0,
    focusCalls:[],focus(options){this.focusCalls.push(options);},setSelectionRange(start,end){this.selectionStart=start;this.selectionEnd=end;},setAttribute(key,value){attributes[key]=value;},getAttribute:key=>attributes[key]??null};
}
function fixture({controls=[],tableControls=[],details=[],scrolls=[],active=null,tables=[]}={}) {
  return {ownerDocument:{activeElement:active},_uiTables:tables,
    contains(node){return controls.includes(node)||tableControls.includes(node);},
    querySelectorAll(selector){
      if(selector===draftSelector)return controls;
      if(selector===focusSelector)return [...controls,...tableControls];
      if(selector===tableSelector)return tableControls;
      if(selector==='details')return details;
      if(selector==='.task-options,.table-wrap,.history-scroll')return scrolls;
      if(selector==='.field')return this.fields||[];
      throw new Error(`Unsupported test DOM selector: ${selector}`);
    }};
}
function field(input){
  const caption={htmlFor:'',contains:()=>false},help={id:''};
  return {caption,help,querySelector(selector){if(selector==='label')return caption;if(selector==='.field-note')return help;if(selector==='input:not([type="hidden"]),textarea,select')return input;throw Error(selector);}};
}

test('raw drafts preserve decimal precision, source text and checkbox state verbatim',()=>{
  const values=['9007199254740993','1e-400','客户原文 PASS -1.20 kN <script>'];
  const old=values.map((value,i)=>control({id:`value-${i}`,value}));old.push(control({id:'case-one',name:'benchmark-case',type:'checkbox',value:'case-raw-id',checked:true}));
  const saved=capturePageState(fixture({controls:old}));const replacements=old.map(el=>control({id:el.id,name:el.name,type:el.type,value:'new default'}));
  restorePageState(fixture({controls:replacements}),saved);
  assert.deepEqual(replacements.slice(0,3).map(el=>el.value),values);assert.equal(replacements[3].checked,true);assert.equal(replacements[3].value,'case-raw-id');
  assert.deepEqual(saved.controls.slice(0,3).map(el=>el.value),values);
});
test('removed select options and managed engineering selections cannot be restored from an old draft',()=>{
  const old=[control({id:'resume-snapshot',tagName:'SELECT',type:'select-one',value:'removed',options:['removed']}),control({id:'snapshot-select',tagName:'SELECT',type:'select-one',value:'old-engineering-id',options:['old-engineering-id']})];
  const saved=capturePageState(fixture({controls:old}));
  assert.equal(saved.controls.length,1);
  const current=[control({id:'resume-snapshot',tagName:'SELECT',type:'select-one',value:'new',options:['new']}),control({id:'snapshot-select',tagName:'SELECT',type:'select-one',value:'current-id',options:['current-id']})];
  restorePageState(fixture({controls:current}),saved);assert.equal(current[0].value,'new');assert.equal(current[1].value,'current-id');
});
test('password, file, hidden and submit controls never enter the in-tab draft cache',()=>{
  const controls=['password','file','hidden','submit','button'].map(type=>control({id:type,type,value:'private'}));controls.push(control({id:'review-note',tagName:'TEXTAREA',type:'textarea',value:'Raw review note'}));
  const saved=capturePageState(fixture({controls}));assert.deepEqual(saved.controls,[{key:'id:review-note',value:'Raw review note',checked:false}]);
});
test('focus restoration requires the caller scope flag and preserves a text caret',()=>{
  const old=control({id:'review-note',name:'note',value:'Draft'});old.selectionStart=1;old.selectionEnd=4;
  const saved=capturePageState(fixture({controls:[old],active:old}));const current=control({id:'review-note',name:'note'}),root=fixture({controls:[current]});
  restorePageState(root,saved,{restoreFocus:false});assert.equal(current.focusCalls.length,0);
  restorePageState(root,saved,{restoreFocus:true});assert.deepEqual(current.focusCalls,[{preventScroll:true}]);assert.equal(current.selectionStart,1);assert.equal(current.selectionEnd,4);
  current.disabled=true;restorePageState(root,saved,{restoreFocus:true});assert.equal(current.focusCalls.length,1);
});
test('anonymous table filters retain saved preferences and caret across same-scope redraw',()=>{
  const oldFilter=control({value:'客户 NOT VERIFIED',dataset:{tableControl:'true'}});oldFilter.selectionStart=3;oldFilter.selectionEnd=6;
  const size=control({type:'select-one',tagName:'SELECT',value:'25',dataset:{tableControl:'true'}});
  const savedState={filter:oldFilter.value,sortColumn:1,sortDirection:'descending',page:2,pageSize:25};
  const oldTable={captureState:()=>({...savedState})};
  const saved=capturePageState(fixture({tableControls:[oldFilter,size],active:oldFilter,tables:[oldTable]}));
  const newFilter=control({dataset:{tableControl:'true'}}),newSize=control({type:'select-one',tagName:'SELECT',value:'10',dataset:{tableControl:'true'}});
  let restored;
  const currentTable={restoreState(value){restored={...value};newFilter.value=value.filter;newSize.value=String(value.pageSize);}};
  restorePageState(fixture({tableControls:[newFilter,newSize]}),saved,{tables:[currentTable],restoreFocus:true});
  assert.deepEqual(restored,savedState);assert.equal(newFilter.value,'客户 NOT VERIFIED');assert.equal(newSize.value,'25');assert.equal(newFilter.focusCalls.length,1);assert.equal(newFilter.selectionStart,3);assert.equal(newFilter.selectionEnd,6);
  assert.equal(newSize.focusCalls.length,0);
});
test('generated field identities are stable and use the actual form attribute despite name=id masking',()=>{
  const create=()=>{const first=control({name:'value'}),second=control({name:'value'});const form={id:control({name:'id'}),getAttribute:key=>key==='id'?'rule-form':null};first.form=second.form=form;const root=fixture({controls:[first,second]});root.fields=[field(first),field(second)];enhanceFormAccessibility(root);return {first,second,root};};
  const old=create(),next=create();assert.equal(old.first.id,next.first.id);assert.equal(old.second.id,next.second.id);assert.notEqual(old.first.id,old.second.id);
  assert.equal(controlKey(old.first),controlKey(next.first));assert.ok(controlKey(old.first).startsWith('rule-form:'));
  assert.equal(old.root.fields[0].caption.htmlFor,old.first.id);assert.equal(old.first.getAttribute('aria-describedby'),`${old.first.id}-help`);
});

test('duplicate detail captions stay on the correct second section after a translated redraw',()=>{
  const detail=(caption,open=false,key)=>({dataset:key?{detailKey:key}:{},open,querySelector:()=>({textContent:caption})});
  const saved=capturePageState(fixture({details:[detail('Field values',false),detail('Field values',true)]}));
  const current=[detail('字段数值',false),detail('字段数值',false)];
  restorePageState(fixture({details:current}),saved);assert.equal(current[0].open,false);assert.equal(current[1].open,true);
});
test('explicit resource detail keys preserve the correct section when resource order changes',()=>{
  const detail=(key,open)=>({dataset:{detailKey:key},open,querySelector:()=>({textContent:'Read rule and parameters'})});
  const saved=capturePageState(fixture({details:[detail('rule:R1',false),detail('rule:R2',true)]}));
  const current=[detail('rule:R3',false),detail('rule:R2',false),detail('rule:R1',true)];
  restorePageState(fixture({details:current}),saved);assert.deepEqual(current.map(x=>x.open),[false,true,false]);
});

test('index fallbacks are discarded when results insert new sections during completion',()=>{
  const detail=(open,key)=>({dataset:key?{detailKey:key}:{},open,querySelector:()=>({textContent:'Original UI caption'})});
  const saved=capturePageState(fixture({details:[detail(true),detail(true,'run:trace')]}));
  const current=[detail(false,'finding:C1'),detail(false),detail(false,'run:trace')];
  restorePageState(fixture({details:current}),saved);
  assert.deepEqual(current.map(x=>x.open),[false,false,true]);
});
