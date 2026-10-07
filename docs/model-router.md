# 旧版可选服务端模型任务路由

本文记录旧 demo 的 Node 路由桥，沿用零依赖静态服务，把模型 API Key 放在服务端。它不是新版 FastAPI 后端，也不是工程 QA 模型。手动任务选择及确定性检查不依赖模型。

该旧桥只完成 mock 测试，没有真实模型服务调用、路由质量、账号访问或模型兼容性验证。新版已实测的本地 Qwen 路由位于 `backend/strata/model.py`，结果见 [历史验证](../VALIDATION.md)，两者不能混用验收结论。

## 发送与返回内容

只发送问题文字和固定任务目录，不附工程文件、证据、计算值、复核历史或浏览器凭据。用户写在问题里的文字仍会发给已配置服务，所以旧 demo 只使用合成、非机密问题。

模型只可返回以下任务之一或 null：

| 任务 ID | 对应确定性任务 |
|---|---|
| `gravity-full` | 六项受支持楼层重力检查 |
| `gravity-distribution` | 各楼层重力荷载分布 |
| `gravity-balance` | 独立反力与设计要求荷载平衡 |
| `load-combination` | 给定合成线性静力组合算术 |
| `null` | 不支持或不清楚的请求 |

不允许返回工程数值、规则、因子、容差或判定。选择任务不等于 PASS／FAIL 或工程批准。应用仍须执行自己的白名单和确定性检查。

## 配置

在 Node 服务进程中设置：

| 环境变量 | 含义 |
|---|---|
| `STRATA_LLM_API_KEY` | 必需服务凭据，只在服务器保存 |
| `STRATA_LLM_MODEL` | 必需明确模型标识，不自动采用可能昂贵的默认值 |
| `STRATA_LLM_BASE_URL` | 可选基础地址，默认 `https://api.openai.com/v1` |

配置缺失或无效时关闭路由。自定义端点必须 HTTPS，HTTP 只接受明确配置的本机地址。URL 中的账号、查询参数和 fragment 被拒绝。服务追加 `/chat/completions`，应配置基础 URL 而不是完整端点；不接受重定向。

`.env.example` 只有空值，不是凭据。应用不自动加载 .env，优先使用开发环境的密钥配置。如果自行创建私有 .env，Node 20.11+ 可以明确加载：

```sh
node --env-file=.env scripts/serve.mjs
```

不要提交该文件或复制进 dist。更改环境后重启。安全配置端点只报告 enabled、通用服务标签和模型名称，不测试凭据，也不泄露 URL／Key。

## 调用契约

```js
modelRouterConfig(env) // {enabled:false} or {enabled:true, provider, model}
await routeWithModel({question}, {env, fetchImpl})
// {taskId, mode:'model', model}
// Unsupported: {taskId:null, mode:'model', model, reason}
```

routeWithModel 拒绝额外输入字段、空问题和超过 2,000 个 JavaScript 字符的问题。错误为 ModelRouterError，message／code／statusCode 经过安全处理，不附上游正文、网络异常细节或凭据。

本地服务集成 `GET /api/model-config` 和 `POST /api/model-route`。HTTP 层需要限定本机 Origin、同源请求、JSON 大小，不开放宽松 CORS；本模块本身不实现 HTTP 权限。浏览器必须明确选择模型路由，加载页面、配置检查和普通本地检查不能触发模型请求。

## 限制与故障行为

每次模型路由最多发出一次服务请求，不自动重试或换模型。请求使用一份 completion、`max_completion_tokens: 128`、`stream: false`、`store: false`，严格 JSON 结构只有 task_id。completion 预算含推理 token，模型可能耗尽预算或不支持参数；失败后安全停止，用户可手动选择任务。store:false 不代表服务端完全不保留或记录。

连接及正文读取总超时 15 秒，读取时限制响应 64 KiB。不支持 task ID、额外或重复 JSON 字段、多个 completion／JSON 块、Markdown 包裹 JSON、拒答、截断和函数／工具调用均拒绝。不支持请求应返回 task_id:null，不编造任务。

只有配置启用且用户选择模型路由后才可能产生服务费用。失败、超时或拒绝的请求仍可能收费；token 限制不是金额预算或账号消费上限，服务预算需另行设置。开发与测试此旧模块时没有真实或付费调用。

## 测试与官方参考

```sh
node --test tests/model-router.test.mjs
```

测试注入 fetchImpl 和明确的模拟环境值，不读取真实凭据，不访问模型服务。

请求结构依据 [官方 Chat Completions API](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create) 和 [Structured Outputs 指南](https://developers.openai.com/api/docs/guides/structured-outputs)，包括 response_format.json_schema、completion token 限制及截断／拒答行为。兼容 API 的其他服务需要单独验证这些能力，不自动降级成自由文本输出。
