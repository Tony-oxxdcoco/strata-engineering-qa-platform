# 合成线性静力组合检查契约

本文记录旧版独立基础受控检查模块。它比较独立提供的组合响应与独立基础工况响应的线性和，不验证结构承载力、设计合理性、AS 1170 因子、完整组合覆盖或真实客户模型，不连接 ETABS／SAFE 或 LLM。重力引擎及其历史独立保留；新版配置完整性检查见 [工具实现](../backend/strata/data_tools.py)。

## 输入

```json
{
  "schemaVersion": "combination-1.0",
  "synthetic": true,
  "project": {"name": "Synthetic linear response fixture", "revision": "COMB-R01"},
  "analysisType": "linear-static",
  "unit": "kN",
  "baseCases": [
    {"id": "SDL", "value": 100, "evidenceRef": "reference-responses"},
    {"id": "LIVE", "value": 50, "evidenceRef": "reference-responses"}
  ],
  "combinations": [
    {
      "id": "C1",
      "terms": [{"caseId": "SDL", "factor": 1.2}, {"caseId": "LIVE", "factor": 1.5}],
      "reportedValue": 195,
      "evidenceRef": "reported-combinations"
    }
  ],
  "evidence": [
    {"id": "reference-responses", "title": "Independent synthetic reference", "locator": "Fixture reference sheet", "content": "SDL = 100 kN; LIVE = 50 kN."},
    {"id": "reported-combinations", "title": "Separate synthetic export", "locator": "Fixture export, C1", "content": "C1 = 195 kN; synthetic factors 1.2 and 1.5."}
  ]
}
```

全部响应必须指同一标量分量、位置、符号约定、修订和单位。这些工程对应关系由样例作者负责，结构本身不能认证。线性静力响应允许有符号数值、正负或零因子；示例因子是合成值，不是规范要求。

每个数组最多 1000 项。ID 为非空、首尾无空格、最多 160 字符的字符串；项目 name／revision 以及 analysis／unit 声明必填。值和因子必须是有限 JSON 数字，拒绝数字字符串、null、NaN、无穷。基础工况和组合 ID 命名空间不得重叠。重复基础工况、组合、证据 ID，或同一组合内重复 case ID 均拒绝，不自动去重。JSON 不能有循环、undefined 或稀疏数组。

引用证据需要非空 title、locator、content。组合报告值不能与基础参考使用同一 evidence ID；这只保证声明上分开，不认证真实性或现实独立性。证据正文展示并保留，不从正文解析重建报告值。基础值、因子和报告值由调用者独立提供。缺参考 ID／记录或空证据让受影响组合返回 NOT VERIFIED；容器或数值字段无效时，在计算前抛出输入错误。

## 计算与三态结果

每个组合采用：

```text
expected = Σ(factor × independent base response)
tolerance = max(1 kN, 0.01 × abs(expected))
PASS iff expected − tolerance ≤ reportedValue ≤ expected + tolerance
```

闭区间包含两侧容差边界，用户不能覆盖固定容差。求和使用补偿以保留抵消过程中的小幅有符号贡献。乘积、中间和、修正量或比较差为非有限数时，返回 NOT VERIFIED；非零乘积下溢为零也相同。即使后续项可能抵消，溢出的中间和仍被阻断。这是有限浮点演示计算，不是任意精度工程算术。

- **PASS**：输入是完整、无歧义、具备证据的合成线性静力案例，报告值在容差内。
- **FAIL**：上述前提成立，但独立提供的报告值超出容差。
- **NOT VERIFIED**：前提缺失，范围／单位／分析不支持，无组合项或无法可靠计算。未知工况和嵌套组合不计算；零因子项仍要求对应基础工况和证据。

非线性、包络和嵌套组合尚未实现。`synthetic: false`、不支持单位或分析类型返回 NOT VERIFIED，不自动转换或回退。没有组合时显式产生 COMB-INPUT NOT VERIFIED，不返回空结果 PASS。汇总优先级为 FAIL → NOT VERIFIED → PASS，因此一个确认不一致不会被其他无法验证项覆盖。

## 导出接口

- `COMBINATION_VERSION`：用于重放校验的实现／规则版本。
- `COMBINATION_SCENARIOS`：`{id,title,note}`，包含 clean、mismatch、missing、unsupported。
- `getCombinationSample(id = 'clean')`：返回新的样例输入，拒绝未知 ID。
- `validateCombinationInput(input)`：结构校验后返回原输入，不修改对象；格式或歧义错误抛出异常。
- `runCombinationChecks(input)`：返回 `{version,status,summary:{PASS,FAIL,'NOT VERIFIED'},results}`。每个组合一条 `{id,name,status,summary,details}`，明细为 `{label,expected,actual,unit,formula,tolerance,reason,location,evidenceRefs}`。不可用预期／容差为 null。公式含符号项和数值代入；不支持单位仍保留声明，不把 N 原值标成 kN，不生成预期或容差。
- `await createCombinationRun(input)`：校验、创建独立 JSON 快照、计算，返回结果和 `{id,createdAt,inputHash,input,reviews:[]}`。inputHash 为 JSON.stringify(inputSnapshot) 的 SHA-256，键顺序有影响，负零规范化为零；需要浏览器 Web Crypto 或 Node.js 20+。
- `await combinationReport(run)`：先取一次快照，重放全部技术字段，核对输入哈希和复核信息，再生成 Markdown。输入、结果或版本不一致即拒绝。报告含公式、来源、完整快照、人工意见和合成范围。下载前必须 await，不接受重力运行记录。

应用可以追加 `{at,reviewer,note,disposition}` 复核记录。at 能解析为日期，reviewer／note 非空；disposition 为 reviewed 或 request_evidence。复核不修改技术结果。未复核报告标记 DRAFT，已复核也不等于工程批准。哈希／重放检查不是数字签名、认证身份或防篡改共享审计存储。

## 独立样例预期与验证

`dist/examples/combination-*.json` 的四份样例使用独立写出的输入，不由检查器生成预期：

| 案例 | 手算预期 | 提供的报告值 | 预期状态 |
|---|---|---|---|
| clean | C1：1.2 × 100 + 1.5 × 50 = 120 + 75 = 195；C2：100 − 50 = 50 | 195、50 | PASS、PASS |
| mismatch | 参考值和因子相同 | 210、50 | FAIL、PASS |
| missing | 缺少 LIVE 基础记录 | 195、50 | NOT VERIFIED、NOT VERIFIED |
| unsupported | 声明非线性分析，线性求和不适用 | 195、50 | NOT VERIFIED、NOT VERIFIED |

`node --test tests/combinations.test.mjs` 验证手算结果、有符号响应、抵消、零／容差边界、来源分离、缺失／重复／无效数据、溢出／下溢及重放报告。这些是软件样例测试，不能替代客户模型准确率或客户验收。
