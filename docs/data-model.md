# Data Model

This document explains the core tables Slipstream uses and what they are for.

It is intentionally practical:

- which tables matter most
- which columns are important for product behavior
- how large-data tables differ from compact tables

## Core idea

Slipstream stores one normalized session dataset that is reused by:

- the backend API
- the frontend UI
- the ML pipeline

That means most features are built on the same underlying tables rather than each layer inventing its own storage format.

## Main tables

### `sessions`

Purpose:

- one row per session
- acts as the top-level anchor for everything else

Important columns:

- `session_key`
- `year`
- `gp_name`
- `country`
- `session_type`
- `session_name`
- `date_start`
- `date_end`
- `track_temp_c`
- `air_temp_c`
- `humidity_pct`
- `rainfall`
- `wind_speed_ms`

Typical uses:

- session list pages
- filtering qualifying vs race vs practice
- weather context in analysis and ML

### `drivers`

Purpose:

- driver metadata for a specific session

Important columns:

- `driver_number`
- `session_key`
- `full_name`
- `abbreviation`
- `team_name`
- `team_colour`

Notes:

- keyed by `(driver_number, session_key)`
- session-scoped because team and metadata can vary across seasons or data sources

### `lap_times`

Purpose:

- the main timing table
- used across qualifying, race, and practice analytics

Important columns:

- `session_key`
- `driver_number`
- `lap_number`
- `lap_time_ms`
- `s1_ms`
- `s2_ms`
- `s3_ms`
- `compound`
- `tyre_life_laps`
- `track_status`
- `deleted`
- `stint`
- `position`
- `fresh_tyre`
- `is_accurate`
- `speed_i1`
- `speed_i2`
- `speed_fl`
- `speed_st`
- `quali_segment`

Why `lap_times` matters so much:

- most backend analysis routes can run from this table alone
- it is compact enough to keep many seasons locally
- it powers race results, pace analysis, strategy, and most ML features

### `telemetry`

Purpose:

- high-volume sampled lap traces for visual overlays and telemetry stats

Important columns:

- `session_key`
- `driver_number`
- `lap_number`
- `distance_m`
- `speed_kmh`
- `throttle_pct`
- `brake`
- `gear`
- `rpm`
- `drs`
- `x_pos`
- `y_pos`
- `recorded_at`

Why this table is special:

- it is much larger than `lap_times`
- it is used for rich comparison views, not as the default data source for every screen
- Slipstream intentionally stores it selectively
- hosted deployments can leave this table empty and serve raw traces from artifacts instead

### `telemetry_artifacts`

Purpose:

- compact metadata pointing to raw telemetry stored outside Postgres
- lets the API fetch a whole lap trace without keeping every sample row in the database

Important columns:

- `session_key`
- `driver_number`
- `lap_number`
- `storage_key`
- `storage_backend`
- `format`
- `sample_count`
- `size_bytes`
- `checksum_sha256`

Current artifact format:

- one compressed `json.gz` file per session/driver/lap
- path shape: `telemetry/session_<session_key>/driver_<driver_number>/lap_<lap_number>.json.gz`

Why this exists:

- hosted Postgres limits are usually tight
- raw telemetry is bulky and can be regenerated from public sources
- AI and product views mostly need summaries, while charts need exact lap traces only on demand

### `race_results`

Purpose:

- compact final race outcome table

Important columns:

- `session_key`
- `driver_number`
- `position`
- `grid_position`
- `points`
- `status`
- `fastest_lap`

Typical uses:

- results displays
- ML targets and validation

### `race_intelligence_events`

Purpose:

- event storage for the Race Intelligence feature
- stores derived analysis events (driver scores, stint summaries, battle gaps, insights, etc.)

Important columns:

- `session_key`
- `event_type`
- `event_key`
- `driver_number`
- `lap_number`
- `payload` (JSONB)

Typical uses:

- Race Intelligence frontend page
- vector-search retrieval for AI/report generation

Notes:

- populated on demand via `POST /sessions/:key/analysis/race-intelligence/events/refresh`
- indexed in LanceDB for semantic search

## Important concepts

### Clean vs deleted laps

Column:

- `lap_times.deleted`

Meaning:

- `FALSE` means the lap is considered valid for fastest-lap style analytics
- `TRUE` means the lap should usually be excluded from performance comparisons

Many queries explicitly filter on:

```sql
deleted = FALSE
```

### `quali_segment`

Column:

- `lap_times.quali_segment`

Meaning:

- persisted qualifying phase marker
- typically `1`, `2`, or `3` for `Q1`, `Q2`, `Q3`

Why it exists:

- runtime boundary inference was too fragile for production telemetry switching
- storing the segment on each lap makes qualifying analysis stable and reproducible

This field is especially important for:

- `/analysis/quali-segments`
- segment-aware driver selection in the frontend
- pinned qualifying telemetry comparisons

### Session-scoped telemetry

Telemetry rows are always tied to:

- a session
- a driver
- a lap

That means the frontend can ask for:

- fastest telemetry lap
- or a pinned `driver:lap` pair

without inventing any extra mapping layer.

## Storage strategy by table

### Compact tables

Mostly compact:

- `sessions`
- `drivers`
- `lap_times`
- `race_results`
- `race_intelligence_events`

These are the tables you can keep for many seasons without much pain.

### Large table

Potentially large:

- `telemetry`
- raw telemetry artifacts outside the database

Slipstream keeps telemetry smaller by storing only the laps that provide the most value for the UI.

Current policy for qualifying:

- store telemetry for each driver's best `Q1` lap
- store telemetry for each driver's best `Q2` lap
- store telemetry for each driver's best `Q3` lap

Not every qualifying lap gets telemetry.

For cheap hosted deployments, set ingestion to `TELEMETRY_STORAGE_MODE=files`.
That stores artifact metadata in `telemetry_artifacts`, deletes raw rows from
`telemetry`, and keeps the public API shape unchanged.

## Which layers use which tables

### Frontend / backend analysis

Mostly uses:

- `sessions`
- `drivers`
- `lap_times`
- `telemetry` when traces are needed
- `race_intelligence_events` for the Race Intelligence feature

### ML

Mostly uses:

- `sessions`
- `drivers`
- `lap_times`
- `race_results` or race-derived outcomes

The ML pipeline relies more on compact timing/history features than raw telemetry.

## Contributor notes

When adding new analytics:

- prefer `lap_times` if possible
- use `telemetry` only when a feature truly needs sampled trace data
- if a derived value is critical to UX correctness, consider persisting it rather than recomputing it at request time

`quali_segment` is the best current example of that design rule.

## Related docs

- [docs/architecture.md](/Users/abdullahmusharaf/Desktop/F1/Slipstream/docs/architecture.md)
- [docs/ingestion.md](/Users/abdullahmusharaf/Desktop/F1/Slipstream/docs/ingestion.md)
- [docs/concepts/qualifying-telemetry.md](/Users/abdullahmusharaf/Desktop/F1/Slipstream/docs/concepts/qualifying-telemetry.md)
