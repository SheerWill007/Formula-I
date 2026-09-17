# Deployment

This guide covers the practical deployment flow for Slipstream's current stack.

Today that usually means:

- backend on Railway
- frontend on Vercel
- Postgres on Railway, Neon, or Supabase
- optional compressed telemetry artifacts outside Postgres

The most important deployment rule in this project is:

> deploy backend code, database changes, and re-ingestion in the right order

That matters especially for qualifying telemetry and any feature that stores derived metadata.

## Deployment responsibilities

### Backend

Responsible for:

- API routes
- SQL queries
- analysis logic
- prediction endpoints

Backend changes must be deployed before the frontend depends on new response shapes or semantics.

### Frontend

Responsible for:

- rendering UI based on backend responses
- segment-aware selection logic
- prediction UI

Frontend deploys should generally happen after backend deploys for data-shape changes.

### Database

Responsible for:

- schema changes
- migration state
- stored derived metadata such as `quali_segment`
- compact analytics and artifact metadata

The main database should stay relational. Keep `sessions`, `drivers`,
`lap_times`, `race_results`, prediction rows, and telemetry summaries in
Postgres. Raw telemetry can be stored outside the database when hosted storage
is tight.

### Ingestion

Responsible for:

- populating new columns or newly required derived fields
- aligning stored telemetry and lap metadata after schema changes

## Recommended deploy order

### For backend-only logic changes

1. Deploy backend
2. Verify target endpoints manually
3. Deploy frontend if needed

### For schema changes

1. Deploy backend code that can work with the new schema
2. Run DB migrations
3. Re-ingest sessions that need the new stored fields
4. Verify data in the database or via API
5. Deploy frontend if the UI depends on that new behavior

## Qualifying telemetry checklist

This is the most important concrete deploy recipe in the repo today.

When shipping `Q1/Q2/Q3` telemetry changes:

1. Deploy backend code that reads stored `quali_segment`
2. Run database migrations
3. Re-ingest the qualifying sessions that need segment comparison
4. Verify `/analysis/quali-segments`
5. Verify pinned-lap telemetry compare
6. Deploy frontend
7. Hard refresh and confirm the telemetry UI updates correctly

Verification endpoints:

- `GET /api/v1/sessions/:key/analysis/quali-segments`
- `GET /api/v1/sessions/:key/telemetry/compare?drivers=12,63&laps=12:8,63:5`

Expected behavior after a correct deploy:

- `Q2` and `Q3` are populated where appropriate
- `Q2_start_lap` and `Q3_start_lap` are not `null`
- the frontend segment tabs show different lap badges and overlays

## Environment variables to verify

### Backend / Railway

Check:

- `DATABASE_URL`
- `TELEMETRY_ARTIFACT_DIR` if raw telemetry is stored as compressed artifacts
- `ML_MODELS_DIR` if deployed predictions need persisted model files
- `AUTO_INGEST_ENABLED` if you want to disable the built-in backend scheduler
- `AUTO_INGEST_INTERVAL_MINUTES` to control how often production checks for new sessions
- `REDIS_URL` if workers are in use
- `KAFKA_BOOTSTRAP_SERVERS` if stream/worker features depend on it
- `MLFLOW_TRACKING_URI` if training/registry behavior depends on it

### Ingestion

Check:

- `DATABASE_URL`
- `TELEMETRY_STORAGE_MODE`
- `TELEMETRY_ARTIFACT_DIR`

`TELEMETRY_STORAGE_MODE=database` keeps raw samples in the `telemetry` table.
This is useful locally with TimescaleDB.

`TELEMETRY_STORAGE_MODE=files` writes one compressed `json.gz` artifact per
session/driver/lap and stores only metadata in `telemetry_artifacts`. This is
the cheaper hosted mode for Neon/Supabase-style databases.

Example hosted setting:

```bash
TELEMETRY_STORAGE_MODE=files
TELEMETRY_ARTIFACT_DIR=/app/telemetry_artifacts
```

Railway files are not durable unless you attach a volume. Use this mode for
testing or with a persistent volume first; move the artifact directory to object
storage such as Cloudflare R2 when telemetry becomes a production feature.

### Frontend / Vercel

Check:

- API base URL points to the correct backend deployment

### Local shell before production commands

Before running migration or re-ingest commands against Railway, verify:

```bash
echo $DATABASE_URL
```

This avoids accidentally pointing operational commands at the wrong database.

## Railway operational notes

### Single-service deployments

This repo now starts a lightweight auto-ingest scheduler inside the backend process for production-style runs.

Why:

- Railway is often running only the Flask web service from `railway.json`
- in that setup, Celery beat and worker schedules do not exist unless you deploy separate worker services
- the backend scheduler closes that gap by periodically calling `ingestion.auto_ingest`

Safety:

- runs are guarded by a PostgreSQL advisory lock so only one instance ingests at a time
- local `flask --debug` and tests do not start the scheduler by default

### Deployed ML predictions

Slipstream's deployed predictions can train on demand from the web service when a request arrives and no model file exists yet.

Practical implications:

- the first prediction request after a fresh deploy may be slow
- model files should live in a persistent directory such as `/app/ml_models`
- `ML_MODELS_DIR=/app/ml_models` should be set on the deployed backend
- if `MLFLOW_TRACKING_URI` is unreachable, training continues and only the tracking/logging step is skipped

This is the simplest production path when you do not want a separate long-running trainer service.

### Rotate exposed credentials immediately

If a Railway database password is ever pasted in chat, logs, screenshots, or shell history:

1. rotate it in Railway
2. update Railway environment variables
3. update any local or CI secrets that still reference it
4. remove stale values from `.env`

### Keep local and hosted environments separate

Recommended pattern:

- local `.env` uses local Postgres
- Railway dashboard holds production `DATABASE_URL`
- shell exports are used temporarily for production maintenance only

## CI and test safety

Do not point tests at Railway.

Backend tests should use local Postgres or a dedicated test database. A remote production-like database introduces:

- accidental data mutation risk
- flaky auth and network dependencies
- harder-to-debug failures

## Manual verification checklist

After deploy, check:

1. `/health`
2. session list loads
3. target session page loads
4. telemetry compare works for a known qualifying session
5. any new endpoint returns the expected shape
6. if ML changed, training or inference still runs against the intended environment

For ML specifically:

1. hit a known qualifying predictions endpoint once and expect the first request to take longer if the model is being built
2. confirm later requests are much faster
3. confirm the response includes model metadata rather than `503 Model not trained`

## Rollback mindset

If something is wrong after deploy:

- first confirm backend version and environment variables
- then confirm migration state
- then confirm whether the target sessions were re-ingested

For data-backed features, code-only rollback is often not enough if the issue is really stale or missing ingested data.

## Related docs

- [docs/local-development.md](/Users/abdullahmusharaf/Desktop/F1/Slipstream/docs/local-development.md)
- [docs/ingestion.md](/Users/abdullahmusharaf/Desktop/F1/Slipstream/docs/ingestion.md)
- [README.md](/Users/abdullahmusharaf/Desktop/F1/Slipstream/README.md)
