import {parseStrictJSON} from './strict-json.js';
import {openOCR} from './ocr-ui.js';
import {ui, t, label, systemLabel, translateSystemText, displayStatus, getLanguage, setLanguage, translateMarked} from './i18n.js';
import {openAdapterBuilder, adapterFromForm, openCaseBuilder, caseFromForm, installRuleEditor, ruleParameters, installSnapshotEditor, snapshotInput, ruleConditions, correctionValues} from './editors.js';
const API = '/api/v1';
const TOKEN_KEY = 'strata.workbench.session';
const app = document.getElementById('app');
const modal = document.getElementById('modal');
const tasks = [
  {id:'gravity-full',title:'Complete gravity review',description:'Six checks for the controlled gravity profile.'},
  {id:'gravity-distribution',title:'Floor load distribution',description:'Compare each floor with the design requirements.'},
  {id:'gravity-balance',title:'Independent reaction balance',description:'Compare reactions with the independent load baseline.'},
  {id:'load-combination',title:'Linear load combination',description:'Recalculate the supplied factors and base responses.'},
  {id:'combination-configuration',title:'Combination configuration',description:'Check required combinations against an approved manifest.'},
  {id:'handoff',title:'Engineering handoff',description:'Compare two snapshots using an approved mapping.'},
  {id:'seismic-configuration',title:'Seismic setup',description:'Check explicit settings against an approved checklist.'},
  {id:'mass-source',title:'Mass source configuration',description:'Verify the required mass source settings.'},
  {id:'additional-settings',title:'Additional settings',description:'Run the selected approved settings checklist.'},
];
const icons = {
  layers:'<path d="m3 7 9-5 9 5-9 5-9-5Zm0 5 9 5 9-5M3 17l9 5 9-5"/>',
  grid:'<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>',
  book:'<path d="M12 5C8 2 4 3 2 4v16c3-1 6-1 10 1 4-2 7-2 10-1V4c-3-1-7-2-10 1Zm0 0v16"/>',
  check:'<path d="m5 12 4 4L19 6"/><circle cx="12" cy="12" r="9"/>',
  history:'<path d="M3 11a9 9 0 1 1 2 7M3 4v7h7m2-5v6l4 2"/>',
  arrow:'<path d="M4 12h16m-6-6 6 6-6 6"/>',
  upload:'<path d="M12 16V3m-5 5 5-5 5 5M4 15v6h16v-6"/>',
  download:'<path d="M12 3v13m-5-5 5 5 5-5M4 16v5h16v-5"/>',
  file:'<path d="M14 2H5v20h14V7Zm0 0v5h5M8 12h8M8 16h6"/>',
  play:'<path d="m8 4 12 8-12 8Z"/>',
  plus:'<path d="M12 5v14M5 12h14"/>',
  close:'<path d="m6 6 12 12M18 6 6 18"/>',
  lock:'<rect x="5" y="10" width="14" height="11" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3m-4 5v2"/>',
  refresh:'<path d="M20 8a8 8 0 0 0-14-2L3 9m0-5v5h5M4 16a8 8 0 0 0 14 2l3-3m0 5v-5h-5"/>',
  logout:'<path d="M9 4H4v16h5m6-13 5 5-5 5m-6-5h11"/>',
  info:'<circle cx="12" cy="12" r="9"/><path d="M12 11v6m0-10v.1"/>',
  search:'<circle cx="10" cy="10" r="6"/><path d="m15 15 6 6"/>',
  menu:'<path d="M4 6h16M4 12h16M4 18h16"/>',
  users:'<circle cx="9" cy="8" r="3"/><path d="M3 20v-3a6 6 0 0 1 12 0v3m1-15a3 3 0 0 1 0 6m2 3a5 5 0 0 1 3 4v2"/>',
};
const icon = name => `<svg viewBox="0 0 24 24" aria-hidden="true">${icons[name] || icons.file}</svg>`;
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const json = value => JSON.stringify(value ?? null, null, 2);
const array = value => Array.isArray(value) ? value : [];
const resource = value => value && typeof value === 'object' ? {...(value.data && typeof value.data === 'object' ? value.data : {}), ...value} : value;
const unwrap = (value, key) => resource(value?.[key] ?? value);
const titleOf = value => value?.title || value?.name || value?.filename || value?.id || 'Untitled';
const taskTitle = id => tasks.find(task => task.id === id)?.title || id || 'Engineering check';
const displayDate = value => {
  if (!value) return '—';
  const date = new Date(value);
  return Number.isFinite(date.valueOf()) ? date.toLocaleString('en-AU',{month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'}) : String(value);
};
const bytesLabel = n => Number.isFinite(Number(n)) ? Number(n) >= 1048576 ? `${(Number(n)/1048576).toFixed(1)} MB` : `${Math.max(1,Math.round(Number(n)/1024))} KB` : '—';
const short = value => String(value || '').slice(-8);
const phase = run => String(run?.state || '').toUpperCase();
const running = run => ['QUEUED','RUNNING'].includes(phase(run));
const ruleValue = item => item?.rule || item;
const approved = item => ruleValue(item)?.status === 'approved';
const badge = (value, text = value) => `<span data-i18n-status="${esc(text || 'UNKNOWN')}" class="badge ${esc(String(value || 'unknown').toLowerCase().replace(/[^a-z0-9]+/g,'-'))}">${esc(displayStatus(text || 'UNKNOWN'))}</span>`;
const rawDetails = (caption,value) => `<details class="raw-details"><summary>${label(caption)}</summary><pre class="code-block">${esc(json(value))}</pre></details>`;
let savedToken = '';
try { savedToken = sessionStorage.getItem(TOKEN_KEY) || ''; } catch { /* In-memory session remains usable. */ }
const state = {
  token:savedToken,user:null,needsSetup:false,setupTokenRequired:false,authError:'',authBusy:false,
  projects:[],projectId:'',dashboard:null,view:'workspace',loading:false,busy:false,error:'',
  snapshotId:'',taskId:'gravity-full',question:'',useModel:false,compareTo:'',
  run:null,selectedRunId:'',model:{enabled:false},search:'',retrieval:null,searchTask:'gravity-full',
  beforeId:'',afterId:'',comparison:null,sidebar:false,loadEpoch:0,users:[],requestKey:null,validation:null,runtime:null,runFilter:'all',issueFilter:'open',connector:{configured:false},
};
let pollTimer, toastTimer, evaluationTimer;

function languageSwitch() {
  return `<div class="language-switch" role="group" aria-label="${esc(t('interface.language'))}" data-i18n-aria-label="interface.language"><button type="button" data-action="language" data-language="zh-CN" aria-pressed="${getLanguage()==='zh-CN'}">中文</button><span aria-hidden="true">/</span><button type="button" data-action="language" data-language="en" aria-pressed="${getLanguage()==='en'}">English</button></div>`;
}
const structuredMessages=new Map();
function systemMessage(message) {
  const detail=structuredMessages.get(message);
  if(!detail)return systemLabel(message);
  return `${detail.kind?label(detail.kind)+': ':''}${systemLabel(detail.message)}${array(detail.errors).map(e=>`<div class="field-note">${esc([e.file,e.table,e.row,e.field].filter(v=>v!==null&&v!==undefined).join(' / '))}: ${systemLabel(e.reason)}</div>`).join('')}`;
}
function setSystemError(node,message) {
  if(!node)return;
  delete node.dataset.i18nSystem;
  node.innerHTML=systemMessage(message);
}

function toast(message, error = false) {
  const node = document.getElementById('toast');
  setSystemError(node,message);
  node.className = `visible${error ? ' error' : ''}`;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => node.className = '', 6500);
}
function invalidateSelection() {
  clearTimeout(pollTimer);
  state.run=null;state.selectedRunId='';state.requestKey=null;
  const result=document.getElementById('workspace-result');
  if(result)result.innerHTML=`<div class="panel-head"><h2>${label("Review result")}</h2><small>${label("Selection changed")}</small></div><div class="empty-state"><div class="empty-icon">`+icon('check')+`</div><h3>${label("Run the updated review.")}</h3><p>${label("The previous run is still saved in Review. Execute this selection to obtain its own result.")}</p></div>`;
}
function setToken(token) {
  state.token = token || '';
  try { token ? sessionStorage.setItem(TOKEN_KEY,token) : sessionStorage.removeItem(TOKEN_KEY); } catch { /* Do not store in localStorage. */ }
}
function detailMessage(detail) {
  if(detail&&typeof detail==='object'&&!Array.isArray(detail)&&detail.message){
    const original=detail.errors?`${detail.message}: ${detail.errors.map(e=>[e.file,e.table,e.row,e.field,e.reason].filter(v=>v!==null&&v!==undefined).join(' / ')).join('; ')}`:detail.message;
    structuredMessages.set(original,detail);if(structuredMessages.size>100)structuredMessages.delete(structuredMessages.keys().next().value);return original;
  }
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) return detail.map(item => `${array(item.loc).join('.')}: ${item.msg || 'Invalid value'}`).join('; ');
  return detail?.message || detail?.error || 'The request could not be completed.';
}

async function request(path, {method='GET',body,raw=false,idempotencyKey,setupToken}={}) {
  const headers = {Accept:raw ? '*/*' : 'application/json'};
  if(idempotencyKey)headers['Idempotency-Key']=idempotencyKey;
  if (setupToken && path === '/auth/bootstrap') headers['X-Setup-Token'] = setupToken;
  if (state.token) headers.Authorization = `Bearer ${state.token}`;
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  let response;
  try {
    response = await fetch(`${API}${path}`, {method,headers,body:body === undefined ? undefined : JSON.stringify(body),signal:AbortSignal.timeout(45000),cache:'no-store'});
  } catch (error) {
    throw new Error(error.name === 'TimeoutError' ? 'The server took too long to respond. Check the saved run before trying again.' : 'Cannot reach the workspace server. Check that the backend is running.');
  }
  if (!response.ok) {
    let failure;
    try { failure = await response.json(); } catch { failure = {}; }
    if (response.status === 401 && !path.startsWith('/auth/')) {
      setToken(''); state.user = null; clearTimeout(pollTimer);
      state.authError = 'Your session has expired. Sign in again.'; render();
    }
    throw new Error(detailMessage(failure.detail || failure.error || failure.message) || `Request failed (${response.status}).`);
  }
  if (raw) return response;
  if (response.status === 204) return {};
  return response.json();
}
const projectPath = suffix => `/projects/${encodeURIComponent(state.projectId)}${suffix}`;
const snapshots = () => array(state.dashboard?.snapshots);
const files = () => array(state.dashboard?.files);
const rules = () => array(state.dashboard?.rules);
const runs = () => array(state.dashboard?.runs);
const selectedSnapshot = () => snapshots().find(item => item.id === state.snapshotId);
const snapshotOptions = (selected,placeholder='Select a snapshot',excluded='') => `<option value="" data-i18n="${esc(placeholder)}">${esc(ui(placeholder))}</option>${snapshots().filter(item => item.id !== excluded).map(item => `<option value="${esc(item.id)}" ${item.id === selected ? 'selected' : ''}>${esc(titleOf(item))} · ${short(item.id)}</option>`).join('')}`;
const taskOptions = selected => tasks.map(task => `<option value="${task.id}" ${task.id === selected ? 'selected' : ''} data-i18n="${esc(task.title)}">${esc(ui(task.title))}</option>`).join('');

