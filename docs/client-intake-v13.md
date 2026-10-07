# STRATA 1.3.0 全新模拟资料接入验证

本轮用一套**新编写、明确标注合成的供应商式资料**验证接入流程，不复用旧18条固定工作流或5条适配案例的工程字段/数据。本轮交付目标1.3.0，开发基线为 `221fcb3`。最早TestClient收据保留rc身份，最终容器真实HTTP与GUI收据另列，不伪改原成绩。资料不是客户提供的，结果不能当作客户工程准确率、规范批准或真实CSI联调。

## 1. 资料包与独立预期

资料目录：`examples/client-intake-v13/`。生成时先保存 `oracle.json` 的手工预期，再编写导出文件/规则包；运行系统前用 `fixture-manifest.json` 固定原字节SHA。没有调用被测工具产生正确答案。

| 文件 | 内容与支持边界 |
|---|---|
| `source.two-sheet.synthetic.xlsx` | 两工作表 `P17_Vertical` / `P17_Transverse`，字段名/列序不同；负竖向 -1850000 N、字符串形式横向225000 N，明确单位。元数据列显式忽略 |
| `source.reissued.synthetic.xlsx` | 再发行参考文件：原始备注不同，数值不变；用于证明原资料/新快照及历史确认有正确版本关系 |
| `target-pass.synthetic.csv` | 新字段名、乱序、显式comment额外列；竖 -1849.8 kN、横225 kN |
| `target-fail.synthetic.csv` | 换用预先声明的 `V_Result` / `H_Result` aliases与另一列序；横225.6 kN构成故意错误 |
| `target-missing.synthetic.csv` | 缺必填横向列；strict adapter必须拒绝，partial adapter只允许保存不完整数据，工程工具仍必须NV |
| `target-reissued.synthetic.csv` | 新列序与原始备注，数值不变；与新source共同创建后继快照，不覆写原文件 |
| `target-MN-unsupported.synthetic.csv` | 单位明确写MN。当前 `data_tools.UNITS`仅注册N/kN force单位，MN必须明确拒绝，不能猜测换算 |
| `target-undeclared-column.synthetic.csv` | 未声明额外列 `UnreviewedExtra`，必须定位到该列拒绝 |
| `adapter-source.json` / `adapter-target.json` / `adapter-target-partial.json` | 可在GUI导入/导出的明确配置；source与target输出不同路径，后者partial的横向required=false只针对不完整导出保存，不豁免工程必填项 |
| 三份 `rule-package-INTAKE-R*.json` 与对应TXT | 每包两条标量映射，来源/版本/修订/绝对相对容差明确，初始draft；只能调用既有handoff工具 |
| `oracle.json` / `fixture-manifest.json` | 独立预期、判定/数值/映射错误定位、资料hash；全包synthetic，非客户批准内容 |

固定 source revision 为 **INTAKE-SRC-R17**，target为 **INTAKE-TGT-R6**。字段路径：source `/loads/vertical/force`、`/loads/horizontal/force`；target `/received/vertical/force`、`/received/horizontal/force`。单位路径也分两侧明确配置。原对象ID与备注保留，工具只验证manifest明确列出的两条数值映射，不能据此宣称全面核验对象身份、几何或模型安全。

独立手算：-1850000 N = -1850 kN，225000 N = 225 kN；目标竖向差 **+0.2 kN**，错误目标横向差 **+0.6 kN**。

| 规则版本 | abs / rel容差 | 竖向容差 | 横向容差 | 三类预期 |
|---|---|---:|---:|---|
| INTAKE-R1 | 0.25 / 0.00001 | 0.25 kN | 0.25 kN | 正确目标PASS；横225.6 FAIL；缺横NV |
| INTAKE-R2 | 0.10 / 0 | 0.10 kN | 0.10 kN | 原“正确目标”的竖差0.2现在FAIL；证明规则变化影响判定 |
| INTAKE-R3 | 0.10 / 0.0002 | 0.37 kN | 0.10 kN | 正确目标PASS；横225.6仍FAIL；缺横仍NV |

