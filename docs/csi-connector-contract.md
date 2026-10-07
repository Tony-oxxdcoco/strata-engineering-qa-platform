# 客户 CSI 连接器接口契约

STRATA 调用明确配置的 HTTP 服务。当前没有控制用户桌面、安装 CSI 或建立真实连接。`backend/strata/connector.py` 已实现请求客户端；客户 IT 工程师维护的 Windows 服务需要提供以下只读导出接口。

`POST /v1/export`

```json
{"contract":"strata-csi-export-1.0","model_id":"opaque-model-id","revision":"R1","profile":"approved-gravity-export","read_only":true}
```

响应保留相同标识，并包含 `software_version`、UTC 时间 `exported_at`、`snapshot`、`snapshot_sha256`、`read_only:true`。snapshot 是系统支持的标准 JSON 工程输入。本版哈希算法严格对应 Python `json.dumps(snapshot, allow_nan=False, ensure_ascii=False, separators=(',', ':')).encode('utf-8')` 的 SHA-256，不排序对象键。它不是完整 HTTP 响应的字节哈希：保存的原始导出文件是此算法编码的 snapshot，来源元数据另存。不同语言的科学计数法、整数／小数输出可能不同（例如 `1e-7` 和 `1e-07`），不能直接假设任意 `JSON.stringify` 或 .NET 序列化都会匹配；客户连接器必须用具体数值样本核对字节与哈希。哈希不匹配时拒绝导入，不能跳过校验。接口不提供命令、表达式或模型写入端点。独立设计要求、支座和参考依据必须来自实际来源，不能由被检查模型反推。

维护人员在服务器配置 `STRATA_ETABS_URL` 和可选的 `STRATA_ETABS_TOKEN`。除本机开发地址外，必须使用 HTTPS；用户请求不能自行指定 URL。超时默认 15 秒，`STRATA_ETABS_TIMEOUT_SECONDS` 仅允许 0.1–60 秒。重定向、非 JSON 内容、模型／修订／profile 不一致、不支持的契约版本或映射、超限响应、缺少来源和字节变化都会被拒绝。`software_version` 必须为有界字符串，`exported_at` 必须含明确 UTC 时区。目前标准导出要求 m2、kN、kN/m2（组合响应为 kN）；其他单位要求显式适配，连接器不会猜测单位。工具能力页面区分“已配置”和“已实际验证”。

已登录 engineer 通过 `POST /api/v1/projects/{id}/connector/import` 导入。合法导出保存为原始文件和不可变快照，仍需经过规则验证及通常的 QA 流程。权限在网络请求前后都检查。相同项目内，模型、revision、profile、契约、软件版本及快照哈希相同时复用原始文件／快照，不改变当前输入或使已有确认无端失效；审计记录新观察到的导出时间，原文件的来源时间仍保留。不同项目、数据或导出软件版本不复用。配置连接器不会让真实客户数据自动获准使用旧版仅限合成案例的计算范围。

## 本轮可复现的模拟验证

```sh
python3.12 scripts/csi-mock-server.py --port 4188 --fault normal
```

这个服务只绑定 `127.0.0.1`，只提供 `M-SYNTHETIC`、`R-SYNTHETIC`、`synthetic-gravity`。输入与响应均为自制测试材料；不安装、调用或模拟真实 CSI 分析引擎。另一个终端在启动应用前设置 `STRATA_ETABS_URL=http://127.0.0.1:4188`。通过界面配置可用的 CSI 导入入口（或上述 API）使用这三个标识。

`--fault` 可选 `missing-field`、`wrong-unit`、`unsupported-version`、`wrong-revision`、`timeout`、`disconnect`、`duplicate-key`、`bad-hash`、`repeat-response`。故障测试时可把应用超时设为 `STRATA_ETABS_TIMEOUT_SECONDS=0.1`；默认合成 timeout 为 0.3 秒，方便可重复地触发超时。不要在真实工程联调中盲目复用这个测试超时。

```sh
python3.12 -m pytest backend/tests/test_connector.py backend/tests/test_connector_network.py backend/tests/test_connector_import.py -q
```

本轮已在实际 loopback TCP 上验证正常返回、缺字段、单位错误、不支持契约、断连、超时和重复响应，并通过 API 验证重复导入不改变当前 revision、项目隔离和请求中撤权。**这些是我们自制 HTTP 服务的契约结果，不是真实 ETABS/SAFE 联调，也不是工程准确率。**

真实联调验收需要客户 Windows 主机、实际 CSI 版本及许可、可安全只读的模型、已知正确／错误导出、批准的字段／单位映射和负责工程师的对照检查。mock 测试只验证 HTTP 边界；原生 CSI 适配器实现和互通仍需这些外部资源。
