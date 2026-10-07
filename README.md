# STRATA — Evidence-Grounded Engineering QA Platform

**English** · [简体中文](README.zh-CN.md)

STRATA is a local workspace for traceable engineering checks. It connects explicit input data, versioned rules and registered calculation tools, then presents each result with its sources, numerical evidence and review history.

The application works without a model or paid API. English and Simplified Chinese share the same data and calculation logic.

![STRATA running locally with an explicitly synthetic case](docs/frontend/screenshots/open-source-workspace.png)

## What it does

- **Import and map sources:** CSV, Excel (`.xlsx`), JSON, text, Markdown and text-based PDF. Save reusable field and unit mappings; inspect original values, normalized values and source locations. PDF text extraction does not reconstruct engineering tables automatically.
- **Manage rules:** validate, import and export rule packages; track versions, applicability, parameters, tolerances, citations and draft/approved/retired states. Configuration invokes implemented tools rather than arbitrary formulas or code.
- **Retrieve evidence:** BM25 retrieval with project, task, version and approval filtering, plus source citations.
- **Run controlled checks:** gravity QA, linear combination arithmetic, configuration checks and source-to-target comparisons within declared tool contracts. Display `PASS`, `FAIL` or `NOT VERIFIED` with calculations and missing-material requests.
- **Review changes:** preserve old snapshots and results, create linked rechecks, track findings and record human review. Changed dependencies invalidate old confirmations.
- **Share inspectable records:** HTML and JSON reports, project audit records, persistent storage and backup/recovery. Viewer, engineer and reviewer roles separate inspection, editing and approval.
- **Use a bilingual interface:** eight views with a light workspace and dark navigation, responsive layouts, local icons, table filtering/sorting/pagination and in-place language switching.

## How results are produced

```text
Source files → mapped snapshot → approved rules → registered tools
             → result and evidence → findings/recheck → human review
```

Deterministic tools produce engineering numbers and outcomes. An optional local model can route a natural-language request to a supported task; it cannot replace tool results or approve a design. Insufficient evidence produces `NOT VERIFIED` and an explicit request for material.

The stack is Python 3.12, FastAPI, SQLAlchemy with SQLite, Node.js calculation tools, and native JavaScript/CSS. There is no frontend framework or vector database dependency.

## Run locally

Install **Python 3.12** and **Node.js 20.11+**; Node.js 22 or 24 is recommended. First setup needs network access to install the declared Python dependencies.

```sh
git clone https://github.com/Tony-oxxdcoco/strata-engineering-qa-platform.git
cd strata-engineering-qa-platform
npm run setup
npm start
```

Open **http://127.0.0.1:4180** and create your own account. There is no preset username or password. Create a project and select **Load example** to try the included synthetic cases, then inspect the result and export a report.

Local accounts, uploads and saved records live in `.runtime/`. Keep this directory for persistence; exclude it from source sharing. Each installation owns its data.

## Docker

In a macOS/Linux shell, use the base `compose.yaml` with a separate Compose project and an available local port. This example uses port 4181 and persistent project-specific volumes:

```sh
export STRATA_SETUP_TOKEN="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
STRATA_PORT=4181 docker compose -p strata-local up -d --build
```

Open **http://127.0.0.1:4181**. Enter the generated operator setup token in the first-account form and choose your own account credentials. Keep the token local; it is separate from the login password. The base application starts without downloading a model.

Reuse the same project name and port when restarting to retain its data volumes. See [Docker configuration and verification](docs/DOCKER.md) for recorded scope and platform details; the commands above create a fresh local instance.

## Optional model and OCR

If Ollama is running and a model such as `qwen2.5:7b` is already installed, enable task routing when starting STRATA:

```sh
STRATA_OLLAMA_MODEL=qwen2.5:7b npm start
```

Manual task selection remains available. Model setup and resource requirements are separate from the base installation; `.env.example` lists the supported configuration.

Optional macOS Vision OCR requires Swift and `pdftoppm`, with `STRATA_OCR_ENABLED=1`. Scanned pages retain the original image, recognition text and correction history. Numbers, signs, units and table alignment require human checking before confirmed transcription can support a check. OCR is not enabled in the Linux container.

## Validation

Run the current checkout's checks:

```sh
npm run setup:dev
npm test
npm run check
npm run check:i18n
.venv/bin/python -m pytest -q
```

On Windows, use `.venv\Scripts\python.exe` for the final command. [Current release verification](docs/RELEASE_VERIFICATION.md) and [frontend verification notes](docs/frontend/VERIFICATION.md) and [recorded receipts](docs/frontend/) retain their source version, environment, failures and unverified scope. Test counts and synthetic-case matches are software evidence, not engineering accuracy claims.

## Extending STRATA

| Change | Entry point |
|---|---|
| File formats, aliases and unit mappings | `backend/strata/adapters.py`, `backend/strata/data_tools.py` |
| Rule contracts and package validation | `backend/strata/contracts.py`, `backend/strata/adaptation_api.py` |
| Registered checks and workflow | `backend/strata/data_tools.py`, `dist/`, `backend/strata/workflow.py` |
| Evidence retrieval and task routing | `backend/strata/knowledge.py`, `backend/strata/model.py` |
| Independent cases and evaluation | `backend/strata/cases.py`, `examples/`, `backend/tests/` |
| UI components and translations | `web/ui-foundation.js`, `web/design-system.css`, `web/locales/` |

See [the adaptation guide](CLIENT_ADAPTATION.md) for concrete extension procedures. A new engineering method needs an implemented tool and independent validation; changing a prompt or rule parameter does not add a verified method.

## Scope and limits

- Included rules, data and expected answers are explicitly synthetic test materials. A software `PASS` is not structural certification or an engineer's acceptance.
- Controlled gravity and numerical combination profiles are restricted to synthetic inputs. Combination arithmetic assumes linear static responses; configuration comparisons check supplied criteria rather than establish code compliance.
- The read-only ETABS/SAFE connector has a tested simulated contract. Integration with licensed Windows software and real engineering models requires separate validation.
- Recorded installation and browser evidence covers specified environments. Native Windows/Linux installers, real mobile devices/Safari, production deployment and independent engineering acceptance have outstanding verification requirements.

## Contributing and license

See [CONTRIBUTING.md](CONTRIBUTING.md) for contribution guidelines. Source is available under the [MIT License](LICENSE).
