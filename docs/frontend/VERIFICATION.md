# 前端验收说明

此次基线是immutable 1.3.0 / d0df3b0，改造在隔离副本完成。浏览器资料和预期都是明确标注的合成材料，不能用于声明客户工程准确率。

验证以本目录`browser-verification.json`、`regression.json`、`docker-verification.json`及发布包旁的身份记录为准。旧版本368 Python/187 Node成绩保留为历史记录，不冒称本轮又完成全量运行。

浏览器使用Chromium，桌面1440×960及手机390×844视口。手机是浏览器模拟视口，不能据此声称真实iOS/Safari或Android已验证。原生Windows/Linux安装器、真实客户材料/批准规则、真实ETABS/SAFE及工程师验收仍待对应环境与客户资料。

已记录的验证故障：Docker首次构建找不到`docker-credential-desktop`，原因是执行环境PATH未包含Docker的辅助程序目录；补齐后独立重建与完整容器流程通过。首次选择了不存在的Python测试路径，未运行任何测试；更正后执行API/发布隐私相关测试。浏览器的route故障注入探针出现`Route is already handled`，后续fetch探针的Close选择器也有歧义；保留原日志，不将这些探针写成产品通过或产品失败。正常界面流程另行验收。

Node DOM stand-in测试只验证控制逻辑，真实布局、焦点和点击结果以浏览器记录为准。核心算法没有改变，既有模型/检索成绩没有重新包装成界面升级成果。

专用Docker概览准备脚本曾按错误的完成批次/仪表盘响应封装读取，出现KeyError；修为实际API形状后直接复用已保存运行完成复核，没有重跑计算。该过程是环境准备，不记为产品故障或新增基准成绩。

真实界面曾发现“Make current期间打开Inspect input后，更正按钮保持禁用”，已在withBusy结束时同步更新打开的modal；浏览器按原操作路径复验解除。最终运行逻辑修复仅web/app.js；另更新web/README.md的导航说明。cached重建、67runtime逐文件核验、10个实际HTTP资产与重建后3运行/复核保留均通过，见docker-final-binding.json。完整Docker核心流程/第二卷恢复沿用独立的同版本完整收据，不伪写成在最终镜像重新跑过全量。

全新macOS解压安装见fresh-install-verification.json：不存在venv/runtime的起点实际安装声明依赖、启动4200、创建独立账号和项目、手动合成PASS/软件复核/HTML导出及10资产HTTP检查通过。该候选包的67运行文件与冻结源码相同，最终发布包完整性另行核验。工具Ctrl+C已停止该进程，Uvicorn退出时有lifespan cancellation traceback，不把它记录成干净关闭验收。

独立真实浏览器权限检查见permission-browser-verification.json：viewer只读提示与上传/执行禁用、engineer可检查而人工确认和Request evidence禁用、中英文原因均已观察。当前唯一规则已批准，viewer草稿批准按钮未渲染，该分支未单独实测。未新增计算或修改原规则。

最后两项补验见browser-supplement.json：关闭应用标签页、同源新标签页打开后仍显示中文（不是浏览器进程重启）；156字符文件名的98字节合成CSV保留原hash，完整值查看后主映射弹窗、同一form、选择和创建按钮保持。208字符文件名被既有180字符限制拒绝，缩短后通过；没有放宽输入限制、新建工程快照或再跑计算。
