# Optional server-side model task router

This is a temporary Node service bridge for the local demo, using the existing zero-dependency host. It keeps the provider API key on the server. It is not the planned shared FastAPI backend, a production service, or an engineering QA model. The ordinary task selector and deterministic checks remain usable without a model.

The integration has mock-based tests only. No live provider call, routing-quality evaluation, account access or model compatibility has been verified.

## What it sends and returns

Only the question text and a fixed catalogue are sent to the configured provider. The bridge does not attach model files, evidence, calculated values, review history, or credentials from the browser. Text the user puts in the question is still sent to that provider, so use synthetic, non-confidential questions for this demo.

The model can return one of:

| Task ID | Existing deterministic task |
| --- | --- |
| `gravity-full` | All six supported floor-gravity checks |
| `gravity-distribution` | Per-floor gravity-load distribution |
| `gravity-balance` | Independent reaction versus design-brief load balance |
| `load-combination` | Arithmetic for the supplied synthetic linear-static combination |
| `null` | Unsupported or unclear request |

It cannot return engineering values, rules, factors, tolerances or outcomes. A task selection is not PASS, FAIL, or engineering approval. The application must retain its own whitelist and run the actual deterministic checker after task selection.

## Configuration

Set these environment variables in the Node server process:

| Variable | Meaning |
| --- | --- |
| `STRATA_LLM_API_KEY` | Required provider credential; server only |
| `STRATA_LLM_MODEL` | Required explicit model identifier; no automatic or expensive default |
| `STRATA_LLM_BASE_URL` | Optional base URL; defaults to `https://api.openai.com/v1` |

Missing or invalid configuration disables model routing. Custom endpoints must use HTTPS; HTTP is accepted only for explicitly configured loopback services. Credentials in URL user-info, query strings and fragments are rejected. The bridge appends `/chat/completions`; configure a base URL, not the completed endpoint path. Redirects are rejected.

`.env.example` contains blanks, not a usable credential. The app does not automatically load `.env`. Prefer your development environment's secret configuration. If you deliberately create a private `.env` file, Node 20.11+ can load it explicitly:

```sh
node --env-file=.env scripts/serve.mjs
```

Do not commit that private file or copy it into `dist/`. Restart the server after changing its environment. The safe configuration endpoint reports only `enabled`, a generic provider label and the configured model name; it does not test the credential or reveal the URL/key.

## Handler contract

```js
modelRouterConfig(env) // {enabled:false} or {enabled:true, provider, model}
await routeWithModel({question}, {env, fetchImpl})
// {taskId, mode:'model', model}
// Unsupported: {taskId:null, mode:'model', model, reason}
```

`routeWithModel` rejects extra input fields, blank questions and questions longer than 2,000 JavaScript string characters. Errors are `ModelRouterError` instances with safe `message`, `code`, and `statusCode` values. No upstream body, network exception text or credential is copied into them.

The local host integrates `GET /api/model-config` and `POST /api/model-route`. The HTTP layer must enforce its fixed loopback origin, same-origin requests, JSON body limits and no permissive CORS. This module does not implement HTTP access control. The browser must explicitly select model routing; page load, configuration checks and normal local checks must not make a model request.

## Limits and failure behaviour

Each selected model-routing request makes at most one provider request, with no automatic retry or fallback model. The request uses one completion, `max_completion_tokens: 128`, `stream: false`, `store: false`, and strict JSON schema containing only `task_id`. The completion budget includes reasoning tokens; a chosen model may exhaust that budget or reject these parameters. In either case, routing fails safely and the user can select a local task. `store: false` is not a claim of zero provider retention or zero provider logging.

There is a 15-second deadline covering connection and body reading, plus a 64 KiB response limit enforced while reading bytes. Unsupported task IDs, additional or duplicate JSON fields, multiple completions/JSON blocks, markdown-wrapped JSON, refusals, truncated output and function/tool calls are rejected. Unsupported requests should return `task_id: null` rather than a fabricated task.

Provider charges can occur only after configuration enables the bridge and the user selects model routing. Failed, timed-out or rejected responses may still incur provider charges. Token limits are not a monetary budget or account-level spending cap; configure the provider's budget separately. No paid or live request was made while implementing or testing this module.

## Tests and official references

```sh
node --test tests/model-router.test.mjs
```

Tests inject `fetchImpl` and explicit fake environment values; they do not read a real credential or contact a model service.

The request shape was checked against the [official Chat Completions API reference](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create) and [Structured Outputs guide](https://developers.openai.com/api/docs/guides/structured-outputs). These document `response_format.json_schema`, completion token limits and incomplete/refused output. OpenAI-compatible providers must be checked separately for these capabilities; the bridge does not silently downgrade to free-form output.
