# Maintenance checkpoint — 1.4.1

Canonical repository: https://github.com/Tony-oxxdcoco/strata-engineering-qa-platform . Maintainer commits use Haoyang Tian and the account-associated GitHub noreply address. Published history is mapped in [SOURCE_HISTORY.md](SOURCE_HISTORY.md); original private history remains recoverable separately.

Completed: the unified frontend; bilingual interface; controlled tools/evidence/review; generic public installation, license and contribution guides; all historical source versions without private hosting/course manuscripts; current local regression and actual isolated Docker build/workflow/persistence/recovery. See [release verification](RELEASE_VERIFICATION.md) and the latest Release attachments for exact source/image/archive bindings. Earlier frontend/model/retrieval receipts remain historical records.

Resume by checking `git status --short` and `git log -1`, then the latest release receipt. Avoid modifying a real runtime directory or repeating unaffected tests. Local data and private backups are excluded from Git and distribution. Start with `npm run setup`, `npm start`; see [Docker](DOCKER.md) for an independent persisted container instance. Current runtime assets do not require a paid API or model.

Validate relevant changes with `npm test`, `npm run check`, `npm run check:i18n`, and `.venv/bin/python -m pytest backend/tests tests -q`. Development dependencies come from `npm run setup:dev`. Pack reviewed/staged source using `.venv/bin/python scripts/package-release.py`; check ZIP CRC, per-file manifest and forbidden/private paths. Never publish `.runtime`, private environment files or recovery bundles.

Remaining external verification: independently approved real engineering inputs/rules/expected answers, engineer acceptance, licensed Windows CSI, optional model container/OCR/platform paths and deployment policy. Follow [input requirements](INPUT_REQUIREMENTS.md) and [adaptation guide](../CLIENT_ADAPTATION.md); do not invent missing units, engineering standards, authority or benchmark truths. No automatic further feature expansion is scheduled.
