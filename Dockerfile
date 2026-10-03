# Runtime-only image; build from demo/, never from the report directory.
FROM node:22-bookworm-slim AS node
FROM python:3.12-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/app/backend \
    STRATA_DATA_DIR=/app/.runtime

RUN apt-get update \
    && apt-get install --no-install-recommends -y ca-certificates libstdc++6 libatomic1 \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 strata \
    && useradd --uid 10001 --gid strata --create-home --shell /usr/sbin/nologin strata

COPY --from=node /usr/local/bin/node /usr/local/bin/node
WORKDIR /app
COPY backend/requirements.txt backend/constraints.txt /app/backend/
RUN python -m pip install --no-cache-dir -r /app/backend/requirements.txt \
    && node --version
COPY --chown=strata:strata backend/strata /app/backend/strata
COPY --chown=strata:strata web /app/web
COPY --chown=strata:strata dist /app/dist
COPY --chown=strata:strata scripts /app/scripts
COPY --chown=strata:strata docs/*evaluation*.json /app/docs/
# .js files imported by the Node bridge are ES modules.
COPY --chown=strata:strata package.json /app/package.json
RUN mkdir /app/.runtime && chown strata:strata /app/.runtime && chmod 700 /app/.runtime

USER 10001:10001
EXPOSE 4180
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import json,urllib.request; d=json.load(urllib.request.urlopen('http://127.0.0.1:4180/api/v1/health',timeout=3)); assert d['status']=='ok' and d['worker'] is True"
CMD ["python", "-m", "uvicorn", "strata.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "4180", "--workers", "1", "--no-proxy-headers"]
