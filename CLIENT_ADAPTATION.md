# 客户资料接入指南（STRATA 1.4.0）

接入顺序是：原资料 → 明确映射与单位 → 数据快照 → 适用且已批准的规则 → 已注册的确定性工具 → 证据核验 → 工程师复核。基础流程不用付费 API，本地模型可选。`examples/` 中的工程规则、数据和预期答案都是合成测试材料，不能直接充当客户批准内容。

本文对应当前代码。客户批准字段含义、规则和预期答案后，优先修改配置；新增工程方法必须实现并验证计算工具，不能只修改提示词。

## 1. 从哪里修改

| 目标 | 实际代码／配置 | 针对性验证 |
|---|---|---|
| CSV／XLSX／JSON 列名、类型和单位映射 | `backend/strata/adapters.py`、`backend/strata/adaptation_api.py`、`web/editors.js`；`examples/adapter-*.json` | `backend/tests/test_adaptation.py`、`backend/tests/test_engineering_boundaries_v12.py` |
| 新增文件解析格式 | `backend/strata/data_tools.py` 的 `ingest()`；适配时另改 `adapters.source_tables()` | `backend/tests/test_data_tools.py`，新格式的边界样本 |
| 已支持方法的参数、容差与适用条件 | `backend/strata/contracts.py`；客户规则版本／规则包；`web/editors.js` | 参数契约、对应工具、规则失效与完整工作流 |
| 新计算工具 | `backend/strata/contracts.py`、`backend/strata/data_tools.py`／`dist/` 注册工具、`backend/strata/workflow.py`、`backend/strata/model.py` | 独立数值答案、异常边界与端到端案例 |
| 客户案例／批量对照 | `backend/strata/cases.py`、`backend/strata/adaptation_api.py`、`web/editors.js` | 固定输入和规则、独立预期、评测差异分类 |
| 扫描页校对及来源链 | `backend/strata/ocr.py`、`backend/strata/ocr_api.py`、`backend/strata/provenance.py`、`web/ocr-ui.js` | `backend/tests/test_ocr_v12.py`、`backend/tests/test_source_binding_security.py` |
| CSI 只读接口 | `backend/strata/connector.py`、`backend/strata/app.py` 的 `connector_import()` | `backend/tests/test_connector_network.py`、`backend/tests/test_connector_import.py`，客户环境另做真实联调 |
| 界面与报告文案 | `web/locales/en.js`、`web/locales/zh-CN.js`、`web/i18n.js`；`backend/strata/locales/` | `npm run check:i18n`，两种语言下的实际操作 |

沿用现有项目权限、SQLite Resource 存储、原文件和持久队列，不需要新增业务数据库。路径均相对仓库根目录。

本轮全新配置接入实测包：`examples/client-intake-v13/`，接入方法与边界见 `docs/client-intake-v13.md`，最小收资料清单见 `docs/INPUT_REQUIREMENTS.md`。三种独立案例在三份规则参数上复用，不写成客户工程准确率。

## 2. 已支持格式：建立适配配置

在 **Data adaptation → Upload source for mapping** 上传原文件，进入 **Create adapter** 检查存储来源、工作表、列名和原始样本。为每个字段填写明确目标路径、类型、必填项、别名和单位，再保存版本。也可以 **Import profile** 导入经过审核的 JSON 配置；导出的配置可在其他项目复用，原文件和应用结果仍按项目隔离。

点击 **Apply to source → Preview mapping** 检查映射结果；确认后 **Create snapshot**。预览不创建快照，失败保留原文件，响应指明文件、表、行、字段和原因。未知单位、歧义别名或非法数值不会通过默认值掩盖。

配置参考 `examples/adapter-transfer.json`、`examples/adapter-mass.json`：

