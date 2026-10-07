import {parseStrictJSON} from './strict-json.js';
// Explicit configuration editors. They construct registered contracts, never formulas.
import {ui, label, displayStatus} from './i18n.js';
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const units = ['kN','N','m2','m²','kN/m2','kN/m²','kPa','N/m2','N/m²'];
const options = (values, chosen='') => values.map(v=>{const status=['synthetic','client','PASS','FAIL','NOT VERIFIED'].includes(v),trans=['number','string','boolean','rows','single','eq','in','range'].includes(v);return `<option value="${esc(v)}" ${status?`data-i18n-status="${esc(v)}"`:trans?`data-i18n="${esc(v)}"`:''} ${v===chosen?'selected':''}>${esc(status?displayStatus(v):trans?ui(v):v)}</option>`;}).join('');
const field = (text,name,value='',type='text',required=true) => `<div class="field"><label>${label(text)}${text.includes('one per line')?`<textarea name="${name}" rows="2" ${required?'required':''}>${esc(value)}</textarea>`:`<input name="${name}" value="${esc(value)}" type="${type}" ${type==='number'?'step="any"':''} ${required?'required':''}>`}</label></div>`;
const select = (text,name,values,chosen='') => `<div class="field"><label>${label(text)}<select name="${name}">${options(values,chosen)}</select></label></div>`;
const split = text => String(text||'').split('\n').filter(x=>x!=='');
const valueOf = (root,name) => root.querySelector(`[name="${name}"]`)?.value ?? '';
const typed = (raw,type) => {if(type==='string')return raw;if(type==='boolean'){if(!['true','false'].includes(raw))throw Error(ui('Boolean must be true or false.'));return raw==='true';}if(!/^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$/.test(raw)||!Number.isFinite(Number(raw)))throw Error(ui('Enter an explicit finite number.'));const n=Number(raw);if(n===0&&/[1-9]/.test(raw.split(/[eE]/)[0]))throw Error(ui('Numeric underflow is not allowed.'));return n;};
const button = (text,action) => `<button type="button" class="button small" data-editor="${action}">${label(text)}</button>`;
const footer = id => `<button class="button" data-action="close-modal">${label('Cancel')}</button><button class="button primary" type="submit" form="${id}">${label('Save new version')}</button>`;