async function initialize() {
  try {
    const setup = await request('/auth/setup'); state.needsSetup = setup.needs_setup === true; state.setupTokenRequired = setup.token_required === true;
    if (!state.token) return render();
    const me = await request('/auth/me'); state.user = unwrap(me,'user');
    await loadProjects();
  } catch (error) {
    setToken(''); state.authError = error.message; render();
  }
}
// A project change starts a new UI context. Persisted records remain on the
// server; only selections, drafts and polling for the previous project are reset.
function changeProjectContext(projectId) {
  clearTimeout(pollTimer);
  clearTimeout(evaluationTimer);
  clearTimeout(toastTimer);
  state.loadEpoch += 1; // Discard any dashboard response already in flight.
  Object.assign(state, {
    projectId, dashboard:null, run:null, selectedRunId:'', evaluation:null,
    snapshotId:'', beforeId:'', afterId:'', compareTo:'', comparison:null,
    retrieval:null, search:'', question:'', reviewNote:'', requestKey:null,
    runtime:null, error:'', loading:false,
  });
  structuredMessages.clear();
  delete app.dataset.formScope;
  const toastNode=document.getElementById('toast');
  if(toastNode){toastNode.textContent='';toastNode.className='';delete toastNode.dataset.i18nSystem;}
  if(modal.open)modal.close();
}
async function loadProjects(preferred) {
  const result = await request('/projects');
  state.projects = array(result.items || result.projects || result).map(resource);
  const chosen = preferred || state.projectId;
  const nextProjectId = state.projects.some(item => item.id === chosen) ? chosen : state.projects[0]?.id || '';
  if(nextProjectId !== state.projectId) changeProjectContext(nextProjectId);
  try { state.model = await request('/model'); } catch { state.model = {enabled:false}; }
  try { state.connector = (await request('/tools')).etabs || {configured:false}; } catch { state.connector={configured:false}; }
  if (state.projectId) await loadDashboard(); else { state.dashboard = null; render(); }
}
async function loadDashboard({silent=false}={}) {
  if (!state.projectId) return;
  const epoch = ++state.loadEpoch, projectId = state.projectId;
  if (!silent) { state.loading = true; state.error = ''; render(); }
  try {
    const result = await request(`/projects/${encodeURIComponent(projectId)}/dashboard`);
    if (epoch !== state.loadEpoch || projectId !== state.projectId) return;
    const data = result.dashboard || result;
    state.dashboard = {...data,files:array(data.files).map(resource),snapshots:array(data.snapshots).map(resource),rules:array(data.rules).map(resource),runs:array(data.runs).map(resource),audit:array(data.audit?.items || data.audit).map(resource),auditValid:data.audit?.valid};
    if (!snapshots().some(item => item.id === state.snapshotId)) state.snapshotId = data.project?.active_snapshot_id || snapshots()[0]?.id || '';
    if (!snapshots().some(item => item.id === state.beforeId)) state.beforeId = snapshots()[1]?.id || snapshots()[0]?.id || '';
    if (!snapshots().some(item => item.id === state.afterId)) state.afterId = snapshots()[0]?.id || '';
    // A dependency mutation may invalidate the selected result while this
    // dashboard is loaded. Keep full calculation details from the run endpoint;
    // only fetch again when lifecycle/dependency fields actually changed.
    const selectedRunId=state.run?.id;
    const savedRun=state.dashboard.runs.find(item=>item.id===selectedRunId);
    const lifecycleFields=['state','status','review_state','stale','rule_hash','input_hash','output_hash','stale_reasons'];
    if(savedRun && lifecycleFields.some(key=>JSON.stringify(savedRun[key])!==JSON.stringify(state.run[key]))) {
      try {
        const refreshed=await request(`/projects/${encodeURIComponent(projectId)}/runs/${encodeURIComponent(selectedRunId)}`);
        if(epoch!==state.loadEpoch || projectId!==state.projectId || state.run?.id!==selectedRunId)return;
        state.run=unwrap(refreshed,'run');
      } catch(error) {
        // Do not leave an apparently confirmable old result on screen when its
        // current review state could not be retrieved. The saved run is retained.
        if(epoch!==state.loadEpoch || projectId!==state.projectId || state.run?.id!==selectedRunId)return;
        state.run=null;state.selectedRunId='';throw error;
      }
    }
  } catch (error) { state.error = error.message; }
  finally { if (epoch === state.loadEpoch) { state.loading = false; render(); } }
}
async function selectRun(id,{navigate=false}={}) {
  if (!id) return;
  const projectId = state.projectId;
  const result = await request(projectPath(`/runs/${encodeURIComponent(id)}`));
  if (projectId !== state.projectId) return;
  state.run = unwrap(result,'run'); state.selectedRunId = id;
  if (navigate) state.view = 'review';
  render(); schedulePoll();
}
function schedulePoll() {
  clearTimeout(pollTimer);
  if (!running(state.run)) return;
  const projectId = state.projectId, runId = state.run.id;
  pollTimer = setTimeout(async() => {
    if (projectId !== state.projectId || state.run?.id !== runId) return;
    try {
      const result = await request(`/projects/${encodeURIComponent(projectId)}/runs/${encodeURIComponent(runId)}`);
      if (projectId !== state.projectId || state.run?.id !== runId) return;
      state.run = unwrap(result,'run'); render();
      if (!running(state.run)) await loadDashboard({silent:true});
      schedulePoll();
    } catch (error) { toast(`Run polling stopped: ${error.message}`,true); }
  },1400);
}
function scheduleEvaluationPoll() {
  clearTimeout(evaluationTimer);
  if (!['QUEUED','RUNNING'].includes(state.evaluation?.state)) return;
  const projectId=state.projectId,id=state.evaluation.id;
  evaluationTimer=setTimeout(async()=>{
    if(projectId!==state.projectId || id!==state.evaluation?.id || !state.user) return;
    try {
      const value=(await request(`/projects/${encodeURIComponent(projectId)}/evaluations/${encodeURIComponent(id)}`)).evaluation;
      if(projectId!==state.projectId || id!==state.evaluation?.id) return;
      state.evaluation=value;render();
      if(value.state==='COMPLETED') await loadDashboard({silent:true});
      scheduleEvaluationPoll();
    } catch(error) {toast(`Run polling stopped: ${error.message}`,true);}
  },1400);
}
function mappingPreview(mapping) {
  return `<div class="table-wrap"><table><thead><tr>${['Source location','Field path','Original value','Original unit','Mapped value','Conversion unit'].map(k=>`<th>${label(k)}</th>`).join('')}</tr></thead><tbody>${array(mapping.provenance).map(p=>`<tr><td>${esc([p.location?.file,p.location?.table,p.location?.row,p.location?.column,p.location?.cell].filter(v=>v!=null).join(' · '))}</td><td class="mono">${esc(p.target)}</td><td>${esc(json(p.original_value))}</td><td>${esc(p.original_unit??'—')}</td><td>${esc(json(p.value))}</td><td>${esc(p.unit??'—')}</td></tr>`).join('')}</tbody></table></div>${rawDetails('Mapped values and original provenance',mapping)}`;
}
function heading(eyebrow,title,description,actions='') {
  return `<div class="page-heading"><div><div class="eyebrow">${label(eyebrow)}</div><h1>${label(title)}</h1><p>${label(description)}</p></div>${actions ? `<div class="heading-actions">${actions}</div>` : ''}</div>`;
}
function action(caption,name,iconName='',classes='',attrs='') {
  return `<button class="button ${classes}" data-action="${name}" ${attrs}>${iconName ? icon(iconName) : ''}${label(caption)}</button>`;
}
function notice(text,type='') { return `<div class="notice ${type}">${icon('info')}${systemMessage(text)}</div>`; }
const adapterExample = {schema:'strata-adapter/1',id:'TEST-TRANSFER',version:'1',title:'SYNTHETIC transfer table',authority:'synthetic',format:'csv',base:{synthetic:true,project:{revision:'E1'}},tables:[{source:'csv',target:'/transfer',mode:'single',ignored_columns:[],fields:[{aliases:['Force','Vertical'],target:'/vertical',type:'number',required:true,unit:{aliases:['Unit'],target:'kN',output:'/unit'}}]}]};
function materialView(items) {
  if (!array(items).length) return '';
  return `<section class="section-gap"><h3>${label("Materials needed")}</h3>${items.map(item=>`<article class="list-card"><h4>${systemLabel(item.what)}</h4><p>${systemLabel(item.why)}</p><p class="field-note">${label(item.where.view)} · ${systemLabel(item.where.action)}${item.where.field?` · ${esc(item.where.field)}`:''}${item.where.side?` · ${label(item.where.side)}`:''}</p></article>`).join('')}</section>`;
}
function adaptationView() {
  const adapters=array(state.dashboard?.adapters), cases=array(state.dashboard?.cases), evaluations=array(state.dashboard?.evaluations), editable=['engineer','reviewer'].includes(state.dashboard.project.role);
  const result=state.evaluation;
  return heading('Client adaptation','Prepare once. Reuse with evidence.','Save explicit mappings, transfer rule packages and compare cases against independent expected answers.',action('Refresh','refresh','refresh'))+
    notice('Included examples are synthetic software tests. Client input meanings, engineering rules and independent answers must be provided and reviewed.')+
    `<div class="section-grid section-gap"><section class="panel"><div class="panel-head"><h2>${label("Reusable data adapters")}</h2>${editable?action('Create adapter','builder-adapter','plus','small')+action('Import profile','config-adapter','','small'):''}</div><div class="panel-body">${adapters.map(item=>`<article class="list-card"><h3>${esc(item.profile.title)}</h3><p>${esc(item.profile.id)} · ${esc(item.profile.version)} · ${esc(item.profile.format)} · ${badge(item.profile.authority)}</p><div class="row-actions">${action('Export profile','export-adapter','download','small',`data-id="${esc(item.id)}"`)}${editable?action('Apply to source','apply-adapter','','small',`data-id="${esc(item.id)}"`):''}</div></article>`).join('')||`<p class="field-note">${label("No saved profiles yet. Import an explicit configuration; unknown fields and units are rejected.")}</p>`}${editable?action('Upload source for mapping','upload-mapping','upload','small'):''}</div></section><section class="panel"><div class="panel-head"><h2>${label("Rule packages")}</h2></div><div class="panel-body"><p>${label("Packages include rules and exact source files. Imported approvals are reset to drafts. Only registered calculation tools and fixed comparison operators are supported.")}</p><div class="row-actions">${editable?action('Validate / import package','config-package','book','small'):''}${state.dashboard.project.role==='reviewer'?action('Export synthetic rules','export-rules','','small','data-type="synthetic"')+action('Export client rules','export-rules','','small','data-type="client"'):''}</div><p class="field-note">${label("Review and approve imported rules in Knowledge. A software approval does not establish structural certification.")}</p></div></section></div>
    <section class="panel section-gap"><div class="panel-head"><h2>${label("Independent benchmark cases")}</h2><div class="row-actions">${editable?action('Register case','builder-case','plus','small')+action('Advanced JSON','config-case','','small')+action('Run selected cases','evaluate-cases','play','small primary',cases.length?'':'disabled'):''}</div></div><div class="panel-body">${cases.map(item=>`<label class="checkbox-label list-card"><input type="checkbox" name="benchmark-case" value="${esc(item.id)}"><span><strong>${esc(item.case.case_id)} · ${esc(item.case.version)}</strong><br>${esc(item.case.title)} · ${badge(item.case.expected.status)}<br><small>${badge(item.case.authority)} · ${label('Independent truth declared by')} ${esc(item.case.truth.author)}</small></span></label>`).join('')||`<p class="field-note">${label("Register input snapshots, pin approved rule versions, then enter independently checked expected statuses and numeric tolerances. The system never generates the expected answers.")}</p>`}</div></section>
    <section class="panel section-gap"><div class="panel-head"><h2>${label("Batch evaluations")}</h2></div><div class="panel-body">${evaluations.map(item=>action(`${short(item.id)} · ${displayDate(item.created_at)}`,'open-evaluation','','small',`data-id="${esc(item.id)}"`)).join(' ')}${result?`<div class="section-gap">${badge(result.state)}${action('Refresh batch','open-evaluation','refresh','small',`data-id="${esc(result.id)}"`)}${action('Export comparison','export-evaluation','download','small',`data-id="${esc(result.id)}"`)}${rawDetails('Measured counts',result.summary)}<div class="table-wrap"><table><thead><tr><th>${label("Case")}</th><th>${label("Expected")}</th><th>${label("Actual")}</th><th>${label("Comparison")}</th></tr></thead><tbody>${result.items.map(item=>`<tr><td>${esc(item.case_id)}</td><td>${badge(item.expected)}</td><td>${badge(item.actual)}</td><td>${label(item.state==='QUEUED'||item.state==='RUNNING'?'Pending':item.matched?'Matched':'Review required')}${rawDetails('Per-item differences and oracle',item)}</td></tr>`).join('')}</tbody></table></div><p class="field-note">${systemLabel(result.scope)}</p></div>`:`<p class="field-note">${label("Select a saved batch to view missed issues, false alarms, false PASS results, missing evidence and numeric mismatches.")}</p>`}</div></section>`;
}
function configModal(kind) {
  const selected=selectedSnapshot()||snapshots()[0];
  const sampleCase={schema:'strata-case/1',case_id:'TEST-CASE',version:'1',title:'SYNTHETIC independently specified case',authority:'synthetic',task_id:'mass-source',snapshot_id:selected?.id||'SELECT_SNAPSHOT_ID',rule_versions:[{id:'MASS-SOURCE',version:'CONTROLLED-1'}],expected:{status:'PASS',complete:true,findings:[{key:'MASS-SOURCE',status:'PASS'}]},truth:{author:'YOUR NAME',basis:'REPLACE with independent expected answer and source; do not copy checker output.',independent:true}};
  const sample=kind==='adapter'?adapterExample:kind==='case'?sampleCase:{};
  const title=kind==='adapter'?'Import adapter profile':kind==='case'?'Register independent case':'Validate / import rule package';
  openModal(title,`<form method="post" id="adaptation-config-form" class="form-stack"><div class="field"><label>${label("Import configuration file")}<input type="file" name="config_file" accept=".json,application/json"></label></div><input name="kind" type="hidden" value="${esc(kind)}"><p class="field-note">${label(kind==='package'?'Paste an exported strata-rule-package/1 object. Validation checks exact sources and tool parameters; import creates drafts.':'Use an explicit configuration. The example is synthetic; replace it with independently reviewed definitions.')}</p><div class="field"><label for="adaptation-json">${label("Configuration JSON")}</label><textarea id="adaptation-json" name="config" rows="14" required spellcheck="false">${esc(json(sample))}</textarea></div>${kind==='case'?rawDetails('Available snapshot IDs',snapshots().map(s=>({id:s.id,title:s.title}))):''}</form>`,`${action('Cancel','close-modal')}${kind==='package'?`<button class="button" form="adaptation-config-form" type="submit" name="operation" value="validate">${label("Validate only")}</button>`:''}<button class="button primary" form="adaptation-config-form" type="submit" name="operation" value="save">${label(kind==='package'?'Import as drafts':'Save new version')}</button>`);
  document.querySelector('#adaptation-config-form [name="config_file"]').addEventListener('change',async e=>{
    try {const file=e.target.files[0];if(!file)return;if(file.size>10_000_000)throw Error('Source exceeds 10 MB');document.getElementById('adaptation-json').value=await file.text();}
    catch(error){toast(error.message,true);}
  });
}
function adapterModal(id) {
  openModal('Apply explicit adapter',`<form method="post" id="adapter-apply-form" class="form-stack"><input name="adapter_id" type="hidden" value="${esc(id)}"><div class="field"><label for="adapter-source">${label("Stored source file")}</label><select id="adapter-source" name="file_id" required>${files().map(file=>`<option value="${esc(file.id)}">${esc(file.filename)}</option>`).join('')}</select></div><p class="field-note">${label("Preview validates the mapping without saving a snapshot. Apply creates a new revision and retains the original bytes and every mapped original value.")}</p></form>`,`${action('Cancel','close-modal')}<button class="button" form="adapter-apply-form" type="submit" name="operation" value="preview">${label("Preview mapping")}</button><button class="button primary" form="adapter-apply-form" type="submit" name="operation" value="apply">${label("Create snapshot")}</button>`);
}

