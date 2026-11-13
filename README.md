# BoxUp: Formula 1 Data Analytics Platform

BoxUp is a Formula 1 analytics platform for exploring race sessions, qualifying
telemetry, tyre strategy, driver profiles and race predictions, built on public
motorsport data.

## Features

- **Sessions & telemetry**: lap times, sector analysis, speed traces, braking and corner insights
- **Strategy**: stints, race order, race-intelligence insights
- **Driver profiles**: career stats, season heatmap, driving-style radar, career trajectory
- **Race predictions** (sign-in required): podium probabilities from a gradient-boosted model
- **Calendar & standings**, plus a **blog** with model write-ups
- **Pitwall AI agent / analyst** (backend only for now, needs an OpenRouter key)

## Architecture

| Part | Where | Notes |
| --- | --- | --- |
| Frontend (`apps/frontend`) | Vercel | Next.js 15, React 19. Clerk sign-in gates `/predictions` only. |
| API (`apps/backend`) | Render (Docker) | Flask + SQLAlchemy. Runs `alembic upgrade head` on every start. |
| Database | Neon Postgres | Sessions, laps, results, trained model files (`ml_model_files`). |
| Ingestion (`packages/ingestion`) | GitHub Actions | FastF1, with an OpenF1 fallback now that F1's live-timing feed needs a login. |
| Model training (`packages/ml`) | GitHub Actions | Publishes the model to Postgres; the API restores it on first prediction. |

### Workflows

- `.github/workflows/ingest.yml`: weekly (Monday 06:00 UTC) ingest of new sessions, then retrain.
- `.github/workflows/backfill.yml`: one-off historical backfill by year (OpenF1 covers 2023+).
- `.github/workflows/train.yml`: retrain on demand.
- `.github/workflows/ci.yml`: backend tests, lint and frontend build on every push.

All three data workflows need the `DATABASE_URL` repository secret.

## Run locally

Requirements: Python 3.11+, [uv](https://docs.astral.sh/uv/), Node.js 22, pnpm 9 and Docker Compose.

```bash
make install
make up        # Postgres/TimescaleDB, Redis, Kafka via infra/docker-compose.yml
make migrate
make backend   # http://localhost:8000
make frontend  # http://localhost:3000
```

Copy `.env.example` to `.env` and `apps/frontend/.env.example` to
`apps/frontend/.env.local` to override defaults.

## Configuration

Backend (Render):

- `DATABASE_URL`: Neon connection string
- `CORS_ORIGINS`: comma-separated frontend origins, e.g. `https://boxup-f1.vercel.app`
- `CORS_ORIGIN_REGEX`: optional, allows Vercel preview URLs
- `CLERK_ISSUER`: Clerk Frontend API URL, needed for predictions sign-in
- `OPENROUTER_API_KEY`: optional, enables the AI agent

Frontend (Vercel):

- `NEXT_PUBLIC_API_URL`: the Render API URL
- `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` and `CLERK_SECRET_KEY`: Clerk keys for predictions sign-in

## Credits and licence

BoxUp is licensed under the GNU AGPL v3 (see `LICENSE`). The backend, ingestion,
ML packages, driver profiles and blog are adapted from the
[Slipstream](https://github.com/abdullah-azeemi/Slipstream) project, used under the
Apache License 2.0 (see `LICENSES/Slipstream-Apache-2.0.txt`).
