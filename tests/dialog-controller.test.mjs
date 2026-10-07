import test from 'node:test';
import assert from 'node:assert/strict';
import {createDialogController} from '../web/dialog-controller.js';

// Minimal DOM stand-ins exercise the real controller; browser focus/layout are
// separately checked in the acceptance run, not claimed by these unit tests.
function fixture() {
  const listeners = new Map(), nodes = [];
  const document = {activeElement:null, querySelector:() => null, createElement:() => node()};
  function node() {
    return {isConnected:true, disabled:false, dataset:{}, children:[], attributes:{},
      setAttribute(k,v) {this.attributes[k]=v;}, querySelectorAll:() => [],
      querySelector() {return {focus(){}};}, append(el) {this.children.push(el);nodes.push(el);},
      remove() {this.isConnected=false;}, contains:() => false,
      focus() {document.activeElement=this;}, closest:() => null};
  }
  const opener = node(); document.activeElement = opener;
  const body = node(), heading = node(), form = node(); form.getAttribute = () => 'edit-form';
  const input = {...node(),form,type:'text',name:'title',id:'title',value:'',closest:() => form};
  const controls = [input];
  const dialog = {...node(), ownerDocument:document, open:false,
    querySelectorAll:selector => selector.startsWith('form input') ? controls : [],
    querySelector:selector => selector === '.modal-body' ? body : selector === 'h2' ? heading : selector === 'form' ? form : controls.find(c => !c.disabled),
    contains:el => el !== opener,
    addEventListener(name,fn) {listeners.set(name,fn);},
    getBoundingClientRect:() => ({left:0,right:100,top:0,bottom:100}),
    close() {this.open=false;queueMicrotask(() => listeners.get('close')?.({}));},
  };
  const controller = createDialogController(dialog);
  const open = () => {controller.prepare();dialog.open=true;controller.opened();};
  return {document,opener,dialog,controller,input,controls,nodes,listeners,open};
}
const tick = () => Promise.resolve();

test('opened baseline includes synchronous editor hydration and focuses a form control', async () => {
  const f=fixture();f.open();f.controls.push({...f.input,name:'hydrated',value:'initial'});await tick();
  assert.equal(f.document.activeElement,f.input);
  assert.equal(f.controller.requestClose(),true);
  await tick();assert.equal(f.document.activeElement,f.opener);
});

test('dirty close retains the original form and presents an inline choice', async () => {
  const f=fixture();f.open();await tick();f.input.value='unsaved value';
  assert.equal(f.controller.requestClose(),false);assert.equal(f.dialog.open,true);
  assert.equal(f.input.value,'unsaved value');
  const guard=f.nodes.find(n=>n.className?.includes('dialog-close-guard'));
  assert.match(guard.innerHTML,/data-dialog-choice="keep"/);
  assert.match(guard.innerHTML,/data-dialog-choice="discard"/);
  assert.equal(f.controller.requestClose({force:true}),true);
});

test('native Escape and pending close do not discard an in-flight form', async () => {
  const f=fixture();f.open();await tick();f.controller.setPending(true);
  let prevented=false;f.listeners.get('cancel')({preventDefault(){prevented=true;}});
  assert.equal(prevented,true);assert.equal(f.dialog.open,true);
  assert.equal(f.controller.requestClose(),false);
  f.controller.setPending(false);assert.equal(f.controller.requestClose(),true);
});

test('forced close invalidates the token immediately, including a closed loading context', async () => {
  const f=fixture();f.open();await tick();const old=f.controller.captureSession();
  f.controller.requestClose({force:true});assert.equal(f.controller.isCurrent(old),false);
  await tick();const closed=f.controller.captureSession();f.controller.requestClose({force:true});
  assert.equal(f.controller.isCurrent(closed),false);
});

test('queued close from an older session cannot erase a newly opened dialog', async () => {
  const f=fixture();f.open();await tick();f.controller.requestClose({force:true});f.open();
  const current=f.controller.captureSession();await tick();
  assert.equal(f.dialog.open,true);assert.equal(f.controller.isCurrent(current),true);
  assert.equal(f.document.activeElement,f.input);
});