function render() {
  if (!state.user) return renderAuth();
  const scope=`${state.projectId}:${state.view}:${state.selectedRunId}`;
  const selectedCases=app.dataset.formScope===scope?[...app.querySelectorAll('[name=benchmark-case]:checked')].map(el=>el.value):[];
  const preserved=app.dataset.formScope===scope?[...app.querySelectorAll('form:not(#run-form):not(#search-form):not(#compare-form) input,form:not(#run-form):not(#search-form):not(#compare-form) textarea,form:not(#run-form):not(#search-form):not(#compare-form) select')].map(el=>({form:el.form?.getAttribute('id'),name:el.name,id:el.id,value:el.value,checked:el.checked})):[];
  const nav = [['workspace','grid','Workspace'],['knowledge','book','Knowledge'],['review','check','Review'],['versions','layers','Versions'],['audit','history','Audit trail'],['team','users','Team & access'],['validation','check','Validation'],['adaptation','layers','Adaptation']];
  const currentProject = state.dashboard?.project || state.projects.find(project => project.id === state.projectId);
  app.innerHTML = `<div class="app-shell"><aside class="sidebar ${state.sidebar ? 'open' : ''}" aria-label="${esc(ui("Main navigation"))}" data-i18n-aria-label="Main navigation"><div class="brand"><div class="brand-mark">S</div><div><div class="brand-name">STRATA</div><small>${label("ENGINEERING ASSURANCE")}</small></div></div><div class="nav-label">${label("Project workspace")}</div><nav>${nav.map(([id,image,caption]) => `<button class="nav-button ${state.view === id ? 'active' : ''}" data-action="navigate" data-view="${id}" ${state.view === id ? 'aria-current="page"' : ''}>${icon(image)}${label(caption)}</button>`).join('')}</nav><div class="sidebar-bottom"><div class="environment"><span class="status-dot"></span>${label("Project-scoped workspace")}</div><p>${label("Traceable checks.")}<br>${label("Engineering decisions stay with the reviewer.")}</p><button data-action="logout">${icon('logout')}${label("Sign out")}</button></div></aside><main class="main"><header class="topbar"><button class="icon-button mobile-menu" data-action="menu" aria-label="${esc(ui("Toggle navigation"))}" data-i18n-aria-label="Toggle navigation">${icon('menu')}</button><div class="project-picker">${icon('layers')}<select id="project-picker" aria-label="${esc(ui("Select project"))}" data-i18n-aria-label="Select project" ${state.busy ? 'disabled' : ''}>${state.projects.length ? state.projects.map(project => `<option value="${esc(project.id)}" ${project.id === state.projectId ? 'selected' : ''}>${esc(titleOf(project))}</option>`).join('') : `<option data-i18n="No project yet">${esc(ui("No project yet"))}</option>`}</select><button class="icon-button" data-action="new-project" aria-label="${esc(ui("Create project"))}" data-i18n-aria-label="Create project">${icon('plus')}</button></div>${languageSwitch()}<div class="user-meta"><span class="user-name">${esc(state.user.username || state.user.name || 'Signed in')}</span><span class="avatar" aria-hidden="true">${esc((state.user.username || state.user.name || 'U').slice(0,2).toUpperCase())}</span></div></header>${state.loading ? `<div class="loading-strip" role="status" aria-label="${esc(ui("Loading project"))}" data-i18n-aria-label="Loading project"></div>` : ''}<div class="content">${state.error ? notice(state.error,'error') : ''}${!state.projectId ? emptyProject() : !state.dashboard ? `<section class="panel"><div class="empty-state">${state.loading ? `<span class="spinner"></span><p>${label("Loading project records…")}</p>` : `<h3>${label("Project records could not be loaded")}</h3>`}${action('Try again','refresh','refresh')}</div></section>` : ({workspace:workspaceView,knowledge:knowledgeView,review:reviewView,versions:versionsView,audit:auditView,team:teamView,validation:validationView,adaptation:adaptationView}[state.view] || workspaceView)()}<p class="footer-note">${currentProject?esc(titleOf(currentProject)):label('Untitled')}${currentProject ? ' · ' : ''}${label("Technical results apply only to the selected rule and supplied evidence. A recorded review is not a structural safety certification.")}</p></div></main></div>`;
  app.dataset.formScope=scope;
  for(const saved of preserved){const form=document.getElementById(saved.form);const el=saved.id?document.getElementById(saved.id):form?.elements.namedItem(saved.name);if(el&&el.type!=='file'){el.value=saved.value;if(el.type==='checkbox'||el.type==='radio')el.checked=saved.checked;}}
  for(const el of app.querySelectorAll('[name=benchmark-case]'))el.checked=selectedCases.includes(el.value);
  translateMarked(app);
}
function validationView() {
  const data=state.validation;
  if(!data)return heading('Validation','Inspect the evidence.','Load the recorded evaluations to compare expected and actual results.',action('Load validation','validation-refresh','refresh','primary'));
  const baseline=data.baseline?.engineering, agent=data.baseline?.agent, system=data.records?.system, retrieval=data.records?.retrieval, model=data.records?.model_holdout;
  const summary=system?.summary || {};
  const cases=array(system?.cases);
  const numerator=(part)=>part ? `${part.matched ?? part.correct ?? '—'} / ${part.total ?? '—'}` : 'Not recorded';
  return heading('Validation','Test the workflow, not the claim.','Expected results were written before execution. Synthetic fixtures do not establish real-project engineering accuracy.',action('Refresh fixed checks','validation-refresh','refresh')+action('Download evaluation','validation-download','download','primary'))+notice(data.scope)+`<section class="stats-grid">${stat('Engineering baseline',numerator(baseline?.summary),'Same 16 numerical cases','check')}${stat('Agent baseline',numerator(agent?.summary),'Same 10 workflow cases','layers')}${stat('Server acceptance',numerator(summary),system?.matches_current_tools ? 'Matches current checking code' : 'Historical record — rerun required','file')}${stat('Model holdout',numerator(model?.summary),'Local Qwen routing + rejection policy','book')}</section><section class="panel"><div class="panel-head"><h2>${label("Server acceptance cases")}</h2><small>${label("False PASS:")} ${Number(summary.false_pass ?? 0)} / ${Number(summary.false_pass_denominator_expected_nonpass ?? 0)} ${label("expected non-PASS cases")}</small></div><div class="table-wrap"><table><thead><tr><th>${label("Case")}</th><th>${label("Task")}</th><th>${label("Expected")}</th><th>${label("Actual")}</th><th>${label("Match")}</th></tr></thead><tbody>${cases.map(c=>`<tr><td><span class="table-title">${esc(c.id)}</span><span class="table-sub">${esc(c.title)}</span></td><td>${label(taskTitle(c.task))}</td><td>${badge(c.expected)}</td><td>${badge(c.actual)}</td><td>${c.matched ? '✓' : label('Review')}</td></tr>`).join('')}</tbody></table></div></section><div class="section-grid section-gap"><section class="panel"><div class="panel-head"><h2>${label("Routing iterations")}</h2></div><div class="panel-body">${rawDetails('Initial 32-case model baseline',data.records?.model_baseline?.summary)}${rawDetails('Final 32-case development result',data.records?.model_development?.summary)}${rawDetails('Separate 24-case holdout',model?.summary)}<p class="field-note">${label("The boundary policy can reject a model proposal; it cannot fabricate a task or engineering finding. Holdout results are a small fixed software evaluation, not a production accuracy guarantee.")}</p></div></section><section class="panel"><div class="panel-head"><h2>${label("Retrieval and reuse")}</h2></div><div class="panel-body">${rawDetails('Fixed retrieval evaluation',retrieval?.summary || retrieval?.metrics || retrieval)}${rawDetails('Same-input cache experiment',system?.cache_experiment)}<p class="field-note">${label("Cache timing measures local software execution. Reviewer time, full operating cost and competitive advantage need a customer pilot.")}</p></div></section></div>`;
}
function runtimePanel(owner) {
  const usage=state.runtime?.model_usage;
  return `<section class="panel section-gap"><div class="panel-head"><h2>${label("Usage & project handover")}</h2></div><div class="panel-body">${usage ? `<p>${label("Local model calls:")} <strong>${usage.calls} / ${usage.limit}</strong> · UTC ${esc(usage.day_utc)}</p>${usage.warning?notice(usage.warning):''}<p class="field-note">${systemLabel(usage.billing)} ${label("A reserved call counts even if inference fails or the job is interrupted.")}</p>${owner?`<form method="post" id="policy-form" class="form-stack"><div class="field"><label for="model-limit">${label("Daily model-call limit (0 disables model routing)")}</label><input id="model-limit" name="daily_limit" type="number" min="0" max="10000" step="1" value="${usage.limit}" required></div><button class="button" type="submit">${label("Save model limit")}</button></form>`:''}${rawDetails('Persisted job counts',state.runtime.jobs)}`:''}${state.dashboard.project.role==='reviewer'?`<div class="section-gap">${action('Export project with sources','export-project','download')}<p class="field-note">${label("Includes project records and original files. Keep this bundle private. Account passwords and sessions are excluded.")}</p></div>`:''}</div></section>`;
}
function teamView() {
  const owner=state.dashboard?.project?.owner===state.user.id;
  const members=array(state.dashboard?.members);
  return heading('Team & access','Share deliberately.','Project members use their own application accounts. A local URL still requires a shared server before teammates can connect.')+runtimePanel(owner)+`<div class="section-grid"><div class="stack"><section class="panel"><div class="panel-head"><h2>${label("Project membership")}</h2><small>${members.length} ${label("accounts")}</small></div><div class="panel-body">${members.map(m=>`<article class="list-card"><div class="list-card-head"><h3>${esc(m.username)}</h3>${badge(m.role)}</div><p class="mono">${esc(m.user_id)}</p>${owner && m.user_id!==state.user.id ? action('Remove project access','remove-member','','small danger',`data-user="${esc(m.user_id)}"`) : ''}</article>`).join('')}${owner ? `<form method="post" id="member-form" class="form-stack section-gap"><div class="field"><label for="member-user">${label("Existing account")}</label>${state.users.length ? `<select id="member-user" name="user_id" required>${state.users.filter(u=>u.id!==state.user.id).map(u=>`<option value="${esc(u.id)}">${esc(u.username)}</option>`).join('')}</select>` : `<input id="member-user" name="user_id" placeholder="${esc(ui("Existing user ID"))}" data-i18n-placeholder="Existing user ID" required>`}</div><div class="field"><label for="member-role">${label("Project role")}</label><select id="member-role" name="role"><option value="viewer" data-i18n="Viewer — read and export">${esc(ui("Viewer — read and export"))}</option><option value="engineer" data-i18n="Engineer — upload and run checks">${esc(ui("Engineer — upload and run checks"))}</option><option value="reviewer" data-i18n="Reviewer — approve rules and reviews">${esc(ui("Reviewer — approve rules and reviews"))}</option></select></div><button class="button primary" type="submit">${label("Save membership")}</button></form>` : `<p class="field-note">${label("The project owner manages membership.")}</p>`}</div></section>${state.user.admin ? `<section class="panel"><div class="panel-head"><h2>${label("Create an application account")}</h2><small>${label("Administrator only")}</small></div><div class="panel-body"><form method="post" id="account-form" class="form-stack"><div class="field"><label for="new-username">${label("Username")}</label><input id="new-username" name="username" minlength="3" maxlength="80" required autocomplete="off"></div><div class="field"><label for="new-account-password">${label("Initial password")}</label><input id="new-account-password" name="password" type="password" minlength="12" maxlength="200" required autocomplete="new-password"></div><p class="field-note">${label("Creating an account does not grant project access. Share credentials through your approved channel; this application sends no invitations.")}</p><button class="button primary" type="submit">${label("Create account")}</button></form></div></section>` : ''}</div><section class="panel"><div class="panel-head"><h2>${label("Change your password")}</h2></div><div class="panel-body"><form method="post" id="password-form" class="form-stack"><input type="text" name="username" autocomplete="username" value="${esc(state.user.username)}" hidden><div class="field"><label for="current-password">${label("Current password")}</label><input id="current-password" name="current_password" type="password" required autocomplete="current-password"></div><div class="field"><label for="updated-password">${label("New password")}</label><input id="updated-password" name="new_password" type="password" minlength="12" maxlength="200" required autocomplete="new-password"></div><p class="field-note">${label("Changing it signs out all of your existing sessions.")}</p><button class="button primary" type="submit">${label("Change password")}</button></form></div></section></div>`;
}
function renderAuth() {
  app.innerHTML = `<main class="auth-page"><section class="auth-intro"><div class="brand"><div class="brand-mark">S</div><div><div class="brand-name">STRATA</div><small>${label("ENGINEERING ASSURANCE")}</small></div></div><h1>${label("Every check.")}<br>${label("A clear line")}<br>${label("to the evidence.")}</h1><p>${label("A shared workspace for engineering inputs, reproducible calculations and accountable review.")}</p><div class="auth-lines" aria-hidden="true"></div></section><section class="auth-main"><div class="auth-language">${languageSwitch()}</div><form method="post" id="auth-form" class="auth-form"><div class="eyebrow">${label(state.needsSetup ? 'First-time setup' : 'Your workspace')}</div><h2>${label(state.needsSetup ? 'Create the first account' : 'Welcome back')}</h2><p>${label(state.needsSetup ? 'Set up the workspace administrator. The backend stores projects and records for authorised members.' : 'Sign in to access the projects and evidence shared with your account.')}</p>${state.authError ? `<div class="auth-error" role="alert">${systemLabel(state.authError)}</div>` : ''}<div class="field"><label for="username">${label("Username")}</label><input id="username" name="username" autocomplete="username" maxlength="80" required ${state.authBusy ? 'disabled' : ''}></div><div class="field"><label for="password">${label("Password")}</label><input id="password" type="password" name="password" autocomplete="${state.needsSetup ? 'new-password' : 'current-password'}" ${state.needsSetup ? 'minlength="12"' : ''} maxlength="200" required ${state.authBusy ? 'disabled' : ''}>${state.needsSetup ? `<p class="field-note">${label("Use at least 12 characters.")}</p>` : ''}</div>${state.needsSetup && state.setupTokenRequired ? `<div class="field"><label for="setup-token">${label('Setup token')}</label><input id="setup-token" name="setup_token" type="password" autocomplete="off" required placeholder="${esc(ui('Enter the operator-provided setup token'))}" data-i18n-placeholder="Enter the operator-provided setup token"><p class="field-note">${label('Required only for protected first-account setup, including Docker. It is not your account password.')}</p></div>` : ''}<button class="button primary" type="submit" ${state.authBusy ? 'disabled' : ''}>${state.authBusy ? '<span class="spinner"></span>' : ''}${label(state.needsSetup ? 'Create workspace account' : 'Sign in')}${icon('arrow')}</button><div class="auth-foot">${label("Your session is kept in this browser tab. Engineering records are stored by the workspace server and protected by project permissions.")}</div></form></section></main>`;
  translateMarked(app);
}
function emptyProject() {
  return heading('Start here','A place for your next review.','Create a project to keep source files, rules and review records together.')+`<section class="panel"><div class="empty-state"><div class="empty-icon">${icon('layers')}</div><h3>${label("Create your first project")}</h3><p>${label("You can load a labelled synthetic example after creating a project, or upload your own supported files.")}</p><div class="section-gap">${action('Create project','new-project','plus','primary')}</div></div></section>`;
}
function stat(caption,value,foot,image) { return `<div class="stat-card"><div class="stat-label">${label(caption)}${icon(image)}</div><div class="stat-value">${esc(value)}</div><div class="stat-foot">${label(foot)}</div></div>`; }
function workspaceView() {
  const snapshot = selectedSnapshot();
  const waiting = runs().filter(run => phase(run) === 'WAITING').length;
  return heading('Engineering QA workspace','Review with evidence.','Select a version, run a supported check and follow every result back to its inputs.',action('Load example','seed','layers','',state.busy ? 'disabled' : '')+(state.connector.configured?action('CSI read-only import','connector-import','download','',''):'')+action('Upload files','upload','upload','primary',state.busy ? 'disabled' : ''))+
    (!snapshots().length ? notice('New here? Load a labelled synthetic example to explore the full workflow. Example data is not a client-approved engineering benchmark.') : snapshot?.input?.synthetic === true ? notice('Synthetic example selected. These results demonstrate the software workflow; they do not certify a real engineering design.') : '')+
    `<section class="stats-grid" aria-label="${esc(ui("Project summary"))}" data-i18n-aria-label="Project summary">${stat('Snapshots',snapshots().length,'Versioned engineering inputs','layers')}${stat('Approved rules',rules().filter(approved).length,'Available within this project','book')}${stat('Check runs',runs().length,'Saved by the workspace server','check')}${stat('Needs evidence',waiting,'Runs waiting for follow-up','file')}</section><div class="workspace-grid"><section class="panel"><div class="panel-head"><h2>${icon('play')}${label("Start a review")}</h2><small>${label("Controlled workflow")}</small></div><div class="panel-body"><form method="post" id="run-form" class="form-stack"><div class="field"><label for="snapshot-select">${label("Engineering snapshot")}</label><select id="snapshot-select" required ${state.busy ? 'disabled' : ''}>${snapshotOptions(state.snapshotId)}</select><div class="source-line"><span>${snapshot ? `${esc(displayDate(snapshot.created_at))} · ${label(snapshot.input?.synthetic === true ? 'Synthetic' : 'Supplied data')}` : label('Upload a file or load an example')}</span>${snapshot ? `<button type="button" class="text-link" data-action="snapshot-preview">${label("Inspect input")}</button>` : ''}</div>${snapshot && state.taskId !== 'handoff' && state.dashboard.project.active_snapshot_id !== snapshot.id ? `<div class="source-line"><span>${label("This is not the current project revision.")}</span><button type="button" class="text-link" data-action="activate-snapshot">${label("Make current")}</button></div>` : snapshot ? `<p class="field-note">${label(state.taskId==='handoff' ? 'Source side of the transfer review' : 'Current project revision')}</p>` : ''}</div><div><label class="field-label">${label("Review task")}</label><div class="task-options">${tasks.map(task => `<button type="button" class="task-option ${state.taskId === task.id ? 'selected' : ''}" data-action="task" data-task="${task.id}" aria-pressed="${state.taskId === task.id}" ${state.busy ? 'disabled' : ''}><span class="radio-ring"></span><span><strong>${label(task.title)}</strong><small>${label(task.description)}</small></span></button>`).join('')}</div></div>${state.taskId === 'handoff' ? `<div class="field"><label for="compare-to">${label("Target snapshot")}</label><select id="compare-to" required>${snapshotOptions(state.compareTo,'Select the handoff target',state.snapshotId)}</select><p class="field-note">${label("Handoff confirmation is bound to the target revision.")}</p>${state.compareTo && state.dashboard.project.active_snapshot_id !== state.compareTo ? action('Make target current','activate-snapshot','','small',`data-snapshot="${esc(state.compareTo)}"`) : state.compareTo ? `<p class="field-note">${label("Current target revision")}</p>` : ''}</div>` : ''}<details class="raw-details"><summary>${label("Question and optional local model routing")}</summary><div class="field"><label for="run-question">${label("Question or review context")}</label><textarea id="run-question" rows="3" maxlength="2000" placeholder="${esc(ui("Describe the check you need…"))}" data-i18n-placeholder="Describe the check you need…">${esc(state.question)}</textarea></div><label class="checkbox-label"><input id="use-model" type="checkbox" ${state.useModel ? 'checked' : ''} ${!state.model.enabled ? 'disabled' : ''}>${label("Use the configured local model to select a task")}</label><p class="field-note">${state.model.enabled ? `${label('Local model:')} ${esc(state.model.model || 'configured')}. ${label('The model selects a supported task; deterministic tools produce the engineering result.')}` : label('No local model is configured. Explicit task selection remains available.')}</p></details><button class="button primary run-button" type="submit" ${state.busy || !state.snapshotId ? 'disabled' : ''}>${state.busy ? '<span class="spinner"></span>' : icon('play')}${label(state.busy ? 'Starting review…' : 'Run engineering check')}</button><p class="field-note">${label("Missing rules or evidence return NOT VERIFIED. No missing engineering values are inferred.")}</p></form></div></section><section class="panel" id="workspace-result"><div class="panel-head"><h2>${icon('check')}${label("Review result")}</h2>${state.run ? badge(state.run.state) : `<small>${label("Results will appear here")}</small>`}</div>${state.run ? `<div class="panel-body">${runContent(state.run)}</div>` : `<div class="empty-state"><div class="empty-icon">${icon('check')}</div><h3>${label("Ready when the evidence is.")}</h3><p>${label("Your result will include the calculation, source citations and a step-by-step execution record.")}</p><div class="empty-steps"><span>${label("Rules")}</span><span>${label("Inputs")}</span><span>${label("Calculation")}</span><span>${label("Evidence")}</span></div></div>`}</section></div><section class="panel section-gap"><div class="panel-head"><h2>${label("Recent review runs")}</h2>${action('Refresh','refresh','refresh','small')}</div>${runTable(runs().slice(0,8))}</section>`;
}
function detailView(detail) {
  return `<div class="result-detail"><p><strong>${detail.label || detail.name ? esc(detail.label || detail.name) : label('Check detail')}</strong></p>${detail.reason ? `<p>${systemLabel(detail.reason)}</p>` : ''}${['expected','actual','tolerance'].some(key => detail[key] !== undefined) ? `<div class="data-grid">${['expected','actual','tolerance'].map(key => `<div><small>${label(key === 'expected' ? 'Expected' : key === 'actual' ? 'Observed' : 'Tolerance')}</small><strong>${detail[key] === undefined || detail[key] === null ? label('Unavailable') : esc(detail[key])}${detail.unit ? ` ${esc(detail.unit)}` : ''}</strong></div>`).join('')}</div>` : ''}${detail.formula ? `<pre class="code-block">${esc(detail.formula)}</pre>` : ''}${detail.location ? `<p class="meta-line">${label("Source:")} ${esc(detail.location)}</p>` : ''}${array(detail.evidenceRefs || detail.evidence_refs).length ? `<p class="meta-line">${label("Evidence:")} ${esc((detail.evidenceRefs || detail.evidence_refs).join(', '))}</p>` : ''}</div>`;
}
function runContent(run,{review=false}={}) {
  const isRunning = running(run), isWaiting = phase(run) === 'WAITING', isError = phase(run) === 'ERROR';
  const resultRows = array(run.results), citations = array(run.citations), trace = array(run.trace || run.toolTrace), summary = run.summary || {};
  const canApprove = phase(run) === 'COMPLETED' && run.status === 'PASS' && !run.stale && state.dashboard?.project?.role === 'reviewer';
  return `${run.stale ? notice('This run is stale. Review its changed dependencies and create a new run before confirming.','warning') : ''}<div class="run-summary"><div><div class="eyebrow">${label(taskTitle(run.task_id || run.taskId))}</div><h3>${label(isRunning ? 'Review in progress' : isWaiting ? 'More evidence is needed' : isError ? 'The workflow stopped' : 'Calculation completed')}</h3></div>${run.status ? badge(run.status) : badge(run.state)}</div>${isRunning ? `<p class="explanation"><span class="spinner"></span> ${label("Checking the saved run. You can return to this record later.")}</p>` : ''}${run.cache_hit ? `<p class="field-note">${label("A matching verified calculation was reused. This run has its own saved record.")}</p>` : ''}<div class="result-counts"><span><b>${Number(summary.PASS || 0)}</b> ${label("passed")}</span><span><b>${Number(summary.FAIL || 0)}</b> ${label("failed")}</span><span><b>${Number(summary['NOT VERIFIED'] || 0)}</b> ${label("not verified")}</span></div>${run.explanation ? `<p class="explanation">${systemLabel(run.explanation)}</p>` : ''}${run.error || run.reason ? notice(run.error || run.reason,isError ? 'error' : 'warning') : ''}${materialView(run.material_requests)}${run.missing && (Array.isArray(run.missing) ? run.missing.length : true) ? rawDetails('Required evidence or data',run.missing) : ''}<div class="result-list">${resultRows.map(result => `<details class="result-item"><summary><span><strong>${systemLabel(result.name || result.title || result.id)}</strong><small>${esc(result.id)}</small></span>${badge(result.status)}</summary><div class="result-detail"><p>${systemLabel(result.summary || result.reason || '')}</p>${array(result.details).map(detailView).join('')}${!Array.isArray(result.details) ? rawDetails('Calculation record',result) : ''}</div></details>`).join('')}</div>${citations.length ? `<details class="raw-details"><summary>${label("Source citations ·")} ${citations.length}</summary>${citations.map(citation => `<article><p class="meta-line"><strong>${esc(citation.rule_id || citation.ruleId || citation.id)} · ${esc(citation.version)}</strong><br>${esc(citation.title)} · ${esc(citation.locator)}</p><blockquote class="source-quote">${esc(citation.quote || citation.text || citation.source?.text || '')}</blockquote>${sourceButton(citation.source_sha256)}</article>`).join('')}</details>` : ''}${trace.length ? `<details class="raw-details"><summary>${label("Execution trace ·")} ${trace.length} ${label("steps")}</summary>${trace.map((step,index) => `<div class="trace-step"><span class="trace-number">${index+1}</span><div class="trace-copy"><strong>${esc(step.tool || step.name || step.step || step.event || 'Workflow step')}</strong><small>${badge(step.status || step.state || '')}${step.duration_ms !== undefined || step.durationMs !== undefined ? ` · ${esc(step.duration_ms ?? step.durationMs)} ms` : ''}</small>${rawDetails('Inputs, outputs and evidence',step)}</div></div>`).join('')}</details>` : ''}${run.route ? rawDetails('Task routing record',run.route) : ''}${array(run.reviews).length ? `<details class="raw-details"><summary>${label("Recorded reviews ·")} ${run.reviews.length}</summary>${run.reviews.map(review => `<article class="list-card"><div class="list-card-head"><h3>${esc(review.username || review.actor)}</h3>${badge(review.action)}</div><p>${esc(review.note)}</p><p class="meta-line">${esc(displayDate(review.created_at))}</p></article>`).join('')}</details>` : ''}<p class="run-meta-small">${label("Run")} ${esc(run.id)}<br>${label("Snapshot")} ${esc(run.snapshot_id || run.snapshotId)} · ${esc(displayDate(run.created_at || run.createdAt))}<br>${label("Review state:")} ${badge(run.review_state || 'not confirmed')}</p><div class="run-footer">${action('Preview / print PDF','report-html','file','small',isRunning ? 'disabled' : '')}${action('Export JSON','report-json','download','small',isRunning ? 'disabled' : '')}${action('Refresh run','refresh-run','refresh','small')}${isRunning || isWaiting ? action('Cancel run','cancel-run','','small danger') : ''}${!review ? action('Review & follow up','open-review','arrow','small') : ''}</div>${!isRunning ? `<div class="review-form"><div class="field"><label for="resume-snapshot">${label("Snapshot for resumed run")}</label><select id="resume-snapshot">${snapshotOptions(run.snapshot_id || state.snapshotId,'Use the current run snapshot')}</select><p class="field-note">${label("Choose a revised snapshot after supplying missing evidence. The server creates a linked follow-up run and retains the earlier record.")}</p></div>${run.task_id==='handoff' ? `<div class="field"><label for="resume-target">${label("Target for follow-up run")}</label><select id="resume-target">${snapshotOptions(run.compare_to,'Select target')}</select></div>` : ''}${action(isError ? 'Retry workflow' : 'Create follow-up run','resume','play','',state.busy ? 'disabled' : '')}</div>` : ''}${review && !isRunning ? `<form method="post" id="review-form" class="review-form"><h3>${label("Record an engineering review")}</h3><p class="field-note">${label("Technical outcomes remain unchanged. Confirmation requires a current passing run and the appropriate project role.")}</p><div class="field section-gap"><label for="review-note">${label("Review note")}</label><textarea id="review-note" name="note" rows="3" maxlength="2000" required placeholder="${esc(ui("Record your decision, evidence requests or outstanding concerns."))}" data-i18n-placeholder="Record your decision, evidence requests or outstanding concerns."></textarea></div><div class="row-actions"><button class="button primary" name="decision" value="approve" type="submit" ${!canApprove || state.busy ? 'disabled' : ''}>${icon('check')}${label("Confirm review")}</button><button class="button" name="decision" value="request_evidence" type="submit" ${state.busy ? 'disabled' : ''}>${label("Request evidence")}</button></div>${!canApprove ? `<p class="field-note">${label("Confirmation requires a completed, current PASS run and a reviewer role.")}</p>` : ''}</form>` : ''}`;
}
function sourceButton(sha) {
  const file = files().find(item => item.sha256 === sha);
  return file ? `<button class="text-link" data-action="download-file" data-file="${esc(file.id)}">${label("Open")} ${esc(file.filename)}</button>` : '';
}
function runTable(items) {
  return `<div class="table-wrap"><table><thead><tr><th>${label("Review task")}</th><th>${label("Result")}</th><th>${label("Review")}</th><th>${label("Created")}</th><th></th></tr></thead><tbody>${items.length ? items.map(run => `<tr class="${run.id === state.selectedRunId ? 'selected-row' : ''}"><td><button class="run-list-button" data-action="select-run" data-run="${esc(run.id)}"><span class="table-title">${label(taskTitle(run.task_id || run.taskId))}</span><span class="table-sub">${short(run.id)}${run.stale ? ` · ${label('Stale dependencies')}` : ''}</span></button></td><td>${badge(run.status || run.state)}</td><td>${badge(run.review_state || 'not reviewed')}</td><td class="nowrap">${esc(displayDate(run.created_at))}</td><td><button class="icon-button" data-action="select-run" data-run="${esc(run.id)}" aria-label="${esc(ui("Open run"))} ${esc(short(run.id))}" data-i18n-aria-label="Open run">${icon('arrow')}</button></td></tr>`).join('') : `<tr><td colspan="5" class="table-empty">${label("No saved runs yet. Run a check to start the review record.")}</td></tr>`}</tbody></table></div>`;
}
function knowledgeView() {
  const retrieval = state.retrieval;
  return heading('Knowledge & rules','Make the source explicit.','Versioned rules are linked to project files. Uploading a source does not approve a rule.',action('Upload source','upload','upload')+action('Add rule','new-rule','plus','primary',!files().length ? 'disabled' : ''))+notice('Only approved rules in this project can authorise a check. Rule approval records a software review; it is not structural certification.')+`<div class="section-grid"><div class="stack"><section class="panel"><div class="panel-head"><h2>${icon('book')}${label("Rule register")}</h2><span class="inline-count">${rules().length} ${label("rules")}</span></div>${rules().length ? rules().map(item => {const rule=ruleValue(item); return `<article class="list-card"><div class="list-card-head"><div><h3>${esc(rule.title)}</h3><p>${esc(rule.id)} · ${label('version')} ${esc(rule.version)} · ${badge(rule.authority)}</p></div>${badge(rule.status)}</div><p>${array(rule.task_ids).map(id=>label(taskTitle(id))).join(' · ')}</p><p class="meta-line">${esc(rule.locator)}${rule.approved_by ? ` · ${label('Approved by')} ${esc(rule.approved_by)}` : ''}</p><details class="raw-details"><summary>${label("Read rule and parameters")}</summary><blockquote class="source-quote">${esc(rule.text)}</blockquote>${rule.parameters ? rawDetails('Executable rule parameters',rule.parameters) : ''}<p class="mono">${label("Source SHA-256:")} ${esc(rule.source_sha256)}</p>${sourceButton(rule.source_sha256)}</details><div class="row-actions">${rule.status === 'draft' ? action('Approve rule','approve-rule','check','small',`data-rule="${esc(item.id)}"`) : ''}${rule.status === 'approved' ? action('Retire version','retire-rule','','small danger',`data-rule="${esc(item.id)}"`) : ''}</div></article>`;}).join('') : `<div class="compact-empty">${label("No rules registered.")}<br>${label("Load an example or upload a source and add a draft rule.")}</div>`}</section><section class="panel"><div class="panel-head"><h2>${icon('file')}${label("Source files")}</h2><small>${files().length} ${label("saved")}</small></div>${files().length ? files().map(file => `<article class="list-card"><div class="list-card-head"><div><h3 class="file-name">${esc(file.filename)}</h3><p>${bytesLabel(file.size_bytes)} · ${esc(displayDate(file.created_at))}</p></div>${badge(file.ingestion?.status || 'stored')}</div><p class="mono">SHA-256 ${esc(file.sha256)}</p><div class="row-actions">${action('Open source','download-file','download','small',`data-file="${esc(file.id)}"`)}${action('Inspect extraction','file-preview','','small',`data-file="${esc(file.id)}"`)}${action('Create snapshot','new-snapshot','plus','small',`data-file="${esc(file.id)}"`)}${file.filename?.toLowerCase().endsWith('.pdf')?action('Scanned page review','ocr-review','','small',`data-file="${esc(file.id)}"`):''}</div></article>`).join('') : `<div class="compact-empty">${label("No project source files.")}</div>`}</section></div><section class="panel"><div class="panel-head"><h2>${icon('search')}${label("Retrieve evidence")}</h2><small>${label("Project and approval filtered")}</small></div><div class="panel-body"><form method="post" id="search-form" class="form-stack"><div class="field"><label for="search-task">${label("Task scope")}</label><select id="search-task">${taskOptions(state.searchTask)}</select></div><div class="field"><label for="knowledge-query">${label("Question or rule identifier")}</label><input id="knowledge-query" value="${esc(state.search)}" maxlength="2000" required placeholder="${esc(ui("For example, required load combinations"))}" data-i18n-placeholder="For example, required load combinations"></div><button class="button primary" type="submit" ${state.busy ? 'disabled' : ''}>${icon('search')}${label("Retrieve approved sources")}</button></form>${retrieval ? `<div class="divider"></div>${badge(retrieval.status)}<p class="explanation">${systemLabel(retrieval.reason || '')}</p>${array(retrieval.citations).map(citation => `<p class="meta-line"><strong>${esc(citation.rule_id || citation.ruleId)}</strong> · ${esc(citation.version)}<br>${esc(citation.title)} · ${esc(citation.locator)}</p><blockquote class="source-quote">${esc(citation.quote || citation.text)}</blockquote>${sourceButton(citation.source_sha256)}`).join('')}${rawDetails('Retrieval record',retrieval)}` : `<p class="field-note section-gap">${label("Search uses the server’s supported retrieval method. A relevant passage alone does not authorise an engineering calculation.")}</p>`}</div></section></div>`;
}
function issuesView() {
  const issues=array(state.dashboard?.issues).filter(i=>state.issueFilter==='all'||i.state!=='RESOLVED'), members=array(state.dashboard?.members);
  return `<section class="panel section-gap"><div class="panel-head"><h2>${label("Finding register")}</h2><select id="issue-filter" aria-label="${esc(ui("Filter findings"))}" data-i18n-aria-label="Filter findings"><option value="open" ${state.issueFilter==='open'?'selected':''} data-i18n="Open findings">${esc(ui("Open findings"))}</option><option value="all" ${state.issueFilter==='all'?'selected':''} data-i18n="All findings">${esc(ui("All findings"))}</option></select></div><div class="panel-body">${issues.length ? issues.map(issue=>`<article class="list-card"><div class="list-card-head"><h3>${esc(issue.finding_id)} · ${esc(issue.title)}</h3>${badge(issue.state)}</div><p class="meta-line">${label("Original result:")} ${badge(issue.technical_status)} · ${label('Run')} ${short(issue.source_run_id)} · ${label('Assigned to')} ${members.find(m=>m.user_id===issue.assignee)?.username ? esc(members.find(m=>m.user_id===issue.assignee).username) : label('unassigned')}</p>${issue.resolution_run_id ? `<p class="field-note">${label("Verified in linked run")} ${short(issue.resolution_run_id)}. ${label('The original result is retained.')}</p>` : ''}<div class="row-actions">${action('Open original run','select-run','','small',`data-run="${esc(issue.source_run_id)}"`)}${action(issue.state==='RESOLVED'?'View resolution':'Manage finding','manage-issue','','small',`data-issue="${esc(issue.id)}"`)}</div></article>`).join('') : `<p class="field-note">${label("Non-passing findings from new runs are registered here. Missing workflow prerequisites remain in the run evidence request.")}</p>`}</div></section>`;
}
function issueModal(id) {
  const issue=array(state.dashboard?.issues).find(i=>i.id===id);
  if(!issue)throw Error('Finding unavailable.');
  const isReviewer=state.dashboard.project.role==='reviewer', canEdit=['reviewer','engineer'].includes(state.dashboard.project.role) && issue.state!=='RESOLVED';
  openModal(`${issue.finding_id} · ${issue.state}`,`${rawDetails('Finding history',issue)}${canEdit ? `<form method="post" id="issue-form" class="form-stack section-gap"><input type="hidden" name="issue_id" value="${esc(id)}"><div class="field"><label for="issue-action">${label("Action")}</label><select id="issue-action" name="action"><option value="request_evidence" data-i18n="Request evidence">${esc(ui("Request evidence"))}</option><option value="assign" data-i18n="Assign responsibility">${esc(ui("Assign responsibility"))}</option>${isReviewer?`<option value="resolve" data-i18n="Resolve using a linked passing finding">${esc(ui("Resolve using a linked passing finding"))}</option>`:''}</select></div><div class="field"><label for="issue-assignee">${label("Responsible member (for assignment)")}</label><select id="issue-assignee" name="assignee">${array(state.dashboard.members).filter(m=>['engineer','reviewer'].includes(m.role)).map(m=>`<option value="${esc(m.user_id)}">${esc(m.username)}</option>`).join('')}</select></div>${isReviewer?`<div class="field"><label for="issue-resolution">${label("Verification run (for resolution)")}</label><select id="issue-resolution" name="resolution_run_id"><option value="" data-i18n="Select a linked follow-up run">${esc(ui("Select a linked follow-up run"))}</option>${runs().filter(r=>r.parent_run_id && !r.stale && array(r.results).some(f=>f.id===issue.finding_id && f.status==='PASS')).map(r=>`<option value="${esc(r.id)}">${short(r.id)} · ${esc(r.status)} · ${esc(displayDate(r.created_at))}</option>`).join('')}</select><p class="field-note">${label("The server verifies the same finding passes in this original run’s successor chain.")}</p></div>`:''}<div class="field"><label for="issue-note">${label("Reason and evidence")}</label><textarea id="issue-note" name="note" maxlength="2000" rows="3" required></textarea></div></form>`:''}`,`${action('Close','close-modal')}${canEdit?`<button class="button primary" form="issue-form" type="submit">${label("Save finding action")}</button>`:''}`);
  modal.querySelector('h2').innerHTML=`${esc(issue.finding_id)} · ${badge(issue.state)}`;
}
function reviewView() {
  const filtered=runs().filter(run=>state.runFilter==='all' || (state.runFilter==='STALE'?run.stale:run.status===state.runFilter));
  return heading('Review & follow-up','Keep decisions accountable.','Inspect findings, request missing evidence and record a review against the exact saved run.',action('Refresh','refresh','refresh'))+
    `${state.run ? `<section class="panel"><div class="panel-head"><h2>${icon('check')}${label(taskTitle(state.run.task_id))}</h2>${badge(state.run.state)}</div><div class="panel-body">${runContent(state.run,{review:true})}</div></section>` : ''}${issuesView()}<section class="panel section-gap"><div class="panel-head"><h2>${label("Saved review runs")}</h2><div class="field"><label for="run-filter">${label("Filter runs")}</label><select id="run-filter">${['all','PASS','FAIL','NOT VERIFIED','STALE'].map(value=>`<option data-i18n-status="${value==='all'?'All results':value}" value="${value}" ${state.runFilter===value?'selected':''}>${value==='all'?esc(ui('All results')):esc(displayStatus(value))}</option>`).join('')}</select></div></div><div class="history-scroll">${runTable(filtered)}</div></section>`;
}

