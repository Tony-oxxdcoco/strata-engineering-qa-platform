# Windows CI 修复记录 / Windows CI repair

## 范围 / Scope

这是 1.4.1 发布后的维护修复。应用版本和工程计算不变；旧版发布包、旧提交及失败记录保持原样。当前 `main` 的检查结果以对应 GitHub Actions 为准。没有将 Windows 自动化回归写成原生交互式安装或真实 ETABS/SAFE 验收。

Maintenance after the 1.4.1 release: calculation behavior and application version are unchanged. Historical packages, commits and failed runs remain intact. Cross-platform automated tests are not native interactive installation or licensed CSI integration evidence.

## 已复现的问题 / Reproduced problems

原提交 `8bfb0e0` 的 Windows 任务两次超时；正式注释为 “The job has exceeded the maximum execution time of 15m0s”。诊断运行 [37650901343](https://github.com/Tony-oxxdcoco/strata-engineering-qa-platform/actions/runs/37650901343) 保留完整 JUnit 和逐项事件，得到 365 passed、2 failed、2 errors：

1. `backend/tests/test_data_tools.py` 的超大文件输入被 pytest 自动放进测试名称，产生约 10 MB 的参数 ID。Windows 写入 `PYTEST_CURRENT_TEST` 时超过 32,767 字符，导致 setup 和 teardown 都报错。给全部非法输入设置简短、稳定的 ID；原输入大小及拒绝断言不变。
2. `tests/test_week5_docker_verifier.py` 用 Unix 的 mode bits 判断 Windows 文件访问权限。改为独立检查 Windows 实际 DACL；Unix 仍检查 0600。`scripts/verify-week5-docker.py` 在写日志内容前设置并校验当前用户独占访问，失败时不写入、不替换旧日志，并把验证收据标为 FAILED。
3. `tests/test_week5_environment.py` 使用 SQLite 事务上下文，却没有显式关闭连接。Windows 恢复演练重命名目录时遇到文件占用。用 `contextlib.closing` 配合事务上下文，提交后明确释放文件句柄，保留原有回滚和历史保全断言。生产备份脚本已有显式关闭，不重复改写。

The oversized-input test now has a short ID without reducing its 10 MB boundary. Recovery fixtures explicitly close SQLite handles. Private Docker logs use owner-only Windows ACLs or Unix 0600 before content is written. Access-control failure preserves the previous log and cannot report PASS.

## 后续诊断 / Future diagnostics

`.github/scripts/backend-checks.py` 运行完整原有 Python 回归，记录 JUnit、逐项事件和周期线程栈；300 秒后主动失败并保留证据。三平台矩阵、Node 回归、静态检查及合成案例校验保留。整个 job 的 15 分钟限制未延长，没有跳过失败检查或放宽判定。失败诊断 artifact 仅保留七天，不作为发布安装包。

The full regression suite remains enabled on Ubuntu, macOS and Windows. The bounded runner preserves failure diagnostics; it does not alter assertions, permissions or engineering outcomes. The original 15-minute job limit remains unchanged.

## 复现 / Reproduce

```sh
npm run setup:dev
npm test
npm run check
npm run validate
.venv/bin/python .github/scripts/backend-checks.py
```

Windows PowerShell：最后一条用 `.venv\Scripts\python.exe .github/scripts/backend-checks.py`。Windows 日志权限核验使用系统内置 Windows PowerShell 和 .NET ACL API，不依赖 `Set-Acl` 模块自动加载；子进程不继承其他 PowerShell 版本的 `PSModulePath`。不引入新的 Python 包；无法设置权限时明确失败。

实际修复分支验证及最终 main 的运行链接另附本次维护交付收据；旧 1.4.1 Docker、浏览器及安装成绩继续保留原版本口径，本次不宣称重新执行。
