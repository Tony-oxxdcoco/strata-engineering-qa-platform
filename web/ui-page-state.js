// In-tab drafts belong to an exact project/page/run scope, never localStorage.
// Raw values are copied verbatim; field mapping and engineering input are not changed.
export function controlKey(control) {
  if(control.dataset?.uiGeneratedId)return `${control.form?.getAttribute('id') || 'page'}:${control.name || 'field'}:${control.dataset.uiFieldIndex}`;
  return control.id ? `id:${control.id}` : `${control.form?.getAttribute('id') || ''}:${control.name || ''}:${control.value && ['checkbox','radio'].includes(control.type)?control.value:''}`;
}
const managed = new Set(['snapshot-select','run-question','use-model','knowledge-query','search-task','before-snapshot','after-snapshot','compare-to','project-picker','run-filter','issue-filter']);
function draftControls(root) {
  return [...root.querySelectorAll('form input,form textarea,form select,#resume-snapshot,#resume-target,[name="benchmark-case"]')]
    .filter(el=>!managed.has(el.id) && !['file','hidden','submit','button','password'].includes(el.type));
}
export function capturePageState(root) {
  const active=root.ownerDocument.activeElement;
  const focus=root.contains(active)?{tableControl:[...root.querySelectorAll('input[data-table-control],select[data-table-control]')].indexOf(active),key:controlKey(active),action:active.dataset?.action,task:active.dataset?.task,run:active.dataset?.run,start:active.selectionStart,end:active.selectionEnd}:null;
  return {controls:draftControls(root).map(el=>({key:controlKey(el),value:el.value,checked:el.checked})),
    details:[...root.querySelectorAll('details')].map((el,index)=>({key:el.dataset.detailKey || `index:${index}`,open:el.open})),
    scrolls:[...root.querySelectorAll('.task-options,.table-wrap,.history-scroll')].map(el=>({left:el.scrollLeft,top:el.scrollTop})),
    tables:root._uiTables?.map(controller=>controller.captureState())||[],focus};
}
export function restorePageState(root,saved,{tables=[],restoreFocus=false}={}) {
  const controls=draftControls(root);
  for(const value of saved.controls || []) {
    const control=controls.find(el=>controlKey(el)===value.key);
    if(!control)continue;
    if(control.tagName==='SELECT' && ![...control.options].some(option=>option.value===value.value))continue;
    control.value=value.value;
    if(['radio','checkbox'].includes(control.type))control.checked=value.checked;
  }
  const details=[...root.querySelectorAll('details')];
  for(const value of saved.details || []){if(value.key.startsWith('index:') && saved.details.length!==details.length)continue;const detail=details.find((el,index)=>(el.dataset.detailKey || `index:${index}`)===value.key);if(detail)detail.open=value.open;}
  tables.forEach((controller,index)=>{if(saved.tables?.[index])controller.restoreState(saved.tables[index]);});
  [...root.querySelectorAll('.task-options,.table-wrap,.history-scroll')].forEach((el,index)=>{const position=saved.scrolls?.[index];if(position){el.scrollLeft=position.left;el.scrollTop=position.top;}});
  if(restoreFocus && saved.focus){
    const f=saved.focus;
    const focus=f.tableControl>=0?[...root.querySelectorAll('input[data-table-control],select[data-table-control]')][f.tableControl]:[...root.querySelectorAll('input,textarea,select,button,summary')].find(el=>f.key.startsWith('id:')?controlKey(el)===f.key:f.action?el.dataset.action===f.action && (!f.task||el.dataset.task===f.task) && (!f.run||el.dataset.run===f.run):el.name && controlKey(el)===f.key);
    if(focus && !focus.disabled){focus.focus({preventScroll:true});if(typeof f.start==='number' && focus.setSelectionRange)try{focus.setSelectionRange(f.start,f.end);}catch{/* Select/number inputs have no caret API. */}}
  }
}
export function enhanceFormAccessibility(root) {
  const seen=new Map();
  for(const field of root.querySelectorAll('.field')) {
    const control=field.querySelector('input:not([type="hidden"]),textarea,select');
    const caption=field.querySelector('label');
    if(!control)continue;
    if(!control.id){const identity=`${control.form?.getAttribute('id') || 'page'}-${control.name || 'field'}`;const index=seen.get(identity)||0;seen.set(identity,index+1);control.id=`strata-field-${identity.replace(/[^a-zA-Z0-9_-]/g,'-')}-${index}`;control.dataset.uiGeneratedId='true';control.dataset.uiFieldIndex=String(index);}
    if(caption && !caption.contains(control) && !caption.htmlFor)caption.htmlFor=control.id;
    const help=field.querySelector('.field-note');
    if(help){help.id ||= `${control.id}-help`;control.setAttribute('aria-describedby',help.id);}
    if(control.required)control.setAttribute('aria-required','true');
  }
}