function versionsView() {
  const comparison = state.comparison;
  return heading('Version comparison','See what changed.','Compare two saved snapshots before deciding which checks need to be repeated.',action('Upload revision','upload','upload','primary'))+notice('A difference is not automatically an engineering error. Approved mappings and change requirements determine whether a difference is allowed.')+`<section class="panel"><div class="panel-head"><h2>${icon('layers')}${label("Compare snapshots")}</h2><small>${label("Read-only comparison")}</small></div><div class="panel-body"><form method="post" id="compare-form"><div class="form-row"><div class="field"><label for="before-snapshot">${label("Before")}</label><select id="before-snapshot" required>${snapshotOptions(state.beforeId)}</select></div><div class="field"><label for="after-snapshot">${label("After")}</label><select id="after-snapshot" required>${snapshotOptions(state.afterId)}</select></div></div><div class="section-gap">${action('Compare versions','compare','layers','primary',state.busy || snapshots().length < 2 ? 'disabled' : '')}</div></form>${comparison ? `<div class="divider"></div>${comparison.status ? badge(comparison.status) : ''}${comparison.summary ? `<p class="explanation">${esc(typeof comparison.summary === 'string' ? comparison.summary : json(comparison.summary))}</p>` : ''}${comparison.explanation || comparison.reason ? `<p class="explanation">${esc(comparison.explanation || comparison.reason)}</p>` : ''}${rawDetails('Comparison details',comparison)}` : ''}</div></section><section class="panel section-gap"><div class="panel-head"><h2>${label("Snapshot register")}</h2><small>${snapshots().length} ${label("saved versions")}</small></div><div class="table-wrap"><table><thead><tr><th>${label("Snapshot")}</th><th>${label("Parent")}</th><th>${label("Created")}</th><th></th></tr></thead><tbody>${snapshots().length ? snapshots().map(snapshot => `<tr><td><span class="table-title">${esc(titleOf(snapshot))}</span><span class="table-sub">${short(snapshot.id)} · ${label(snapshot.input?.synthetic === true ? 'Synthetic' : 'Supplied input')}${state.dashboard.project.active_snapshot_id === snapshot.id ? ' · '+label('Current') : ''}</span></td><td class="mono">${esc(short(snapshot.parent_id) || '—')}</td><td>${esc(displayDate(snapshot.created_at))}</td><td>${action('Inspect input','snapshot-preview','','small',`data-snapshot="${esc(snapshot.id)}"`)} ${state.dashboard.project.active_snapshot_id !== snapshot.id ? action('Make current','activate-snapshot','','small',`data-snapshot="${esc(snapshot.id)}"`) : badge('active','Current')}</td></tr>`).join('') : `<tr><td colspan="4" class="table-empty">${label("No saved snapshots.")}</td></tr>`}</tbody></table></div></section>`;
}
function auditView() {
  const entries = array(state.dashboard?.audit);
  return heading('Project audit','A record of the work.','Server-recorded events for this project, including changes to files, rules, runs and reviews.',action('Refresh','refresh','refresh'))+`${state.dashboard.auditValid === false ? notice('The server reported an inconsistent audit chain. Do not treat these events as verified.','error') : ''}<div class="stats-grid">${stat('Audit events',entries.length,'Events returned for this project','history')}${stat('Members',array(state.dashboard?.members).length,'Project access records','users')}${stat('Files',files().length,'Sources retained by the server','file')}${stat('Runs',runs().length,'Saved execution records','check')}</div><section class="panel"><div class="panel-head"><h2>${icon('history')}${label("Activity record")}</h2><small>${label(state.dashboard.auditValid === true ? 'Chain consistency verified by server' : 'Project-scoped')}</small></div>${entries.length ? entries.map(entry => `<article class="audit-entry"><time>${esc(displayDate(entry.created_at || entry.at))}</time><div><h3>${esc(entry.action || entry.type || entry.event || 'Recorded event')}</h3><p>${esc(entry.actor || entry.username || entry.user_id || 'Recorded by server')}</p>${entry.detail || entry.details || entry.data ? rawDetails('Event details',entry.detail || entry.details || entry.data) : ''}</div></article>`).join('') : `<div class="compact-empty">${label("No audit events returned.")}</div>`}</section><section class="panel section-gap"><div class="panel-head"><h2>${icon('users')}${label("Project members")}</h2><small>${label("Access is enforced by the server")}</small></div>${array(state.dashboard?.members).length ? array(state.dashboard.members).map(member => `<article class="list-card"><div class="list-card-head"><h3>${esc(member.username || member.name || member.user_id || member.id)}</h3>${badge(member.role || 'member')}</div></article>`).join('') : `<div class="compact-empty">${label("No membership records returned.")}</div>`}</section>`;
}

