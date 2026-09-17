# Local Development

This guide is for contributors running Slipstream on their own machine.

It focuses on:

- local infrastructure
- safe environment settings
- migrations and seed data
- testing
- recovery from common broken states

## Local defaults

Slipstream is designed to work locally without hosted infrastructure.

Default local services:

- Postgres / TimescaleDB: `localhost:5432`
- Redis: `localhost:6379`
- Kafka: `localhost:9092`
- MLflow: `http://localhost:5001`

Default local database URL:

```bash
postgresql+psycopg://pitwall:pitwall@localhost:5432/pitwall
```

Backend and ML both fall back to this local URL if you do not override it.

Relevant config files:

- [apps/backend/src/backend/config.py](/Users/abdullahmusharaf/Desktop/F1/Slipstream/apps/backend/src/backend/config.py)
- [packages/ml/src/ml/config.py](/Users/abdullahmusharaf/Desktop/F1/Slipstream/packages/ml/src/ml/config.py)

## Recommended setup

### 1. Install dependencies

```bash
make install
```

### 2. Start infrastructure

```bash
make up
```

### 3. Run migrations

```bash
make migrate
```

### 4. Ingest sample data

```bash
make seed
```

### 5. Start the app

Backend:

```bash
make backend
```

Frontend:

```bash
make frontend
```

## Safe env habits

### Use local DB for local work

For day-to-day development, keep `.env` local:

```bash
DATABASE_URL=postgresql+psycopg://pitwall:pitwall@localhost:5432/pitwall
```

This matters because tests, backend dev runs, and ML training all read `DATABASE_URL`.

### Do not leave Railway credentials in `.env`

Use Railway credentials only when you are intentionally:

- migrating production
- re-ingesting production sessions
- verifying deployed data

Otherwise local commands may accidentally hit a hosted database.

## Testing

### Backend tests

Run:

```bash
uv run --project apps/backend python -m pytest apps/backend/tests
```

Expected behavior:

- tests create their own schema in the configured database
- they should be run against local Postgres, not Railway

### Frontend tests

Run:

```bash
pnpm -C apps/frontend test
pnpm -C apps/frontend exec tsc --noEmit
```

## ML training locally

Run:

```bash
UV_CACHE_DIR=/tmp/uv-cache MPLCONFIGDIR=/tmp/matplotlib uv run python -m ml.train
```

Why those env vars help:

- `UV_CACHE_DIR` avoids permission issues with a protected global uv cache
- `MPLCONFIGDIR` avoids Matplotlib cache warnings on systems where the default config path is not writable

## Common local failures

### `relation "sessions" does not exist`

Meaning:

- local DB is reachable
- schema has not been created

Fix:

```bash
make up
make migrate
```

### Alembic upgrade fails because a table does not exist

Meaning:

- local DB is in a broken migration state
- Alembic version history and actual schema no longer match

Fix:

Reset the local schema and rerun migrations:

```bash
psql "postgresql://pitwall:pitwall@localhost:5432/pitwall" -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"
cd apps/backend
UV_CACHE_DIR=/tmp/uv-cache uv run alembic upgrade head
```

Then re-ingest sample data.

### Password authentication failed for Railway during a local command

Meaning:

- your shell or `.env` still points to Railway

Check:

```bash
echo $DATABASE_URL
grep DATABASE_URL .env
```

Fix:

- unset the shell variable if needed
- replace `.env` with the local database URL

### `KeyError: 'team_name'` during ML training

Cause:

- there is no FP2 data for the loaded history set

Current behavior:

- this is now handled safely with neutral fallback values

## Local reset recipe

If local state gets messy, this sequence usually gets you back to a clean baseline:

```bash
make down
make up
psql "postgresql://pitwall:pitwall@localhost:5432/pitwall" -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"
make migrate
make seed
```

Then rerun backend, frontend, or tests.

## Contributor guidance

When debugging locally:

- prefer local Postgres over Railway
- keep production re-ingest work separate from local testing
- verify data shape with simple SQL before assuming the frontend or model is wrong

## Related docs

- [docs/ingestion.md](/Users/abdullahmusharaf/Desktop/F1/Slipstream/docs/ingestion.md)
- [docs/deployment.md](/Users/abdullahmusharaf/Desktop/F1/Slipstream/docs/deployment.md)
- [docs/ml-race-prediction.md](/Users/abdullahmusharaf/Desktop/F1/Slipstream/docs/ml-race-prediction.md)