function constantRow() { return `<div class="editor-row constant-row">${field('Output path','path')}${select('Type','type',['string','number','boolean'])}${field('Explicit value','value')}${button('Remove','remove')}</div>`; }
function mappingRow() { return `<div class="editor-row mapping-row">${field('Column aliases (one per line)','aliases')}${field('Output field path','target')}${select('Type','type',['number','string','boolean'])}<label class="checkbox-label"><input type="checkbox" name="required" checked>${label('Required')}</label>${field('Unit column aliases (one per line, optional)','unit_aliases','','text',false)}${select('Conversion unit','unit',units)}${field('Unit output field (optional)','unit_output','','text',false)}${button('Remove','remove')}</div>`; }
function tableRow() { return `<fieldset class="editor-table"><legend>${label('Source table')}</legend>${field('Table name / JSON path','source')}${field('Output table path','target')}${select('Mode','mode',['rows','single'])}${field('Ignored columns (one per line)','ignored','','text',false)}${field('Unique record field paths (one per line, optional)','unique','','text',false)}<div class="mapping-rows">${mappingRow()}</div>${button('Add field','add-field')}${button('Remove table','remove')}</fieldset>`; }
function setPath(object,path,value) {
  if(!path.startsWith('/')||path==='/'||path.split('/').some(x=>['__proto__','constructor','prototype'].includes(x)))throw Error(ui('Use an explicit safe output path.'));
  const parts=path.slice(1).split('/').map(x=>x.replace(/~1/g,'/').replace(/~0/g,'~'));let node=object;
  for(const part of parts.slice(0,-1)){if(Object.hasOwn(node,part)&&(!node[part]||typeof node[part]!=='object'))throw Error(ui('Output paths overlap.'));node=node[part]??=(Object.create(null));}
  if(Object.hasOwn(node,parts.at(-1)))throw Error(ui('Output paths overlap.'));node[parts.at(-1)]=value;
}
export function adapterFromForm(form) {
  const base={synthetic:valueOf(form,'authority')==='synthetic'};
  for(const row of form.querySelectorAll('.constant-row'))setPath(base,valueOf(row,'path'),typed(valueOf(row,'value'),valueOf(row,'type')));
  return {schema:'strata-adapter/1',id:valueOf(form,'id'),version:valueOf(form,'version'),title:valueOf(form,'title'),authority:valueOf(form,'authority'),format:valueOf(form,'format'),base,tables:[...form.querySelectorAll('.editor-table')].map(table=>{
    const fields=[...table.querySelectorAll('.mapping-row')].map(row=>{const f={aliases:split(valueOf(row,'aliases')),target:valueOf(row,'target'),type:valueOf(row,'type'),required:row.querySelector('[name="required"]').checked};const aliases=split(valueOf(row,'unit_aliases')),out=valueOf(row,'unit_output');if(aliases.length||out)f.unit={aliases,target:valueOf(row,'unit'),output:out};return f;});
    const t={source:valueOf(table,'source'),target:valueOf(table,'target'),mode:valueOf(table,'mode'),ignored_columns:split(valueOf(table,'ignored')),fields};const unique=split(valueOf(table,'unique'));if(unique.length)t.unique_by=unique;return t;
  })};
}
export function openAdapterBuilder(ctx) {
  ctx.openModal('Create adapter',`<form method="post" id="adapter-builder-form" class="form-stack"><p>${label('Define field meanings and units explicitly. No values or units are inferred.')}</p><div class="form-row">${field('Profile identifier','id')}${field('Version','version','1')}</div>${field('Title','title')}${select('Source type','authority',['synthetic','client'])}${select('File format','format',['csv','xlsx','json'])}<div class="field"><label>${label('Inspect a stored source')}<select name="inspect_file">${ctx.files().map(f=>`<option value="${esc(f.id)}">${esc(f.filename)}</option>`).join('')}</select></label></div>${field('JSON table paths for inspection (one per line)','inspect_paths','','text',false)}${button('Inspect columns and raw samples','inspect-tables')}<div id="table-inspection"></div><h3>${label('Explicit constants')}</h3><p class="field-note">${label('For example, revision or completeness. Only record independently confirmed values.')}</p><div class="constant-rows"></div>${button('Add constant','add-constant')}<div class="editor-tables">${tableRow()}</div>${button('Add table','add-table')}<details class="raw-details"><summary>${label('Generated configuration preview')}</summary><pre id="adapter-config-preview" class="code-block"></pre></details>${button('Preview configuration','preview-config')}</form>`,footer('adapter-builder-form'));
  const form=document.getElementById('adapter-builder-form');
  const session=ctx.captureDialogSession?.(), projectBase=ctx.projectPath('');
  const target=form.querySelector('#table-inspection'), inspect=form.querySelector('[data-editor="inspect-tables"]');
  let inspectionEpoch=0;
  const current=()=>form.isConnected && target.isConnected && (!ctx.isDialogCurrent || ctx.isDialogCurrent(session));
  // Editing the inspected source invalidates its pending response immediately.
  const sourceChanged=e=>{
    if(!['inspect_file','inspect_paths'].includes(e.target.name))return;
    inspectionEpoch+=1;target.textContent='';inspect.disabled=false;inspect.removeAttribute('aria-busy');
  };
  form.addEventListener('input',sourceChanged);form.addEventListener('change',sourceChanged);
  form.addEventListener('click',async e=>{const b=e.target.closest('[data-editor]');if(!b)return;const kind=b.dataset.editor;
    if(kind==='remove')b.closest('.editor-row,.editor-table').remove();
    if(kind==='add-constant')form.querySelector('.constant-rows').insertAdjacentHTML('beforeend',constantRow());
    if(kind==='add-table')form.querySelector('.editor-tables').insertAdjacentHTML('beforeend',tableRow());
    if(kind==='add-field')b.closest('.editor-table').querySelector('.mapping-rows').insertAdjacentHTML('beforeend',mappingRow());
    if(kind==='inspect-tables') {
      if(b.disabled || !current())return;
      const fileId=valueOf(form,'inspect_file'), sources=split(valueOf(form,'inspect_paths')), epoch=++inspectionEpoch;
      if(!fileId){ctx.error(new Error('Select a stored project file.'));return;}
      b.disabled=true;b.setAttribute('aria-busy','true');
      try {
        const r=await ctx.request(`${projectBase}/files/${encodeURIComponent(fileId)}/mapping-tables`,{method:'POST',body:{sources}});
        if(current() && epoch===inspectionEpoch)target.innerHTML=`<pre class="code-block">${esc(JSON.stringify(r,null,2))}</pre>`;
      }catch(error){if(current() && epoch===inspectionEpoch)ctx.error(error);}
      finally{if(current() && epoch===inspectionEpoch){b.disabled=false;b.removeAttribute('aria-busy');}}
      return;
    }
    try {
      if(kind==='preview-config')form.querySelector('#adapter-config-preview').textContent=JSON.stringify(adapterFromForm(form),null,2);
    }catch(error){if(current())ctx.error(error);}
  });
}