所有容差都是本次软件测试选择。R3采用 `abs(source)`，负号不会生成负容差。预期数值比较给定1e-8绝对误差，用于浮点软件对照，不是放宽工程工具容差。

## 2. 可复现API验证

安装开发依赖后执行：

```sh
npm run setup:dev
.venv/bin/python scripts/verify-client-intake-v13.py --output output/client-intake-v13
```

Windows把Python路径换成 `.venv\Scripts\python.exe`，当前尚未在Windows实测。基础流程不调用付费API，不下载模型，不连接真实CSI，也不需要Docker。

默认模式：临时SQLite＋**真实认证FastAPI路由（TestClient）＋真实确定性工具**。不是HTTP网络服务或浏览器验收。临时模式屏蔽已有数据目录、数据库、部署origin/hosts/setup token以及模型、CSI、OCR服务配置，退出后精确恢复，避免意外连接现有资料或继承其他安装配置。保留 `STRATA_NODE` 以使用明确安装的本地Node执行器。结束后删除临时账号和runtime，保留合成结果。`--url`模式使用运行中服务器本身的配置，不修改服务环境。

要在已运行本地服务器的新项目中持久保存结果：

```sh
.venv/bin/python scripts/verify-client-intake-v13.py --url http://127.0.0.1:4190 --output output/client-intake-v13-http
```

按提示输入自己的本地用户名和密码；密码不写文件。脚本只接受纯loopback HTTP origin，创建新的SYNTHETIC项目，不修改原项目。4190是本轮隔离环境默认端口，应替换为实际服务器地址。此模式使用真实HTTP和后台worker，尚须单独执行，不能用TestClient结果代替。

每次运行的报告在新的 `attempt-时间-随机值/` 子目录，避免旧报告残留误作本次结果；目录中保存本次 `verification.json`、英中HTML和JSON。`output/client-intake-v13/verification.json`指向最新验收内容，包含该报告目录。output是私人本地验证输出，不直接打包个人运行数据库或凭据。

## 3. 已实际验证的内容与发现修复

2026-10-07默认隔离API模式，在1.3.0-rc.1工作代码上完整运行，结果 **PASS**。代码：`scripts/verify-client-intake-v13.py`；证据：最新output验证JSON及独立attempt目录。没有把该结果冒充浏览器或Docker验证。

| 验收内容 | 实际结果 |
|---|---|
| 新XLSX/CSV配置保存、导出、预览/应用、两侧不同路径 | 通过；preview与保存结果/原值provenance一致 |
| 三种错误导入 | 缺横向列、MN单位、未知额外列分别HTTP422，准确file/table/row/field/reason；不产生快照 |
| Draft→approve规则门禁 | draft不能授权检查，NV/WAITING；批准后运行按固定版本 |
| 独立三案对照 | R1 3/3匹配，R3 3/3匹配；每组2条预期非通过的错误通过均0 |
| 参数变化 | R2竖FAIL；R3用相对容差恢复PASS，并核对两项expected/actual/delta/tolerance |
| 材料需求侧/字段 | 最终仅target `/received/horizontal/force` 和 `/received/horizontal/unit`，不错误要求补source路径 |
| 输入、来源与历史 | 8个实际上传原文件下载SHA一致；XLSX原-1850000 N与字符串225000都可追溯；重发行资料不同raw hash、相同标准数值，原资料保留 |
| 关联与人工review | 新文件/快照使旧review STALE且记录保留；rule版本变化再次失效；关联R3 PASS解决原R2发现后由reviewer确认 |
| 固定案例与规则退休 | R1三个旧case在规则退休后报告invalid，不继续显示为当前有效匹配；曾经的3/3保留为当时历史口径 |
| 英中HTML及JSON | 原数值1850/1849.8可见，英中DRAFT/STALE/REVIEWED文档状态标记逐次硬断言通过；真实GUI另见UI_ACCEPTANCE与browser-verification.json |

