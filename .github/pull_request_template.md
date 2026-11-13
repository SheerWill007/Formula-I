## Summary

Describe the change and why it matters.

## What Changed

- 

## Why

Explain the user-facing or contributor-facing value.

## Verification

- [ ] `make up`
- [ ] `make backend`
- [ ] `make frontend`
- [ ] `make seed`
- [ ] `UV_CACHE_DIR=/tmp/uv-cache uv run pytest apps/backend/tests/ -v --tb=short`
- [ ] `pnpm lint` in `apps/frontend`
- [ ] `pnpm exec tsc --noEmit` in `apps/frontend`

## Screenshots / Notes

Add screenshots, logs, or extra context if helpful.

## Risk Check

- [ ] This does not rely on stale local env state
- [ ] I verified any DB-backed behavior against the intended database
- [ ] I called out any follow-up work or known limitations below

## Checklist

- [ ] I updated docs if behavior or setup changed
- [ ] I added or updated tests when appropriate
- [ ] I did not commit secrets, caches, or generated junk
