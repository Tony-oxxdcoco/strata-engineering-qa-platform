# 新模拟客户包：真实界面接入验收

本记录来自 `http://127.0.0.1:4190` 的独立合成项目 **SYNTHETIC V13 browser intake - new supplier aliases**。运行服务身份为1.3.0-rc.1，界面代码包含本次项目状态隔离和依赖变化同步修复；最终1.3.0 Docker环境另行记录。所有资料、规则和答案都是自制测试材料，不是客户文件或工程验收。

实际通过界面新建项目、上传Excel/CSV、文件选择导入适配配置、预览并创建映射快照、校验及导入规则包为draft、reviewer软件批准、手动选择 **Engineering handoff**、分别选源和目标、运行检查、关联重检、解决发现、人工确认并下载JSON报告。没有手改数据库或调用隐藏接口造结果。

| 验收场景 | 真实结果 |
|---|---|
| 两工作表原值与位置 | P17_Vertical D2 `-1850000 N → -1850 kN`；P17_Transverse A2 字符串 `225000 N → 225 kN` |
| 新别名、乱序字段与不同输出路径 | source `/loads/...`、target `/received/...`，保留原字段/表/单元格 |
| R1 draft | WAITING / NOT VERIFIED，明确缺批准HANDOFF依据 |
| R1正确目标 | 竖向 -1849.8，差0.2≤0.25；横向225，差0，通过 |
| R1错误目标 | 横向225.6，差0.6>0.25，未通过；不被竖向通过掩盖 |
| strict缺横向字段 | 预览和保存均拒绝，文件/表/行/字段定位；未生成第4个快照 |
| 显式partial配置 | 生成部分输入，工程检查NOT VERIFIED；只要求目标侧horizontal force/unit两项 |
| R2缩紧容差 | 相同竖向差0.2>0.1，FAIL；旧R1批准正确STALE |
| R3明确相对容差 | 竖向tol0.37、横向tol0.1，独立预期PASS |
| R3关联复核 | 从R2 FAIL派生PASS，原HANDOFF发现RESOLVED，人工APPROVED且导出时Current |
| 项目隔离修复 | 旧项目→新项目→旧项目，以及创建项目，清掉旧结果/草稿；保留语言 |
| 依赖同步修复 | 批准/退休规则后选中结果立即STALE、禁Confirm；不用手动刷新 |

最终R3 run：`run_305e31993142f2916e72bcc4`，父run：`run_83c91118941b11a784401e72`。原始下载见 `output/client-intake-v13/exports/r3-reviewed-pass-ui.json`；收据和截图SHA-256见同目录 `browser-verification.json`。可分享图在 `docs/client-intake-v13/screenshots/`。`10`是修前问题，最终展示使用`13`、`14`、`15`、`16`。

基础流程没有付费模型调用。该新包的批量案例评测由独立API验收执行，本轮没有再把Register case及批量运行GUI走一遍；两个验证范围不能混称。原native Week5项目规则在最后被故意退休，用来核验旧APPROVED即时失效；其之前导出仍是当时状态的历史记录。Docker的prepared起点不受影响。

公开JSON报告在同目录 `exports/`，每份SHA与收据 `actual_report_exports` 一致；原 rc 运行身份保持原样。
