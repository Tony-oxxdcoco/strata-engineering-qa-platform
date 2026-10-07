# 1.1.0 基线核查与本轮差异

2026-10-07。实际源码目录为 `project——team/demo`，初始HEAD为413d444（无远端），159 Node／224 Python回归通过。唯一未跟踪阶段报告保留。原目录并非最早聊天中的project/demo路径。本轮在隔离克隆开发，私有运行目录未用于测试或打包。

| 客户要求 | 原版实际接入／验证 | 本轮完成的真实缺口 | 必须等待 |
|---|---|---|---|
| Agent架构 | 9任务catalogue、可选本地路由、持久worker/trace在Workspace接入 | 全流程易用入口、批次自动更新、错误类型、中英界面、最终原子发布 | 客户SSO／规模／批准设计责任 |
| Knowledge/RAG | 原文件、dynamic rule draft/approve/retire、exactID/BM25在Knowledge接入；规则包API＋JSON界面 | 多规则覆盖拒绝、明确Page N检查、扫描件来源校对、开发/保留候选比较；拒绝无收益候选 | 授权标准、真实文档语料、客户批准参数 |
| Agent工作流 | rule→data→check→verify→explain，缺证据清单、linked rerun、review/export已有 | 原文件identity绑定、人工操作更正/独立case图形表单、中文系统消息；真实浏览器NV/FAIL/PASS闭环 | 客户工程师验收、真实案例 |
| Tool calling | 确定性Node/配置/transfer工具，adapter保存/复用及CSI接口已有；多数配置依靠JSON | 无需编辑内部JSON的明确字段/单位/规则参数配置；CSI故障和重复导入准备；strictJSON拒绝变值 | 原生ETABS/SAFE、版本与许可 |
| AI验证／幻觉控制 | 输出验证、来源/hash/version、保守NV、模型只选任务已实测 | 最后边界权限/取消、OCR链同SHA绕过阻断、空集合/下溢/容差/独立性专项；真实模型7工作流验证 | 没有客户黄金集，不能报告工程准确率或零幻觉 |
| Testing | 固定16数值/10Agent/18服务案例、独立case API、macOS安装证据 | 代表性坏输入、真实TCP模拟、双语Chrome、严格JSON、全新安装及含OCR的备份恢复 | Docker/Windows/Linux未运行 |

后台适配、规则包、独立案例在1.1已有API和高级JSON入口，因此本轮补图形配置，不重写存储或引入新框架。CSI此前及本轮都不是原生联调；旧静态dist演示不是账号共享后端。旧报告/计划的已完成勾选只代表当时范围，不能代替本轮证据。

原版理想输入回归没有覆盖最终发布间隙撤权、来源被另一合法blob替换、同SHA OCR来源绕过、OCR超时/缺metadata、表单id被输入遮蔽、blob原图CSP、严格配置重复键以及语言下原始标识误译。本轮独立审查复现后修复；位置与具体触发见安全、工程边界记录和新测试文件。

硬编码保留范围：早期gravity-full/basic load-combination为明确标注synthetic的固定profile和注册checkID；它们不冒充通用客户工程方法。mass/seismic/settings/combinationconfiguration/handoff通过批准参数和明确契约配置。示例名称、测试答案只用于seed/fixtures/独立case，不决定客户导入的结论；前端固定checkID仅表达已实现工具合同。

本轮新增依赖：无必需第三方框架或数据库。OCR是可选本机Swift/Vision+pdftoppm；测试页生成Pillow只用于开发夹具，不阻断应用。独立推导和固定数值断言仅核对软件计算，不等于工程师验收。基础应用无需模型或付费API。