- `id`／`version` 固定配置身份。同一版本不可覆盖，改变定义要新建版本。
- `authority` 是 `synthetic` 或 `client`；对应 `base.synthetic` 必须明确为 `true` 或 `false`。设置 client 不能替代客户批准。
- `format` 是 `csv`、`xlsx`、`json`。CSV 使用 `source: csv`；XLSX 使用准确工作表名；JSON 使用明确 JSON Pointer。JSON 来源检查需要先填写想检查的表路径。
- `tables[].mode` 的 `single` 要求一条记录，`rows` 产生列表。列顺序可以变化；字段只按声明的别名匹配，区分大小写，同时出现两个别名会报歧义。
- `required`／`type` 明确是否允许缺值、使用 number／string／boolean。CSV 布尔值使用小写 `true`／`false`，不猜测 0/1。原始数值文本与标准化数值分别保留。
- `unit` 明确单位来源列、输出单位和路径；转换只使用 `data_tools.UNITS` 的有限单位表。未知单位、维度不兼容、非有限数值、溢出或下溢被拒绝。
- `ignored_columns` 明确允许忽略的额外列。未声明的列报错；未选中的 XLSX 工作表保留在原文件中，不会自动分配。物理空行可跳过，实际来源行号保留。
- `unique_by` 可为 `rows` 指定已映射字段路径组成的唯一键。重复身份明确报错，不会合并。同名对象是否允许、外键是否存在仍需由具体数据契约与工具检查，不能依赖自动猜测。
- `base` 记录明确常量，例如 revision。`configuration_complete: true` 必须有独立资料支持，不能为了获得 PASS 随意勾选。

成功快照保存配置身份与 hash、原文件 hash、原值／原单位／标准化值和来源位置。原字节独立保留。可解析快照仍可能缺少工程检查需要的数据；字段映射不执行 Excel 公式、Python 或任意表达式。

**Create snapshot** 还支持明确类型的手工字段表单，必须填写映射依据。**Sources & revisions → Inspect input → Correct a field** 要求原值、新值、类型、来源位置和理由，并创建后继快照；旧快照不覆盖。不要把手工映射当成缺证据时的自动补值渠道。

### 新增文件格式

现有格式仅列名不同，新增配置即可。确实需要新格式时：

1. 在 `data_tools.ingest()` 增加受限解析，设置字节、记录数、嵌套／工作表等边界，拒绝活动内容，返回明确来源位置。
2. 需要表格映射时，扩展 `adapters.source_tables()` 及格式白名单，保留原值和原单位；禁止模糊推测字段含义。
3. 更新 `web/app.js` 上传白名单及 `web/editors.js` 的格式选项，同步两个语言文件。
4. 加入正常、损坏、空数据、重复身份、歧义别名、错误单位和来源追溯测试；独立建立预期，不复用被测输出作为答案。
5. 检查旧格式、导出和来源 hash 行为。新格式未完成验证前，不在界面声明支持。

CSV／XLSX／JSON 的实际限制以解析器和配置契约为准，不承诺支持所有供应商导出。PDF 文本提取不等于结构化表格解析，也不会自动识别所有工程字段。

## 3. 扫描 PDF：先校对，再引用

可选 OCR 使用 macOS Vision；需要 macOS、`swift`、`pdftoppm`，并设置 `STRATA_OCR_ENABLED=1`。Windows／Linux 尚未接入 OCR 提供者。原 PDF、渲染页图、识别文本、文本位置、更正和确认记录分别保留。

**Rules & evidence → Scanned page review** 中选择单页识别，状态为 PENDING_REVIEW。reviewer 必须逐项核对数字、负号、小数点、单位和表格列对应关系，填写更正及理由后确认。确认生成可引用的文本文件；之后仍需明确映射，系统不会把 OCR 表格自动变成工程数据。

未经确认的扫描页或页图不能直接生成工程快照。本轮一张自制测试页中小数和负号被识别，但 `kN` 识别错误；即使 OCR 置信分数高也不能跳过核对。手工转录同样需要获授权的原来源和核对依据。

接入其他 OCR 提供者时，应延续 `backend/strata/ocr_api.py` 的确认状态、页图和原 PDF hash 绑定，延续 `backend/strata/provenance.py` 对来源链的核验。不能用换引擎或改提示词绕过人工确认。

## 4. 接入规则：批准状态不能随包迁移

规则包格式见 `examples/rule-package.synthetic.json`。客户包使用 `material_type: client`，每条规则使用 `authority: client`，并附获授权的规范／内部 QA 文件。包内 `sources` 携带名称、SHA-256 和 base64 原内容，或引用本项目已有的准确来源 hash。

网页 **Data adaptation → Validate / import package** 可选择配置文件，先校验再导入。API：

