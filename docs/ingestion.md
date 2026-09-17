# Ingestion

Slipstream ingestion turns raw FastF1 session data into the database tables used by the backend, frontend, and ML pipeline.

This guide explains:

- what gets ingested
- what is stored for each session type
- how reruns behave
- what to do when ingestion goes wrong

## Entry point

Primary command:

```bash
uv run python -m ingestion.ingest_session --year 2026 --gp "Australian" --session Q
```

Package path:

- [packages/ingestion/src/ingestion/ingest_session.py](/Users/abdullahmusharaf/Desktop/F1/Slipstream/packages/ingestion/src/ingestion/ingest_session.py)

Core modules:

- [fastf1_client.py](/Users/abdullahmusharaf/Desktop/F1/Slipstream/packages/ingestion/src/ingestion/fastf1_client.py)
- [loader.py](/Users/abdullahmusharaf/Desktop/F1/Slipstream/packages/ingestion/src/ingestion/loader.py)
- [database.py](/Users/abdullahmusharaf/Desktop/F1/Slipstream/packages/ingestion/src/ingestion/database.py)

## What gets stored

### Sessions

Stored in `sessions`.

Includes:

- session key
- year
- GP name
- session type and name
- date range
- country
- weather summary fields

### Drivers

Stored in `drivers`.

Includes:

- driver number
- abbreviation
- team name
- team colour

### Lap times

Stored in `lap_times`.

Includes:

- lap number
- lap time
- sector times
- compound
- tyre life
- track status
- position
- deletion flag
- `quali_segment` for qualifying sessions

### Telemetry

Stored in `telemetry`.

Includes sampled per-distance/per-time telemetry points used for:

- speed traces
- throttle / brake overlays
- telemetry stats

In hosted low-storage mode, raw samples are written as compressed telemetry
artifacts instead:

- set `TELEMETRY_STORAGE_MODE=files`
- set `TELEMETRY_ARTIFACT_DIR` to the artifact root
- metadata is stored in `telemetry_artifacts`
- old raw rows for that session are deleted from `telemetry`

The backend telemetry API checks the database first, then falls back to the
artifact metadata and compressed file. Frontend callers do not need to know
which storage mode was used.

### Weather

Session-level weather summary is written to `sessions`.

## Session-type behavior

### Qualifying (`Q`)

Slipstream stores:

- lap times for all qualifying laps
- persisted `quali_segment` metadata on `lap_times`
- telemetry only for each driver's best lap in `Q1`, `Q2`, and `Q3`

Why:

- qualifying comparison needs rich telemetry
- storing every qualifying lap's telemetry would be much larger with little UI benefit
- storing selected traces as artifacts keeps hosted Postgres small

### Race (`R`)

Slipstream stores:

- lap times
- positions
- stint and strategy-relevant fields
- race results derived from lap progression

Telemetry is not the main focus for race ingestion in the current product flow.

### Practice (`FP2` and others)

Slipstream stores:

- lap times
- compounds
- sector pace

FP2 is especially useful for the ML strategy signal because it is the most race-representative practice session.

## Rerun behavior

Slipstream uses a delete-then-insert pattern for session reloads.

Why:

- it avoids fragile upsert logic on hypertables
- it keeps reruns deterministic
- it is safe for "re-ingest this session" workflows

In practical terms, rerunning ingestion for a session should replace that session's derived rows cleanly.

## Qualifying segment behavior

Qualifying segment handling is important enough to call out separately.

Current design:

- each qualifying lap gets a stored `quali_segment`
- `/analysis/quali-segments` reads the stored segment data first
- qualifying telemetry is aligned to those stored segments

This avoids runtime ambiguity and prevents frontend segment tabs from drifting away from the data actually stored in `telemetry`.

## Recommended ingest order

### For local app exploration

```bash
uv run python -m ingestion.ingest_session --year 2026 --gp "Australian" --session Q
uv run python -m ingestion.ingest_session --year 2026 --gp "Australian" --session R
uv run python -m ingestion.ingest_session --year 2026 --gp "Australian" --session FP2
```

### For ML training

Ingest many paired weekends:

- `Q`
- `R`
- optionally `FP2`

The model trains only on weekends that have both qualifying and race sessions.

## Common ingestion issues

### Missing tables locally

Symptom:

- `relation "sessions" does not exist`

Cause:

- local database schema has not been created yet

Fix:

1. Start local infra with `make up`
2. Run migrations with `make migrate` or Alembic directly
3. Re-run ingestion

### Qualifying segment data exists in `lap_times` but UI still shows empty Q2/Q3

Cause:

- backend is still running old code
- or the target qualifying sessions were not re-ingested after the migration

Fix:

1. deploy backend code that reads stored `quali_segment`
2. run migration `0010`
3. re-ingest the target qualifying sessions

### FP2 missing for ML training

Cause:

- no FP2 session was ingested for that weekend

Current behavior:

- training and inference fall back to neutral FP2 strategy features
- this is allowed and no longer crashes the pipeline

### Railway vs local database confusion

Cause:

- `.env` or shell `DATABASE_URL` points at Railway while you think you are running locally

Fix:

- use local Postgres for local development
- reserve Railway credentials for deploy and production ingestion tasks

## Useful verification queries

Check whether qualifying segment metadata exists:

```sql
SELECT session_key, driver_number, lap_number, quali_segment
FROM lap_times
WHERE session_key = 11241
ORDER BY driver_number, lap_number;
```

Check how much qualifying telemetry was stored:

```sql
SELECT session_key, COUNT(DISTINCT (driver_number, lap_number)) AS driver_laps
FROM telemetry
WHERE session_key = 11241
GROUP BY session_key;
```

## Related docs

- [docs/architecture.md](/Users/abdullahmusharaf/Desktop/F1/Slipstream/docs/architecture.md)
- [docs/ml-race-prediction.md](/Users/abdullahmusharaf/Desktop/F1/Slipstream/docs/ml-race-prediction.md)
- [README.md](/Users/abdullahmusharaf/Desktop/F1/Slipstream/README.md)
