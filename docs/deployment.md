# Deployment

BoxUp runs on free tiers:

| Part | Host | How it deploys |
| --- | --- | --- |
| Frontend (`apps/frontend`) | Vercel project `formula-1` | Every push to `main` |
| API (`apps/backend`, `Dockerfile`) | Render web service `boxup-api` | Every push to `main` (see `render.yaml`) |
| Database | Neon project `formula-1`, database `boxup` | Migrations run when the API container starts |
| Ingestion + training | GitHub Actions | Weekly cron, or run by hand |

## Deploy order

1. Push to `main`. Render builds the Docker image, runs `alembic upgrade head`
   against Neon, then starts gunicorn. Vercel builds the frontend.
2. If the change needs new data, run **Backfill Sessions** (or **Ingest & Train**)
   from the GitHub Actions tab.
3. If the model changed, run **Train Model**. It publishes the model files to
   the `ml_model_files` table; the API downloads them on the next prediction
   request, so there is nothing to redeploy.

## Environment variables

### Render (API)

- `DATABASE_URL`: Neon connection string (direct host, `sslmode=require`)
- `SECRET_KEY`: random string
- `CORS_ORIGINS`: `https://boxup-f1.vercel.app,http://localhost:3000`
- `CORS_ORIGIN_REGEX`: `^https://formula-1-[a-z0-9-]+\.vercel\.app$` for preview deployments
- `CLERK_ISSUER`: Clerk Frontend API URL (for example `https://<name>.clerk.accounts.dev`). Required for predictions.
- `OPENROUTER_API_KEY`: optional, enables the AI agent endpoints

### Vercel (frontend)

- `NEXT_PUBLIC_API_URL`: `https://boxup-api-npz2.onrender.com`
- `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY`, `CLERK_SECRET_KEY`: Clerk keys. Without them the
  site still works and the predictions page says sign-in is not switched on.

`NEXT_PUBLIC_*` values are baked in at build time, so redeploy after changing them.

### GitHub Actions

- `DATABASE_URL` secret (required)
- `TELEMETRY_ARTIFACT_BUCKET`, `R2_ENDPOINT_URL`, `R2_ACCESS_KEY_ID`,
  `R2_SECRET_ACCESS_KEY` (optional): store raw telemetry traces in Cloudflare R2.

## Data sources and their limits

- F1's live-timing feed now rejects anonymous requests, so FastF1 can only load
  sessions already in its cache. Ingestion falls back to **OpenF1** for 2023+.
- OpenF1 has no car telemetry traces, so speed/throttle/brake charts need either
  cached FastF1 data or an F1TV login (`F1_USERNAME` / `F1_PASSWORD`, FastF1 3.9+).

## Verification

After a deploy check:

1. `GET /health` returns `{"status": "ok", "database": "ok"}`
2. `GET /api/v1/sessions` returns sessions
3. The sessions, telemetry and strategy pages load on the frontend
4. Signed in, `/predictions` shows podium probabilities (not "model is still being trained")

## Render free tier notes

- The service sleeps after 15 minutes idle; the first request then takes 30-60 s.
- The disk is wiped on every deploy, which is why model files live in Postgres.
