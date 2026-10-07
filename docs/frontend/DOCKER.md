# 升级界面的本地Docker运行

复用既有`Dockerfile`和`compose.yaml`，`web/`整体进入镜像，包括新CSS、语言文件与JS模块。模型默认关闭，基础手动检查不下载模型；Linux容器不支持macOS Vision，继续提供人工转录和校对路径。

新建自己的本地演示，不挂载现有个人数据库：

```sh
# 在项目目录执行。STRATA_SETUP_TOKEN是一次性初始化令牌，不是账号密码。
# 不要把它发到聊天、截图或Git仓库。
export STRATA_SETUP_TOKEN="$(python3 -c 'import secrets;print(secrets.token_urlsafe(32))')"
STRATA_PORT=4181 docker compose -p strata-ui-local up -d --build
STRATA_PORT=4181 docker compose -p strata-ui-local ps
```

打开`http://127.0.0.1:4181`，使用本机终端环境里的初始化令牌创建自己的账号。账户建立后，令牌不用于日常登录。使用同样的项目名和端口配置重启，数据保留在该项目专用runtime卷；不要执行`down -v`或全局prune。

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


## 公开源码的运行入口

本文保留1.4.0前端升级时的Docker验证范围。原机器的账号、私有环境配置、数据库和检查点不在开源副本中。请按[通用Docker说明](../DOCKER.md)创建自己的隔离实例，不依赖旧机器上的文件或端口。最新源码/镜像/安装包绑定见[发布验证](../RELEASE_VERIFICATION.md)。