```text
POST /api/v1/projects/{project_id}/rule-packages/validate
POST /api/v1/projects/{project_id}/rule-packages/import
GET  /api/v1/projects/{project_id}/rule-packages/export?material_type=client
```

POST 请求体为 `{"package": <package object>}`。包受规则数、源文件数、字节量和整体请求限制；具体上限见 `backend/strata/adaptation_api.py`。导入先全量预检，再保存；准确引用必须能在来源文本中核对。结构化 `Page N` 定位会核对对应页；自由格式工作表／单元格 locator 仍需 reviewer 核对，不能当作程序已验证坐标。批准者／批准时间不会迁移，导入总是 draft，由 reviewer 在 **Rules & evidence** 批准。同一规则 ID 的旧批准版本退役。

单条规则也可用 **Add rule** 图形表单配置参数与适用条件。`contracts.executable_rule()` 限制为已实现方法：组合配置的工况／因子／额外项策略／容差，交接的两侧 revision／字段路径／单位／绝对相对容差，以及配置项 `eq`／`in`／`range`。适用条件也只能使用固定比较方式；条件未知不得授权执行，条件为 false 的规则不适用。

未知参数、任意公式和代码被拒绝。既有重力算术和基础 load-combination 方法仍限定合成配置，不能仅将 authority 改成 client 就用于真实工程。

调整参数的流程：新建规则版本 → 修改明确参数／条件 → 加入独立边界案例 → 校验 → reviewer 批准 → 重跑受影响任务。引用缺失、规则冲突或未知适用条件应进入 NOT VERIFIED。BM25 与精确 ID 用于检索，检索相似度不能成为工程批准依据。

## 5. 新增确定性计算工具

先取得客户确认的方法、输入要求、单位、适用范围和独立算例，再写工具。

1. 在 `backend/strata/data_tools.py` 增加纯确定性函数，或扩展隔离 Node bridge 中的固定工具。明确验证缺字段、有限数值、单位、对象关联与支持范围。
2. 在 `backend/strata/contracts.py` 注册任务、check IDs 和严格参数契约，不允许规则输入执行代码。写清工程方法与拒绝范围。
3. 在 `backend/strata/workflow.py` 添加固定调用分支、证据要求和结果完整性核验；将新增计算依赖加入 `TOOL_FINGERPRINT`，避免旧缓存复用。
4. 更新 `backend/strata/model.py` 任务白名单、`web/app.js` 任务入口及两个语言文件。手动选择任务始终可用，模型不能改工程数值和判定。
5. 用独立推导、不同实现或数学不变量验证软件计算；覆盖正常、边界、重复记录、符号／单位错误、缺资料、溢出和空集合，再加入完整工作流案例。

软件验证仍不等于工程师验收。缓存包含输入、目标、规则和工具身份；发布结果前再次检查权限、资料及规则有效性。新功能必须保留历史结果、旧确认和当前失效原因。

## 6. 独立案例与批量评测

先生成快照、批准规则，再用 **Data adaptation → Register case** 填写图形表单：案例 ID／版本、client 或 synthetic、任务、输入与交接目标、固定规则版本、总体预期、逐项预期、数值容差、独立答案作者和依据。

高级格式是 `strata-case/1`，参考 `examples/case-suite.synthetic.json`。客户输入必须明确 `synthetic: false`。`truth.independent: true` 只是作者声明；真正答案需来自客户工程师、独立计算或审核过的依据，不能直接复制系统输出。

逐项 key 例如 `HANDOFF`、`HANDOFF/vertical-transfer`；数值断言使用 `numbers` 的 `path`、`value`、`absolute_tolerance`、`relative_tolerance`。路径定义见 `cases.flattened()`／`compare()`。`expected.complete: true` 会报告意外的非通过项。

```text
POST /api/v1/projects/{project_id}/evaluations
{"case_ids": ["case resource ID", "another case resource ID"]}

GET /api/v1/projects/{project_id}/evaluations/{evaluation_id}
GET /api/v1/projects/{project_id}/evaluations/{evaluation_id}/report
```

每批最多 20 条，受项目队列限制。系统保存独立预期副本与 hash，固定批准规则版本，添加客户案例通常不用修改评测程序。界面显示总体错误通过、逐项漏检／误报／错误通过／证据不足／数值偏差／缺项。

