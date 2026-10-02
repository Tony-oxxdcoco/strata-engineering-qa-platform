import {RULES,ENGINE_VERSION,validateInput,createRun,addReview,verifyRun,verifiedMarkdownReport} from './engine.js';
import {parseControlledCsv,controlledCsvTemplate} from './csv.js';
import {COMBINATION_SCENARIOS,COMBINATION_VERSION,getCombinationSample,validateCombinationInput,createCombinationRun,combinationReport} from './combinations.js';
import {runValidation} from './validation.js';
import {getSample,SCENARIOS} from './samples.js';
const icons={layers:'<path d="m3 7 9-5 9 5-9 5-9-5Zm0 5 9 5 9-5M3 17l9 5 9-5"/>',grid:'<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>',book:'<path d="M12 5C8 2 4 3 2 4v16c3-1 6-1 10 1 4-2 7-2 10-1V4c-3-1-7-2-10 1Zm0 0v16"/>',history:'<path d="M3 11a9 9 0 1 1 2 7M3 4v7h7m2-5v6l4 2"/>',help:'<circle cx="12" cy="12" r="9"/><path d="M9 9a3 3 0 1 1 4 3c-1 .5-1 1-1 2m0 3h.01"/>',building:'<path d="M5 21V3h11v18M3 21h18M9 7h3M9 11h3M9 15h3m4-4h4v10"/>',play:'<path d="m8 4 12 8-12 8Z"/>',upload:'<path d="M12 16V3m-5 5 5-5 5 5M4 15v6h16v-6"/>',download:'<path d="M12 3v13m-5-5 5 5 5-5M4 16v5h16v-5"/>',code:'<path d="m8 6-6 6 6 6m8-12 6 6-6 6m-3-15-2 18"/>'};
const icon=n=>`<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${icons[n]||icons.grid}</svg>`;
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmt=v=>typeof v==='number'&&Number.isFinite(v)?v.toLocaleString('en-AU',{maximumFractionDigits:2}):'—';
const statusClass=s=>s==='PASS'?'pass':s==='FAIL'?'fail':s==='NOT VERIFIED'?'unknown':'pending';
const symbol=s=>s==='PASS'?'✓':s==='FAIL'?'!':'−';
const badge=s=>`<span class="badge ${statusClass(s)}">${s||'待检查'}</span>`;
const storageKey='strata-demo-history-v2';
let history=[];
const views=['workspace','combinations','validation','rules','audit','help'];
const initialView=location.hash.slice(1);
const state={view:views.includes(initialView)?initialView:'workspace',scenario:'issues',input:getSample(),run:null,selected:'QA-003',filter:'ALL',busy:false,combinationScenario:'clean',combinationInput:getCombinationSample('clean'),combinationRun:null,validation:null,historyNotice:''};
let editorMode='gravity';
const root=document.getElementById('app');let toastTimer;
function toast(message){const t=document.getElementById('toast');t.textContent=message;t.classList.add('visible');clearTimeout(toastTimer);toastTimer=setTimeout(()=>t.classList.remove('visible'),4200);}
function persist(){if(!state.run)return;history=[state.run,...history.filter(r=>r.id!==state.run.id)].slice(0,5);try{localStorage.setItem(storageKey,JSON.stringify(history));}catch{toast('浏览器存储不可用；当前结果仍可导出。');}}
function download(name,content,type='application/json'){const u=URL.createObjectURL(new Blob([content],{type}));const a=document.createElement('a');a.href=u;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(u),1000);}
function applyData(data,label='custom'){if(state.busy)throw Error('请等待当前检查完成后再修改输入。');validateInput(data);state.input=structuredClone(data);state.scenario=label;state.run=null;state.filter='ALL';state.selected='QA-003';render();}
async function execute(){if(state.busy)throw Error('检查正在运行。');state.busy=true;render();try{state.run=await createRun(state.input);state.filter='ALL';persist();toast(`${state.run.results.length} 项检查已完成，等待工程师复核。`);return {runId:state.run.id,...state.run.summary};}finally{state.busy=false;render();}}
function header(title,sub,actions=''){return `<div class="page-heading"><div><div class="eyebrow">STRUCTURAL ENGINEERING / QUALITY ASSURANCE</div><h1>${title}</h1><p class="subheading">${sub}</p></div>${actions}</div>`;}
function render(){
 const nav=[['workspace','grid','审查工作台'],['combinations','layers','荷载组合'],['validation','play','验证中心'],['rules','book','规则知识库'],['audit','history','审核记录'],['help','help','演示指南']];
 root.innerHTML=`<div class="shell"><aside class="sidebar"><div class="brand">${icon('layers')}<div>STRATA<small>ENGINEERING INTELLIGENCE</small></div></div><div class="workspace-name">ENGINEERING WORKSPACE</div><nav aria-label="主导航">${nav.map(([id,ic,label])=>`<button class="nav-item ${state.view===id?'active':''}" data-nav="${id}" aria-label="${label}" ${state.view===id?'aria-current="page"':''}>${icon(ic)}<span>${label}</span>${id==='rules'?'<span class="nav-count">6</span>':''}</button>`).join('')}</nav><div class="sidebar-bottom"><div class="sidebar-note"><span class="demo-label">CONTROLLED DEMO / 0.2</span>每一个判断，都有依据。<br>每一次审核，都可回溯。</div><div class="avatar-row"><span class="avatar">ME</span><div>Engineering Lab<br><small style="color:#8191ac">本地浏览器工作区</small></div></div></div></aside><main class="main"><div class="topbar"><div class="crumb">工作区 <span>/</span> 项目 144 <span>/</span> <strong>${nav.find(n=>n[0]===state.view)[2]}</strong></div><div class="top-status"><span><i class="dot"></i>确定性规则引擎</span><span class="monogram">QA</span></div></div><div class="content">${state.view==='workspace'?workspace():state.view==='combinations'?combinationView():state.view==='validation'?validationView():state.view==='rules'?ruleView():state.view==='audit'?auditView():helpView()}<footer class="footer"><span>合成规则演示 · 未接入 LLM / CSI API · 非澳标验收或结构安全结论</span><span>数据仅存于当前浏览器 · ENGINE v${ENGINE_VERSION}</span></footer></div></main></div>`;
 bind();
}
function workspace(){const run=state.run;
 return header('结构工程质量审查','从模型数据到检查结论，每一步都保留证据。',`<div class="heading-actions"><button class="button secondary" id="export-report" ${!run?'disabled':''}>${icon('download')}导出报告</button><button class="button primary" id="run-check" ${state.busy?'disabled':''}>${icon('play')}${state.busy?'正在检查…':'运行检查'}</button></div>`)+`
 <section class="project-strip" aria-label="当前模型"><div class="project-info"><span class="project-icon">${icon('building')}</span><div><strong>${esc(state.input.project.name)} <span class="tiny-label">${esc(state.input.project.revision||'Imported')}</span></strong><small>${state.input.floors.length} 个楼层 · ${state.input.assignments.length} 条荷载分配 · ${state.input.synthetic?'合成样例':'用户导入 / 未认证来源'}</small></div></div><div class="source-select"><label for="scenario">选择演示案例</label><select id="scenario" ${state.busy?'disabled':''}>${state.scenario==='custom'?'<option value="custom">自定义导入数据</option>':''}${SCENARIOS.map(s=>`<option value="${s.id}" ${s.id===state.scenario?'selected':''}>${s.title}</option>`).join('')}</select></div><div class="source-actions"><button class="button secondary" id="import-data" ${state.busy?'disabled':''}>${icon('upload')}导入 JSON / CSV</button><button class="button secondary" id="edit-data" ${state.busy?'disabled':''}>${icon('code')}查看输入</button></div></section>
 ${importProvenance()}<div class="flow" aria-label="受控检查流程">${['输入校验','匹配规则','独立计算','证据核对','生成结果','人工复核'].map((s,i)=>`${i?'<span class="flow-line"></span>':''}<div class="flow-step ${run?i===5?'current':'done':i===0?'current':''}"><span class="step-icon">${run&&i<5?'✓':i+1}</span>${s}</div>`).join('')}</div>
 <section class="stat-grid" aria-label="检查结果汇总">${[['PASS','已验证通过','✓','pass'],['FAIL','需要修正','!','fail'],['NOT VERIFIED','需要补充证据','−','unknown']].map(([s,sub,sign,c])=>`<button class="stat" data-filter="${s}" aria-label="筛选 ${s}"><span class="stat-icon ${c}-bg">${sign}</span><div><div class="stat-name">${s}</div><div class="stat-sub">${sub}</div></div><span class="stat-number">${run?run.summary[s]:'—'}</span></button>`).join('')}</section>
 <div class="work-grid"><div><section class="panel"><div class="panel-head"><h2>检查清单 <span class="count">06</span></h2><small>${run?'已完成 · 待人工复核':'已载入 · 等待检查'}</small></div><div class="filters" role="group" aria-label="结果筛选">${[['ALL','全部检查'],['FAIL','需修正'],['NOT VERIFIED','待验证'],['PASS','已通过']].map(([v,t])=>`<button class="filter ${state.filter===v?'active':''}" data-filter="${v}" aria-pressed="${state.filter===v}">${t}</button>`).join('')}</div>${checkList()}<div class="list-foot">${run?`本次运行 ${run.id.slice(0,8)} · ${new Date(run.createdAt).toLocaleTimeString('zh-CN')}<br>技术结论独立于人工处置；已复核不表示设计已批准。`:'选择样例或导入文件后，点击「运行检查」。'}</div></section>${chart()}</div><section class="panel detail-panel" aria-label="检查详情">${detail()}</section></div>`;
}
function checkList(){const rows=(state.run?.results||RULES).filter(r=>state.filter==='ALL'||r.status===state.filter);return rows.length?rows.map(r=>`<button class="check-item ${state.selected===r.id?'selected':''}" data-rule="${r.id}" aria-pressed="${state.selected===r.id}"><span class="status-symbol ${statusClass(r.status)}-bg">${symbol(r.status)}</span><div><span class="check-meta">${r.id} · ${r.category}</span><span class="check-name">${r.name}</span><span class="check-summary">${r.status?esc(shortSummary(r)):r.requires}</span>${state.run?.reviews.some(x=>x.ruleId===r.id)?'<div class="reviewed-text">已有人工复核记录</div>':''}</div><div class="check-end">${badge(r.status)}<span class="chevron">›</span></div></button>`).join(''):'<div class="empty">此筛选下没有检查项。<br>切换「全部检查」查看完整清单。</div>';}
function shortSummary(r){return r.summary.length>30?r.summary.slice(0,29)+'…':r.summary;}
function chart(){const run=state.run;if(!run)return '';const rows=run.comparisons.filter(r=>r.label.endsWith('/ LIVE'));const max=Math.max(1,...rows.flatMap(r=>[r.expected||0,r.actual||0]));return `<section class="panel lower-panel"><div class="panel-head"><h2>楼层荷载分布</h2><small>LIVE · kN</small></div><div class="load-chart"><div class="chart-legend"><span><i class="legend-mark"></i>独立任务书</span><span><i class="legend-mark actual"></i>模型分配</span></div>${rows.map(r=>`<div class="chart-row"><span>${esc(r.label.split(' / ')[0])}</span><div class="bars"><div class="bar" style="width:${Math.min(100,(r.expected||0)/max*100)}%"></div>${r.status==='NOT VERIFIED'?'<span class="chart-warning">数据未验证</span>':`<div class="bar actual ${r.status==='FAIL'?'different':''}" style="width:${Math.min(100,(r.actual||0)/max*100)}%"></div>`}</div><span class="chart-value">${fmt(r.expected)} / ${r.status==='NOT VERIFIED'?'—':fmt(r.actual)}</span></div>`).join('')}<div class="chart-warning">独立基准 / 模型实际 · 总量相同也可能存在分层错配</div></div></section>`;}
function detail(){const run=state.run,r=run?.results.find(r=>r.id===state.selected)||RULES.find(r=>r.id===state.selected);if(!r)return '';
 const refs=[...new Set(r.details?.flatMap(d=>d.evidenceRefs||[])||[])];
 const selectedEvidence=(refs.length?refs:state.input.evidence.map(e=>e.id));
 return `<div class="detail-head"><div class="row"><span class="eyebrow">CHECK DETAIL / ${r.id}</span>${badge(r.status)}</div><h2>${r.name}</h2><p>${esc(r.summary||r.description)}</p></div><div class="detail-body"><div class="section-label">检查依据</div><div class="formula-box"><code>${esc(r.formula)}</code><p>${r.source} · ${r.version}<br>合成演示规则 · 数值容差 ${esc(r.tolerance)}</p></div>${!run?'<div class="empty">运行检查后，这里会显示计算与证据。</div>':`${renderDetails(r)}<div class="section-label">来源证据 / ${selectedEvidence.length}</div>${selectedEvidence.map(id=>{const e=run.input.evidence.find(x=>x.id===id);return `<details class="source-card"><summary><span class="source-title">${e?'↗':'!'} ${esc(e?.title||id)}</span>${e?'':' · 未提供'}</summary>${e?`<p><code>${esc(e.locator)}</code></p><p>${esc(e.content)}</p>`:'<p>请补充此来源的内容和定位后重新运行。</p>'}</details>`;}).join('')}<form class="review-form" id="review-form"><div class="section-label">人工复核</div><div class="review-fields"><div><label for="reviewer">复核人（自填）</label><input id="reviewer" name="reviewer" placeholder="填写姓名" maxlength="80" required></div><div><label for="disposition">处置</label><select id="disposition" name="disposition"><option value="reviewed">已阅并记录意见</option><option value="request_evidence">要求补充证据</option></select></div></div><label for="review-note">复核意见</label><textarea id="review-note" name="note" placeholder="记录判断、修正建议或待补资料…" maxlength="2000" required></textarea><button class="button subtle" type="submit">保存复核记录</button><p class="review-note">复核不会修改技术结论，也不构成工程设计签核。</p></form>`}</div>`;
}
function renderDetails(r,combination=false){if(r.details.some(d=>Object.hasOwn(d,'expected')))return `<div class="section-label">计算核对 <span style="font-weight:400">/ ${esc(r.details[0]?.unit||'kN')}</span></div><div class="table-scroll"><table class="detail-table"><thead><tr><th>${combination?'组合':'楼层 / 工况'}</th><th>期望</th><th>实际</th><th>结果</th></tr></thead><tbody>${r.details.map(d=>`<tr class="${d.status==='FAIL'?'problem':''}"><td>${esc(d.label)}</td><td>${fmt(d.expected)}</td><td>${d.status==='NOT VERIFIED'?'—':fmt(d.actual)}</td><td>${d.status==='PASS'?'✓':d.status==='FAIL'?'超差':'待验证'}</td></tr>`).join('')}</tbody></table></div><details class="source-card"><summary>展开公式、容差与输入路径</summary>${r.details.map(d=>`<p><strong>${esc(d.label)}</strong> · ${esc(d.formula)}<br>容差 ±${fmt(d.tolerance)} ${esc(d.unit||'kN')}<br><code>${esc(d.location)}</code>${d.reason?'<br>'+esc(d.reason):''}</p>`).join('')}</details><p class="data-note">缺少依据的子项保留为待验证，不纳入通过项。</p>`;
 return r.details.length?`<ul class="plain-list">${r.details.map(d=>`<li>${esc(d.label)}<br><code>${esc(d.location)}</code></li>`).join('')}</ul>`:'<p class="data-note">此项检查未发现违反演示规则的记录。数据来源可在下方展开查看。</p>';
}
function ruleView(){return header('规则知识库','6 项演示规则 · 版本固定 · 与每次检查结果绑定')+`<div class="callout">当前规则由本项目为演示编写，未获客户工程师批准，不包含澳大利亚标准正文。真实规范检索与批准规则库属于下一阶段。</div><div class="rule-grid">${RULES.map(r=>`<article class="panel rule-card"><span class="eyebrow">${r.id} / ${r.category}</span><h2>${r.name}</h2><p>${r.description}</p><code>${esc(r.formula)}</code><p>所需证据：${r.requires}<br>演示容差：${esc(r.tolerance)}<br>来源：${r.source} · ${r.version}</p><span class="tag">合成规则 · 未经工程批准</span></article>`).join('')}</div>`;}
function auditView(){const run=state.run;return header('审核记录','楼层重力检查历史 · 载入及导出前核验输入指纹与重算结果。',`<div class="heading-actions"><button class="button secondary" id="export-json" ${!run?'disabled':''}>${icon('download')}导出完整 JSON</button></div>`)+`<div class="callout">此演示仅保留当前浏览器最近 5 次运行。姓名由使用者填写，不是已验证的工程师身份；本地记录可以被清除或修改，不能作为防篡改审计。</div>${state.historyNotice?`<div class="callout">${esc(state.historyNotice)}</div>`:''}<div class="history-controls">${history.map(r=>`<button class="button ${r.id===run?.id?'subtle':'secondary'}" data-history="${esc(r.id)}" ${state.busy?'disabled':''}>${esc(r.input.project.name)} · ${new Date(r.createdAt).toLocaleTimeString('zh-CN')} · ${r.id.slice(0,8)}</button>`).join('')}</div><section class="panel"><div class="panel-head"><h2>运行与复核事件</h2><small>${run?esc(run.id.slice(0,8)):'未运行'}</small></div>${run?`<div class="audit-entry"><time>输入快照</time><div><strong>${esc(run.input.project.name)} · ${badge(run.status)}</strong><p class="run-meta">SHA-256 ${esc(run.inputHash)}</p></div></div>${run.audit.map(e=>`<div class="audit-entry"><time>${new Date(e.at).toLocaleString('zh-CN')}</time><div><strong>${e.type==='HUMAN_REVIEW'?'人工复核意见':'确定性检查完成'}</strong><p>${esc(e.detail)}</p>${e.note?'<p>'+esc(e.note)+'</p>':''}</div></div>`).join('')}`:'<div class="empty">运行检查后开始记录。</div>'}</section>`;}
function navigate(view){state.view=view;location.hash=view;render();window.scrollTo(0,0);}
function openEditor(mode){
 if(state.busy){toast('请等待当前检查完成。');return;}
 editorMode=mode;
 document.getElementById('input-title').textContent=mode==='combination'?'荷载组合输入 · JSON':'工程输入 · JSON';
 document.getElementById('json-editor').value=JSON.stringify(mode==='combination'?state.combinationInput:state.input,null,2);
 document.getElementById('editor-error').textContent='';
 document.getElementById('input-dialog').showModal();
}
async function boot(){
 let invalid=0;
 try{
  const raw=localStorage.getItem(storageKey)||'[]';
  if(raw.length>6*1048576)throw Error('历史记录过大');
  const saved=JSON.parse(raw);
  if(!Array.isArray(saved))throw Error('历史格式错误');
  for(const run of saved.slice(0,5)){
   const verified=await verifyRun(run);
   if(verified.valid)history.push(run);else invalid++;
  }
 }catch{invalid++;}
 if(invalid)state.historyNotice=`${invalid} 条历史记录不一致或无法读取，已禁止载入旧结论。请用原始输入重新检查。`;
 await execute();
 if(invalid)toast(state.historyNotice);
}
async function loadHistoryRun(id){
 if(state.busy)return;
 const stored=history.find(run=>run.id===id);if(!stored)return;
 state.busy=true;render();
 try{
  const snapshot=structuredClone(stored),check=await verifyRun(snapshot);
  if(!check.valid)throw Error(check.reason);
  state.run=snapshot;state.input=structuredClone(snapshot.input);state.scenario='custom';state.filter='ALL';
  toast('输入指纹与重算结果一致，历史记录已载入。');
 }catch(err){toast(err.message);}
 finally{state.busy=false;render();}
}
async function exportGravity(format){
 try{
  const run=structuredClone(state.run),verification=await verifyRun(run);
  if(!verification.valid)throw Error(verification.reason);
  if(format==='md')download(`Strata-QA-${run.id.slice(0,8)}.md`,await verifiedMarkdownReport(run),'text/markdown;charset=utf-8');
  else download(`Strata-QA-${run.id.slice(0,8)}.json`,JSON.stringify(run,null,2));
 }catch(err){state.run=null;render();toast(err.message);}
}
function importProvenance(){
 const metadata=state.input.importMetadata;
 if(!metadata||metadata.format!=='strata-controlled-csv'||!Array.isArray(metadata.rows))return '';
 const numericRows=metadata.rows.filter(row=>row&&typeof row==='object'&&row.originalUnit);
 return `<details class="panel import-panel"><summary><span class="import-mark">CSV</span><strong>${esc(metadata.filename)}</strong> · ${metadata.rows.length} 条来源记录 <span>查看行号与单位换算 ↓</span></summary><p class="data-note">受控模板导入。原始行保留在输入快照中；来源内容的真实性仍需人工核对。</p><div class="table-scroll provenance-table"><table class="detail-table"><thead><tr><th>CSV 行</th><th>输入位置</th><th>原始值</th><th>标准化值</th></tr></thead><tbody>${numericRows.slice(0,100).map(row=>`<tr><td>${esc(row.row)}</td><td><code>${esc(row.target)}</code></td><td>${esc(row.originalValue)} ${esc(row.originalUnit)}</td><td>${fmt(row.normalizedValue)} ${esc(row.normalizedUnit)}</td></tr>`).join('')}</tbody></table></div>${numericRows.length>100?'<p class="data-note">显示前 100 条数值记录，完整来源见下载输入。</p>':''}</details>`;
}
function applyCombination(input,scenario='custom'){
 if(state.busy)throw Error('请等待当前检查完成。');
 validateCombinationInput(input);
 state.combinationInput=structuredClone(input);state.combinationScenario=scenario;state.combinationRun=null;render();
}
async function executeCombination(){
 if(state.busy)throw Error('检查正在运行。');
 state.busy=true;render();
 try{state.combinationRun=await createCombinationRun(state.combinationInput);toast('组合检查完成，请查看计算及来源。');}
 finally{state.busy=false;render();}
}
function combinationView(){
 const input=state.combinationInput,run=state.combinationRun;
 const selected=COMBINATION_SCENARIOS.find(s=>s.id===state.combinationScenario);
 return header('基础荷载组合','Sprint 1 · 将独立基础工况响应按给定因子组合，再与模型结果核对。',`<div class="heading-actions"><button class="button secondary" id="combo-export" ${!run?'disabled':''}>${icon('download')}导出组合报告</button><button class="button primary" id="combo-run" ${state.busy?'disabled':''}>${icon('play')}${state.busy?'正在检查…':'运行组合检查'}</button></div>`)+`
 <section class="project-strip"><div class="project-info"><span class="project-icon">${icon('layers')}</span><div><strong>${esc(input.project.name)}</strong><small>${input.baseCases.length} 个基础工况 · ${input.combinations.length} 个组合 · ${input.synthetic?'合成样例':'用户导入 / 未认证来源'}</small></div></div><div class="source-select"><label for="combo-scenario">选择组合案例</label><select id="combo-scenario" ${state.busy?'disabled':''}>${state.combinationScenario==='custom'?'<option value="custom">自定义组合输入</option>':''}${COMBINATION_SCENARIOS.map(s=>`<option value="${s.id}" ${state.combinationScenario===s.id?'selected':''}>${esc(s.title)}</option>`).join('')}</select></div><div class="source-actions"><button class="button secondary" id="combo-import" ${state.busy?'disabled':''}>${icon('upload')}导入 JSON</button><button class="button secondary" id="combo-edit" ${state.busy?'disabled':''}>${icon('code')}查看输入</button></div></section>
 <div class="callout">只验证给定线性静力组合的算术结果，不判断组合清单或因子是否符合规范。演示因子并非澳标规定；缺工况不按零处理，包络、非线性和嵌套组合保留为未验证。${selected?.note?`<br>${esc(selected.note)}`:''}</div>
 <div class="combo-layout"><section class="panel"><div class="panel-head"><h2>独立基础工况</h2><small>${esc(input.unit)} · ${esc(input.analysisType)}</small></div><div class="detail-body"><div class="table-scroll"><table class="detail-table"><thead><tr><th>工况</th><th>参考响应</th><th>证据引用</th></tr></thead><tbody>${input.baseCases.map(c=>`<tr><td>${esc(c.id)}</td><td>${fmt(c.value)}</td><td>${esc(c.evidenceRef)}</td></tr>`).join('')}</tbody></table></div><p class="data-note">参考响应与模型组合结果分开提供。这里验证声明的来源引用，不认证原始文件或数值真实性。</p><div class="section-label">待核对组合</div>${input.combinations.map(c=>`<div class="formula-box"><strong>${esc(c.id)}</strong><br><code>${c.terms.map(t=>`${esc(t.factor)} × ${esc(t.caseId)}`).join(' + ')}</code><p>模型报告值：${fmt(c.reportedValue)} ${esc(input.unit)}</p></div>`).join('')}<button class="button secondary" id="combo-template">${icon('download')}下载组合模板</button></div></section>
 <section class="panel"><div class="panel-head"><h2>复算结果</h2>${badge(run?.status)}</div><div class="detail-body">${run?`<div class="compact-stats"><span class="pass-bg">${run.summary.PASS} PASS</span><span class="fail-bg">${run.summary.FAIL} FAIL</span><span class="unknown-bg">${run.summary['NOT VERIFIED']} NOT VERIFIED</span></div>${run.results.map(result=>`<article class="combination-result"><div class="result-heading"><strong>${esc(result.id)} · ${esc(result.name)}</strong>${badge(result.status)}</div><p class="data-note">${esc(result.summary)}</p>${renderDetails(result,true)}</article>`).join('')}<div class="section-label">输入指纹 / ${esc(run.version||COMBINATION_VERSION)}</div><p class="run-meta">${esc(run.inputHash)}</p><form id="combo-review" class="review-form"><div class="section-label">人工复核 · 导出报告保存</div><label for="combo-reviewer">复核人（自填）</label><input id="combo-reviewer" name="reviewer" required maxlength="80" placeholder="填写姓名"><label for="combo-disposition">处置</label><select id="combo-disposition" name="disposition"><option value="reviewed">已阅并记录意见</option><option value="request_evidence">要求补充证据</option></select><label for="combo-note">复核意见</label><textarea id="combo-note" name="note" required maxlength="2000" placeholder="记录核对结果或待补资料…"></textarea><button class="button subtle" type="submit">保存组合复核</button><p class="review-note">已记录 ${run.reviews.length} 条意见。复核不会修改技术结论；本页记录在刷新后清除，请先导出报告。</p></form>`:'<div class="empty">选择案例并运行检查。<br>结果将列出公式、参考值、报告值、容差及未验证原因。</div>'}</div></section></div>
 <section class="panel lower-panel"><div class="panel-head"><h2>组合来源证据</h2><small>独立基准 / 模型报告</small></div><div class="detail-body">${combinationEvidence(input)}</div></section>`;
}
function combinationEvidence(input){
 const refs=[...new Set([...input.baseCases.map(c=>c.evidenceRef),...input.combinations.map(c=>c.evidenceRef)])];
 return refs.map(id=>{const source=input.evidence.find(e=>e.id===id);return `<details class="source-card"><summary>${esc(source?.title||id||'缺少来源引用')}${source?'':' · 未提供'}</summary>${source?`<p><code>${esc(source.locator)}</code></p><p>${esc(source.content)}</p>`:'<p>需要补充来源并重新运行检查。</p>'}</details>`;}).join('');
}
function validationView(){
 const report=state.validation,summary=report?.summary;
 return header('验证中心','用固定预期核对实现；保留错误与未验证两类结果。',`<div class="heading-actions"><button class="button secondary" id="export-validation" ${!report?'disabled':''}>${icon('download')}下载验证记录</button><button class="button primary" id="run-validation">${icon('play')}运行验证案例</button></div>`)+`
 <div class="callout">16 个手写合成案例，预期结果独立固定。此页衡量演示规则实现是否符合预期，不代表真实工程准确率。全部输出 NOT VERIFIED 也无法通过验证。</div>
 ${report?`<section class="validation-stats"><div class="panel metric"><small>预期匹配案例</small><strong>${summary.matched}<span> / ${summary.total}</span></strong><p>${summary.mismatched} 个不匹配案例</p></div><div class="panel metric"><small>错误判为 PASS</small><strong class="${summary.falsePass?'text-fail':''}">${summary.falsePass}</strong><p>预期 FAIL / NOT VERIFIED，却返回 PASS</p></div><div class="panel metric"><small>NOT VERIFIED · 预期 / 实际</small><strong>${summary.expectedNotVerified}<span> / ${summary.actualNotVerified}</span></strong><p>按案例中的检查项计数</p></div></section><section class="panel"><div class="panel-head"><h2>逐案例对照</h2><small>${new Date(report.generatedAt).toLocaleTimeString('zh-CN')} · Engine ${esc(report.engineVersion)}</small></div><div class="validation-rows">${report.cases.map(item=>`<details class="validation-case"><summary><span class="case-id">${item.id}</span><strong>${esc(item.title)}</strong><span class="badge ${item.matched?'pass':'fail'}">${item.matched?'符合预期':'不符合预期'}</span></summary><div class="validation-detail">${typeof item.expected==='string'?`<p>预期：拒绝非法输入 · 实际：${item.actual==='REJECTED'?'已拒绝':'未拒绝'}</p><p class="data-note">${esc(item.error||'')}</p>`:`<table class="detail-table"><thead><tr><th>检查项</th><th>预期</th><th>实际</th></tr></thead><tbody>${Object.entries(item.expected).map(([id,status])=>`<tr><td>${id}</td><td>${badge(status)}</td><td>${badge(item.actual?.[id]||'执行失败')}</td></tr>`).join('')}</tbody></table>${item.error?`<p class="text-fail">${esc(item.error)}</p>`:''}`}${item.numericChecks.map(check=>`<p class="data-note">${esc(check.id)} 独立数值预期：${check.expected.join(' / ')} kN；复算：${check.actual.map(fmt).join(' / ')} kN；输入报告值：${check.reported.map(fmt).join(' / ')} kN · ${check.matched?'一致':'不一致'}</p>`).join('')}</div></details>`).join('')}</div></section><p class="data-note lower-panel">验证范围：6 项楼层重力规则 + 基础线性组合。导入解析、记录一致性等边界另由 Node 自动化测试覆盖。</p>`:'<section class="panel"><div class="empty">点击「运行验证案例」开始。<br>正确、超差、缺证据、未知单位、重复、零值及溢出均有对应预期。</div></section>'}`;
}

