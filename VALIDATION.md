# v0.3 验证记录

日期：2026-10-03（Australia/Sydney）。环境：Node.js 24.12.0、macOS、隔离的Chrome浏览器会话。

## 自动化结果

- `npm test`：**159 / 159 通过**，0失败、0跳过。
- `npm run check`：网页入口、本地资源引用、模块语法及页面元信息通过。
- `npm run validate`：**16 / 16 数值案例**、**10 / 10 Agent案例**符合独立手写预期。
- 数值案例中预期/实际NOT VERIFIED检查项为**19 / 19**，错误判为PASS的检查项为**0**。

这些是受控合成案例的实现验证，不能推导真实工程准确率、模型路由准确率或“零幻觉”。测试输出保存在 `output/test-results.txt`，可见案例记录由 `npm run validate` 写入 `output/validation/`。

## 浏览器实际验收

使用Playwright CLI操作实际本地页面，未仅依赖HTTP状态或单元测试。

| 流程 | 实际观察 |
| --- | --- |
| Agent正确/错误/缺证据 | 分别PASS、FAIL、NOT VERIFIED；每次切换案例清空旧结果 |
| ETABS未配置 | 返回NOT VERIFIED；没有假装取得CSI数据 |
| 规则搜索 | QA-003检索返回规则和原文定位 |
| 缺规则 | 返回NOT VERIFIED，计算步骤明确为“未调用” |
| 可见验证中心 | 显示16/16与10/10，预期/实际未验证计数一致 |
| 基础组合 | 正确PASS；超差FAIL；缺工况/非线性NOT VERIFIED |
| CSV导入 | 正确模板得到6 PASS；输入保留文件名与44条来源记录；旧报告不可继续导出 |
| 人工复核与报告 | 组合、楼层Markdown及完整JSON均实际下载；下载内容包含复核人、意见及正确输入快照 |
| Agent报告 | 实际下载带规则、来源、输入和工具轨迹的Markdown |
| 历史一致性 | 修改测试浏览器中的历史输入后，旧记录被拒绝载入；原测试历史随后恢复 |
| 模型界面 | 仅使用本地浏览器mock路由；编辑问题后旧结果移除、导出禁用。未调用真实模型 |
| 手机布局 | 390×844检查无页面横向溢出；1440×1000检查桌面布局 |
| 浏览器控制台 | 最终检查0错误、0警告 |

已目视查看桌面与手机截图：

- [Agent桌面](output/playwright/agent-desktop.png)
- [CSV工作台](output/playwright/csv-desktop.png)
- [验证中心](output/playwright/validation-desktop.png)
- [Agent手机](output/playwright/agent-mobile-viewport.png)

下载证据位于 `output/playwright/gravity-reviewed.json`、`gravity-reviewed.md`、`combination-reviewed.md`；它们是合成测试数据，不是客户报告。`output/` 不进入源码提交或静态发布包。

## 独立复核

模块分别实现后，另行检查了来源门控、单位、报告、模型权限边界与UI状态连接。已修复的实际问题记录在 [PROJECT_JOURNAL.md](PROJECT_JOURNAL.md)。除自动化套件外，审查还执行了17个反例，包含规则注入、未知单位、重复反力和篡改报告后重新计算哈希；未发现这些情况能越过相关检查得到错误PASS。

单项任务只覆盖本项：反力问题不自动使“仅分层分配”任务失败，分层问题也不自动改变“仅反力平衡”结果。需要全范围结果时选择完整重力QA。

## 未执行的验证

- 真实客户资料和独立工程黄金集验收。
- 真实ETABS/SAFE软件、CSI API和授权规范检索。
- 真实LLM调用、任务路由质量、付费成本或延迟实验。
- 生产共享权限、服务器数据库、电子签章和防篡改存储。
- 浏览器WebMCP扩展契约。页面的普通操作不依赖它。

## 报告文件与运行方式

与开始时的SHA-256清单对比，`report/`内**12/12文件未改变**。本轮只改demo代码及其说明。

本地入口为 http://127.0.0.1:4173/#agent ，需要 `npm start` 进程运行。静态线上副本与本地服务相互独立；发布记录见下方。默认模型桥接关闭，只有配置服务端密钥并在本机界面明确选择模型模式才会产生外部请求。

## 发布记录

待本轮已验证源码提交、上传并完成部署后填写实际结果，不把本地成功当作线上已更新。
