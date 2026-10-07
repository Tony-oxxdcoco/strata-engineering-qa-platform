# 结构化合成规则检索契约

本文说明旧版 `dist/` 知识模块：在七条合成规则上做精确任务／规则过滤和小规模词法排序。它不运行 LLM、不使用嵌入或向量索引、不理解自由文本任务、不访问 ETABS、不批准规则或声称结构合规。新版动态规则管理和 BM25 实现见 [知识检索实现](../backend/strata/knowledge.py)。

## 接口

```js
import {
  getDemoKnowledge, validateKnowledgeCorpus, retrieveRules, searchRules,
  KNOWLEDGE_VERSION, KNOWLEDGE_TASKS
} from './knowledge.js';

const corpus = getDemoKnowledge(); // fresh JSON-compatible copy
const checkedCorpus = validateKnowledgeCorpus(corpus); // fresh validated copy, or Error
const context = retrieveRules({ taskId: 'gravity-distribution', corpus });
const matches = searchRules({ query: 'reaction balance', corpus, limit: 5 });
```

两个检索函数均返回 `{ status, reason, rules, citations }`，状态为 `FOUND` 或 `NOT VERIFIED`。阻断时 rules／citations 均为空，不能把部分内容作为完整任务依据。FOUND 只表示检索成功，不表示工程检查通过。

`retrieveRules({ taskId, corpus, ruleIds?, version?, scope?, query? })` 要求精确的已注册任务 ID，可选规则 ID、版本和范围也是精确过滤。过滤后全部必需规则必须仍然有效且可用。query 只影响展示排序，不能删掉必需规则或补出缺失规则。

`searchRules({ query, corpus, taskId?, ruleIds?, version?, scope?, limit? })` 用于浏览，只返回词法匹配，不能授权任务执行。limit 默认 10，范围 1–100；问题最多 500 字符。排序统计字面 token 匹配：规则／检查 ID 权重 8、来源标题 4、位置 2、正文 1，同分按规则 ID 排序。此模块没有已测量的搜索相关性或工程准确率结论。

省略 corpus 时使用内置规则库。导入知识不可用时应明确传空规则库或 null，不能把无效导入替换成默认库。无效检索输入均阻断。`validateKnowledgeCorpus` 抛出可读错误；调用方可保留原始导入用于显示错误，但运行工具前必须经过检索。界面读取器应在解析前拒绝超过 1 MiB 的 JSON。

## 规则库结构与信任边界

```js
{
  schemaVersion: 'knowledge-1.0',
  synthetic: true,
  authority: 'SYNTHETIC',
  purpose: 'controlled-demo',
  version: 'knowledge-demo-1.0.0',
  rules: [{
    id: 'QA-003',
    version: 'DEMO-2026.09',
    authority: 'SYNTHETIC',
    approval: 'demo-approved',
    status: 'active', // or retired
    scope: 'gravity-unfactored-static-excluding-self-weight',
    source: { title: '...', locator: '...', text: '...' },
    checkIds: ['QA-003'],
    taskIds: ['gravity-full', 'gravity-distribution']
  }]
}
```

上例只说明结构；完整精确记录见 `getDemoKnowledge()` 或 `examples/demo-knowledge.json`。最多 100 条记录。未知字段、新规则 ID、不支持版本、范围／适用性改变、缺少或改变原文、声称客户批准都会被拒绝。记录身份和来源正文必须与模块内置定义相同。`demo-approved` 只说明演示包含该定义，调用者不能靠填写标签批准新规则或修改规则。

输入可以移除规则或将其标为 retired，任务因此可能不可用。重复定义即使完全相同也会让规则库被拒绝，不自动选第一条、最新或最相关的一条。缺少或退役的必需规则返回 NOT VERIFIED。空规则列表合法，但不提供任务依据。

来源文字不执行，也不能改变工具名称、参数、因子、容差或结果。要求改变这些内容的导入文本会被精确正文检查拒绝。该检查不是数字签名，也不是通用提示注入解决方案；客户知识导入仍需独立管理的复核和版本流程。

## 注册任务覆盖

| 任务 | 必需规则 ID | 演示检查 ID |
|---|---|---|
| `gravity-full` | `QA-001` 至 `QA-006` | 相同六个 ID |
| `gravity-distribution` | `QA-003` | `QA-003` |
| `gravity-balance` | `QA-005` | `QA-005` |
| `load-combination` | `COMB-001` | `C1`、`C2` |

重力规则使用当前引擎 RULE_VERSION，范围为 `gravity-unfactored-static-excluding-self-weight`；组合规则使用 COMBINATION_VERSION 和 `linear-static-combination-response`。C1／C2 是内置组合案例 ID，同一确定性求和可用于组合工具契约允许的其他明确 ID。检索不批准输入因子，也不扩大分析类型。

## 引用与工作流集成

每条规则保留 `source: {title, locator, text}`，对应引用结构为：

```js
{
  ruleId: 'QA-003', version: 'DEMO-2026.09',
  authority: 'SYNTHETIC', approval: 'demo-approved',
  scope: 'gravity-unfactored-static-excluding-self-weight',
  title: '...', locator: '...', quote: '...'
}
```

quote 是完整精确的 source.text，不由模型生成或改写。界面应把这些字符串作为文本显示。工作流必须取得完整 retrieveRules 依据，单独校验工具请求，并随运行保存规则库／版本和返回引用。工程输入证据仍是独立条件：找到规则不能补齐缺失模型数据或反力依据。
