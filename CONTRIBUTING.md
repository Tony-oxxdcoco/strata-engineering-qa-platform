# Contributing

Use an issue or pull request to describe a reproducible problem, proposed change and affected contract. Use synthetic/minimized inputs; do not post customer files, credentials or account databases. Explain supported scope before adding a new engineering method.

Install development dependencies with `npm run setup:dev`. Run `npm test`, `npm run check`, `npm run check:i18n` and `.venv/bin/python -m pytest -q` (Windows: `.venv\Scripts\python.exe`). Focus new tests on failure modes and independently specified expectations. Preserve initial failures and distinguish simulated inputs from real engineering acceptance.

Keep deterministic tools separate from optional model routing. Models cannot change engineering numbers, verdicts, approval status or permission checks. Do not treat missing evidence as a default zero or a PASS. New formulas require registered implementations with independent verification, not prompt-only configuration.

Interface text belongs in both `web/locales/en.js` and `web/locales/zh-CN.js`; keep the existing JSON-compatible object format and run the diagnostic translation test. Preserve original engineering text, units, precision, project state and keyboard access when editing UI.

Do not commit `.runtime`, `.env`, private helper JSON, backup databases, model weights or raw confidential material. The release packager uses reviewed Git index paths; verify its manifest, exclusions and hashes when changing delivery. Preserve documented engineering and platform limits.
