# Repository guide

BoxUp is a Python and TypeScript monorepo.

## Main folders

| Path | Purpose |
|---|---|
| `apps/backend/` | Flask API, agent, migrations, backend tests |
| `apps/frontend/` | Next.js web application and UI tests |
| `packages/ingestion/` | FastF1 clients and database loading |
| `packages/ml/` | Feature building, training, and predictions |
| `packages/config/` | Shared environment and service configuration |
| `packages/workers/` | Background jobs |
| `packages/stream/` | Stream processing components |
| `infra/` | Docker Compose and database initialization |
| `docs/` | Project, repository, and agent guides |

## Local workflow

At the repository root:

```bash
make install       # install Python and frontend dependencies
make up            # start Docker services
make migrate       # apply database migrations
make seed          # optional sample F1 sessions
make backend       # Flask API on port 8000
make frontend      # Next.js app on port 3000
```

The default local database is `postgresql+psycopg://pitwall:pitwall@localhost:5432/pitwall`.
If you set `DATABASE_URL`, verify that it points to local infrastructure before
running the app, migrations, or tests. Never use a production URL for routine
testing.

## Useful commands

```bash
make lint
make test
uv run --project apps/backend python -m pytest apps/backend/tests
cd apps/frontend && pnpm test
cd apps/frontend && pnpm tsc --noEmit
```

Use `make down` to stop local services. `make reset` deletes their persisted
data.

## Configuration

Copy `.env.example` to `.env` when present and set only the services you use.
The backend reads shared settings from environment variables and `.env`.
Production secrets must be configured in the deployment environment; do not
commit them. Agent provider settings and key requirements are described in the
[agent guide](agent.md).
