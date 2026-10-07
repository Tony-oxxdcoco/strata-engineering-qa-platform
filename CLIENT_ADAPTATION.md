# 客户资料接入指南（STRATA 1.1.0）

这份指南对应当前源码。网页和 API 字段保持英文，团队说明使用中文。`examples/` 下的规则、数据和答案全部是合成测试材料。客户规则不能用示例参数替代；软件中的 Approve 只是有权限账号的审核记录。

## 1. 当前工作方式

原文件 → 明确字段映射 → 新快照 → 适用且已批准的规则 → 注册过的确定性工具 → 证据核验 → PASS / FAIL / NOT VERIFIED → 工程师复核。

资料、规则或工具发生变化时，旧记录保留，但不再作为当前确认使用。基础流程不调用付费 API。可选本地模型只选择任务，不计算数值，不填写缺失字段，不决定工程结论。

| 修改目标 | 对应代码 | 首先运行的验证 |
|---|---|---|
| 复用已有 CSV / XLSX / JSON 的不同列名 | `backend/strata/adapters.py`、`examples/adapter-*.json` | `backend/tests/test_adaptation.py` |
| 新增解析格式 | `backend/strata/data_tools.py: ingest()` | `backend/tests/test_data_tools.py` |
| 调整已支持方法的参数 / 容差 / 条件 | `backend/strata/contracts.py`、规则包 | 适配测试 + 对应数值测试 |
| 新增工程计算方法 | `contracts.py`、`data_tools.py`、`workflow.py`、`model.py` | 工具单元测试 + 完整工作流独立案例 |
| 新增客户案例 | `backend/strata/cases.py`、`adaptation_api.py` 的 `/cases`、`/evaluations` | 案例对照与真实客户验收 |
| 补资料和关联重检 | `evidence.py`、`app.py` 的 `/corrections`、`/resume` | 失效 / 人工审核测试 |

上表给的是文件内函数名。所有新模块仍使用现有 SQLite Resource 存储、项目角色和持久任务队列，没有第二套业务数据库。

## 2. 接入数据：先配置，后映射

先在网页 **Adaptation → Import profile** 注册配置，再用 **Upload source for mapping** 上传原始 CSV / JSON。上传时关闭自动创建快照；通过 **Apply to source → Preview mapping** 检查映射，确认后创建新快照。XLSX 可以正常上传，再应用同格式配置。

配置完整例子见 `examples/adapter-transfer.json` 和 `adapter-mass.json`：

- `id` / `version`：配置不可覆盖。同一 ID 改定义必须用新版本。
- `authority`：合成材料使用 `synthetic`，客户材料使用 `client`；`base.synthetic` 必须分别为 `true` / `false`。
- `format`：`csv`、`xlsx`、`json`。CSV 的 `source` 固定为 `csv`；XLSX 使用准确工作表名；JSON 使用指向对象或对象列表的 JSON Pointer。
- `tables[].mode`：`single` 要求恰好一条记录；`rows` 产生列表。
- `aliases`：只有列出的名称才匹配，区分大小写；同时出现两个别名会报歧义。
- `required` / `type`：必填值不允许为空；支持 `number`、`string`、`boolean`。CSV 布尔值为小写 `true` / `false`，不猜测 0/1。
- `unit`：明确给出单位列、目标单位和输出路径；当前使用 `data_tools.UNITS` 的有限单位表。未知单位、维度不一致、溢出或下溢均报错。不能把单位缺失当成 kN。
- `ignored_columns`：明确允许忽略的列。其他未知列报错。XLSX 只映射配置中指定的工作表；其他工作表仍保存在原文件中，不进入这次检查。
- `base`：显式提供不来自表格的元数据。`configuration_complete: true` 必须有完整导出的依据，不能为了通过检查随意填写。

出错响应包含 `file`、`table`、`row`、`field`、`reason`。失败不会创建半成品快照；已经上传的原文件可继续下载。成功快照保存 `adapter_id`、配置 hash、`provenance` 原值 / 原单位 / 新值 / 位置，原文件 hash 和原字节另存。配置是映射声明，不会自动证明其字段含义正确。

资料必须先经过对应工具的数据结构要求。适配器产出的“可解析快照”不等于工程检查 PASS。禁止映射器执行 Excel 公式、Python 或表达式。

### 真正新增一种文件格式

如果只是现有格式的列名不同，新增配置即可。如果是新格式：

1. 在 `data_tools.ingest()` 增加有字节、记录数、嵌套深度限制的解析分支；返回原始来源定位，禁止执行文件中的代码。
2. 如果需要表格适配，扩展 `adapters.source_tables()` 的明确格式分支和配置格式白名单。不要用模糊猜列名代替配置。
3. 在 `web/app.js` 的上传扩展名白名单、文件选择器中添加该格式。
4. 在 `test_data_tools.py` 和 `test_adaptation.py` 加入正常、损坏、缺字段、未知单位的独立样本。
5. 检查全量回归和导出来源记录，确认旧格式行为保留。

扫描 PDF 目前只标记 NEEDS_OCR；没有实现 OCR。需要 OCR 时应另建提取和人工确认流程，不能把识别文本直接当工程数值。

## 3. 接入规则：包可迁移，批准不可迁移

格式见 `examples/rule-package.synthetic.json`。客户接入时使用 `material_type: client`，每条规则 `authority: client`，保留合法可用的原标准 / 客户内部文件。包中的 `sources` 提供文件名、SHA-256、base64 原内容；也可以引用本项目已上传的准确 hash。

网页 **Adaptation → Validate / import package** 先校验，再导入。API 分别为：

```text
POST /api/v1/projects/{project_id}/rule-packages/validate
POST /api/v1/projects/{project_id}/rule-packages/import
GET  /api/v1/projects/{project_id}/rule-packages/export?material_type=client
```

