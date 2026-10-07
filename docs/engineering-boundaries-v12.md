# 计算、适配和检索审查（1.2 开发轮）

这里的规则、输入和预期答案均为自制测试材料。软件验证证明的是实现符合声明的比较契约，不等于结构安全、规范合规或工程师验收。真实客户方法仍需客户提供并批准。

## 九类任务实际边界

| 任务 | 实际计算及所需资料 | 范围与阻断条件 |
| --- | --- | --- |
| `gravity-full` | `dist/engine.js` 的 QA-001…006；楼层、独立面积和压力、模型分配、独立反力、支座清单及来源记录 | 固定 SDL/LIVE、未分项静力、排除自重、反力向上为正；只接受合成资料与合成规则。唯一性、覆盖、分层、总量、反力、证据分别检查。 |
| `gravity-distribution` | 同一计算器的 QA-003，比较模型分配与独立 `area × pressure` | 同上；缺楼层/工况、重复记录或缺来源不能用汇总值掩盖。固定容差 `max(1 kN, 1% × abs(expected))` 是测试契约。 |
| `gravity-balance` | 同一计算器的 QA-005，逐工况比较反力和独立面积压力总量 | 同上；必须完整覆盖独立支座清单，不能用模型分配自证反力。 |
| `load-combination` | `dist/combinations.js` 线性静力 `sum(factor × independent base response)`，独立 reported response | 仅合成资料、kN、线性静力；空组合、未知/嵌套基础工况、缺独立来源、溢出/下溢均不能通过。系数是自制测试系数，不是任何规范系数。 |
| `combination-configuration` | `data_tools.verify_combination_configuration`；显式独立所需基础工况/组合/项/系数、额外项政策、有限非负容差 | 只核对声明配置，不进行响应计算或推断规范组合。声明完整时遗漏为 FAIL；完整性未知时缺项为 NOT VERIFIED。重复项不合并。 |
| `handoff` | `data_tools.verify_handoff`；独立源/目标快照、指定版本、完整一一字段映射、单位、绝对/相对容差 | `abs(actual-expected) <= max(abs_tol, abs(expected)*rel_tol)`；有限量纲兼容转换，保留有符号原值。不是原生 CSI 联调或模型安全验证。工作流另外验证不同原文件及完整来源。 |
| `seismic-configuration` | `data_tools.verify_settings` 的显式 `eq/in/range` | 对批准参数所列设置逐项核对，不推断抗震规范、动力响应或设计等级。需要完整性声明，缺值不补默认。 |
| `mass-source` | 同一 settings 工具，独立声明的质量来源设置 | 不计算质量或推断工程正确性；布尔与数值严格区分；空/缺值不能通过。 |
| `additional-settings` | 同一 settings 工具，显式字段和条件 | 仅已注册比较方式，不接受代码、公式或任意计算。不同工程方法要新增工具及独立验证，不能改提示词代替。 |

`backend/strata/contracts.py` 集中限定注册任务、比较操作、参数、单位和适用条件。输入缺少适用条件时规则不能授权计算；范围外规则不执行。设置工具范围含端点，`true` 与 `1` 不相同。缺少必需规则、规则冲突、旧版/未批准规则、文件完整性损坏均由工作流门禁阻断。

本轮特别补上：不同 `rule.id` 同时覆盖一个必需 check ID 时，`knowledge.check_coverage` 返回 NOT VERIFIED。当前工具没有注册“合并两个参数规则”的行为，不能按检索排名取第一条并静默忽略第二条。多个分别覆盖 QA-001…006 的规则仍正常使用。后续若确需多条补充条款，应在单个经审阅规则包中明确完整参数和引用，或实现并验证明确的聚合工具。

## 可复用适配的边界与改动

实现路径：`backend/strata/adapters.py`、`backend/strata/data_tools.py`；风险回归：`backend/tests/test_engineering_boundaries_v12.py`。