function openModal(title,body,footer='',originalTitle=false) {
  modal.classList.toggle('mapping-preview-dialog',title === 'Mapping preview');
  modal.innerHTML = `<div class="modal-head"><h2>${originalTitle ? esc(title) : label(title)}</h2>${languageSwitch()}<button class="icon-button" data-action="close-modal" aria-label="${esc(ui("Close dialog"))}" data-i18n-aria-label="Close dialog">${icon('close')}</button></div><div class="modal-body">${body}</div><p class="modal-error" id="modal-error" role="alert"></p>${footer ? `<div class="modal-foot">${footer}</div>` : ''}`;
  if (!modal.open) modal.showModal(); translateMarked(modal);
}
function connectorModal() {
  openModal('Import from configured connector',`<form method="post" id="connector-form" class="form-stack"><p>${label('A configured read-only connector does not establish real ETABS/SAFE interoperability. Confirm the service and profile with the operator before import.')}</p><div class="field"><label>${label('Connector model identifier')}</label><input name="model_id" maxlength="160" required></div><div class="field"><label>${label('Requested revision')}</label><input name="revision" maxlength="160" required></div><div class="field"><label>${label('Connector profile')}</label><input name="profile" maxlength="160" required></div></form>`,`${action('Cancel','close-modal')}<button type="submit" form="connector-form" class="button primary">${label('Import snapshot')}</button>`);
}
function newProjectModal() {
  openModal('Create project',`<form method="post" id="project-form"><div class="field"><label for="project-name">${label("Project name")}</label><input id="project-name" name="name" maxlength="120" required placeholder="${esc(ui("For example, North campus — structural QA"))}" data-i18n-placeholder="For example, North campus — structural QA"></div><p class="field-note">${label("Files, rules, runs and reviews will belong to this project. Membership controls access.")}</p></form>`,`${action('Cancel','close-modal')}<button class="button primary" form="project-form" type="submit">${label("Create project")}</button>`);
}
function uploadModal(mappingOnly=false) {
  openModal('Upload engineering material',`<form method="post" id="upload-form"><div class="field file-drop"><label for="source-upload">${label("Source file")}</label><input id="source-upload" type="file" accept=".json,.csv,.xlsx,.pdf,.txt,.md" required><p>${label("JSON, CSV, XLSX, PDF, TXT or Markdown · maximum 10 MB.")}<br>${label("The server validates and parses supported formats. Scanned or unsupported content may need follow-up.")}</p></div><div class="field"><label for="snapshot-title">${label("Snapshot title")}</label><input id="snapshot-title" name="title" maxlength="200" placeholder="${esc(ui("Use the file name if left blank"))}" data-i18n-placeholder="Use the file name if left blank"></div><label class="checkbox-label"><input id="mapping-source" type="checkbox" ${mappingOnly?'checked':''}>${label("Keep CSV / JSON as raw mapping source")}</label><p class="field-note">${label("Retains original bytes without guessing columns. Apply a saved adapter in Adaptation.")}</p><label class="checkbox-label"><input id="create-snapshot" type="checkbox" ${mappingOnly?'':'checked'}>${label("Create an engineering snapshot after upload")}</label><p class="field-note">${label("Turn this off for source documents used to support rules. An accepted upload does not itself verify engineering data.")}</p><div class="field section-gap"><label for="parent-snapshot">${label("Previous revision (optional)")}</label><select id="parent-snapshot">${snapshotOptions('','No previous revision')}</select></div></form>`,`${action('Cancel','close-modal')}<button class="button primary" form="upload-form" type="submit">${label("Upload to project")}</button>`);
}
function ruleModal() {
  const example = {required_base_cases:['SDL','LIVE'],required_combinations:[{id:'C1',terms:[{caseId:'SDL',factor:1.2},{caseId:'LIVE',factor:1.5}]}],allow_extra_base_cases:false,allow_extra_combinations:false,factor_tolerance:0.000001};
  openModal('Register a draft rule',`<form method="post" id="rule-form"><p class="field-note">${label("Select a stored source and document the rule. It remains a draft until a permitted reviewer approves it. Example parameters below are synthetic, not code-prescribed factors.")}</p><div class="form-row section-gap"><div class="field"><label for="rule-id">${label("Rule identifier")}</label><input id="rule-id" name="id" maxlength="100" required placeholder="PROJECT-COMB-001"></div><div class="field"><label for="rule-version">${label("Version")}</label><input id="rule-version" name="version" value="1" maxlength="100" required></div></div><div class="field"><label for="rule-title">${label("Title")}</label><input id="rule-title" name="title" maxlength="300" required placeholder="${esc(ui("Required combination configuration"))}" data-i18n-placeholder="Required combination configuration"></div><div class="form-row"><div class="field"><label for="rule-task">${label("Task scope")}</label><select id="rule-task" name="task">${taskOptions('combination-configuration')}</select></div><div class="field"><label for="rule-authority">${label("Source type")}</label><select id="rule-authority" name="authority"><option value="synthetic" data-i18n="Synthetic / demonstration">${esc(ui("Synthetic / demonstration"))}</option><option value="client" data-i18n="Client-provided source">${esc(ui("Client-provided source"))}</option></select></div></div><div class="field"><label for="rule-source">${label("Stored source file")}</label><select id="rule-source" name="source_sha256" required><option value="" data-i18n="Choose a project file">${esc(ui("Choose a project file"))}</option>${files().map(file => `<option value="${esc(file.sha256)}">${esc(file.filename)} · ${short(file.sha256)}</option>`).join('')}</select></div><div class="field"><label for="rule-locator">${label("Source location")}</label><input id="rule-locator" name="locator" required maxlength="1000" placeholder="${esc(ui("Page 3, section 2.1 / worksheet and cells"))}" data-i18n-placeholder="Page 3, section 2.1 / worksheet and cells"></div><div class="field"><label for="rule-text">${label("Exact source excerpt")}</label><textarea id="rule-text" name="text" rows="4" required maxlength="20000" placeholder="${esc(ui("Copy an exact excerpt from the selected source file."))}" data-i18n-placeholder="Copy an exact excerpt from the selected source file."></textarea></div><details class="raw-details"><summary>${label("Advanced: check identifiers and explicit parameters")}</summary><div class="field"><label for="rule-checks">${label("Check IDs (comma separated)")}</label><input id="rule-checks" name="check_ids" value="COMB-CONFIG" required></div><div class="field"><label for="rule-parameters">${label("Parameters (JSON object)")}</label><textarea id="rule-parameters" class="rule-editor" name="parameters" rows="10">${esc(json(example))}</textarea></div><p class="field-note">${label("Parameters must match the selected tool contract and the cited source. Draft registration does not validate or approve their engineering meaning.")}</p></details></form>`,`${action('Cancel','close-modal')}<button class="button primary" form="rule-form" type="submit">${label("Save draft rule")}</button>`);
  installRuleEditor();
}
function snapshotModal(fileId) {
  const file=files().find(item=>item.id===fileId);
  if(!file)throw Error('Select a stored project file.');
  openModal('Create an engineering snapshot',`<form method="post" id="snapshot-form"><input type="hidden" name="file_id" value="${esc(file.id)}"><p class="field-note">${label("Source: {filename}. Parsed engineering data can become a snapshot. If the source needs mapping, record the mapping and its justification explicitly.",{filename:file.filename})}</p><div class="field section-gap"><label for="saved-snapshot-title">${label("Snapshot title")}</label><input id="saved-snapshot-title" name="title" value="${esc(file.filename)}" maxlength="160" required></div><div class="field"><label for="saved-parent">${label("Previous revision")}</label><select id="saved-parent" name="parent_id">${snapshotOptions('','No previous revision')}</select></div><label class="checkbox-label"><input id="manual-mapping" type="checkbox">${label("Provide an explicit mapping or corrected input")}</label><div id="manual-fields" hidden><div class="field section-gap"><label for="mapping-note">${label("Mapping / correction justification")}</label><textarea id="mapping-note" name="mapping_note" rows="3" maxlength="1000" placeholder="${esc(ui("Identify the source locations and explain each transformation or correction."))}" data-i18n-placeholder="Identify the source locations and explain each transformation or correction."></textarea></div><div class="field"><label for="mapped-input">${label("Engineering input (JSON object)")}</label><textarea id="mapped-input" name="input" class="rule-editor" rows="10">${esc(json(file.ingestion?.snapshot || {}))}</textarea></div></div><p class="field-note">${label("The original file is retained. Creating a new snapshot makes it the current project revision and can make previous review decisions stale.")}</p></form>`,`${action('Cancel','close-modal')}<button class="button primary" form="snapshot-form" type="submit">${label("Create snapshot")}</button>`);
  installSnapshotEditor();
}
function correctionModal(id) {
  const snapshot=snapshots().find(s=>s.id===id);if(!snapshot)throw Error('Snapshot unavailable.');
  openModal('Record a field correction',`<form method="post" id="correction-form" class="form-stack"><input type="hidden" name="snapshot_id" value="${esc(id)}"><p class="field-note">${esc(titleOf(snapshot))}. ${label('The original source and snapshot remain unchanged. This creates a new current revision, which must be checked again.')}</p>${rawDetails('Original input',snapshot.input)}<div class="field"><label for="correction-path">${label("Field path (JSON Pointer)")}</label><input id="correction-path" name="path" placeholder="/project/name" required></div><div class="form-row"><div class="field"><label for="correction-original">${label("Original value")}</label><select name="original_type">${["number","string","boolean","null"].map(v=>`<option value="${v}" data-i18n="${v}">${esc(ui(v))}</option>`).join("")}</select><input id="correction-original" name="original" required></div><div class="field"><label for="correction-value">${label("Confirmed value")}</label><select name="value_type">${["number","string","boolean","null"].map(v=>`<option value="${v}" data-i18n="${v}">${esc(ui(v))}</option>`).join("")}</select><input id="correction-value" name="value" required></div></div><div class="field"><label for="correction-source">${label("Source location")}</label><input id="correction-source" name="source_locator" maxlength="1000" placeholder="${esc(ui("Worksheet / row / cell, or PDF page and field"))}" data-i18n-placeholder="Worksheet / row / cell, or PDF page and field" required></div><div class="field"><label for="correction-reason">${label("Correction reason")}</label><textarea id="correction-reason" name="reason" maxlength="1000" rows="3" required></textarea></div></form>`,`${action('Cancel','close-modal')}<button class="button primary" form="correction-form" type="submit">${label("Save corrected revision")}</button>`);
  const form=document.getElementById('correction-form');
  const syncNull=()=>{for(const name of ['original','value']){const input=form.querySelector(`[name="${name}"]`),type=form.querySelector(`[name="${name}_type"]`);input.required=type.value!=='null';input.disabled=type.value==='null';}};
  form.addEventListener('change',syncNull);syncNull();
}
async function withBusy(fn) {
  if (state.busy) return;
  state.busy = true; render();
  try { return await fn(); }
  finally { state.busy = false; render(); }
}
async function startRun() {
  if (!state.snapshotId) throw Error('Select an engineering snapshot first.');
  if (state.taskId === 'handoff' && (!state.compareTo || state.compareTo === state.snapshotId)) throw Error('Select a different target snapshot for the handoff.');
  const payload = {snapshot_id:state.snapshotId,task_id:state.taskId,use_model:state.useModel && state.model.enabled};
  if (state.question.trim()) payload.question = state.question.trim();
  if (state.taskId === 'handoff') payload.compare_to = state.compareTo;

  await withBusy(async() => {
    state.requestKey ||= crypto.randomUUID();
    const response = await request(projectPath('/runs'),{method:'POST',body:payload,idempotencyKey:state.requestKey});
    state.requestKey = null;
    state.run = unwrap(response,'run'); state.selectedRunId = state.run.id;
    await loadDashboard({silent:true}); schedulePoll();
    toast('Review run saved. Its status and evidence are shown in the result panel.');
  });
}
async function downloadResource(path,filename,{preview=false}={}) {
  // Open synchronously during the user gesture; otherwise browsers may block the preview tab.
  const target = preview ? window.open('about:blank','_blank') : null;
  if (target) { target.opener = null; target.document.title = ui('Loading report'); target.document.body.textContent = ui('Loading the authorised project document…'); }
  try {
    const response = await request(path,{raw:true});
    let blob = await response.blob();
    if (preview && filename.toLowerCase().endsWith('.pdf')) blob = new Blob([blob],{type:'application/pdf'});
    const url = URL.createObjectURL(blob);
    if (preview && target) target.location.replace(url);
    else { const link=document.createElement('a');link.href=url;link.download=filename;link.click(); }
    setTimeout(() => URL.revokeObjectURL(url),60000);
    if (preview && !target) toast('The preview tab was blocked. The authorised report was downloaded instead.');
  } catch (error) { target?.close(); throw error; }
}
async function compareVersions() {
  if (!state.beforeId || !state.afterId || state.beforeId === state.afterId) throw Error('Choose two different snapshots to compare.');
  await withBusy(async() => {
    const response = await request(projectPath('/compare'),{method:'POST',body:{before_id:state.beforeId,after_id:state.afterId}});
    state.comparison = response.comparison || response;
  });
}