function findingRow() {return `<fieldset class="expected-finding"><legend>${label('Independent expected finding')}</legend>${field('Finding key (parent / child)','key')}${select('Expected status','status',['PASS','FAIL','NOT VERIFIED'])}<div class="numeric-rows"></div>${button('Add numeric assertion','add-numeric')}${button('Remove finding','remove')}</fieldset>`;}
function numericRow() {return `<div class="editor-row numeric-row">${field('Numeric field path','path')}${field('Independent expected value','value','','number')}${field('Absolute tolerance','absolute_tolerance','','number')}${field('Relative tolerance','relative_tolerance','','number')}${button('Remove','remove')}</div>`;}
export function caseFromForm(form) {
  const selected= [...form.querySelectorAll('[name="pinned-rule"]:checked')].map(x=>({id:x.dataset.ruleId,version:x.dataset.version}));
  const result={schema:'strata-case/1',case_id:valueOf(form,'case_id'),version:valueOf(form,'version'),title:valueOf(form,'title'),authority:valueOf(form,'authority'),task_id:valueOf(form,'task_id'),snapshot_id:valueOf(form,'snapshot_id'),rule_versions:selected,expected:{status:valueOf(form,'expected_status'),complete:form.querySelector('[name="complete"]').checked,findings:[...form.querySelectorAll('.expected-finding')].map(f=>{
    const item={key:valueOf(f,'key'),status:valueOf(f,'status')};const ns=[...f.querySelectorAll('.numeric-row')].map(n=>Object.fromEntries(['path','value','absolute_tolerance','relative_tolerance'].map(k=>[k,k==='path'?valueOf(n,k):typed(valueOf(n,k),'number')])));if(ns.length)item.numbers=ns;return item;
  })},truth:{author:valueOf(form,'author'),basis:valueOf(form,'basis'),independent:form.querySelector('[name="independent"]').checked}};
  if(valueOf(form,'compare_to'))result.compare_to=valueOf(form,'compare_to');return result;
}
export function openCaseBuilder(ctx) {
  ctx.openModal('Register independent case',`<form method="post" id="case-builder-form" class="form-stack"><p>${label('Write expected answers independently before running the system. Do not copy checker output.')}</p><div class="form-row">${field('Case identifier','case_id')}${field('Version','version','1')}</div>${field('Title','title')}${select('Source type','authority',['synthetic','client'])}<div class="field"><label>${label('Task scope')}<select name="task_id">${ctx.tasks.map(t=>`<option value="${esc(t.id)}" data-i18n="${esc(t.title)}">${esc(ui(t.title))}</option>`).join('')}</select></label></div><div class="field"><label>${label('Input snapshot')}<select name="snapshot_id">${ctx.snapshots().map(s=>`<option value="${esc(s.id)}">${esc(s.title)}</option>`).join('')}</select></label></div><div class="field"><label>${label('Target snapshot (handoff only)')}<select name="compare_to"><option value=""></option>${ctx.snapshots().map(s=>`<option value="${esc(s.id)}">${esc(s.title)}</option>`).join('')}</select></label></div><h3>${label('Pin approved rule versions')}</h3>${ctx.rules().filter(x=>(x.rule||x).status==='approved').map(x=>{const r=x.rule||x;return `<label class="checkbox-label"><input type="checkbox" name="pinned-rule" data-rule-id="${esc(r.id)}" data-version="${esc(r.version)}">${esc(r.id)} · ${esc(r.version)} · ${esc(r.title)}</label>`;}).join('')}${select('Overall expected status','expected_status',['PASS','FAIL','NOT VERIFIED'])}<label class="checkbox-label"><input name="complete" type="checkbox" checked>${label('Flag unexpected non-passing findings')}</label><div class="expected-findings">${findingRow()}</div>${button('Add finding','add-finding')}${field('Independent answer author','author')}<div class="field"><label>${label('Independent answer basis')}<textarea name="basis" rows="3" required maxlength="2000"></textarea></label></div><label class="checkbox-label"><input name="independent" type="checkbox" required>${label('I confirm the expected answers were independently established.')}</label></form>`,footer('case-builder-form'));
  const form=document.getElementById('case-builder-form');
  form.addEventListener('click',e=>{const b=e.target.closest('[data-editor]');if(!b)return;if(b.dataset.editor==='remove')b.closest('.numeric-row,.expected-finding').remove();if(b.dataset.editor==='add-finding')form.querySelector('.expected-findings').insertAdjacentHTML('beforeend',findingRow());if(b.dataset.editor==='add-numeric')b.closest('.expected-finding').querySelector('.numeric-rows').insertAdjacentHTML('beforeend',numericRow());});
}