function helpView(){return header('演示指南','v0.2 · 文件导入、确定性检查、证据复核与验证。')+`<div class="help-columns"><section class="panel help-card"><h2>5 分钟演示顺序</h2><ol><li>工作台默认展示重复、分配错误及证据缺失。展开失败项的计算与来源。</li><li>切换「总量相同，分配错误」并运行，观察总量通过、分层失败。</li><li>下载受控 CSV 模板，导入后展开行号与单位换算，再运行检查。</li><li>在「荷载组合」检查完整、超差、缺工况和不支持的分析类型。</li><li>打开「验证中心」，运行 16 个案例，比较固定预期与实际结果。</li><li>填写复核意见并导出报告。报告导出前会重新核对输入与计算结果。</li></ol><div class="template-actions"><button class="button secondary" id="download-csv">${icon('download')}CSV 模板</button><button class="button secondary" id="download-template">${icon('download')}JSON 模板</button></div></section><section class="panel help-card"><h2>现在能检查什么</h2><ul><li>楼层重力：重复、覆盖、分层分配、总量、独立反力及来源证据。</li><li>基础组合：独立基础工况 × 给定系数，与单独提供的模型组合结果比较。</li><li>可见验证：逐项预期 / 实际、错误通过数、预期 / 实际未验证数。</li><li>不覆盖：真实 ETABS/SAFE 原生文件、完整组合配置合规、包络与非线性。</li><li>仍未接入：LLM、授权规范检索、CSI API、共享数据库和企业签核。</li></ul></section><section class="panel help-card"><h2>文件与单位</h2><p>楼层工作台接受标准 JSON 或本项目 CSV 模板，单文件最多 1 MB。CSV 支持明确列出的面积、力和面荷载单位，并保留行号及换算记录。未知单位和缺少数值会给出输入错误。</p><p>CSV 是受控契约，不是任意 Excel 或 ETABS 导出文件的自动适配器。模板使用合成数据；组合检查使用单独的 JSON 契约。</p></section><section class="panel help-card"><h2>数据保存与证据边界</h2><p>导入与计算在当前浏览器完成。工作台保留最近 5 次楼层检查；组合运行保留到刷新前，请导出保存。不同用户不会共享导入数据或复核记录。</p><p>历史载入与报告导出会验证输入指纹、版本及重放结果；这能发现不一致，不能认证来源或复核人身份。规则与容差均为演示用途，PASS 不表示结构安全或澳标验收。</p></section></div>`;}

