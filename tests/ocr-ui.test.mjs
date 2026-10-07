import test from 'node:test';
import assert from 'node:assert/strict';
import {openOCR} from '../web/ocr-ui.js';

// Only image/network/DOM stand-ins are mocked. Tests execute the actual UI
// workflow and make no claim about OCR recognition or visual browser rendering.
const deferred = () => {let resolve,reject;const promise=new Promise((a,b)=>{resolve=a;reject=b;});return {promise,resolve,reject};};
const tick = async () => {for(let i=0;i<8;i++)await Promise.resolve();};
function fixture({content}={}) {
  let session=0;
  const calls=[],errors=[],opened=[];
  const controls = name => ({name,value:name==='page'?'1':name==='text'?'-2.5 kN':name==='reason'?'independent review':'',checked:false,disabled:name==='confirmed',isConnected:true});
  function form(names) {
    const values=Object.fromEntries(names.map(name=>[name,controls(name)])),listeners={};
    const button={disabled:names.includes('confirmed'),isConnected:true};
    return {dataset:{ocr:'page-1'},listeners,values,button,elements:{namedItem:name=>values[name]},
      addEventListener:(name,fn)=>listeners[name]=fn,
      querySelector:selector=>selector.includes('confirmed')?values.confirmed:button};
  }
  const confirm=form(['text','reason','confirmed']),extract=form(['page']);
  const image={dataset:{ocrImage:'image-1'},isConnected:true,naturalWidth:64,decode:async()=>{},src:''};
  const status={innerHTML:'',querySelectorAll:()=>[]},retry={hidden:true,listeners:{},addEventListener(name,fn){this.listeners[name]=fn;}};
  const article={querySelector:selector=>({'[data-ocr-image]':image,'[data-ocr-image-status]':status,'[data-ocr-retry]':retry,'.ocr-confirm-form':confirm})[selector]};
  const closeListeners=new Set();
  const modal={open:true,
    querySelectorAll:selector=>selector==='[data-ocr-record]'?[article]:selector.startsWith('form input')?[...Object.values(confirm.values),confirm.button,...Object.values(extract.values),extract.button]:[],
    querySelector:selector=>selector==='#ocr-extract-form'?extract:null,
    addEventListener:(name,fn)=>{if(name==='close')closeListeners.add(fn);},
    removeEventListener:(name,fn)=>{if(name==='close')closeListeners.delete(fn);},
  };
  const priorDocument=globalThis.document;
  globalThis.document={getElementById:()=>modal,title:''};
  const ctx={role:'reviewer',projectPath:suffix=>'/projects/A'+suffix,
    openModal(title,body){session++;opened.push({title,body});},captureDialogSession:()=>session,isDialogCurrent:token=>token===session,
    setDialogPending:()=>{},refresh:async()=>{},error:error=>errors.push(error.message),
    async request(path,options={}) {
      calls.push({path,options});
      if(path==='/ocr')return {enabled:true,available:true,provider:'synthetic test'};
      if(path.endsWith('/content'))return content();
      if(options.method==='POST')return {ok:true};
      return {items:[{id:'page-1',page:1,state:'PENDING_REVIEW',image_file_id:'image-1',text:'-2.5 kN',lines:[]}]};
    },
  };
  const close=()=>{session++;modal.open=false;for(const fn of closeListeners)fn();globalThis.document=priorDocument;};
  return {ctx,calls,errors,opened,confirm,extract,image,status,retry,invalidate:()=>session++,close};
}
const response=()=>({arrayBuffer:async()=>new Uint8Array([1]).buffer});
const submit=form=>{let prevented=false;form.listeners.submit({preventDefault(){prevented=true;}});return prevented;};

test('submit handlers exist before slow images; unseen images cannot be confirmed', async () => {
  const wait=deferred(),f=fixture({content:()=>wait.promise});
  const operation=openOCR(f.ctx,'source-1');await tick();
  assert.equal(typeof f.extract.listeners.submit,'function');assert.equal(typeof f.confirm.listeners.submit,'function');
  assert.equal(submit(f.confirm),true);assert.equal(f.confirm.button.disabled,true);
  assert.equal(f.calls.filter(c=>c.options.method==='POST').length,0);
  wait.resolve(response());await operation;
  assert.equal(f.confirm.button.disabled,false);f.close();
});

test('failed image retains bound forms and a working retry; decoding gates confirmation', async () => {
  let first=true;const decode=deferred();
  const f=fixture({content:()=>first?(first=false,Promise.reject(Error('synthetic image unavailable'))):Promise.resolve(response())});
  await openOCR(f.ctx,'source-1');
  assert.equal(f.retry.hidden,false);assert.equal(f.confirm.button.disabled,true);assert.equal(submit(f.confirm),true);
  f.image.decode=()=>decode.promise;f.retry.listeners.click({preventDefault(){}});await tick();
  assert.equal(f.confirm.button.disabled,true);decode.resolve();await tick();
  assert.equal(f.confirm.button.disabled,false);f.close();
});

test('late image from a replaced dialog cannot enable its confirmation', async () => {
  const wait=deferred(),f=fixture({content:()=>wait.promise});
  const operation=openOCR(f.ctx,'source-1');await tick();f.invalidate();wait.resolve(response());await operation;
  assert.equal(f.confirm.button.disabled,true);assert.equal(f.image.src,'');f.close();
});

test('confirmation is locked while pending and uses the captured project path', async () => {
  const f=fixture({content:()=>Promise.resolve(response())});await openOCR(f.ctx,'source-1');
  const pending=deferred(),original=f.ctx.request;
  f.ctx.projectPath=suffix=>'/projects/B'+suffix;
  f.ctx.request=(path,options={})=>{if(options.method==='POST'){f.calls.push({path,options});return pending.promise;}return original(path,options);};
  f.confirm.values.confirmed.checked=true;assert.equal(submit(f.confirm),true);assert.equal(submit(f.confirm),true);
  const posts=f.calls.filter(c=>c.options.method==='POST');assert.equal(posts.length,1);
  assert.equal(posts[0].path,'/projects/A/ocr/page-1/confirm');
  assert.equal(posts[0].options.body.numbers_units_columns_checked,true);
  pending.reject(Error('synthetic save failure'));await tick();assert.equal(f.confirm.values.text.value,'-2.5 kN');f.close();
});
