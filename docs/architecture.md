# Architecture

Slipstream is an F1 analytics monorepo built around one shared database and several focused services.

This document is the "map" of the project:

- where data comes from
- where it is stored
- which service reads it
- how the frontend and ML layers sit on top

## System overview

```mermaid
flowchart LR
    A["FastF1 / public APIs"] --> B["Ingestion package"]
    B --> C["TimescaleDB / PostgreSQL"]
    C --> D["Backend API (Flask)"]
    C --> E["ML package"]
    D --> F["Next.js frontend"]
    E --> D
    G["Celery worker / beat"] --> B
    G --> E
    H["Redis"] --> G
    I["Kafka (roadmap / worker infra)"] --> G
    J["MLflow"] --> E
```

## Main components

### Frontend

Path: [apps/frontend](/Users/abdullahmusharaf/Desktop/F1/Slipstream/apps/frontend)

Responsibilities:

- render session lists, session detail pages, and overview pages
- show telemetry overlays, race analysis, practice analysis, and schedule views
- host the Race Intelligence page (driver scores, battle gaps, stint insights)
- call backend API routes
- host the emerging predictions UI

Tech:

- Next.js App Router
- TypeScript
- Tailwind CSS
- Vitest for unit tests

### Backend API

Path: [apps/backend](/Users/abdullahmusharaf/Desktop/F1/Slipstream/apps/backend)

Responsibilities:

- expose session, lap, driver, telemetry, strategy, and analysis endpoints
- read from TimescaleDB
- serve the frontend with compact API responses
- provide prediction endpoints as the ML layer matures

Important route groups:

- `sessions`
- `drivers`
- `laps`
- `telemetry`
- `analysis` (includes `race-intelligence`, `quali-segments`, etc.)
- `strategy`
- `schedule`
- `predictions`

### Ingestion

Path: [packages/ingestion](/Users/abdullahmusharaf/Desktop/F1/Slipstream/packages/ingestion)

Responsibilities:

- fetch FastF1 session data
- transform it into the project schema
- load sessions, drivers, lap times, telemetry, and weather into the database
- re-run safely by deleting/reinserting a session's data

Notable behavior:

- qualifying telemetry is stored only for segment-best laps (`best Q1`, `best Q2`, `best Q3`)
- `lap_times.quali_segment` is persisted so qualifying telemetry comparison does not depend on runtime boundary detection

### ML

Path: [packages/ml](/Users/abdullahmusharaf/Desktop/F1/Slipstream/packages/ml)

Responsibilities:

- build features from qualifying, historical race results, and optional FP2 data
- train a race-finish prediction model
- run inference for unseen qualifying sessions
- log training runs to MLflow

See [docs/ml-race-prediction.md](/Users/abdullahmusharaf/Desktop/F1/Slipstream/docs/ml-race-prediction.md) for the detailed feature and session requirements.

### Workers

Path: [packages/workers](/Users/abdullahmusharaf/Desktop/F1/Slipstream/packages/workers)

Responsibilities:

- background ingestion
- scheduled monitoring
- training and stats tasks
- retention / maintenance tasks

These are designed to run with Celery, Redis, and the local infrastructure stack.

### Stream

Path: [packages/stream](/Users/abdullahmusharaf/Desktop/F1/Slipstream/packages/stream)

Purpose:

- reserved for live or near-live data handling
- currently a roadmap-oriented component, not the core local flow

## Data flow

### Ingestion flow

1. A session is requested via `ingestion.ingest_session`.
2. FastF1 data is loaded and normalized.
3. Session rows are written to the database.
4. Drivers, lap times, weather, and optional telemetry are stored.
5. Backend analysis endpoints read the stored data directly.

### Qualifying telemetry flow

1. Qualifying laps are ingested into `lap_times`.
2. Each qualifying lap is tagged with a persisted `quali_segment`.
3. Telemetry is stored only for each driver's best lap in `Q1`, `Q2`, and `Q3`.
4. The frontend segment tabs use `/analysis/quali-segments` to resolve the correct lap per driver.
5. The frontend then calls `/telemetry/compare` with pinned lap numbers.

### ML flow

1. Historical `Q + R` pairs are loaded from the database.
2. Feature rows are built per driver per weekend.
3. FLAML trains a regression model for finish position.
4. The model is saved under `ml_models/`.
5. Inference builds the same feature set from a current qualifying session plus historical context.

## Shared infrastructure

Infrastructure file: [infra/docker-compose.yml](/Users/abdullahmusharaf/Desktop/F1/Slipstream/infra/docker-compose.yml)

Local services:

- TimescaleDB on `localhost:5432`
- Redis on `localhost:6379`
- Kafka on `localhost:9092`
- MLflow on `http://localhost:5001`
- Kafka UI on `http://localhost:8080`

Default local database URL:

```bash
postgresql+psycopg://pitwall:pitwall@localhost:5432/pitwall
```

## Design principles

### One database, many readers

Ingestion owns writing. Backend and ML mostly read from the same schema, which keeps analytics and prediction features aligned.

### Persist important derived metadata

When a derived concept is critical to UX or correctness, store it in the database instead of recomputing it at request time. `quali_segment` is the clearest example.

### Keep telemetry selective

Telemetry is high-volume data, so Slipstream stores it only where it adds clear product value. Right now that means segment-best qualifying laps rather than every lap of every session.

### Prefer reproducible local defaults

Backend and ML both default to local services and load `.env` only as a convenience. This makes local development safer than pointing directly at hosted infrastructure.
