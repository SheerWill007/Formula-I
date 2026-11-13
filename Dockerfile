# Production image for the BoxUp API (Flask, apps/backend) plus the workspace
# packages it imports at runtime (ml, ingestion, shared config).
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv

# libgomp1: OpenMP runtime required by lightgbm / xgboost / scikit-learn.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.10.7 /uv /uvx /bin/

WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY apps/backend apps/backend
COPY packages packages

RUN uv sync --frozen --no-dev --no-cache \
    --package slipstream-backend \
    --package ml \
    --package slipstream-ingestion \
    --package slipstream-config

ENV PATH="/app/.venv/bin:$PATH" \
    FLASK_ENV=production \
    FASTF1_CACHE_DIR=/tmp/fastf1_cache \
    ML_MODELS_DIR=/tmp/ml_models \
    RACE_VECTOR_INDEX_DIR=/tmp/lancedb \
    TELEMETRY_ARTIFACT_DIR=/tmp/telemetry_artifacts \
    PORT=8000

COPY scripts/start-backend.sh /app/start-backend.sh
RUN chmod +x /app/start-backend.sh

WORKDIR /app/apps/backend
EXPOSE 8000
CMD ["/app/start-backend.sh"]
