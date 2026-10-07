import test from 'node:test';
import assert from 'node:assert/strict';
import {openAdapterBuilder} from '../web/editors.js';

// Executes the real editor event handler with controlled requests and minimal
// DOM stand-ins. This does not claim browser accessibility or engineering QA.
const deferred=()=>{let resolve,reject;const promise=new Promise((a,b)=>{resolve=a;reject=b;});return {promise,resolve,reject};};
function fixture() {
  const listeners={},requests=[],errors=[];
  let session=1;
  const selection={name:'inspect_file',value:'source-A'},paths={name:'inspect_paths',value:'/rows'};
  const target={isConnected:true,innerHTML:'',textContent:''};
  const button={dataset:{editor:'inspect-tables'},disabled:false,attributes:{},setAttribute(k,v){this.attributes[k]=v;},removeAttribute(k){delete this.attributes[k];},closest(){return this;}};
  const form={isConnected:true,addEventListener:(name,fn)=>listeners[name]=fn,
    querySelector:selector=>({'#table-inspection':target,'[data-editor="inspect-tables"]':button,'[name="inspect_file"]':selection,'[name="inspect_paths"]':paths})[selector]};
  const priorDocument=globalThis.document;globalThis.document={getElementById:()=>form};
  const ctx={files:()=>[],openModal:()=>{},projectPath:suffix=>'/projects/A'+suffix,captureDialogSession:()=>session,isDialogCurrent:s=>s===session,error:e=>errors.push(e.message),request(path,options){const wait=deferred();requests.push({path,options,...wait});return wait.promise;}};
  openAdapterBuilder(ctx);
  return {form,target,button,selection,requests,errors,ctx,
    click:()=>listeners.click({target:button}),
    choose(value){selection.value=value;listeners.change({target:selection});},
    replace(){session++;},finish(){globalThis.document=priorDocument;}};
}

test('a response from a dismissed editor cannot update a newer dialog', async()=>{
  const f=fixture();const inspect=f.click();f.replace();f.requests[0].resolve({columns:['old private source']});await inspect;
  assert.equal(f.target.innerHTML,'');assert.deepEqual(f.errors,[]);f.finish();
});

test('source changes invalidate an older inspection and latest response wins', async()=>{
  const f=fixture();const old=f.click();f.choose('source-B');const latest=f.click();
  f.requests[1].resolve({columns:['new source']});await latest;
  f.requests[0].resolve({columns:['old source']});await old;
  assert.match(f.target.innerHTML,/new source/);assert.doesNotMatch(f.target.innerHTML,/old source/);
  assert.equal(f.button.disabled,false);f.finish();
});

test('a detached target and stale error cannot write or report into another form', async()=>{
  const f=fixture();const inspect=f.click();f.form.isConnected=false;f.target.isConnected=false;
  f.requests[0].reject(Error('stale failure'));await inspect;assert.deepEqual(f.errors,[]);assert.equal(f.target.innerHTML,'');f.finish();
});

test('inspection keeps the captured project URL and restores a current failed button', async()=>{
  const f=fixture();f.ctx.projectPath=suffix=>'/projects/B'+suffix;const inspect=f.click();
  assert.equal(f.requests[0].path,'/projects/A/files/source-A/mapping-tables');assert.equal(f.button.disabled,true);
  f.requests[0].reject(Error('current source failure'));await inspect;
  assert.deepEqual(f.errors,['current source failure']);assert.equal(f.button.disabled,false);f.finish();
});
