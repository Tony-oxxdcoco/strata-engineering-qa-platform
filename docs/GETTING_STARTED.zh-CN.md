# 安装与开始使用

[English](../GETTING_STARTED.md) · [项目说明](../README.zh-CN.md)

准备Python3.12与Node.js20.11以上版本，在源码目录运行`npm run setup`、`npm start`，打开http://127.0.0.1:4180，自行创建账号，无默认用户名或密码。首次安装需要联网下载声明的开源Python依赖；基础应用不需要付费API或模型下载。网页使用期间保留服务进程。

`npm run doctor`检查依赖、目录写入和端口。macOS/Linux可用`STRATA_PORT=4198 npm start`换端口；PowerShell先执行`$env:STRATA_PORT="4198"`再启动。Windows的.cmd和macOS的.command启动器均保留，自动化回归通过不等于全部平台启动器已实测。

数据保存在`.runtime/`，包含账号、项目原文件和结果，不要删除或作为源码分享。修改密码需要当前密码，系统没有忘记密码恢复向导。请妥善保管凭据，不要手改密码hash。演示请优先用隔离项目和数据目录，保护已有数据。

新建项目、Load example、按需批准明确标注的合成规则、选择受支持检查、查看结果及证据、导出记录。当前材料和问题经过复核后由reviewer确认。NOT VERIFIED表示依据或批准条件不足，不能当作通过。

Docker见[运行说明](DOCKER.md)，扩展见[适配指南](../CLIENT_ADAPTATION.md)，验证边界见[验收说明](frontend/VERIFICATION.md)。真实工程应用仍需要独立批准的规则与专业复核；内置案例只验证软件。