const checkIds={'gravity-full':'QA-001,QA-002,QA-003,QA-004,QA-005,QA-006','gravity-distribution':'QA-003','gravity-balance':'QA-005','load-combination':'COMB-001','combination-configuration':'COMB-CONFIG','handoff':'HANDOFF','seismic-configuration':'SEISMIC','mass-source':'MASS-SOURCE','additional-settings':'SETTINGS'};
function settingRow(){return `<div class="editor-row setting-row">${field('Field path','path')}${select('Comparison','operator',['eq','in','range'])}${select('Value type','type',['string','number','boolean'])}${field('Expected value / allowed values (one per line)','value')}${field('Minimum (range only)','min','','number',false)}${field('Maximum (range only)','max','','number',false)}${button('Remove','remove')}</div>`;}
function transferRow(){return `<div class="editor-row transfer-row">${field('Mapping identifier','id')}${field('Source value path','source_path')}${field('Target value path','target_path')}${field('Source unit path','source_unit_path')}${field('Target unit path','target_unit_path')}${select('Conversion unit','comparison_unit',units)}${field('Absolute tolerance','absolute_tolerance','','number')}${field('Relative tolerance','relative_tolerance','','number')}${button('Remove','remove')}</div>`;}
function combinationRow(){return `<fieldset class="combination-row">${field('Combination identifier','id')}<div class="term-rows">${termRow()}</div>${button('Add term','add-term')}${button('Remove combination','remove')}</fieldset>`;}
function termRow(){return `<div class="editor-row term-row">${field('Base case identifier','caseId')}${field('Factor','factor','','number')}${button('Remove','remove')}</div>`;}
export function installRuleEditor() {
  const form=document.getElementById('rule-form');if(!form)return;
  const advanced=form.querySelector('#rule-parameters').closest('details');
  advanced.insertAdjacentHTML('beforebegin',`<section><h3>${label('Applicability conditions')}</h3><p>${label('All conditions must hold. Missing condition fields block verification.')}</p><div class="condition-rows"></div>${button('Add condition','add-condition')}</section>`);

  advanced.insertAdjacentHTML('beforebegin',`<label class="checkbox-label"><input type="checkbox" name="advanced_parameters">${label('Use advanced JSON parameters')}</label><section id="rule-visual-parameters"></section>`);
  const build=()=>{const task=form.task.value;form.check_ids.value=checkIds[task];let content='';
    if(['mass-source','seismic-configuration','additional-settings'].includes(task))content=`<div class="setting-rows">${settingRow()}</div>${button('Add setting','add-setting')}`;
    else if(task==='handoff')content=`${field('Source revision','source_revision')}${field('Target revision','target_revision')}<div class="transfer-rows">${transferRow()}</div>${button('Add mapping','add-mapping')}`;
    else if(task==='combination-configuration')content=`${field('Required base cases (one per line)','base_cases')}${field('Factor tolerance','factor_tolerance','','number')}<label class="checkbox-label"><input name="extra_cases" type="checkbox">${label('Allow extra base cases')}</label><label class="checkbox-label"><input name="extra_combinations" type="checkbox">${label('Allow extra combinations')}</label><div class="combination-rows">${combinationRow()}</div>${button('Add combination','add-combination')}`;
    else content=`<p>${label('This registered arithmetic profile is fixed and synthetic only.')}</p>`;
    document.getElementById('rule-visual-parameters').innerHTML=content;sync();
  };
  const sync=()=>{const enabled=!form.advanced_parameters.checked;advanced.hidden=enabled;const visual=document.getElementById('rule-visual-parameters');visual.hidden=!enabled;for(const el of visual.querySelectorAll('input,textarea,select'))el.disabled=!enabled;};
  build();form.task.addEventListener('change',build);
  form.advanced_parameters.addEventListener('change',sync);
  form.addEventListener('click',e=>{const b=e.target.closest('[data-editor]');if(!b)return;const kind=b.dataset.editor;if(kind==='remove')b.closest('.editor-row,.combination-row').remove();if(kind==='add-condition')form.querySelector('.condition-rows').insertAdjacentHTML('beforeend',settingRow().replace('setting-row','condition-row'));if(kind==='add-setting')form.querySelector('.setting-rows').insertAdjacentHTML('beforeend',settingRow());if(kind==='add-mapping')form.querySelector('.transfer-rows').insertAdjacentHTML('beforeend',transferRow());if(kind==='add-combination')form.querySelector('.combination-rows').insertAdjacentHTML('beforeend',combinationRow());if(kind==='add-term')b.closest('.combination-row').querySelector('.term-rows').insertAdjacentHTML('beforeend',termRow());});
  // Conditional bounds/value requirements follow the selected comparator.
  form.addEventListener('change',e=>{if(e.target.name==='operator'){const r=e.target.closest('.setting-row,.condition-row');r.querySelector('[name="value"]').required=e.target.value!=='range';r.querySelector('[name="min"]').required=e.target.value==='range';r.querySelector('[name="max"]').required=e.target.value==='range';}});
}
export function ruleParameters(form) {
  if(form.advanced_parameters?.checked)return parseStrictJSON(form.parameters.value||'{}');
  const task=form.task.value;
  if(['mass-source','seismic-configuration','additional-settings'].includes(task))return {settings:[...form.querySelectorAll('#rule-visual-parameters .setting-row')].map(r=>{const operator=valueOf(r,'operator'),result={path:valueOf(r,'path'),operator};if(operator==='range'){result.min=typed(valueOf(r,'min'),'number');result.max=typed(valueOf(r,'max'),'number');}else result.value=operator==='in'?split(valueOf(r,'value')).map(x=>typed(x,valueOf(r,'type'))):typed(valueOf(r,'value'),valueOf(r,'type'));return result;})};
  if(task==='handoff'){const mappings=[...form.querySelectorAll('.transfer-row')].map(r=>Object.fromEntries(['id','source_path','target_path','source_unit_path','target_unit_path','comparison_unit','absolute_tolerance','relative_tolerance'].map(k=>[k,k.endsWith('_tolerance')?typed(valueOf(r,k),'number'):valueOf(r,k)])));return {source_revision:valueOf(form,'source_revision'),target_revision:valueOf(form,'target_revision'),required_source_paths:mappings.map(m=>m.source_path),required_target_paths:mappings.map(m=>m.target_path),mappings};}
  if(task==='combination-configuration')return {required_base_cases:split(valueOf(form,'base_cases')),factor_tolerance:typed(valueOf(form,'factor_tolerance'),'number'),allow_extra_base_cases:form.extra_cases.checked,allow_extra_combinations:form.extra_combinations.checked,required_combinations:[...form.querySelectorAll('.combination-row')].map(c=>({id:valueOf(c,'id'),terms:[...c.querySelectorAll('.term-row')].map(r=>({caseId:valueOf(r,'caseId'),factor:typed(valueOf(r,'factor'),'number')}))}))};
  return {};
}

