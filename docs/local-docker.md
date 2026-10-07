> 本文初始验证记录属于1.2.0：当时没有Docker。1.3.0实际安装／容器状态以 [后续容器实测记录](frontend/docker-verification.json) 和最新发布说明为准；原先“未运行”不能自动改成实测通过。

# 本地 Docker 交付与验证边界

本轮机器没有 Docker CLI 或 Docker Desktop。因此下面配置已做源码、YAML 结构和边界检查，**没有实际构建、启动或重建容器**，不能作为 Docker 运行成绩。原生 macOS 安装验证见本轮发布记录。Windows、Linux 原生运行也需分别验收。云部署暂缓。

应用镜像包含前端、FastAPI、现有 Node 确定性工具和明确列出的合成样例；没有 ETABS/SAFE 本体、许可、个人数据库、模型权重或付费 API。`app` 只发布宿主机 `127.0.0.1:4180`，以 UID 10001 运行，只读根文件系统，状态写入命名卷。基础启动不下载模型。

## 首次启动

在解压后的 STRATA 文件夹运行，安装 Docker Desktop 或 Docker Engine + Compose v2。`.env` 是本机配置，禁止分享；`.env.example` 只有空的密钥字段。

```sh
cp .env.example .env
docker compose config
docker compose build app
docker compose run --rm --no-deps app python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Windows PowerShell 第一步为 `Copy-Item .env.example .env`，其他 Docker 命令相同。把生成的随机字符串填入 `.env` 的 `STRATA_SETUP_TOKEN=`，然后运行：

```sh
docker compose up -d app
docker compose ps
docker compose logs --tail=50 app
```

打开 `http://127.0.0.1:4180`，创建自己的管理员账号。Docker 转发后的请求源地址通常来自容器网桥，不能冒充宿主机 loopback，因此首次账号表单需要填写同一个 operator setup token。此设计保持首次管理员的权限校验。没有默认用户名或密码。

成功创建后删除 `.env` 中 token 的值，执行 `docker compose up -d --force-recreate app`。账号已存入数据库，移除 token 不影响登录。不要把 token 发给使用者；每人运行自己的实例并创建账号。

健康检查访问 `/api/v1/health`，要求数据库健康且后台 worker 存活。启动失败先看日志和端口，不能通过关闭权限检查解决。

## 持久化、备份与重建

`runtime` 卷保存 SQLite、原始文件和必要任务状态；`backups` 卷保存明确生成的备份；可选 `model-data` 卷保存模型权重。`docker compose down` 保留卷，重新 `up` 应保留账号和项目。**不要运行 `down -v` 或 volume rm，除非明确决定删除资料。**

下面 `example-backup` 必须是尚不存在的目录名称；备份包含账号密码哈希和工程资料，不能放进源码发布包。

```sh
docker compose exec app python scripts/backup.py create --data-dir /app/.runtime --output /backups/example-backup
docker compose exec app python scripts/backup.py verify /backups/example-backup
docker compose cp app:/backups/example-backup ./output/backups/example-backup
```

先创建宿主机 `output/backups` 目录，再执行 `cp`。恢复在新目录进行：

```sh
docker compose exec app python scripts/backup.py restore /backups/example-backup --output /backups/example-restored
```

保留旧运行目录，把 `.env` 中 `STRATA_CONTAINER_DATA_DIR` 改为 `/backups/example-restored`，停止并重建 app，重新登录，核对原文下载、历史结果、规则及报告。恢复会撤销旧会话；不会删除旧运行目录。Docker 验收人员必须实际证明重建后的持久化及备份恢复，而非仅观察 YAML 配置。

## 可选本地模型

`ollama` 是可选 Compose profile，独立进程共享 app 的网络命名空间，并只监听 `127.0.0.1:11434`。这样保留现有模型连接器只允许 loopback 的约束；不把宿主机或外网地址加入允许列表。模型服务没有单独发布的端口。

```sh
docker compose --profile model up -d app ollama
docker compose exec ollama ollama pull qwen2.5:7b
```

下载成功后，将 `.env` 中 `STRATA_OLLAMA_MODEL` 设为 `qwen2.5:7b`，执行：

```sh
docker compose --profile model up -d --force-recreate app ollama
```

重建 app 时也重建共享其网络命名空间的 ollama。下载权重是显式操作；手动选任务的基础流程不依赖它。此配置未配置 GPU，CPU 推理耗时应现场测量。Mac 容器不能据此假设使用 Metal。模型服务不可用时界面应明确提示并保留手动任务选择。

客户只读连接器的 `STRATA_ETABS_URL`、`STRATA_ETABS_TOKEN` 和超时也由 Compose 转发，默认空地址即关闭。容器中的 `127.0.0.1` 指容器网络，不能用它假设连到宿主机 Windows/CSI；客户服务应提供受授权的 HTTPS 地址。ETABS/SAFE 本体不属于此 Linux 镜像。真实 token 仅放本机 `.env` 或客户指定的密钥配置，不能发进发布包。

镜像默认固定到 `ollama/ollama:0.40.0`，版本标签已查阅 [Ollama 官方镜像列表](https://hub.docker.com/r/ollama/ollama/tags)。权重下载方法参考 [Ollama 官方 Docker 文档](https://docs.ollama.com/docker)。镜像标签可被上游重发布；正式复现验收还应记录实际镜像 digest 和模型 digest。当前未实际拉取该 Docker 镜像，也未宣称它已通过本项目运行验证。

## 样例与容器验收清单

```sh
docker compose exec app python scripts/demo-workflow.py --output /tmp/strata-synthetic-demo
docker compose cp app:/tmp/strata-synthetic-demo ./output/docker-synthetic-demo
```

此脚本仅运行自制合成案例，独立预期答案存于源码。实际验收还需在浏览器创建项目并完成上传、适配、规则批准、检查、更正、关联重检、人工确认与导出，以及中英文和手机布局检查。

容器环境可用后应依次记录：`docker compose config` → 构建 → health → 首次 token/账号 → 手工任务与报告 → 重建后数据不变 → 备份验证/恢复 → 可选模型在线/离线。失败时保留日志并修复；不以原生 macOS 验证替代这些步骤。

## 发布边界

`scripts/package-release.py` 仅收录 Git 已跟踪或已暂存且通过目录限制的源文件。未跟踪的会议笔记、工程输入，即使放在 `docs/` 或 `examples/`，也不会自动打包。新增源码应审阅并 `git add` 后再打包，不能盲目 `git add .` 纳入私人资料。脱离 Git 的既有安装包只按其 `release-manifest.json` 重新打包；新增未列出的文件不会自动进入。

`.env.example` 可进入交付，但 token/password/secret/key 字段必须为空；真实 `.env`、数据库、私钥、运行目录、模型文件与输出目录均排除。发布 ZIP 提供逐文件 SHA256 及整包 SHA256；这些校验用于发现损坏，不是工程正确性或来源授权证明。
