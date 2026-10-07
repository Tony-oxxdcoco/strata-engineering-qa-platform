# v1.2 独立安全与交付审查

范围：实际源码中的权限、结果发布、原文件绑定、扫描件校对、CSI 边界及发布包。审查发现交由主任务修复；本文件记录可重现触发条件和修复后验证，不宣称覆盖全部漏洞或真实工程正确性。

| 发现 | 触发条件及代码 | 处理与验证 |
|---|---|---|
| 最终发布存在撤权窗口 | `backend/strata/workflow.py` 的权限／规则重查与最终结果写入原先分属两个事务；两步之间撤权可能仍提交 PASS | `Runner.publish` 用 SQLite `BEGIN IMMEDIATE`，在同一事务中校验并写入缓存、结果、问题及审计。`test_publication_security.py` 覆盖最后边界撤权、取消、规则退役，以及问题／审计写入失败时整体回滚；已通过 |
| 原文件被另一合法 blob 替换仍可能保留 PASS | `app.py:run_view` 原先只校验当前 blob 的自身哈希，没有比较运行保存的原文件哈希；`workflow.py` 最终检验仍使用旧的文件对象 | 主任务增加 input／target 的文件 ID、哈希绑定及最终重新读取。`test_source_binding_security.py` 验证历史输入、handoff 目标和最终发布前替换均阻断；已通过 |
| 严格 JSON 校验可绕过 | `app.py:boundaries` 原先只精确匹配 `application/json`；缺 Content-Type、大小写、空格或 `+json` 变体仍可能被 FastAPI 解析 | 规范化并覆盖所有支持的 JSON 媒体类型。`test_request_security.py` 的四种实际请求均拒绝重复键；已通过 |
| 扫描件可绕过 OCR 校对 | 创建快照的人工映射入口原先可直接使用 `NEEDS_OCR` 或 page image 来源，无须页面确认 | 主任务在 `add_snapshot` 拒绝未校对扫描来源，增加 OCR extraction/source/image 绑定及确认链验证。独立复读确认门已接入；运行测试由 `test_ocr_v12.py` 的负责成员记录，不把本次复读算作 OCR 实测 |
| 发布目录中的私人未跟踪文件可能进入包 | 原包脚本遍历整个 `docs/`、`examples/`、`scripts/`，目录允许并不等于文件已获发布授权 | `package-release.py` 改为 Git index 文件列表或已有发布清单，继续过滤运行数据／凭据，并仅允许密钥字段为空的 `.env.example`。`test_delivery_package.py` 用独立 Git fixture 验证未跟踪笔记、客户文件、数据库、`.env` 不打包，空范例保留；5 项通过 |
| CSI 来源元数据和重复响应边界不完整 | `connector.py` 原先只检查非空 software_version 和字符串 exported_at；重复导入会创建新当前快照 | 增加 UTC 时间、版本字符串、内容类型、单位及有界超时；项目内按明确 identity 与 snapshot hash 复用，不改变当前 revision。TCP fault 和实际 API 流程测试已通过 |
| Docker 首次账号流程不完整 | 容器网桥请求不属于服务的 loopback；设置 token 后，旧 UI 不能传 `X-Setup-Token` | 主任务补齐首次设置 token 输入；容器定义保留服务端边界。Docker 启动仍待可用环境实际验收，不能用 API 测试代替 |

报告脚本注入另通过实际 review API 传入自制 `<script>`／`<img onerror>` 文本：HTML 报告将其转义，JSON 保留原始审计文本。该测试覆盖报告导出，浏览器其余页面及手机交互由主任务的实际浏览器验证记录。

## 已实际运行

- 连接器原测试、真实 loopback TCP 故障、来源字段／超时与包边界：40 项通过。
- 最终发布边界、撤权／取消／回滚，既有部署／worker／备份回归：23 项通过。
- CSI API 重复导入、项目隔离、软件版本变化、网络响应后撤权：4 项通过。
- JSON 媒体类型与 HTML／JSON 原文区别：5 项通过。
- 原文件与 handoff 目标绑定：3 项通过。

这 75 项是本审查实际执行的不同风险案例，不是项目完整回归成绩。仅原测试与本轮相关新增测试包含在统计中。FastAPI TestClient 出现已有 Starlette/httpx 弃用提示，未用换依赖或吞掉异常掩盖它。

首次 TCP 运行因执行沙箱禁止绑定端口而失败；获准在本机 loopback 执行后，相关测试通过。该失败不是连接器软件通过证据，也未改为 mock 后冒充真实网络测试。

复现（在已安装 dev 依赖的源码目录，用对应 Python 虚拟环境运行）：

```sh
python -m pytest backend/tests/test_connector.py backend/tests/test_connector_network.py backend/tests/test_connector_import.py backend/tests/test_publication_security.py backend/tests/test_source_binding_security.py backend/tests/test_request_security.py backend/tests/test_deployment.py backend/tests/test_jobs.py tests/test_backup.py tests/test_delivery_package.py -q
```

## 尚待环境／客户

Docker CLI/Desktop 未找到，实际 `docker compose config`、镜像构建、容器启动、重建和容器恢复全部 **NOT RUN**。已解析 YAML 并检查本机端口、命名卷、只读根目录和可选模型网络结构；结果见 `delivery-evaluation-v12.json`，明确只代表结构检查。

本轮 CSI 服务由我们用标准库编写，所有资料标记 SYNTHETIC。Windows／Linux 原生运行、真实 ETABS/SAFE 和 CSI license、客户 connector、客户批准规则和独立案例没有验证。连接器跨语言数值序列化／哈希一致性需客户实包对照，不能假定所有 JSON 实现一致。

SQLite 的原子发布在当前环境验证。自定义数据库服务、共享主机、HTTPS 代理、机构账号政策和正式密钥管理仍需独立验收。备份哈希可发现损坏，不能防御拥有主机权限的人同时改写数据和校验值。