async function handleAction(button) {
  const name = button.dataset.action;
  if (name === 'language') { setLanguage(button.dataset.language); translateMarked(document); return; }
  const editorContext = {openModal, request, projectPath, files, snapshots, rules, tasks, error:error=>setSystemError(document.getElementById('modal-error'),error.message),role:state.dashboard?.project?.role,refresh:()=>loadDashboard({silent:true})};
  if (name === 'ocr-review') return openOCR(editorContext,button.dataset.file);
  if (name === 'connector-import') return connectorModal();
  if (name === 'builder-adapter') return openAdapterBuilder(editorContext);
  if (name === 'builder-case') return openCaseBuilder(editorContext);
  if (name === 'close-modal') return modal.close();
  if (name === 'menu') { state.sidebar = !state.sidebar; return render(); }
  if (name === 'logout') {
    await request('/auth/logout',{method:'POST',body:{}}).catch(()=>{});
    setToken(''); clearTimeout(pollTimer); state.user=null;state.dashboard=null;state.run=null;state.projectId='';state.authError='';modal.close();return render();
  }
  if (name === 'navigate') { state.view=button.dataset.view;state.sidebar=false;if(state.view==='team'){if(state.user.admin)state.users=(await request('/users')).items;state.runtime=await request(projectPath('/runtime'));}if(state.view==='validation'){state.validation=await request('/validation');}render();return; }
  if (name === 'manage-issue') return issueModal(button.dataset.issue);
  if (name === 'remove-member') return withBusy(async()=>{await request(projectPath(`/members/${encodeURIComponent(button.dataset.user)}`),{method:'DELETE'});await loadDashboard({silent:true});toast('Project access removed. Existing sessions no longer have access to this project.');});
  if (name === 'export-project') return downloadResource(projectPath('/export'),'strata-project-export.zip');
  if (name === 'new-project') return newProjectModal();
  if (name === 'config-adapter' || name === 'config-package' || name === 'config-case') return configModal(name.slice(7));
  if (name === 'upload-mapping') return uploadModal(true);
  if (name === 'apply-adapter') return adapterModal(button.dataset.id);
  if (name === 'export-adapter') return downloadResource(projectPath(`/adapters/${encodeURIComponent(button.dataset.id)}/export`),'adapter-profile.json');
  if (name === 'export-rules') return downloadResource(projectPath(`/rule-packages/export?material_type=${button.dataset.type}`),`${button.dataset.type}-rules.json`);
  if (name === 'evaluate-cases') {
    const case_ids=[...document.querySelectorAll('input[name="benchmark-case"]:checked')].map(input=>input.value);if(!case_ids.length)throw Error('Select at least one case.');
    const result=await request(projectPath('/evaluations'),{method:'POST',body:{case_ids}});await loadDashboard({silent:true});state.evaluation=(await request(projectPath(`/evaluations/${result.evaluation.id}`))).evaluation;render();scheduleEvaluationPoll();toast('Batch queued. Refresh the batch to inspect completed comparisons.');return;
  }
  if (name === 'open-evaluation') {state.evaluation=(await request(projectPath(`/evaluations/${encodeURIComponent(button.dataset.id)}`))).evaluation;render();scheduleEvaluationPoll();return;}
  if (name === 'export-evaluation') return downloadResource(projectPath(`/evaluations/${encodeURIComponent(button.dataset.id)}/report`),'case-evaluation.json');
  if (name === 'upload') return uploadModal();
  if (name === 'new-rule') return ruleModal();
  if (name === 'new-snapshot') return snapshotModal(button.dataset.file);
  if (name === 'task') { state.taskId=button.dataset.task;invalidateSelection();return render(); }
  if (name === 'refresh') {await loadDashboard();if(state.run)await selectRun(state.run.id);return;}
  if (name === 'activate-snapshot') return withBusy(async()=>{const id=button.dataset.snapshot || state.snapshotId;await request(projectPath(`/snapshots/${encodeURIComponent(id)}/activate`),{method:'POST',body:{}});await loadDashboard({silent:true});if(state.run)await selectRun(state.run.id);toast('Current project snapshot updated. Review status was re-evaluated.');});
  if (name === 'seed') return withBusy(async() => {await request(projectPath('/seed'),{method:'POST',body:{}});await loadDashboard({silent:true});toast('Synthetic example records were loaded into this project.');});
  if (name === 'select-run') return selectRun(button.dataset.run,{navigate:true});
  if (name === 'refresh-run') return state.run && selectRun(state.run.id);
  if (name === 'open-review') { state.view='review';return render(); }
  if (name === 'snapshot-preview') {const snapshot=snapshots().find(item=>item.id === (button.dataset.snapshot || state.snapshotId));return openModal(titleOf(snapshot),`<p class="field-note">${label("Read-only server record. Editing a source requires a new snapshot.")}</p><pre class="code-block">${esc(json(snapshot))}</pre>`,`${action('Close','close-modal')}${action('Correct a field','correct-field','','primary',`data-snapshot="${esc(snapshot.id)}"`)}`,true);}
  if (name === 'correct-field') return correctionModal(button.dataset.snapshot);
  if (name === 'file-preview') {const file=files().find(item=>item.id===button.dataset.file);return openModal(file?.filename || 'Source file',`<pre class="code-block">${esc(json(file))}</pre>`,action('Close','close-modal'),true);}
  if (name === 'download-file') {const file=files().find(item=>item.id===button.dataset.file);if(!file)throw Error('The source file is no longer in this project.');return downloadResource(projectPath(`/files/${encodeURIComponent(file.id)}/content`),file.filename,{preview:file.filename?.toLowerCase().endsWith('.pdf')});}
  if (name === 'approve-rule' || name === 'retire-rule') return withBusy(async()=>{await request(projectPath(`/rules/${encodeURIComponent(button.dataset.rule)}/${name === 'approve-rule' ? 'approve' : 'retire'}`),{method:'POST',body:{}});await loadDashboard({silent:true});state.retrieval=null;toast(name === 'approve-rule' ? 'Rule approval recorded by the server.' : 'Rule version retired. Dependent runs may need review.');});
  if (name === 'report-html' || name === 'report-json') {if(!state.run)throw Error('Select a saved run first.');const format=name === 'report-html' ? 'html' : 'json';return downloadResource(projectPath(`/runs/${encodeURIComponent(state.run.id)}/report?format=${format}&language=${getLanguage()}`),`strata-${short(state.run.id)}.${format}`,{preview:format==='html'});}
  if (name === 'resume') {const selected=document.getElementById('resume-snapshot')?.value;const target=document.getElementById('resume-target')?.value;return withBusy(async()=>{const response=await request(projectPath(`/runs/${encodeURIComponent(state.run.id)}/resume`),{method:'POST',body:{...(selected?{snapshot_id:selected}:{}),...(state.run.task_id==='handoff'?{compare_to:target}:{})}});state.run=unwrap(response,'run');state.selectedRunId=state.run.id;await loadDashboard({silent:true});schedulePoll();toast('Resume request saved.');});}
  if (name === 'cancel-run') return withBusy(async()=>{await request(projectPath(`/runs/${encodeURIComponent(state.run.id)}/cancel`),{method:'POST',body:{}});await selectRun(state.run.id);await loadDashboard({silent:true});toast('Cancellation recorded.');});
  if (name === 'validation-download') return downloadResource('/validation','strata-validation.json');
  if (name === 'validation-refresh') {state.validation=await request('/validation');return render();}
  if (name === 'compare') return compareVersions();
}
document.addEventListener('click',event=>{
  const button=event.target.closest('[data-action]');if(!button||button.disabled)return;
  event.preventDefault();Promise.resolve(handleAction(button)).catch(error=>toast(error.message,true));
});
document.addEventListener('input',event=>{
  const {id,value,checked}=event.target;
  if(id==='run-question'){state.question=value;invalidateSelection();}
  if(id==='knowledge-query')state.search=value;
  if(id==='use-model'){state.useModel=checked;invalidateSelection();}
});
document.addEventListener('change',event=>{
  const {id,value,checked}=event.target;
  if(id==='run-filter'){state.runFilter=value;render();}
  if(id==='issue-filter'){state.issueFilter=value;render();}
  if(id==='project-picker') {
    if(value !== state.projectId) changeProjectContext(value);
    loadDashboard().catch(error=>toast(error.message,true));
  }
  if(id==='snapshot-select'){state.snapshotId=value;const suggested=selectedSnapshot()?.suggested_task;if(suggested)state.taskId=suggested;if(state.compareTo===value)state.compareTo='';invalidateSelection();render();}
  if(id==='compare-to'){state.compareTo=value;invalidateSelection();render();}
  if(id==='use-model')state.useModel=checked;
  if(id==='search-task')state.searchTask=value;
  if(id==='before-snapshot')state.beforeId=value;
  if(id==='after-snapshot')state.afterId=value;
  if(id==='manual-mapping'){document.getElementById('manual-fields').hidden=!checked;document.getElementById('mapping-note').required=checked;}
});
document.addEventListener('invalid',event=>{
  const control=event.target;
  if(!control?.validity||!control.setCustomValidity)return;
  const v=control.validity;
  const key=v.valueMissing?(control.type==='file'?'Please select a file.':'Please complete this field.'):v.badInput?'Enter a valid number.':v.rangeOverflow||v.rangeUnderflow?'The value is outside the allowed range.':v.stepMismatch?'The value does not match the required step.':v.tooShort||v.tooLong?'Use the required number of characters.':'Enter a value in the required format.';
  control.dataset.i18nValidity=key;control.setCustomValidity(t(key));
},true);
document.addEventListener('input',event=>{
  const control=event.target;
  if(control.dataset?.i18nValidity){control.setCustomValidity('');delete control.dataset.i18nValidity;}
});
document.addEventListener('change',event=>{
  const control=event.target;
  if(control.dataset?.i18nValidity){control.setCustomValidity('');delete control.dataset.i18nValidity;}
});
document.addEventListener('submit',async event=>{
  const form=event.target;const formId=form.getAttribute('id');
  if(!['auth-form','project-form','upload-form','snapshot-form','rule-form','run-form','review-form','search-form','compare-form','account-form','member-form','password-form','issue-form','correction-form','policy-form','adaptation-config-form','adapter-apply-form','adapter-builder-form','case-builder-form','connector-form'].includes(formId))return;
  event.preventDefault();
  const submitter=event.submitter;
  if(submitter)submitter.disabled=true;
  const fail=error=>{const node=modal.open ? document.getElementById('modal-error') : null;if(node)setSystemError(node,error.message);else toast(error.message,true);};
  try {
    if(formId==='auth-form') {
      const values=Object.fromEntries(new FormData(form)), setupToken=values.setup_token;delete values.setup_token;state.authBusy=true;state.authError='';
      try {const result=await request(`/auth/${state.needsSetup?'bootstrap':'login'}`,{method:'POST',body:values,setupToken});setToken(result.token);state.user=result.user;state.needsSetup=false;await loadProjects();}
      catch(error){state.authError=error.message;}
      finally{state.authBusy=false;render();}
    } else if(formId==='connector-form') {
      const payload=Object.fromEntries(new FormData(form));const result=await request(projectPath('/connector/import'),{method:'POST',body:payload});state.snapshotId=result.snapshot.id;modal.close();await loadDashboard({silent:true});toast(result.reused?'Connector returned a previously imported snapshot. No new revision was created.':'Connector snapshot imported. Original export and provenance were retained.');
    } else if(formId==='adapter-builder-form' || formId==='case-builder-form') {
      const isAdapter=formId==='adapter-builder-form';const config=isAdapter?adapterFromForm(form):caseFromForm(form);
      await request(projectPath(isAdapter?'/adapters':'/cases'),{method:'POST',body:{[isAdapter?'profile':'case']:config}});modal.close();await loadDashboard({silent:true});toast(isAdapter?'Adapter profile saved.':'Independent case saved.');
    } else if(formId==='adaptation-config-form') {
      const values=Object.fromEntries(new FormData(form));const config=parseStrictJSON(values.config);
      const path=values.kind==='adapter'?'/adapters':values.kind==='case'?'/cases':`/rule-packages/${submitter?.value==='validate'?'validate':'import'}`;
      const key=values.kind==='adapter'?'profile':values.kind==='case'?'case':'package';
      const result=await request(projectPath(path),{method:'POST',body:{[key]:config}});
      if(submitter?.value==='validate'){toast(`Package valid: ${result.rules} rules. Approval remains local.`);}else{modal.close();await loadDashboard({silent:true});toast('Saved. Imported rules remain drafts until reviewed.');}
    } else if(formId==='adapter-apply-form') {
      const values=Object.fromEntries(new FormData(form));const preview=submitter?.value==='preview';
      const result=await request(projectPath(`/adapters/${encodeURIComponent(values.adapter_id)}/apply`),{method:'POST',body:{file_id:values.file_id,preview}});
      if(preview){openModal('Mapping preview',mappingPreview(result.mapping),action('Close','close-modal'));}
      else{state.snapshotId=result.snapshot.id;modal.close();await loadDashboard({silent:true});toast('Mapped revision saved. Prior reviews were re-evaluated.');}
    } else if(formId==='project-form') {
      const name=new FormData(form).get('name').trim();
      const response=await request('/projects',{method:'POST',body:{name}});const project=unwrap(response,'project');modal.close();await loadProjects(project.id);toast('Project created. Load an example or upload a source file.');
    } else if(formId==='upload-form') {
      const file=document.getElementById('source-upload').files[0];
      if(!file)throw Error('Select a source file.');
      if(file.size>10_000_000)throw Error('The source file exceeds the 10 MB upload limit.');
      if(!/\.(json|csv|xlsx|pdf|txt|md)$/i.test(file.name))throw Error('Select a JSON, CSV, XLSX, PDF, TXT or Markdown file.');
      const uploadProjectId=state.projectId;const uploadPath=suffix=>`/projects/${encodeURIComponent(uploadProjectId)}${suffix}`;
      const sourceOnly=document.getElementById('mapping-source').checked;
      const create=document.getElementById('create-snapshot').checked;
      if(sourceOnly&&create)throw Error('Raw mapping sources need an explicit adapter. Turn off automatic snapshot creation.');
      const snapshotTitle=document.getElementById('snapshot-title').value.trim()||file.name;
      const parent=document.getElementById('parent-snapshot').value;
      const buffer=await file.arrayBuffer();let binary='';const bytes=new Uint8Array(buffer);
      for(let i=0;i<bytes.length;i+=8192)binary+=String.fromCharCode(...bytes.subarray(i,i+8192));
      const response=await request(uploadPath('/files'),{method:'POST',body:{filename:file.name,content_base64:btoa(binary),source_only:sourceOnly}});
      const uploaded=unwrap(response,'file');
      if(create) {
        try {const payload={file_id:uploaded.id,title:snapshotTitle};if(parent)payload.parent_id=parent;const result=await request(uploadPath('/snapshots'),{method:'POST',body:payload});state.snapshotId=unwrap(result,'snapshot').id;}
        catch(error){await loadDashboard({silent:true});throw Error(`The source file was saved, but no snapshot was created: ${error.message} You can inspect the saved file in Knowledge.`);}
      }
      modal.close();await loadDashboard({silent:true});toast(create?'Source and engineering snapshot saved.':'Source document saved. It can now support a draft rule.');
    } else if(formId==='snapshot-form') {
      const values=Object.fromEntries(new FormData(form));
      const payload={file_id:values.file_id,title:values.title.trim()};
      if(values.parent_id)payload.parent_id=values.parent_id;
      if(document.getElementById('manual-mapping').checked){
        try{payload.input=snapshotInput(form);}catch(error){if(error instanceof SyntaxError)throw Error('Mapped input must be valid JSON.');throw error;}
        if(!payload.input||typeof payload.input!=='object'||Array.isArray(payload.input))throw Error('Mapped input must be a JSON object.');
        payload.mapping_note=values.mapping_note.trim();if(!payload.mapping_note)throw Error('Record the source mapping or correction justification.');
      }
      const result=await request(projectPath('/snapshots'),{method:'POST',body:payload});state.snapshotId=unwrap(result,'snapshot').id;invalidateSelection();modal.close();await loadDashboard({silent:true});toast('New snapshot saved. The original source is retained.');
    } else if(formId==='rule-form') {
      const values=Object.fromEntries(new FormData(form));let parameters;
      try{parameters=ruleParameters(form);}catch(error){if(error instanceof SyntaxError)throw Error('Rule parameters must be valid JSON.');throw error;}
      if(!parameters||typeof parameters!=='object'||Array.isArray(parameters))throw Error('Rule parameters must be a JSON object.');
      const rule={id:values.id.trim(),version:values.version.trim(),title:values.title.trim(),text:values.text.trim(),locator:values.locator.trim(),task_ids:[values.task],check_ids:values.check_ids.split(',').map(id=>id.trim()).filter(Boolean),status:'draft',authority:values.authority,source_sha256:values.source_sha256,project_id:state.projectId,approved_by:null,approved_at:null,parameters,conditions:ruleConditions(form)};
      await request(projectPath('/rules'),{method:'POST',body:{rule}});modal.close();await loadDashboard({silent:true});toast('Draft rule saved. It cannot authorise a check until approved.');
    } else if(formId==='correction-form') {
      const values=Object.fromEntries(new FormData(form)), id=values.snapshot_id;delete values.snapshot_id;
      Object.assign(values,correctionValues(form));delete values.original_type;delete values.value_type;
      const response=await request(projectPath(`/snapshots/${encodeURIComponent(id)}/corrections`),{method:'POST',body:{corrections:[values]}});state.snapshotId=response.snapshot.id;invalidateSelection();modal.close();await loadDashboard({silent:true});toast('Corrected revision saved. Run the relevant check again.');
    } else if(formId==='policy-form') {
      const daily_limit=Number(new FormData(form).get('daily_limit'));await request(projectPath('/model-policy'),{method:'POST',body:{daily_limit}});state.runtime=await request(projectPath('/runtime'));render();toast('Model limit saved. Explicit task selection remains available.');
    } else if(formId==='issue-form') {
      const values=Object.fromEntries(new FormData(form)), issueId=values.issue_id;delete values.issue_id;
      if(values.action!=='assign')delete values.assignee;if(values.action!=='resolve')delete values.resolution_run_id;
      await request(projectPath(`/issues/${encodeURIComponent(issueId)}`),{method:'POST',body:values});modal.close();await loadDashboard({silent:true});toast('Finding action saved with its evidence trail.');
    } else if(formId==='account-form') {
      const values=Object.fromEntries(new FormData(form));await request('/users',{method:'POST',body:values});state.users=(await request('/users')).items;render();toast('Account created. Grant project membership separately.');
    } else if(formId==='member-form') {
      const values=Object.fromEntries(new FormData(form));await request(projectPath('/members'),{method:'POST',body:values});await loadDashboard({silent:true});toast('Project access updated.');
    } else if(formId==='password-form') {
      const values=Object.fromEntries(new FormData(form));delete values.username;await request('/auth/password',{method:'POST',body:values});setToken('');state.user=null;state.authError='Password changed. Sign in with the new password.';clearTimeout(pollTimer);render();
    } else if(formId==='run-form') await startRun();
    else if(formId==='review-form') {
      const note=new FormData(form).get('note').trim();if(!note)throw Error('Add a review note.');
      const decision=submitter?.value;if(!['approve','request_evidence'].includes(decision))throw Error('Choose a review action.');
      await request(projectPath(`/runs/${encodeURIComponent(state.run.id)}/review`),{method:'POST',body:{action:decision,note}});await selectRun(state.run.id);await loadDashboard({silent:true});toast('Review decision recorded. Technical results were retained.');
    } else if(formId==='search-form') {
      state.search=document.getElementById('knowledge-query').value;state.searchTask=document.getElementById('search-task').value;
      await withBusy(async()=>{const result=await request(projectPath('/retrieve'),{method:'POST',body:{query:state.search,task_id:state.searchTask}});state.retrieval=result.retrieval||result;});
    } else if(formId==='compare-form') await compareVersions();
  } catch(error) {fail(error);}
  finally {if(submitter?.isConnected)submitter.disabled=false;}
});
modal.addEventListener('click',event=>{if(event.target===modal){const rect=modal.getBoundingClientRect();if(event.clientX<rect.left||event.clientX>rect.right||event.clientY<rect.top||event.clientY>rect.bottom)modal.close();}});
initialize();