export function installSnapshotEditor() {
  const form=document.getElementById('snapshot-form');if(!form)return;
  const input=form.querySelector('[name="input"]');
  input.closest('.field').hidden=true;
  input.closest('.field').insertAdjacentHTML('beforebegin',`<section id="snapshot-field-editor">${select('Source type','snapshot_authority',['synthetic','client'])}<p>${label('Record each source field with an explicit path and type. Unknown values must remain missing.')}</p><div class="constant-rows">${constantRow()}</div>${button('Add field','add-constant')}</section><label class="checkbox-label"><input type="checkbox" name="advanced_input">${label('Use advanced JSON input')}</label>`);
  const sync=()=>{const manual=form.querySelector('#manual-mapping').checked,useJSON=form.advanced_input.checked;input.closest('.field').hidden=!useJSON;input.disabled=!manual||!useJSON;const editor=document.getElementById('snapshot-field-editor');editor.hidden=useJSON;for(const el of editor.querySelectorAll('input,textarea,select'))el.disabled=!manual||useJSON;};
  form.advanced_input.addEventListener('change',sync);
  form.addEventListener('click',e=>{const b=e.target.closest('[data-editor]');if(!b)return;if(b.dataset.editor==='add-constant')form.querySelector('.constant-rows').insertAdjacentHTML('beforeend',constantRow());if(b.dataset.editor==='remove')b.closest('.constant-row').remove();});
  form.querySelector('#manual-mapping').addEventListener('change',sync);sync();
}
export function snapshotInput(form) {
  if(form.advanced_input?.checked)return parseStrictJSON(form.input.value);
  const result={synthetic:valueOf(form,'snapshot_authority')==='synthetic'};
  for(const row of form.querySelectorAll('#snapshot-field-editor .constant-row'))setPath(result,valueOf(row,'path'),typed(valueOf(row,'value'),valueOf(row,'type')));
  return result;
}

export function ruleConditions(form) {
  return [...form.querySelectorAll('.condition-row')].map(r=>{
    const operator=valueOf(r,'operator'),condition={path:valueOf(r,'path'),operator};
    if(operator==='range'){condition.min=typed(valueOf(r,'min'),'number');condition.max=typed(valueOf(r,'max'),'number');}
    else condition.value=operator==='in'?split(valueOf(r,'value')).map(x=>typed(x,valueOf(r,'type'))):typed(valueOf(r,'value'),valueOf(r,'type'));
    return condition;
  });
}
export function correctionValues(form) {
  const scalar=(raw,type)=>type==='null'?null:typed(raw,type);
  return {original:scalar(valueOf(form,'original'),valueOf(form,'original_type')),value:scalar(valueOf(form,'value'),valueOf(form,'value_type'))};
}
