# 受控本地 QA 工作流契约

本文说明 `dist/` 保留的旧版本地模块。它编排已有确定性重力／组合引擎和合成规则检索，不调用 ETABS、SAFE、模型 API 或网络端点；可运行的数据提供器只有 `controlled-file`，其他提供器明确阻断。新版服务端 Agent 的实现见 [服务端工作流](../backend/strata/workflow.py)。

## 公共接口

```js
import {
  AGENT_VERSION, AGENT_TASKS, AGENT_TOOLS, AGENT_CALL_BUDGET,
  executeAgent, validateModelTaskProposal, agentReport, runAgentValidation,
} from './agent.js';

const run = await executeAgent({
  taskId: 'gravity-full',
  input,                       // existing gravity schema or combination-1.0
  corpus,                      // getDemoKnowledge() when omitted
  dataMode: 'controlled-file',
});
const markdown = await agentReport(run);
```

`AGENT_TASKS` 包含 `{id,title,description,ruleIds}`：

| 任务 ID | 必需规则 ID | 返回发现 |
|---|---|---|
| gravity-full | QA-001 至 QA-006 | 六项重力检查 |
| gravity-distribution | QA-003 | 仅楼层分布检查 |
| gravity-balance | QA-005 | 仅独立竖向反力平衡 |
| load-combination | COMB-001 | 每个给定线性组合一条发现 |

单项重力任务由已注册引擎计算依赖，工作流再选取所需发现。COMB-001 定义计算方法，合法自定义组合 ID 可以使用同一受限计算；样例 C1／C2 不限制方法，也不代表设计因子已经批准。

返回的不可变运行记录包括 `version`、`versions`、`id`、`createdAt`、`taskId`、`task:{id,title}`、`dataMode`、input／corpus 快照、`inputHash`、`corpusHash`、`runHash`、`status`、`summary:{PASS,FAIL,'NOT VERIFIED'}`、`results`、`citations`、`explanation`、`toolTrace`、`callsUsed`、`callBudget`、被拒绝的 `requestFields` 和明确的 `scope`。所有嵌套值冻结，调用后修改原请求不会改变保存记录。发现沿用引擎结果／明细字段，证据阶段记录对应规则 ID。

input／corpus 哈希为所存 JSON 序列化的 SHA-256，属性顺序有影响，JSON 将负零规范化为零。`runHash` 覆盖除自身外的整个运行记录。哈希可检测快照不一致，但不是签名或已认证来源，也不能防止攻击者替换应用。

## 固定编排与轨迹

工具白名单和最大调用次数固定在代码中，调用者不能覆盖，不能注入工具实现或参数。每次运行按以下五步展示：

1. `retrieve_engineering_rules`：取得注册任务完整的必需规则。知识模块按内置合成定义检查来源、范围、版本、批准标签和任务绑定；缺失、退役、修改、冲突或不支持的规则阻断运行。
2. `request_engineering_data`：按引擎结构验证明确标记为合成的输入。只支持 controlled-file；选择 ETABS／SAFE 或任意其他提供器得到 NOT VERIFIED，不自动回退。
3. `run_deterministic_check`：调用一个已注册检查引擎。规则或输入／提供器校验未通过时跳过，不执行计算。
4. `verify_evidence`：保留引擎发现及规则绑定。缺少引用来源可以把 PASS 降为 NOT VERIFIED，不能升级结果。未执行计算时返回明确的 AGENT-GATE NOT VERIFIED。
5. `compose_response`：根据状态、计数、发现、数值和精确规则引用生成固定说明，不做自由生成的工程解释。

每步轨迹为 `{index,tool,status,called,inputs,outputs,sources,errors,durationMs}`。状态为 `ok`、`blocked`、`skipped` 或 `error`；`called:false` 表示工具未运行，耗时为零。检查确认不一致属于正常完成的工具调用，不是软件错误。记录的耗时只是该次本地测量，不是性能基准。调用预算为五次，不重试、不递归、不由模型选择调用链。阻断运行仍核验原因并生成 NOT VERIFIED 说明，实际调用可以少于五次。

非 JSON 请求，例如 NaN、循环或稀疏数组，在执行前抛错，避免有损序列化。通常的 JSON 输入结构错误记录为数据工具错误，返回 NOT VERIFIED，不调用计算。空／缺失／无效规则、未知任务同样阻断；数值引擎范围不支持时仍遵守它自身的 NOT VERIFIED 校验。

## 模型输出边界

`validateModelTaskProposal(proposal)` 只接受四个已注册 ID 之一的 `{taskId}`，返回 `{accepted,taskId,reason}`。未知任务或额外的 `status`、`findings`、`explanation`、`tool`、`args`、数值覆盖字段均拒绝。`executeAgent` 另行拒绝 `taskId,input,corpus,dataMode` 之外的请求字段，避免绕过任务校验直接提交伪造发现。

接入该模块的模型路由必须先通过任务校验，只传入获准 task ID。工程输入、规则库、工具参数和结果仍由本地模块控制。来源文字是数据，不是指令。内置规则明确为 synthetic 和 demo-approved，不是客户批准规范。本旧模块没有实际 LLM 测试，不宣称检索消除幻觉或样例因子满足规范；新版模型评测另见发布记录。

## 报告核验与验证集

`agentReport(run)` 先取一次快照，检查 run／input／corpus 哈希，重跑同一请求，比较技术字段、引用、说明、版本、调用次数和轨迹语义。历史时间值需合法，但新旧执行耗时不要求相同。结果变化、来源变化、旧版本、输入变动或轨迹不一致均拒绝。Markdown 包含全部工程来源、精确规则原文、计算明细、完整工具轨迹和两个快照，标为 DRAFT — NOT ENGINEERING APPROVAL，不伪造工程师复核或签名。

`runAgentValidation()` 执行固定本地验证集，返回：

```text
{generatedAt, summary:{total,matched,mismatched},
 cases:[{id,title,expected,actual,matched,reason}]}
```

十个独立手写预期覆盖正确／失败／缺证据重力案例、正确／失败／缺参考组合、空知识库、ETABS 不可用、未知任务，以及拒绝模型伪造结论后真实组合仍为 FAIL。缺规则／提供器／任务案例还检查未调用确定性计算。这是合成软件验证，不能作为客户资料上的工程准确率。

执行 `node --test tests/agent.test.mjs` 验证工作流、阻断、来源和重放；重力及组合测试分别验证数值方法。
