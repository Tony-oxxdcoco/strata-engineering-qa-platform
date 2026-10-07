export const ENGINE_VERSION = '0.2.0';
export const RULE_VERSION = 'DEMO-2026.09';
export const CASES = ['SDL', 'LIVE'];
export const RULES = [
  {id:'QA-001',name:'模型记录唯一性',category:'数据质量',description:'模型分配按楼层 + 工况唯一，反力按支座 + 工况唯一；记录 ID 也须唯一。',formula:'count(unique keys) = count(records)',requires:'非空模型记录',source:'合成 QA 手册 §1 · 数据唯一性'},
  {id:'QA-002',name:'楼层与荷载工况覆盖',category:'输入完整性',description:'每个独立任务书要求，都有对应的模型分配；不能遗漏或额外增加楼层/工况。',formula:'model keys = brief keys',requires:'独立任务书及完整楼层清单',source:'合成 QA 手册 §2 · 覆盖范围'},
  {id:'QA-003',name:'分层荷载分配',category:'数值核对',description:'逐楼层、逐工况比较模型分配力与任务书的面积 × 荷载强度。总量相同不能替代分层检查。',formula:'Fexpected = Abrief × qbrief',requires:'独立面积、荷载强度、模型分配及其证据',source:'合成 QA 手册 §3 · 分层分配'},
  {id:'QA-004',name:'各工况荷载总量',category:'数值核对',description:'SDL 与 LIVE 分别汇总，不允许跨工况抵消；重复分配阻断总量判断。',formula:'Σ Fmodel ≈ Σ (Abrief × qbrief)',requires:'唯一且完整的荷载分配、独立任务书',source:'合成 QA 手册 §4 · 荷载总量'},
  {id:'QA-005',name:'独立竖向反力核对',category:'数值核对',description:'独立导出反力的向上幅值，逐工况与任务书预期的向下荷载幅值比较。仅附加恒载及活载，无自重与组合。',formula:'Σ Rz,export ≈ Σ (Abrief × qbrief)',requires:'同一范围的反力结果、支座清单、独立任务书',source:'合成 QA 手册 §5 · 独立反力'},
  {id:'QA-006',name:'证据与资料完整性',category:'证据门槛',description:'每个工程数值都必须关联有内容和定位的证据记录，且具备任务书、模型分配表、反力结果、审核说明。',formula:'required evidence ⊆ supplied evidence',requires:'内容非空的证据条目及来源定位',source:'合成 QA 手册 §6 · 证据完整性'},
].map(r=>({...r,version:RULE_VERSION,authority:'SYNTHETIC · 演示规则，未经工程批准',tolerance:'max(1 kN, |期望值| × 1%)'}));
const obj=v=>v!==null&&typeof v==='object'&&!Array.isArray(v);
const str=v=>typeof v==='string'&&v.trim().length>0&&v.length<=2000;
const num=v=>typeof v==='number'&&Number.isFinite(v);
const key=r=>JSON.stringify([r.floorId,r.caseId]);
const label=r=>`${r.floorId} / ${r.caseId}`;
const dup=xs=>[...new Set(xs.filter((v,i)=>xs.indexOf(v)!==i))];
export function validateInput(d){
  if(!obj(d)||d.schemaVersion!=='1.0')throw Error('需要 schemaVersion 为 1.0 的 JSON 对象。');
  if(typeof d.synthetic!=='boolean')throw Error('synthetic 必须明确为 true 或 false。');
  if(!obj(d.project)||!str(d.project.name))throw Error('缺少 project.name。');
  if(!obj(d.units)||!obj(d.scope))throw Error('缺少 units 或 scope 声明。');
  for(const k of ['floors','requirements','assignments','reactions','supports','evidence'])if(!Array.isArray(d[k])||d[k].length>1000)throw Error(`${k} 必须是最多 1000 项的数组。`);
  if(d.floors.length===0)throw Error('楼层清单不能为空。');
  for(const [i,f] of d.floors.entries())if(!obj(f)||!str(f.id)||!num(f.area)||f.area<=0||!str(f.evidenceRef))throw Error(`floors[${i}]：需要 ID、正数面积和 evidenceRef。`);
  if(dup(d.floors.map(f=>f.id)).length)throw Error('楼层 ID 重复，无法建立可靠模型。');
  if(d.supports.some(s=>!str(s))||dup(d.supports).length)throw Error('支座 ID 必须为不重复的非空字符串。');
  for(const [i,e] of d.evidence.entries())if(!obj(e)||!str(e.id)||!str(e.title)||typeof e.locator!=='string'||typeof e.content!=='string')throw Error(`evidence[${i}] 格式错误。`);
  if(dup(d.evidence.map(e=>e.id)).length)throw Error('证据 ID 重复。');
  for(const list of ['requirements','assignments','reactions'])for(const [i,r] of d[list].entries()){
    const field=list==='requirements'?'q':list==='assignments'?'force':'fz';
    if(!obj(r)||!str(r.id)||!str(r.caseId)||!str(r.evidenceRef)||!num(r[field])||r[field]<0||!str(list==='reactions'?r.supportId:r.floorId))throw Error(`${list}[${i}]：字段缺失或数值非法（${field} 需为有限非负数）。`);
  }
  const areas=new Map(d.floors.map(f=>[f.id,f.area]));
  if(d.requirements.some(r=>areas.has(r.floorId)&&areas.get(r.floorId)!==0&&r.q!==0&&areas.get(r.floorId)*r.q===0))throw Error('Numeric multiplication underflow; input cannot be verified.');
  const products=d.requirements.filter(r=>areas.has(r.floorId)).map(r=>areas.get(r.floorId)*r.q);
  for(const values of [products,d.assignments.map(r=>r.force),d.reactions.map(r=>r.fz)])if(values.some(v=>!Number.isFinite(v))||!Number.isFinite(values.reduce((a,b)=>a+b,0)))throw Error('数值计算溢出；无法可靠核验此输入。');
  return d;
}
export function withinTolerance(actual,expected){return Number.isFinite(actual)&&Number.isFinite(expected)&&actual>=expected-Math.max(1,Math.abs(expected)*0.01)&&actual<=expected+Math.max(1,Math.abs(expected)*0.01);}
export function runChecks(input){
  const d=validateInput(input), results=[];
  const evidence=new Map(d.evidence.map(e=>[e.id,e]));
  const evOK=(r,role)=>{const e=evidence.get(r.evidenceRef);return e&&str(e.locator)&&str(e.content)&&(!role||r.evidenceRef===role);};
  const refs=rows=>[...new Set(rows.map(r=>r.evidenceRef))];
  const add=(id,status,summary,details=[],dependencies=[])=>results.push({...RULES.find(r=>r.id===id),status,summary,details,dependencies});
  const supported=d.units.area==='m2'&&d.units.force==='kN'&&d.units.surfaceLoad==='kN/m2';
  const scopeOK=d.scope.basis==='unfactored-static-gravity'&&d.scope.selfWeight==='excluded'&&d.scope.reactionPositive==='upward';
  const unitReason=!supported?'单位未支持：需要 m2 / kN / kN/m2。':!scopeOK?'工况范围不支持：需要未分项静力重力、排除自重、反力向上为正。':null;
  const floorMap=new Map(d.floors.map(f=>[f.id,f]));
  const reqDup=dup(d.requirements.map(key));
  const modelDup=dup(d.assignments.map(key));
  const reactionDup=dup(d.reactions.map(r=>JSON.stringify([r.supportId,r.caseId])));
  const idDup=['requirements','assignments','reactions'].flatMap(name=>dup(d[name].map(r=>r.id)).map(id=>`${name}: ${id}`));
  const uniqueIssues=[...reqDup.map(v=>`任务书重复：${v}`),...modelDup.map(v=>`模型分配重复：${v}`),...reactionDup.map(v=>`反力重复：${v}`),...idDup.map(v=>`记录 ID 重复：${v}`)];
  const uniqueDetails=uniqueIssues.map(message=>({label:message,location:'requirements / assignments / reactions',evidenceRefs:[]}));
  add('QA-001',uniqueIssues.length?'FAIL':d.assignments.length?'PASS':'NOT VERIFIED',uniqueIssues.length?`发现 ${uniqueIssues.length} 处重复键；不自动去重。`:d.assignments.length?'模型键与记录 ID 均唯一。':'尚无模型分配记录。',uniqueDetails);
  const validReq=d.requirements.length>0&&!reqDup.length&&!dup(d.requirements.map(r=>r.id)).length&&d.requirements.every(r=>floorMap.has(r.floorId)&&CASES.includes(r.caseId));
  const completeReq=validReq&&d.floors.every(f=>CASES.every(c=>d.requirements.some(r=>r.floorId===f.id&&r.caseId===c)));
  const baselineEvidence=d.requirements.every(r=>evOK(r,'design-brief'))&&d.floors.every(r=>evOK(r,'design-brief'));
  const baselineReason=unitReason||(!completeReq?'独立任务书不完整、重复或包含未知楼层/工况。':!baselineEvidence?'独立任务书或面积的来源证据缺失。':null);
  const reqKeys=new Set(d.requirements.map(key)), actualKeys=new Set(d.assignments.map(key));
  const missing=[...reqKeys].filter(k=>!actualKeys.has(k)),extra=[...actualKeys].filter(k=>!reqKeys.has(k));
  const coverageDetails=[...missing.map(k=>({label:`遗漏 ${k}`,location:'assignments',evidenceRefs:[]})),...extra.map(k=>({label:`额外 ${k}`,location:'assignments',evidenceRefs:[]}))];
  add('QA-002',!completeReq||!baselineEvidence?'NOT VERIFIED':missing.length||extra.length?'FAIL':'PASS',!completeReq||!baselineEvidence?'需要有证据的完整任务书，才能确定检查范围。':missing.length||extra.length?`遗漏 ${missing.length} 项，额外 ${extra.length} 项。`:`${reqKeys.size} 个楼层 / 工况要求全部覆盖。`,coverageDetails);
  const comparisons=d.requirements.map((r,i)=>{
    const f=floorMap.get(r.floorId),matching=d.assignments.map((a,j)=>({a,j})).filter(x=>key(x.a)===key(r));
    const expected=f&&!unitReason?f.area*r.q:null;
    const reason=baselineReason||(dup(d.assignments.map(r=>r.id)).length?'模型分配 ID 重复。':null)|| (matching.length!==1?'模型对应行缺失或重复。':!evOK(matching[0].a,'model-export')?'模型分配缺少来源证据。':null);
    const actual=matching.length===1?matching[0].a.force:null;
    const status=reason?'NOT VERIFIED':withinTolerance(actual,expected)?'PASS':'FAIL';
    return {label:label(r),expected,actual,unit:'kN',status,reason,formula:unitReason?'单位/工况未支持，不执行数值换算。':f?`${f.area} m² × ${r.q} kN/m² = ${expected} kN`:'缺少面积',tolerance:expected!==null?Math.max(1,expected*.01):null,location:`requirements[${i}]${matching.length===1?` ↔ assignments[${matching[0].j}]`:''}`,evidenceRefs:refs([r,...(f?[f]:[]),...matching.map(x=>x.a)])};
  });
  const distStatus=baselineReason?'NOT VERIFIED':comparisons.some(c=>c.status==='FAIL')?'FAIL':extra.length?'FAIL':comparisons.some(c=>c.status==='NOT VERIFIED')||!comparisons.length?'NOT VERIFIED':'PASS';
  add('QA-003',distStatus,baselineReason|| (distStatus==='PASS'?'各层分配与独立任务书一致。':distStatus==='FAIL'?'存在不符合任务书的分层分配；请逐项查看。':'部分楼层的分配无法确认。'),comparisons,baselineReason?[baselineReason]:[]);
  const assignmentReason=baselineReason||(modelDup.length||dup(d.assignments.map(r=>r.id)).length?'模型分配重复，禁止汇总后判定。':missing.length||extra.length?'模型分配范围不完整或包含额外项。':!d.assignments.every(r=>evOK(r,'model-export'))?'模型分配缺少证据。':null);
  const totals=CASES.map(c=>{
    const rs=d.requirements.filter(r=>r.caseId===c),ms=d.assignments.filter(r=>r.caseId===c);
    const expected=baselineReason?null:rs.reduce((sum,r)=>sum+(floorMap.get(r.floorId)?.area??0)*r.q,0),actual=ms.reduce((sum,r)=>sum+r.force,0);
    return {label:c,expected,actual:assignmentReason?null:actual,unit:'kN',tolerance:expected===null?null:Math.max(1,expected*.01),status:assignmentReason?'NOT VERIFIED':withinTolerance(actual,expected)?'PASS':'FAIL',reason:assignmentReason,formula:baselineReason?'基准未验证，不生成数值结论。':`Σ(面积 × ${c} 荷载强度) = ${expected} kN`,location:`requirements[caseId=${c}] ↔ assignments[caseId=${c}]`,evidenceRefs:refs([...rs,...ms,...d.floors])};
  });
  add('QA-004',assignmentReason?'NOT VERIFIED':totals.some(t=>t.status==='FAIL')?'FAIL':'PASS',assignmentReason|| (totals.some(t=>t.status==='FAIL')?'至少一个工况的总量超出演示容差。':'各工况模型总量与任务书一致。'),totals,assignmentReason?[assignmentReason]:[]);
  const reactionReason=baselineReason||(!d.supports.length?'独立支座清单缺失。':reactionDup.length||dup(d.reactions.map(r=>r.id)).length?'反力记录重复，无法确认总反力。':d.reactions.some(r=>!d.supports.includes(r.supportId)||!CASES.includes(r.caseId))?'反力包含未知支座或工况。':d.supports.some(s=>CASES.some(c=>!d.reactions.some(r=>r.supportId===s&&r.caseId===c)))?'反力未覆盖所有支座和工况。':!d.reactions.every(r=>evOK(r,'reaction-export'))?'反力结果证据缺失。':!evOK({evidenceRef:'support-schedule'})?'支座清单证据缺失。':null);
  const reactionRows=CASES.map(c=>{const rs=d.reactions.filter(r=>r.caseId===c),expected=totals.find(t=>t.label===c).expected,actual=rs.reduce((s,r)=>s+r.fz,0);return {label:c,expected,actual:reactionReason?null:actual,unit:'kN',tolerance:expected===null?null:Math.max(1,expected*.01),status:reactionReason?'NOT VERIFIED':withinTolerance(actual,expected)?'PASS':'FAIL',reason:reactionReason,formula:`Σ Rz(${c}) ↔ Σ Abrief × qbrief`,location:`reactions[caseId=${c}] ↔ requirements[caseId=${c}]`,evidenceRefs:refs([...rs,...d.requirements.filter(r=>r.caseId===c),...d.floors,{evidenceRef:'support-schedule'}])};});
  add('QA-005',reactionReason?'NOT VERIFIED':reactionRows.some(r=>r.status==='FAIL')?'FAIL':'PASS',reactionReason|| (reactionRows.some(r=>r.status==='FAIL')?'独立反力与预期荷载不平衡。':'独立反力与任务书预期荷载一致。'),reactionRows,reactionReason?[reactionReason]:[]);
  const missingEvidence=['design-brief','model-export','reaction-export','support-schedule','review-note'].filter(id=>!evOK({evidenceRef:id}));
  const dangling=['floors','requirements','assignments','reactions'].flatMap(list=>d[list].flatMap((r,i)=>evOK(r,{floors:'design-brief',requirements:'design-brief',assignments:'model-export',reactions:'reaction-export'}[list])?[]:[{label:`${list}[${i}] → ${r.evidenceRef}`,location:`${list}[${i}]`,evidenceRefs:[r.evidenceRef]}]));
  add('QA-006',missingEvidence.length||dangling.length?'NOT VERIFIED':'PASS',missingEvidence.length||dangling.length?`有 ${missingEvidence.length} 类必需资料、${dangling.length} 条数值来源未验证。`:'必需资料及数值来源均有可查看的证据内容。',[...missingEvidence.map(id=>({label:`需补充 ${id}`,location:'evidence',evidenceRefs:[id]})),...dangling]);
  const summary={PASS:0,FAIL:0,'NOT VERIFIED':0};results.forEach(r=>summary[r.status]++);
  return {engineVersion:ENGINE_VERSION,ruleVersion:RULE_VERSION,results,summary,status:summary.FAIL?'FAIL':summary['NOT VERIFIED']?'NOT VERIFIED':'PASS',comparisons};
}
async function hashInput(snapshot){
  const data=new TextEncoder().encode(JSON.stringify(snapshot));
  const hash=await globalThis.crypto.subtle.digest('SHA-256',data);
  return Array.from(new Uint8Array(hash),b=>b.toString(16).padStart(2,'0')).join('');
}
export async function createRun(input){
  const snapshot=JSON.parse(JSON.stringify(input));const result=runChecks(snapshot);
  const inputHash=await hashInput(snapshot);
  return {...result,id:globalThis.crypto.randomUUID(),createdAt:new Date().toISOString(),inputHash,input:snapshot,reviews:[],audit:[{type:'CHECKS_COMPLETED',at:new Date().toISOString(),detail:`${result.results.length} 个规则已执行；输入 SHA-256 ${inputHash}`} ]};
}
// Compare JSON-shaped results without treating Infinity as null or depending on object key order.
function sameValue(actual,expected){
  if(Object.is(actual,expected))return true;
  if(Array.isArray(expected))return Array.isArray(actual)&&actual.length===expected.length&&expected.every((value,i)=>Object.hasOwn(actual,i)&&sameValue(actual[i],value));
  if(!obj(actual)||!obj(expected))return false;
  const keys=Object.keys(expected);
  return Object.keys(actual).length===keys.length&&keys.every(k=>Object.hasOwn(actual,k)&&sameValue(actual[k],expected[k]));
}
function assertRunConsistency(run){
  if(!obj(run))throw Error('运行记录格式无效，请重新运行检查。');
  if(run.engineVersion!==ENGINE_VERSION||run.ruleVersion!==RULE_VERSION)throw Error('引擎或规则版本不匹配，请使用当前版本重新运行检查。');
  if(typeof run.inputHash!=='string'||!/^[a-f0-9]{64}$/.test(run.inputHash))throw Error('运行记录缺少有效的输入 SHA-256。');
  const replay=runChecks(run.input);
  for(const field of ['results','summary','status','comparisons'])if(!sameValue(run[field],replay[field]))throw Error(`运行记录 ${field} 与输入重算结果不一致，请重新运行检查。`);
  const date=v=>str(v)&&Number.isFinite(Date.parse(v));
  if(!str(run.id)||!date(run.createdAt)||!Array.isArray(run.reviews)||!Array.isArray(run.audit))throw Error('运行标识、时间或复核记录格式无效。');
  for(const review of run.reviews){
    if(!obj(review)||!replay.results.some(r=>r.id===review.ruleId)||!str(review.reviewer)||!str(review.note)||!['reviewed','request_evidence'].includes(review.disposition)||!date(review.at))throw Error('人工复核记录格式无效。');
  }
  for(const event of run.audit){
    if(!obj(event)||!['CHECKS_COMPLETED','HUMAN_REVIEW'].includes(event.type)||!date(event.at)||typeof event.detail!=='string'||!event.detail.trim()||(event.note!==undefined&&!str(event.note)))throw Error('审计记录格式无效。');
  }
}
// This detects inconsistent stored records; it does not authenticate a reviewer or sign the record.
export async function verifyRun(run){
  try{
    const snapshot=structuredClone(run);
    assertRunConsistency(snapshot);
    if(await hashInput(snapshot.input)!==snapshot.inputHash)throw Error('输入快照与记录的 SHA-256 不一致，请重新运行检查。');
    return {valid:true,reason:''};
  }catch(error){
    return {valid:false,reason:error instanceof Error?error.message:'运行记录无法验证，请重新运行检查。'};
  }
}
export async function verifiedMarkdownReport(run){
  // Keep the same snapshot across the asynchronous hash check and report generation.
  let snapshot;
  try{snapshot=structuredClone(run);}catch{throw Error('运行记录无法读取，请重新运行检查。');}
  const verification=await verifyRun(snapshot);
  if(!verification.valid)throw Error(verification.reason);
  return markdownReport(snapshot);
}
export function addReview(run,{ruleId,reviewer,note,disposition}){
  if(!run||!run.results.some(r=>r.id===ruleId)||!str(reviewer)||!str(note)||!['reviewed','request_evidence'].includes(disposition))throw Error('请选择有效检查项，并填写复核姓名与意见。');
  const entry={ruleId,reviewer:reviewer.trim(),note:note.trim(),disposition,at:new Date().toISOString()};
  return {...run,reviews:[...run.reviews,entry],audit:[...run.audit,{type:'HUMAN_REVIEW',at:entry.at,detail:`${entry.ruleId} · ${entry.reviewer} · ${disposition}`,note:entry.note}]};
}
export function markdownReport(run){
  if(!run)throw Error('请先运行检查。');
  // Synchronous compatibility API checks replay consistency; use verifiedMarkdownReport for SHA-256 verification too.
  assertRunConsistency(run);
  const safe=v=>String(v??'—').replaceAll('|','\\|').replaceAll('\n',' ');
  const lines=['# Strata 结构工程 QA 报告','',`项目：${safe(run.input.project.name)}`,`运行：${run.id}`,`时间：${run.createdAt}`,`输入 SHA-256：${run.inputHash}`,`引擎：${run.engineVersion} · 规则：${run.ruleVersion}`,'','> 合成规则演示；非澳标验收、非结构安全结论。未接入 LLM 或 CSI API。复核身份为用户自填，非工程签章。','','## 技术结果',`PASS ${run.summary.PASS} / FAIL ${run.summary.FAIL} / NOT VERIFIED ${run.summary['NOT VERIFIED']}`,''];
  for(const r of run.results){lines.push(`### ${r.id} ${r.name} — ${r.status}`,r.summary,`规则来源：${r.source}，${r.version}`,`公式：${r.formula}`,`容差：${r.tolerance}`,'','| 子项 | 期望 | 实际 | 状态/原因 | 计算/容差 | 输入位置 | 证据 ID |','| --- | --- | --- | --- | --- | --- | --- |');for(const x of r.details)lines.push(`| ${safe(x.label)} | ${safe(x.expected)} | ${safe(x.actual)} | ${safe(x.reason||x.status)} | ${safe(x.formula)} / ±${safe(x.tolerance)} kN | ${safe(x.location)} | ${safe((x.evidenceRefs||[]).join(', '))} |`);lines.push('');}
  lines.push('## 证据内容','');for(const e of run.input.evidence)lines.push(`- ${safe(e.id)} — ${safe(e.title)}；定位：${safe(e.locator)}；内容：${safe(e.content)}`);
  lines.push('','## 人工复核','');for(const r of run.reviews)lines.push(`- ${r.at} · ${safe(r.reviewer)} · ${r.ruleId} · ${r.disposition}：${safe(r.note)}`);if(!run.reviews.length)lines.push('尚未人工复核。');
  lines.push('','## 审计记录','');for(const e of run.audit)lines.push(`- ${e.at} · ${e.type} · ${safe(e.detail)}${e.note?' · '+safe(e.note):''}`);
  lines.push('','## 输入快照','', '```json',JSON.stringify(run.input,null,2),'```','');return lines.join('\n');
}