父项和子项分别对照，不能把逐项计数当作独立工程缺陷个数。未完成批次只统计已完成案例。评测针对固定输入，工作台另选活动快照不会改其答案；来源损坏、规则退役、工具变化和运行失败仍会使结果无效。

检索或模型调参时分开发集和保留集，保留答案与版本来源。本轮旧 24 题模型保留集已经再次观察，后续不得将同一题集当成新的独立测试集。

## 7. CSI、双语与验证命令

CSI 接入是部署者配置的只读接口，界面仅在连接器启用时显示导入。契约见 [docs/csi-connector-contract.md](docs/csi-connector-contract.md)，模拟服务为 `scripts/csi-mock-server.py`。身份、revision、profile、版本、单位、时间与 hash 都需匹配；相同身份和内容的重复响应复用旧来源，不造成重复快照和旧确认失效。模拟验证不能称为真实 ETABS／SAFE 联调，也不能把 Windows／许可依赖放进 Linux 应用容器。

新增界面文案放入 `web/locales/en.js`、`web/locales/zh-CN.js`；HTML 报告放入 `backend/strata/locales/`。英文默认，界面偏好键为 `strata.workbench.language`。内部状态和 API 数据不改，客户原文不翻译。报告接口使用 `language=en` 或 `language=zh-CN`，例如：

```text
GET /api/v1/projects/{project_id}/runs/{run_id}/report?format=html&language=zh-CN
```

开发环境运行：

```sh
npm run setup:dev
npm run doctor
npm test
npm run check
npm run check:i18n
npm run validate
.venv/bin/python -m pytest backend/tests tests -q
.venv/bin/python scripts/evaluate-system.py --output output/system-evaluation.json
.venv/bin/python scripts/evaluate-retrieval.py --output output/retrieval-evaluation.json
npm run demo:workflow
```

Windows 将 Python 路径替换为 `.venv\Scripts\python.exe`，平台未实测。独立运行 Python 测试时需能找到 Node，必要时设置 `STRATA_NODE`。系统评测显式写入 `output/`，避免覆盖旧版本历史记录。

已有本地 Ollama 与模型后，真实模型验证可另执行：

```sh
STRATA_OLLAMA_MODEL=qwen2.5:7b .venv/bin/python scripts/evaluate-agent-boundaries.py --output output/agent-boundaries.json
STRATA_OLLAMA_MODEL=qwen2.5:7b .venv/bin/python scripts/evaluate-model.py --split holdout --label local-replay --output output/model-holdout.json
```

这两个命令不会下载模型。`evaluate-model.py` 会拒绝覆盖既有输出文件，重复评测请换一个新的输出文件名，保留历史记录。前者使用自制工程案例，后者是旧题重评；两者都不能外推为客户工程准确率。实际验证范围见 [v1.2 Agent边界评测](docs/agent-boundaries-v12.json)及[路由保留集](docs/model-evaluation-v12-holdout.json)。

## 8. 客户到来后先补这五组材料

1. **资料与映射**：获授权的真实 CSV／XLSX／JSON／PDF 或 ETABS／SAFE 导出，字段含义、单位、对象身份及关联、版本／revision 和完整性定义。先做一个适配配置；新格式才改解析器。
2. **规则与依据**：批准 QA 清单、适用条件、参数／容差、规范版本和合法引用，批准／复核负责人。已有比较方法改规则版本；新工程方法新增工具并验证。
3. **独立案例**：至少各一条正确、故意错误和缺证据案例，独立预期、应发现的问题与容差。先注册案例，再开展客户对照验收。
4. **CSI 环境**：Windows、CSI 许可及实际版本，客户 IT 维护的只读导出入口、认证方式、profile 与契约样本。先核对模拟契约，再真实联调和结果对照。
5. **使用与部署**：工程师操作流程、必须人工确认的步骤、资料保密和保留政策；多人共享时另行提供机构服务器、账号策略和备份安排。云端部署本轮继续暂缓。

最先完成“一份映射 → 一条批准规则 → PASS／FAIL／NOT VERIFIED 三个独立案例 → 客户工程师复核”，再扩大工程范围。不要用合成成绩替代客户确认。