POST 请求体为 `{"package": <package object>}`。包上限 50 条规则、20 个源文件、原始内容合计 10 MB；整个 HTTP 请求还有 14 MB 限制。源文件和规则全量预检后才写入数据库。引用必须是原文件中可核对的准确文本。导入始终重置为 draft，不信任包内 approved_by / approved_at。reviewer 在 **Knowledge** 中逐条批准；同一规则 ID 的旧批准版本会退役。

`contracts.executable_rule()` 集中限制任务、检查 ID、参数、条件和单位。允许：

- 组合配置：明确组合、基础工况、因子、额外项策略、`factor_tolerance`；
- 交接比较：明确两侧 revision、字段映射、单位、绝对 / 相对容差；
- 配置检查：`eq`、`in`、含上下界的 `range`，布尔值与数字不同；
- `conditions`：同样只用 `eq` / `in` / `range` 表达适用条件。条件未知不能授权执行；条件为 false 的规则被排除。

未知字段、任意公式和代码被拒绝。既有 gravity 和基础 load-combination 算术工具继续限定为合成配置，不能仅把 authority 改成 client 就用于真实工程。

参数调整不改提示词：新建规则版本 → 改参数 → 加入独立预期案例 → 校验 → reviewer 批准 → 重新运行受影响检查。不能声称一个自行填写的容差来自工程规范。

## 4. 新增计算工具

先取得客户定义的工程方法、输入、单位、适用范围和独立算例，再实现工具。

1. 在 `data_tools.py` 新增纯确定性函数，或在隔离 Node bridge 中增加固定注册工具；验证有限数值、单位、缺字段和支持范围。
2. 在 `contracts.py` 注册任务 / check IDs / 严格参数契约，不允许输入提供代码。工程方法和参数解释必须写清。
3. 在 `workflow.py` 增加固定工具分支、结果完整性检查；必要时更新 `TOOL_FINGERPRINT` 文件清单。新增计算依赖也要进入该清单。
4. 在 `model.py` 的任务白名单和 `web/app.js` 增加任务选项。模型只做意图路由，显式选择任务仍可运行。
5. 工具单元测试覆盖正常、边界、错误、缺资料、溢出和单位；用工程师独立计算的答案加入案例。通过后才能提供配置入口。

现有缓存键包含输入、目标、规则和工具指纹；新代码不能绕开它。旧结果和旧确认应保留，并显示已失效。

## 5. 加入客户案例和批量评测

先上传真实资料、生成快照、注册对应规则版本。通过 `POST /cases` 注册 `strata-case/1` 对象，示例见 `examples/case-suite.synthetic.json` 中的独立预期内容；网页 **Register case** 给出结构模板和快照 ID。

每个案例至少包括：案例 ID / 版本、显式 client / synthetic 类型、任务、输入快照、可选目标快照、固定规则 ID / 版本、预期总体状态、逐项状态、独立答案作者及依据。资料的原文件保存在快照关联的 file 记录中。客户案例的输入须明确 `synthetic: false`。

`truth.independent: true` 是作者声明，不是系统自动认证。真正答案必须来自客户工程师、独立计算或审阅过的工程依据。禁止运行被测系统后把输出直接写入 expected。

`expected.findings[].key` 形如 `HANDOFF` 或 `HANDOFF/vertical-transfer`。数值断言使用 `numbers` 中的 `path`、`value`、`absolute_tolerance`、`relative_tolerance`。`expected.complete: true` 会报告额外的非通过项；新增的 PASS 信息项允许保留。路径要求见 `cases.py: flattened()` / `compare()`。

```text
POST /api/v1/projects/{project_id}/evaluations
{"case_ids": ["case resource ID", "another case resource ID"]}

GET /api/v1/projects/{project_id}/evaluations/{evaluation_id}
GET /api/v1/projects/{project_id}/evaluations/{evaluation_id}/report
```

一批最多 20 条，受原项目队列上限约束。添加案例不用修改评测器；每批保存预期答案副本和 hash，实际执行固定批准版本，后台照常可恢复。

显示总体错误通过案例数、逐项漏检 / 误报 / 错误通过 / 证据不足 / 数值偏差 / 缺项。父项与子项各自对照，逐项计数可能包含同一问题的父子记录；不要将它当成工程缺陷个数。队列未完成时仅统计已完成案例。

评测针对案例固定输入，忽略“工作台后来选了其他活动快照”这一显示过期原因；规则退役、工具变更、原文件损坏和执行失败仍使案例无效。这不改变工作台人工确认必须针对当前输入的要求。

## 6. 运行命令

```sh
npm run setup:dev
npm run doctor
npm test
.venv/bin/python -m pytest backend/tests tests/test_backup.py -q
npm run check
.venv/bin/python scripts/evaluate-system.py --output output/system-evaluation.json
npm run demo:workflow
```

Windows 的 Python 路径替换为 `.venv\Scripts\python.exe`。Windows 命令仅提供，当前发行验证环境为 macOS，不能称作已测试。

默认 demo 使用隔离临时数据库，不改你已有项目，输出 `output/adaptation-demo/`，结束后临时数据库删除。保留演示项目供网页查看：先启动服务器和创建账号，再运行 `npm run demo:workflow -- --url http://127.0.0.1:4180`，按提示输入本地账号密码。该模式用真实 HTTP / 队列，并新建一个标注 SYNTHETIC 的项目，不发送到云端。

客户材料到来后，优先确认字段和单位 → 做一个映射配置 → 一条批准规则 → 三个独立 PASS / FAIL / NOT VERIFIED 案例 → 客户工程师复核。软件评测通过不能替代这一步。