- CSV 只忽略全空行，仍保留原物理行号；部分空值必须通过必填校验。列顺序不影响显式别名映射，未知额外列要明确映射或列入 `ignored_columns`。
- JSON 数值词法保留到确定位置后再转浮点。`1e-999` 不能悄悄变成 `0`；错误指出文件、表指针和字段指针。每条 JSON 映射追溯原 JSON pointer。
- Excel 多表按配置中的精确工作表名选择；原列名不自动 trim。若 trim 后出现同名列，拒绝歧义而不是合并。公式和错误值不能充当已计算工程值。
- Excel 在有界 ZIP 的 worksheet XML 层检查数值下溢/溢出，防止 openpyxl 将非零原文变零。拒绝重复 ZIP entry，避免检查和解析看到不同内容。
- 单位必须明确存在于已实现单位表且量纲一致；未知单位不猜。不同适配配置的别名、单位、base 和来源表隔离。
- 配置可选 `table.unique_by`，指定映射结果里的一个或多个字段指针，只用于 `mode: rows`。重复身份指出首次行和重复行，保留原文件，不合并。未声明身份时不猜哪个字段代表对象；后续计算仍按其数据契约验证重复工程对象。

可选身份约束例子（其余配置保持原格式）：

```json
{
  "source": "Loads",
  "target": "/objects",
  "mode": "rows",
  "unique_by": ["/id", "/caseId"]
}
```

预览通过仍只意味着数据已按明确配置标准化，不能代表工程值被批准。单位关系、正负方向、坐标含义和关联对象语义仍需客户确认；当前不支持的物理变换不能通过改配置伪装支持。

## 检索实验和技术取舍

固定合成数据：`examples/retrieval-evaluation.synthetic.json`；复现：

```sh
.venv/bin/python scripts/evaluate-retrieval.py --output output/retrieval-evaluation-v12.json
```

覆盖项目隔离、批准状态、退休版本更新、同名版本冲突、短/高建筑适用条件、相同数值单位干扰、多个必需引用、纯同义表达和无关内容。条件过滤沿用实际工作流的显式条件门禁；检索函数每次根据当前规则构建词项，因此批准状态和版本变化立即反映，不依赖旧索引。

| 数据集 | BM25 匹配期望 | 全局同义词候选匹配期望 | 候选引入的无依据匹配 |
| --- | --- | --- | --- |
| 开发集 | 9/12 | 11/12 | 1（dead battery → permanent load） |
| 保留集 | 12/12 | 11/12 | 1（dead smartphone → permanent load） |

候选仅添加 `floor/storey`、`weight/mass`、`earthquake/seismic`、`dead/permanent` 的词，不修改生产检索。开发集上纯同义词命中增加，同时出现误匹配；保留集无正例收益且多一项误匹配。生产保留简单 BM25，加上精确必需 check ID、批准和覆盖门禁，没有引入 embeddings、重排序服务或新依赖。

实验记录公开了开发集准备过程：初次 smoke 的三个开发查询含共享词，未暴露同义表达缺口；仅去掉开发查询共享词形成压力案例。候选词表与保留集始终未修改。保留集已经观察，不能用它继续调参并宣称独立测试。后续客户资料到来后，应由客户提供真实查询、规则和独立相关性答案，再冻结新的保留集。

这些比例不是客户检索准确率，更不是工程 QA 正确率。FOUND 表示词项匹配到批准记录，无法证明适用性或工程真值；纯同义表达仍可能漏检。任意全局同义词扩展也不是 RAG 的可靠“升级”。

## 验证与下一步

本轮独立 Decimal 推导验证 handoff 的负数、单位换算和容差端点；数值预期由测试作者给定，未调用被测系统生成答案。存在缺陷时先写触发样例，再修复并运行受影响回归。

运行命令：

```sh
.venv/bin/python -m pytest backend/tests/test_engineering_boundaries_v12.py backend/tests/test_adaptation.py backend/tests/test_data_tools.py backend/tests/test_knowledge.py -q
```

实际结果以发布轮的最终验证日志为准。客户仍需提供：允许的文件与列名/对象身份、量纲和符号定义、批准规则及适用条件、独立参考源、工程容差、实际错误案例和工程师验收人员。不能将 synthetic 标签改为 client 后直接复用固定测试算术作为客户工程方法。
