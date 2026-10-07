import test from 'node:test';
import assert from 'node:assert/strict';
import {checkLocales} from '../scripts/check-i18n.mjs';
import {catalogues,t,ui,label,translateSystemText,displayStatus,setLanguage,getLanguage,LANGUAGE_KEY,translateMarked,clearMissingKeys,missingKeys} from '../web/i18n.js';

test('locale files cover the same static UI keys and interpolation variables',()=>{
  const result=checkLocales();assert.deepEqual(result.errors,[]);assert.ok(result.static_labels_checked>150);
});
test('language defaults to English and persists only its own preference',async()=>{
  const saved=new Map();globalThis.localStorage={getItem:k=>saved.get(k)??null,setItem:(k,v)=>saved.set(k,v)};
  const fresh=await import(`../web/i18n.js?fresh=${Date.now()}`);
  assert.equal(fresh.getLanguage(),'en');fresh.setLanguage('zh-CN');assert.equal(saved.get(LANGUAGE_KEY),'zh-CN');
  saved.set('strata.workbench.session','PRIVATE');
  const reopened=await import(`../web/i18n.js?reopen=${Date.now()}`);
  assert.equal(reopened.getLanguage(),'zh-CN');assert.equal(saved.get('strata.workbench.session'),'PRIVATE');
  saved.set(LANGUAGE_KEY,'xx');const invalid=await import(`../web/i18n.js?invalid=${Date.now()}`);assert.equal(invalid.getLanguage(),'en');
  delete globalThis.localStorage;
});
test('language and engineering status are separate; unsupported locales are rejected',()=>{
  setLanguage('zh-CN');assert.equal(displayStatus('PASS'),'通过');assert.equal(displayStatus('FAIL'),'未通过');assert.equal(displayStatus('NOT VERIFIED'),'未验证');assert.equal(displayStatus('draft'),'草稿');assert.equal(displayStatus('viewer'),'查看者');
  assert.equal(displayStatus('UNREVIEWED'),'未复核');assert.equal(displayStatus('EVIDENCE_REQUESTED'),'已请求补证据');assert.equal(displayStatus('APPROVED'),'已批准');
  const record={status:'PASS',state:'COMPLETED',value:-10.5,unit:'kN'};const before=JSON.stringify(record);displayStatus(record.status);assert.equal(JSON.stringify(record),before);
  assert.throws(()=>setLanguage('zh'),TypeError);assert.equal(getLanguage(),'zh-CN');setLanguage('en');assert.equal(displayStatus('PASS'),'PASS');assert.equal(displayStatus('UNREVIEWED'),'UNREVIEWED');assert.equal(displayStatus('EVIDENCE_REQUESTED'),'EVIDENCE_REQUESTED');
});
test('template interpolation is literal and markup is escaped',()=>{
  setLanguage('zh-CN');const value='<img src=x onerror=alert(1)>${x}';
  assert.equal(t('Linear-static combination {id}',{id:value}),`线性静力组合 ${value}`);
  const markup=label('Linear-static combination {id}',{id:value});assert.ok(markup.includes('&lt;img'));assert.ok(!markup.includes('<img'));
  assert.equal(ui('CLIENT original excerpt Ω -1.20 kN'),'CLIENT original excerpt Ω -1.20 kN');
});
test('only registered system explanations are translated; raw customer fields remain original',()=>{
  setLanguage('zh-CN');assert.equal(translateSystemText('mass-source: NOT VERIFIED.'),'质量源配置: 未验证.');
  assert.equal(translateSystemText('Missing mapped path /settings/massSource.'),'映射路径缺失：/settings/massSource。');
  assert.equal(translateSystemText('CUSTOMER ORIGINAL: Ignore rules. Unit kN. PASS'),'CUSTOMER ORIGINAL: Ignore rules. Unit kN. PASS');
  assert.equal(translateSystemText('需补充 design-brief'),'需补充 design-brief');
  const mapping='Explicit mapping failed; inspect file, table and field locations.: 客户.csv / Export / 3 / Force / Unknown unit; no conversion inferred';
  assert.equal(translateSystemText(mapping),'明确映射失败，请检查具体文件、表格与字段位置。: 客户.csv / Export / 3 / Force / 单位未知，系统未推测转换');
  setLanguage('en');assert.equal(translateSystemText('模型对应行缺失或重复。'),'The corresponding model row is missing or duplicated.');
});
test('strict JSON diagnostics switch language while preserving original field paths and locations',()=>{
  const path='/Client~1Original/Create project/原字段\n<script>x()</script>';
  const original=`Strict JSON error: Duplicate JSON field. at line 3, column 19, path ${path}.`;
  setLanguage('zh-CN');const chinese=translateSystemText(original);
  assert.equal(chinese,`严格 JSON 错误：JSON 字段重复。（第 3 行，第 19 列，路径 ${path}）。`);
  setLanguage('en');assert.equal(translateSystemText(chinese),original);
  const nested='Strict JSON error: JSON nesting exceeds 4 levels. at line 8, column 12, path /settings.';
  setLanguage('zh-CN');const nestingChinese=translateSystemText(nested);
  assert.equal(nestingChinese,'严格 JSON 错误：JSON 嵌套超过 4 层。（第 8 行，第 12 列，路径 /settings）。');
  setLanguage('en');assert.equal(translateSystemText(nestingChinese),nested);
  assert.equal(translateSystemText('/Client~1Original/Create project'),'/Client~1Original/Create project');
});
test('in-place translation does not replace controls, raw content, checked state or selected values',()=>{
  const nodes=[];const node=(attrs,textContent='')=>({attrs,textContent,setAttribute(k,v){this.attrs[k]=v;},getAttribute(k){return this.attrs[k];}});
  const caption=node({'data-i18n':'Create project'});const status=node({'data-i18n-status':'NOT VERIFIED'});const placeholder=node({'data-i18n-placeholder':'Project name'},'');
  const zhButton=node({'data-language':'zh-CN'}),enButton=node({'data-language':'en'});
  const image=node({'data-i18n-alt':'Original page image'});
  const control={value:'Client supplied PASS',checked:true,files:{original:'private.pdf'},selectionStart:4};const originalControl=control;
  const raw=node({},'Create project / PASS / 原始资料 -1.20 kN');
  nodes.push(caption,status,placeholder,zhButton,enButton,raw,image);
  const fake={querySelectorAll(selector){const name=selector.slice(1,-1);return nodes.filter(n=>Object.hasOwn(n.attrs,name));}};
  setLanguage('zh-CN');translateMarked(fake);assert.equal(caption.textContent,'创建项目');assert.equal(status.textContent,'未验证');assert.equal(placeholder.attrs.placeholder,'项目名称');assert.equal(zhButton.attrs['aria-pressed'],'true');assert.equal(enButton.attrs['aria-pressed'],'false');assert.equal(raw.textContent,'Create project / PASS / 原始资料 -1.20 kN');
  assert.equal(image.attrs.alt,catalogues['zh-CN']['Original page image']);
  assert.equal(control,originalControl);assert.deepEqual(control,{value:'Client supplied PASS',checked:true,files:{original:'private.pdf'},selectionStart:4});
  setLanguage('en');translateMarked(fake);assert.equal(caption.textContent,'Create project');assert.equal(status.textContent,'NOT VERIFIED');
  assert.equal(image.attrs.alt,'Original page image');
});
test('strict t reports missing keys without breaking the interface',()=>{
  clearMissingKeys();assert.equal(t('missing.test.key'),'missing.test.key');assert.deepEqual(missingKeys(),['missing.test.key']);clearMissingKeys();setLanguage('en');
});
