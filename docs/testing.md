# Testing

This guide explains how testing works in Slipstream and how to avoid the most common mistakes.

The most important rule is simple:

> run tests against local infrastructure, not Railway

## Test layers

### Backend tests

Location:

- [apps/backend/tests](/Users/abdullahmusharaf/Desktop/F1/Slipstream/apps/backend/tests)

What they cover:

- session endpoints
- driver and lap endpoints
- health checks
- qualifying segment analysis behavior

How they work:

- the suite creates its own tables in the configured database
- it seeds minimal data into those tables
- it tears everything down after the run

Key file:

- [conftest.py](/Users/abdullahmusharaf/Desktop/F1/Slipstream/apps/backend/tests/conftest.py)

### Frontend tests

Location:

- [apps/frontend/lib/telemetry-quali.test.ts](/Users/abdullahmusharaf/Desktop/F1/Slipstream/apps/frontend/lib/telemetry-quali.test.ts)

What they cover today:

- qualifying segment selection logic
- segment-aware driver availability
- selection reconciliation when switching segments

The frontend tests currently focus on extracted pure logic rather than browser-level integration.

## Recommended local test setup

### Start local services

```bash
make up
```

### Make sure local DB is selected

Recommended value:

```bash
DATABASE_URL=postgresql+psycopg://pitwall:pitwall@localhost:5432/pitwall
```

Check what your shell is using:

```bash
echo $DATABASE_URL
grep DATABASE_URL .env
```

If you see Railway here during local test runs, fix that first.

## Running backend tests

From repo root:

```bash
uv run --project apps/backend python -m pytest apps/backend/tests
```

Expected result:

- local DB is used
- tables are created by the test suite
- data is seeded and removed automatically

## Running frontend tests

```bash
pnpm -C apps/frontend test
pnpm -C apps/frontend exec tsc --noEmit
```

## Good testing patterns in this repo

### Use isolated fixture data for special-case tests

If a test needs unusual data, create a dedicated session key and clean it up inside the test or fixture.

Why:

- shared session-scoped fixture data can leak into unrelated tests
- isolated seed data makes failures easier to understand

### Extract tricky UI logic into pure helpers

This is the current pattern for telemetry segment selection:

- complex selection rules live in a pure helper
- React components call the helper
- tests assert helper behavior directly

Why this helps:

- no browser setup needed
- logic is easier to reason about
- regressions are caught earlier

### Prefer endpoint-level backend tests for API behavior

For backend regressions, test the route behavior, not just a helper in isolation, when the bug is really about the public response.

That is the pattern used for qualifying segment regression coverage.

## Common test failures

### Password authentication failed for Railway

Meaning:

- tests are pointing at a remote Railway DB
- your current `DATABASE_URL` is stale or wrong

Fix:

- switch to local Postgres before running pytest

### `relation "sessions" does not exist`

Meaning:

- local Postgres is reachable
- but your normal app database is empty or unmigrated

Note:

- backend tests usually create their own schema, so this is more common during local app runs than during tests

### Tests pass locally but fail in CI

Typical causes:

- fixture coupling
- assumptions about seeded row order
- code relying on hidden local state

Best fix:

- make test data explicit
- avoid mutating shared seed fixtures without cleanup

## Current coverage gaps

Still useful future additions:

- API tests for telemetry compare fallback behavior
- frontend integration tests around telemetry page rendering
- safety guard that refuses to run backend tests against Railway-hosted databases

## Contributor checklist

Before opening a PR:

1. Run backend tests
2. Run frontend tests
3. Run frontend typecheck
4. If you changed ingestion or ML behavior, run the smallest realistic local verification command too

## Related docs

- [docs/local-development.md](/Users/abdullahmusharaf/Desktop/F1/Slipstream/docs/local-development.md)
- [docs/ml-race-prediction.md](/Users/abdullahmusharaf/Desktop/F1/Slipstream/docs/ml-race-prediction.md)