初次脚本曾对XLSX误传 `source_only=true`，被已有契约正确拒绝。已修脚本为仅CSV/JSON使用source-only，没有为它放宽后台规则。

这套新输入暴露并促成修复一处真实补证漏洞：原 `evidence.requests()`把handoff四条dependency在source/target两侧都遍历，产生6条错侧清单。由于旧样例常用两侧相同路径，它不容易暴露。现在 `data_tools.verify_handoff()`显式返回 `dependency_sides`，`evidence.requests()`只在对应侧定位；主任务补source/target/both缺项回归，本脚本再硬断言正确两项后完整通过。

三案跨版本反复使用只算**3种新独立资料变体**，不能说6个独立工程案例或客户100%准确率。NV的父/子逐项计数也不是多个独立缺陷。没有为提高测试数字重复运行同一成功流程。

## 4. GUI接入验收路线

以下路线已由真实浏览器完成；具体run/状态/范围与截图见 [UI_ACCEPTANCE.md](client-intake-v13/UI_ACCEPTANCE.md)。这是合成用户流程验证，不是团队口头彩排。

1. 在独立演示实例创建新的SYNTHETIC项目，不复用私人数据库。先不批准规则。
2. Adaptation导入source/target两个profile，再上传XLSX和pass CSV。XLSX正常解析；CSV source-only。预览两个worksheet与新列映射，核对N原值、负号、kN标准值；保存source/target快照。
3. 导入INTAKE-R1 package，观察draft；Knowledge查看规则引用和来源，然后reviewer批准。任务选 **handoff**，source与target分别选正确快照。现场实际PASS应包含两条映射。
4. 上传fail CSV，用相同target profile处理另一alias/列序；选择该target实际运行FAIL，查看横向225.6与225、delta0.6。
5. missing CSV用strict profile应报具体字段；切换明确partial profile保存不完整快照后，handoff应NV，并且只要求补target的横向值/单位。
6. 添加完整的重发行资料，用旧run的Create follow-up run关联重检；查看原文件与原run仍在。确认前处理对应链的原发现。
7. 用INTAKE-R2、R3的明确版本逐次批准，核对旧review失效、绝对/相对容差及判定变化。最后review并导出英中HTML/JSON，对照原单位、引用和数值未被翻译改变。
8. 全程切换两语核对表单、错误、材料需求和手机布局；记录真实run/版本/截图/结果。切换不改变内部状态或数据。

脚本的批次案例登记使用同一已支持case API，GUI可用Register case导入独立预期。需要资料ID才能绑定快照，不能把源码中固定旧ID当作本机的有效ID。来源/对象含义、mapping正确性和容差合法性仍由工程师确认。

## 5. 客户资料到来后改哪些地方

- 列名/工作表/JSON路径、必填、单位和revision：新adapter版本；不修改工具猜测供应商含义。
- 已支持handoff方法的路径、适用条件、参数和容差：新规则包/版本，客户授权来源与本地reviewer审核；设置client标签不能替代批准。
- 独立答案和代表输入：新的strata-case/1资料，固定输入/规则/人工依据；不要从系统结果生成truth。
- 新单位、格式、工程方法或CSI契约差异：先记录具体支持缺口，再实现工具/解析器并独立验证；当前MN拒绝是实测边界。
- 客户最小资料与后补材料见 [CLIENT_INTAKE_CHECKLIST.md](CLIENT_INTAKE_CHECKLIST.md)。Docker/Linux arm64已实测；正式机构上线、原生Windows/Linux、真实CSI及客户工程验收仍需单独完成。

本轮最终Docker HTTP接入公开收据：`docs/client-intake-v13-verification.json`。它包含三版本规则、三独立变体、正确错误及缺证据、原字节hash、历史失效和关联复核。真实GUI收据：`docs/client-intake-v13/browser-verification.json`，17张截图在同目录screenshots；API批量评测和GUI逐步操作是不同范围，不混为同一项成绩。
