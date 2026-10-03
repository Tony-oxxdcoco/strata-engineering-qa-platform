# 客户 CSI 连接器接口契约

STRATA 调用明确配置的 HTTP 服务。当前没有控制用户桌面、安装 CSI 或建立真实连接。`backend/strata/connector.py` 已实现请求客户端；客户 IT 工程师维护的 Windows 服务需要提供以下只读导出接口。

`POST /v1/export`

```json
{"contract":"strata-csi-export-1.0","model_id":"opaque-model-id","revision":"R1","profile":"approved-gravity-export","read_only":true}
```

响应保留相同标识，并包含 `software_version`、UTC 时间 `exported_at`、`snapshot`、`snapshot_sha256`、`read_only:true`。snapshot 是系统支持的标准 JSON 工程输入；哈希为 UTF-8 `JSON.stringify(snapshot)` 的 SHA-256，Unicode 不转义，不加入无意义空格，导出服务需保留数值表示。接口不提供命令、表达式或模型写入端点。独立设计要求、支座和参考依据必须来自实际来源，不能由被检查模型反推。

维护人员在服务器配置 `STRATA_ETABS_URL` 和可选的 `STRATA_ETABS_TOKEN`。除本机开发地址外，必须使用 HTTPS；用户请求不能自行指定 URL。重定向、模型／修订／profile 不一致、不支持的映射、超限响应、缺少来源和字节变化都会被拒绝。工具能力页面区分“已配置”和“已实际验证”。

已登录 engineer 通过 `POST /api/v1/projects/{id}/connector/import` 导入。合法导出保存为原始文件和不可变快照，仍需经过规则验证及通常的 QA 流程。配置连接器不会让真实客户数据自动获准使用旧版仅限合成案例的计算范围。

真实联调验收需要客户 Windows 主机、实际 CSI 版本及许可、可安全只读的模型、已知正确／错误导出、批准的字段／单位映射和负责工程师的对照检查。mock 测试只验证 HTTP 边界；原生 CSI 适配器实现和互通仍需这些外部资源。
