# Local Docker

Base application uses FastAPI/SQLite, the registered Node calculation tools and local web assets. ETABS/SAFE is not a Linux container dependency. Optional models are off by default; macOS Vision OCR is unavailable in Linux and manual transcription/review remains the path.

For macOS/Linux with Docker Desktop/Engine and Compose 2.24.4 or newer:

```sh
export STRATA_SETUP_TOKEN="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
STRATA_PORT=4181 docker compose -p strata-local up -d --build
STRATA_PORT=4181 docker compose -p strata-local ps
```

Open http://127.0.0.1:4181, enter the local setup token in the first-account form and choose your own credentials. The token is distinct from your login password and must not be posted in a screenshot or source. The base process does not wait for a model download.

PowerShell equivalents:

```powershell
$env:STRATA_SETUP_TOKEN = python -c "import secrets; print(secrets.token_urlsafe(32))"
$env:STRATA_PORT = "4181"
docker compose -p strata-local up -d --build
docker compose -p strata-local ps
```

Reuse the same Compose project name to retain its runtime named volume. Do not use `down -v` or global prune as a reset method. Health is `/api/v1/health`. The volume must remain writable by container UID 10001. First build needs network access to base images and declared packages; later use can be local.

The supplied Compose file has an optional `model` profile. Its Ollama service shares the application’s network namespace, so the application connects to that service at `127.0.0.1:11434`. Leave `STRATA_OLLAMA_MODEL` empty for the verified model-free base application. Enabling the profile and preparing its model are separate optional steps; this release did not verify the model container or its download path.

A host-installed Ollama service requires an explicit host address and network configuration. Docker Desktop provides `host.docker.internal` for host access; Linux setups require their own configured route/address. These host model connections were not tested here, and changing the model name alone does not configure them.

Prior actual Linux arm64/macOS host workflow, persistence and independent-volume restore evidence is in `frontend/docker-verification.json`; final 1.4.0 runtime binding is a separate historical receipt. The latest release adds its own source/image/package bindings beside the release archive rather than relabels old scores. Native Windows/Linux installers, real CSI and customer engineering are separate verification scopes.
