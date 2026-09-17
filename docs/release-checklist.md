# Pre-Public Release Checklist

This checklist is for the version of Slipstream you want strangers on the internet to use without you sitting beside them.

It is intentionally opinionated and constrained by one important reality:

> Railway storage is limited to about 400 MB

That means public release should optimize for:

- a polished core experience
- predictable data coverage
- storage discipline

not "ingest everything".

## 1. Product readiness

### UI and UX

- [ ] Home page feels intentional on desktop and mobile
- [ ] Sessions page matches the new design language
- [ ] Session detail pages are visually consistent
- [ ] Telemetry page works cleanly on mobile without overlaps
- [ ] Loading, empty, and error states are styled and understandable
- [ ] Navigation is clear and touch-friendly

### User trust

- [ ] Telemetry pages show the actual lap being used
- [ ] Segment tabs disable unavailable drivers cleanly
- [ ] Partial or missing data is explained instead of silently ignored
- [ ] Key pages show enough session context that users know what they are looking at

## 2. Data coverage strategy

Because of the 400 MB limit, Slipstream should launch with a curated dataset, not a full archive.

### Recommended public dataset

Keep in Railway:

- current season `Q`
- current season `R`
- current season `FP2` for selected headline weekends
- telemetry only for qualifying segment-best laps

Suggested baseline:

- current season for all race weekends:
  - `Q`
  - `R`
- `FP2` only for:
  - recent races
  - marquee circuits
  - sessions used by ML demos or highlighted UI screens

### Avoid at public launch

- full multi-season telemetry archives
- every practice session for every year
- ingesting entire historical calendars into Railway

### Better split of storage

Use Railway for:

- public-facing hot data
- current season
- a curated small historical sample

Use local or another offline database for:

- ML experimentation
- large historical backfills
- validation runs

## 3. Storage budget plan

Target a simple public-storage policy.

### Suggested budget allocation

For a 400 MB Railway database:

- ~150–200 MB for current season `lap_times`, sessions, drivers, and compact analytics data
- ~120–150 MB for qualifying telemetry on selected weekends
- leave the rest as operational headroom for:
  - migrations
  - re-ingests
  - growth during the season

Do not run Railway near 100% capacity.

### Safe product rule

If a new ingestion wave would push the DB close to the cap:

- keep all `Q` and `R`
- keep only selected `FP2`
- keep telemetry only for the public-facing comparison weekends

## 4. Reliability and safety

- [ ] Backend tests pass locally
- [ ] Frontend tests pass
- [ ] Frontend typecheck passes
- [ ] Key telemetry and qualifying segment regressions are covered by tests
- [ ] Local tests do not accidentally point to Railway
- [ ] Secrets have been rotated if previously exposed
- [ ] Local `.env` does not contain stale Railway credentials

## 5. Deployment readiness

- [ ] `DATABASE_URL` is correct in Railway
- [ ] frontend API base URL is correct in Vercel
- [ ] migrations have been applied before relying on new fields
- [ ] qualifying sessions have been re-ingested when segment logic changes
- [ ] smoke tests have been run after deploy

See [deployment.md](/Users/abdullahmusharaf/Desktop/F1/Slipstream/docs/deployment.md) for the full sequence.

## 6. Documentation readiness

- [ ] README explains the product and how to run it
- [ ] docs index exists
- [ ] architecture, ingestion, local dev, testing, and deployment docs are current
- [ ] ML requirements are documented
- [ ] tricky concepts like qualifying telemetry are explained

## 7. Open-source readiness

- [ ] clear issue templates
- [ ] PR template
- [ ] contribution guide or contributor expectations
- [ ] screenshots or GIFs for the main flows
- [ ] roadmap reflects what is real versus planned

## 8. Recommended launch shape

The best first public version is:

- polished frontend on a curated dataset
- strong telemetry comparison
- reliable qualifying/race analysis
- docs that make the repo approachable

Not yet:

- full historical archive
- massive ML dataset on Railway
- every session type for every weekend

## 9. Concrete next actions

If launching soon, do these next in order:

1. Finish frontend polish on sessions and session detail pages
2. Add backend test safety so Railway cannot be used by accident
3. Add issue templates and PR template
4. Curate a Railway-friendly public dataset
5. Run a full smoke test from a clean environment

## 10. Public data policy recommendation

For launch, keep Railway as the serving database, not the master research archive.

Recommended serving policy:

- keep all current-season `Q`
- keep all current-season `R`
- keep only selective `FP2`
- keep telemetry only where the public UI needs it
- archive or skip everything else

That gives you a product that feels rich without burning the full 400 MB budget too early.
