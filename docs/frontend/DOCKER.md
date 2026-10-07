# 升级界面的本地Docker运行

复用既有`Dockerfile`和`compose.yaml`，`web/`整体进入镜像，包括新CSS、语言文件与JS模块。模型默认关闭，基础手动检查不下载模型；Linux容器不支持macOS Vision，继续提供人工转录和校对路径。

新建自己的本地演示，不挂载现有个人数据库：

```sh
# 在项目目录执行。STRATA_SETUP_TOKEN是一次性初始化令牌，不是账号密码。
# 不要把它发到聊天、截图或Git仓库。
export STRATA_SETUP_TOKEN="$(python3 -c 'import secrets;print(secrets.token_urlsafe(32))')"
STRATA_PORT=4196 STRATA_IMAGE_TAG=1.4.0 docker compose -p strata-ui-v14-team up -d --build
STRATA_PORT=4196 STRATA_IMAGE_TAG=1.4.0 docker compose -p strata-ui-v14-team ps
```

打开`http://127.0.0.1:4196`，使用本机终端环境里的初始化令牌创建自己的账号。账户建立后，令牌不用于日常登录。使用同样的项目名和端口配置重启，数据保留在该项目专用runtime卷；不要执行`down -v`或全局prune。

首次构建需要联网。Mac如果调用Docker完整路径后出现找不到`docker-credential-desktop`，在终端先执行：

```sh
export PATH="/Applications/Docker.app/Contents/Resources/bin:$PATH"
docker version
docker compose version
```

本轮完整容器验证见`docker-verification.json`；最终忙态修复后的源码/镜像/HTTP资产绑定见`docker-final-binding.json`，两份记录范围分别保留。验证器使用独立随机项目和卷，检查构建、实际后台计算/复核/英中报告、容器重建持久化及第二卷恢复；不会把ETABS/SAFE本体当作Linux容器依赖。新源码发布前另外绑定最终镜像的逐文件hash，不把较早候选镜像写成最终源码镜像。

```sh
.venv/bin/python scripts/verify-week5-docker.py --output output/ui-upgrade/docker-verification.json
```

此命令是独立验收，正常使用者使用不需要反复执行。macOS/Linux终端的环境变量命令不能直接照搬到Windows CMD；Windows Docker请用已有[通用Docker说明](../local-docker.md)。

## 这台Mac上已经准备的隔离演示

源码仓库中的私有配置是`output/ui-docker-live/.env.week5`，登录信息是同目录`login.private.json`（600权限，仅本机，不打包）。新项目名`strata-ui-v14-demo`，地址4196；旧1.3.0项目名`strata-week5-demo`和4193继续保留。新环境当前有合成PASS/FAIL/NOT VERIFIED及软件复核记录，方便浏览界面。

在源码根目录启动或查看：

```sh
docker compose --env-file output/ui-docker-live/.env.week5 -p strata-ui-v14-demo -f compose.yaml -f compose.week5.yaml up -d --no-build --pull never app
docker compose --env-file output/ui-docker-live/.env.week5 -p strata-ui-v14-demo -f compose.yaml -f compose.week5.yaml ps
```

彩排前回到草稿规则、3个快照、0工程运行：

```sh
docker compose --env-file output/ui-docker-live/.env.week5 -p strata-ui-v14-demo -f compose.yaml -f compose.week5.yaml stop app
docker compose --env-file output/ui-docker-live/.env.week5 -p strata-ui-v14-demo -f compose.yaml -f compose.week5.yaml run --rm --no-deps --pull never app python scripts/week5-environment.py checkpoint --directory /backups/week5 --name completed-ui-v14
docker compose --env-file output/ui-docker-live/.env.week5 -p strata-ui-v14-demo -f compose.yaml -f compose.week5.yaml run --rm --no-deps --pull never app python scripts/week5-environment.py restore --directory /backups/week5 --name prepared
docker compose --env-file output/ui-docker-live/.env.week5 -p strata-ui-v14-demo -f compose.yaml -f compose.week5.yaml up -d --no-build --pull never app
```

检查点名称已经存在时，保留旧点，改用新的唯一名称。restore会撤销旧登录，密码不变；重新登录。若要回到保存的完整历史，将`prepared`改成自己保存的completed名称。禁止向其他项目/卷套用此方法。发布包不附带这台Mac的私有配置、账号或运行数据库，使用者使用上文新建自己的环境。
