# v1.0.0 验证记录

日期：2026-10-03。实际机器：macOS arm64，Node24.12.0，Python3.12.7。原 v0.3 记录保存在 [历史稿](docs/validation-v03-history.md)。这里区分代码回归、固定合成案例、实际模型、浏览器和客户验收，不能互相代替。

## 自动化与独立安装环境

| 检查 | 结果 | 原始记录 |
|---|---|---|
| Node规则/解析/Agent/报告回归 | 159通过，0失败/跳过 | output/v1-node-tests.txt |
| Python API/知识/工具/权限/队列/连接器/更正/问题/配额/备份 | 194通过 | output/v1-python-tests.txt |
| 全新项目内 .venv 安装 | setup成功，pip check无依赖冲突 | output/v1-clean-install.txt |
| 新环境完整Python回归 | 194通过；1条Starlette TestClient弃用提醒 | output/v1-clean-env-tests.txt |
| 固定直接依赖＋已验证依赖约束 | requirements/constraints记录具体版本 | backend/constraints.txt |
| 当前/旧版静态资源、模块引用与全部JS脚本语法 | 通过 | npm run check；output/v1-static-check.txt |
| 源码ZIP独立解压、全新安装、空库启动 | 通过：新账号/项目、19快照、后台6项PASS、JSON导出 | output/v1-package-smoke.json；output/v1-unpacked-setup.txt |

TestClient提醒是测试客户端继续使用httpx的未来迁移提示，不是失败；本次不为消除提示而未经评测更换HTTP栈。新环境使用的依赖与原机器全局环境分开，避免把预装依赖误认为使用者已经拥有。

独立安装验收从源码ZIP解压到另一目录开始，先核验包内逐文件SHA-256，再运行该目录自己的Setup创建.venv。测试进程使用随机本地端口和全新数据库，经真实HTTP创建账号/项目、加载样例、排队检查和下载报告；没有连接作者原有数据库。该验收实际运行于macOS；最后更新交付文档、静态检查脚本、打包排除项和启动器换行格式声明；web/app.js仅清理一行空白，运行行为保持与已验收ZIP一致。可分发的 [安装验收记录](docs/local-install-validation.json) 已去除本机路径和凭据。

## 固定评测

- 原数值16/16、Agent10/10保持一致；原预期/实际NOT VERIFIED检查项19/19。
- 新服务端18/18：7 PASS、6 FAIL、5 NOT VERIFIED。错误PASS为0/11预期非PASS，另报0/7实际PASS；无软件错误。
- 检索45/45：29正例首位正确、16应拒绝题正确。检索集不验证真实规范权威或客户工程准确率。
- 真实本机Qwen2.5:7B：开发集v1为27/32，提示词v2仍27/32且新增误拒绝；v3模型＋拒绝策略32/32，原模型28/32。冻结保留集系统24/24，原模型21/24。
- 服务端缓存实验30对单并发同输入，完整原始耗时均存JSON；它不是工程师人时、生产SLA或竞争成本优势。

逐题输入、预期、实际、哈希、token和时间保存在 docs/*evaluation*.json。当前数字统一引用 [release-v1](docs/release-v1.md)，不把多个集合合并成一个准确率。

## 实际浏览器验收

使用独立Playwright CLI浏览器会话，访问本机4180；实际点击、上传与下载，不仅检查HTTP状态。

| 流程 | 实际验证 |
|---|---|
| 账号与项目 | 浏览器创建本机账号/项目，加载19合成快照和12规则；刷新与服务重启保留 |
| 三态 | 重力正确PASS、故意错误FAIL、缺资料NOT VERIFIED；组合配置/地震/质量源三态按固定例子核对 |
| 原文入库 | TXT源文件通过UI上传、下载前保留hash；Knowledge查HANDOFF返回批准原文引用 |
| 控制CSV | 实际上传模板，生成新快照；六项重力检查全部PASS |
| 交接 | source100kN→target100000N通过；120000N失败 |
| 修订与问题闭环 | 从原FAIL生成linked follow-up；同一发现PASS后关闭两条前序问题；原FAIL保留，再批准当前结果 |
| 更正 | UI保存project/name原值、新值、来源和原因；返回新快照，parent和confirmed_by/at存在 |
| 实际模型 | UI启用本机Qwen，route记录包含local-model与qwen2.5:7b，运行得到确定性PASS |
| 复核/报告 | 实际确认和下载JSON；经鉴权预览后输出PDF，渲染3页A4，检查来源、更正/发现、审批、页码，无遮挡 |
| 资料移交 | 实际下载项目ZIP，ZIP完整性检查通过，包含25个去重原文blob，审计链有效，无会话或密码 |
| 验证页面 | 原16/10、新18、模型24分别显示，当前实现指纹一致 |
| 手机 | 390×844，等待菜单过渡及页面请求完成后截图，Workspace与Validation无页面横向溢出；宽表局部滚动 |
| 桌面 | 1440×1000，检查来源/状态/历史/主工作区排版 |
| 浏览器控制台 | 最终0错误、0警告；曾有1条密码表单无username的verbose提示，已补自动填充字段 |

关键截图在 output/playwright/v1：workspace-final.png、resolved-review.png、knowledge.png、access.png、validation.png、mobile.png、mobile-validation.png、local-model-run.png、report-final-1/2/3.png。原始PDF/JSON/ZIP同目录。它们属于本机验收证据，不进入给使用者的源码ZIP。

浏览器测试暴露了follow-up目标在busy重绘中重置的问题，已把源/目标选择在提交前冻结，并重新完成整个关联检查与复核流程。手机截图曾抓到动画中间态和异步导航尚未完成状态；最终截图等待实际布局和目标页面完成，未把这些中间态当验收。

## 存储、权限和故障验证

源文件、输入、结果、缓存的篡改测试均不允许继续显示/导出可确认的PASS；被破坏的记录读回显示NOT VERIFIED和完整性错误。旧规则/输入/代码使复核失效。跨项目资源、引用和缓存不能越权。撤权对已有登录及worker最终发布生效。取消、幂等、单worker锁、恢复三次上限有专门测试。

真实执行了SQLite＋原始文件备份、校验、恢复到新目录。恢复后旧会话撤销，用本机账号重新登录，读取项目、19快照、12规则、校验审计链、下载原文和JSON报告成功。新目录不覆盖原目录；备份包含敏感记录，始终留在gitignored output/。

Windows/macOS启动脚本与跨平台文件锁已提供；本机验证为macOS。GitHub Actions包含Ubuntu/macOS/Windows矩阵但尚未远程运行。Docker构建、PostgreSQL、Windows原生CSI、客户TLS/身份及生产回滚没有实测，不能标记已验收。

## 发布边界

最新用户要求暂不处理云端，先让使用者独立运行。源码包排除.runtime、.venv、output、.git、原客户PDF和report目录；每个使用者自建账号/项目。旧Sites线上版不等于此版本，没有自动同步资料或改变受邀访问范围。

冻结的report目录12个文件哈希与升级前一致。真实客户规则、数据真值及同任务竞品/人时试验仍未提供，因此没有真实工程准确率、零幻觉或市场优势已被证明的结论。