function bind(){
 root.querySelectorAll('[data-nav]').forEach(b=>b.onclick=()=>navigate(b.dataset.nav));
 root.querySelectorAll('[data-filter]').forEach(b=>b.onclick=()=>{state.filter=b.dataset.filter;render();});
 root.querySelectorAll('[data-rule]').forEach(b=>b.onclick=()=>{state.selected=b.dataset.rule;render();});
 root.querySelectorAll('[data-history]').forEach(b=>b.onclick=()=>loadHistoryRun(b.dataset.history));
 const listen=(id,fn)=>{const el=document.getElementById(id);if(el)el.onclick=fn;};
 listen('run-check',()=>execute().catch(e=>toast(e.message)));
 const select=document.getElementById('scenario');if(select)select.onchange=()=>{if(select.value!=='custom'){applyData(getSample(select.value),select.value);toast('样例已载入，请运行检查。');}};
 listen('import-data',()=>document.getElementById('file-input').click());
 listen('edit-data',()=>openEditor('gravity'));
 listen('export-report',()=>exportGravity('md'));
 listen('export-json',()=>exportGravity('json'));
 listen('download-template',()=>download('strata-clean-template.json',JSON.stringify(getSample('clean'),null,2)));
 listen('download-csv',()=>download('strata-controlled-template.csv',controlledCsvTemplate(),'text/csv;charset=utf-8'));
 listen('combo-run',()=>executeCombination().catch(err=>toast(err.message)));
 listen('combo-edit',()=>openEditor('combination'));
 listen('combo-import',()=>document.getElementById('combination-file-input').click());
 listen('combo-template',()=>download('strata-combination-template.json',JSON.stringify(getCombinationSample('clean'),null,2)));
 listen('combo-export',async()=>{try{const run=structuredClone(state.combinationRun);const report=await combinationReport(run);download(`Strata-Combination-${run.id.slice(0,8)}.md`,report,'text/markdown;charset=utf-8');}catch(err){state.combinationRun=null;render();toast(err.message);}});
 listen('run-validation',()=>{state.validation=runValidation();render();toast('验证完成；请查看预期与实际的逐项对照。');});
 listen('export-validation',()=>download('strata-validation.json',JSON.stringify(state.validation,null,2)));
 const comboSelect=document.getElementById('combo-scenario');if(comboSelect)comboSelect.onchange=()=>{if(comboSelect.value!=='custom'){applyCombination(getCombinationSample(comboSelect.value),comboSelect.value);toast('组合样例已载入，请运行组合检查。');}};
 const comboForm=document.getElementById('combo-review');if(comboForm)comboForm.onsubmit=e=>{e.preventDefault();const values=Object.fromEntries(new FormData(comboForm));if(!values.reviewer.trim()||!values.note.trim()){toast('请填写复核人和意见。');return;}state.combinationRun.reviews.push({...values,reviewer:values.reviewer.trim(),note:values.note.trim(),at:new Date().toISOString()});render();toast('组合复核已记录，请导出报告保存。');};
 const form=document.getElementById('review-form');if(form)form.onsubmit=e=>{e.preventDefault();try{const values=Object.fromEntries(new FormData(form));state.run=addReview(state.run,{...values,ruleId:state.selected});persist();render();toast('复核意见已保存；技术结论保持不变。');}catch(err){toast(err.message);}};
}
document.getElementById('file-input').onchange=async e=>{
 const file=e.target.files[0];if(!file)return;
 try{if(file.size>1048576)throw Error('文件超过 1 MB。');const text=await file.text();const data=file.name.toLowerCase().endsWith('.csv')?parseControlledCsv(text,{filename:file.name}):JSON.parse(text);applyData(data);toast('数据已载入，请运行检查。');}catch(err){toast(`导入失败：${err.message}`);}finally{e.target.value='';}
};
document.getElementById('combination-file-input').onchange=async e=>{
 const file=e.target.files[0];if(!file)return;
 try{if(file.size>1048576)throw Error('文件超过 1 MB。');applyCombination(JSON.parse(await file.text()));toast('组合输入已载入，请运行检查。');}catch(err){toast(`导入失败：${err.message}`);}finally{e.target.value='';}
};
document.getElementById('apply-input').onclick=()=>{
 try{const text=document.getElementById('json-editor').value;if(new TextEncoder().encode(text).length>1048576)throw Error('输入超过 1 MB。');const data=JSON.parse(text);if(editorMode==='combination')applyCombination(data);else applyData(data);document.getElementById('input-dialog').close();toast('输入已更新，旧结果已清空，请重新运行检查。');}catch(err){document.getElementById('editor-error').textContent=err.message;}
};
document.getElementById('download-input').onclick=()=>download(editorMode==='combination'?'strata-combination-input.json':'strata-input.json',JSON.stringify(editorMode==='combination'?state.combinationInput:state.input,null,2));
window.addEventListener('hashchange',()=>{const view=location.hash.slice(1);if(views.includes(view)&&state.view!==view){state.view=view;render();}});
render();boot().catch(err=>toast(err.message));
// Progressive enhancement; uses exactly the same application actions as the UI.
const context=document.modelContext;
if(context?.registerTool){const controller=new AbortController();const registrations=[
 {name:'get_qa_run',title:'Read current structural QA run',description:'Return the current deterministic QA results and review count.',inputSchema:{type:'object',properties:{},additionalProperties:false},annotations:{readOnlyHint:true,untrustedContentHint:true},execute(input){if(input&&Object.keys(input).length)throw Error('No arguments expected.');return state.run?{id:state.run.id,status:state.run.status,summary:state.run.summary,results:state.run.results,reviews:state.run.reviews.length}:{status:'not_run'};}},
 {name:'run_qa_sample',title:'Run a synthetic QA case',description:'Load and check one synthetic sample, update the visible workspace, and save its run in this browser.',inputSchema:{type:'object',properties:{scenario:{type:'string',enum:SCENARIOS.map(s=>s.id)}},required:['scenario'],additionalProperties:false},annotations:{readOnlyHint:false,untrustedContentHint:false},async execute(input){if(!input||Object.keys(input).some(k=>k!=='scenario')||!SCENARIOS.some(s=>s.id===input.scenario))throw Error('Unknown sample.');if(state.busy)throw Error('A check is already running.');applyData(getSample(input.scenario),input.scenario);state.view='workspace';return await execute();}}
 ];for(const tool of registrations){try{Promise.resolve(context.registerTool(tool,{signal:controller.signal})).catch(()=>{});}catch{}}window.addEventListener('pagehide',()=>controller.abort(),{once:true});}
