import {runChecks, ENGINE_VERSION} from './engine.js';
import {getSample} from './samples.js';
import {runCombinationChecks, getCombinationSample, COMBINATION_VERSION} from './combinations.js';

// These expected outcomes are hand-written test oracles, never copied from a run.
const P = 'PASS', F = 'FAIL', N = 'NOT VERIFIED';
const gravity = values => Object.fromEntries(values.map((value, i) => [`QA-00${i + 1}`, value]));
const clean = change => { const input = getSample('clean'); change?.(input); return input; };
const caseOf = (id, title, input, expected, expectedValues) => ({id, title, profile:'gravity', input, expected:gravity(expected), expectedValues});

export function validationCases() {
  return [
    caseOf('G01', '完整输入：6 项通过', clean(), [P,P,P,P,P,P], {'QA-004':[8000,4400], 'QA-005':[8000,4400]}),
    caseOf('G02', '重复、错配与缺证据并存', getSample('issues'), [F,P,F,N,P,N]),
    caseOf('G03', '反力证据缺失', getSample('missing'), [P,P,P,P,N,N]),
    caseOf('G04', '总量相同、分层错配', getSample('redistribution'), [P,P,F,P,P,P]),
    caseOf('G05', '未知单位阻断数值结论', clean(d => d.units.force = 'kg'), [P,P,N,N,N,P]),
    caseOf('G06', '独立任务书缺失', clean(d => d.requirements = []), [P,N,N,N,N,P]),
    caseOf('G07', '重复模型行不得先合并', clean(d => d.assignments.push({...d.assignments[0], id:'A7'})), [F,P,N,N,P,P]),
    caseOf('G08', '支座清单来源缺失', clean(d => d.evidence = d.evidence.filter(e => e.id !== 'support-schedule')), [P,P,P,P,N,N]),
    caseOf('G09', '模型变更不重算独立反力', clean(d => d.assignments[0].force = 6000), [P,P,F,F,P,P]),
    caseOf('G10', '零荷载允许独立验证', clean(d => {d.requirements.forEach(r => r.q = 0); d.assignments.forEach(r => r.force = 0); d.reactions.forEach(r => r.fz = 0);}), [P,P,P,P,P,P], {'QA-004':[0,0], 'QA-005':[0,0]}),
    {id:'G11', title:'乘积溢出拒绝执行', profile:'gravity', input:clean(d => d.floors.forEach(f => f.area = 1e308)), expected:'REJECTED'},
    {id:'G12', title:'空数值拒绝执行', profile:'gravity', input:clean(d => d.floors[0].area = null), expected:'REJECTED'},
    {id:'C01', title:'有符号线性组合：195 / 50 kN', profile:'combination', input:getCombinationSample('clean'), expected:{C1:P,C2:P}, expectedValues:{C1:[195],C2:[50]}},
    {id:'C02', title:'组合超差：210 ≠ 195 kN', profile:'combination', input:getCombinationSample('mismatch'), expected:{C1:F,C2:P}},
    {id:'C03', title:'缺基础工况：不得当作零', profile:'combination', input:getCombinationSample('missing'), expected:{C1:N,C2:N}},
    {id:'C04', title:'非线性分析：超出本轮范围', profile:'combination', input:getCombinationSample('unsupported'), expected:{C1:N,C2:N}}
  ];
}

export function runValidation({gravityRunner = runChecks, combinationRunner = runCombinationChecks} = {}) {
  const cases = validationCases().map(item => {
    let actual, output, error = null;
    try {
      output = (item.profile === 'gravity' ? gravityRunner : combinationRunner)(structuredClone(item.input));
      const shapeValid = output && Array.isArray(output.results) && output.results.length > 0
        && output.results.every(result => result && typeof result.id === 'string' && [P,F,N].includes(result.status)
          && Array.isArray(result.details) && result.details.every(detail => detail && typeof detail === 'object'))
        && new Set(output.results.map(result => result.id)).size === output.results.length;
      actual = shapeValid ? Object.fromEntries(output.results.map(result => [result.id, result.status])) : 'INVALID OUTPUT';
      if(!shapeValid)error='检查器返回了无效结构或重复检查 ID。';
    } catch (err) {actual = 'REJECTED'; error = err.message;}
    const expectedKeys = typeof item.expected === 'object' ? Object.keys(item.expected) : [];
    const statusesMatch = typeof item.expected === 'string'
      ? actual === item.expected
      : typeof actual === 'object' && Object.keys(actual).length === expectedKeys.length && expectedKeys.every(id => actual[id] === item.expected[id]);
    const numericChecks = Object.entries(item.expectedValues || {}).map(([id, values]) => {
      const details = Array.isArray(output?.results) ? output.results.find(result => result?.id === id)?.details : null;
      const observed = Array.isArray(details) ? details.map(detail => detail?.expected) : [];
      const reported = Array.isArray(details) ? details.map(detail => detail?.actual) : [];
      const matches = numbers => numbers.length === values.length && values.every((value, i) => Number.isFinite(numbers[i]) && Math.abs(numbers[i] - value) < 1e-9);
      return {id, expected:values, actual:observed, reported, matched:matches(observed) && matches(reported)};
    });
    return {...item, input:undefined, actual, error, numericChecks, matched:statusesMatch && numericChecks.every(check => check.matched)};
  });
  const results = cases.filter(c => typeof c.expected === 'object');
  const matched = cases.filter(c => c.matched).length;
  const expectedNotVerified = results.reduce((total,c) => total + Object.values(c.expected).filter(s => s === N).length, 0);
  const actualNotVerified = results.reduce((total,c) => total + (typeof c.actual === 'object' ? Object.values(c.actual).filter(s => s === N).length : 0), 0);
  const falsePass = results.reduce((total,c) => total + Object.entries(c.expected).filter(([id,status]) => status !== P && c.actual?.[id] === P).length, 0);
  return {
    generatedAt:new Date().toISOString(), engineVersion:ENGINE_VERSION, combinationVersion:COMBINATION_VERSION,
    scope:'Hand-authored synthetic fixtures; not real-project accuracy or engineering approval.',
    summary:{total:cases.length, matched, mismatched:cases.length - matched, expectedNotVerified, actualNotVerified, falsePass},
    cases
  };
}
