# Qualifying Telemetry

Qualifying telemetry is one of the most product-visible features in Slipstream, and also one of the easiest places to get subtly wrong.

This doc explains:

- why qualifying telemetry is special
- why `Q1/Q2/Q3` cannot be treated as a simple "fastest lap" problem
- why Slipstream stores `quali_segment`
- how the frontend and backend cooperate

## The problem

At first glance, qualifying telemetry sounds easy:

- pick two drivers
- fetch their fastest laps
- overlay speed traces

But that is not enough for a real qualifying UI.

Users want to compare:

- `Q1`
- `Q2`
- `Q3`

The fastest lap overall is often a `Q3` lap, which means a naive implementation makes every segment tab look the same.

## Why segment-aware telemetry is needed

In qualifying:

- drivers improve over time
- some drivers are eliminated in `Q1` or `Q2`
- some drivers do not have a valid lap in later phases
- some laps have timing data but no stored telemetry

So the UI needs to know:

- which drivers are actually present in each phase
- which lap should represent each driver in that phase
- how to fall back if the exact requested lap has no telemetry

## Current design

Slipstream uses a persisted-segment model.

### 1. Persist `quali_segment` on `lap_times`

Each qualifying lap gets a `quali_segment` field:

- `1` = `Q1`
- `2` = `Q2`
- `3` = `Q3`

Why this matters:

- runtime inference was fragile in production
- storing the segment in the database makes the behavior deterministic

### 2. Store only segment-best telemetry laps

Telemetry is stored only for:

- each driver's best `Q1` lap
- each driver's best `Q2` lap
- each driver's best `Q3` lap

Why:

- this gives the UI the meaningful comparison laps
- it avoids storing every qualifying lap's telemetry
- it keeps telemetry volume manageable

### 3. Resolve segment summaries from the database

The backend route:

- `/api/v1/sessions/:key/analysis/quali-segments`

returns:

- qualifying boundaries
- per-segment driver rows
- the lap number that represents each driver in `Q1`, `Q2`, and `Q3`

This route is the source of truth for the frontend segment tabs.

### 4. Request telemetry with pinned lap numbers

Once the frontend knows which lap belongs to each driver in a segment, it calls:

- `/api/v1/sessions/:key/telemetry/compare?drivers=12,63&laps=12:8,63:5`

The `laps=` parameter pins telemetry to specific laps instead of "whatever the global fastest lap is".

## Fallback behavior

Pinned laps are preferred, but telemetry may be missing for a requested lap.

Current backend behavior:

1. try the exact pinned lap
2. if it has no telemetry, look for the nearest clean lap for that driver that does have telemetry
3. if needed, fall back to the driver's fastest telemetry-backed lap

Why this fallback exists:

- it keeps the UI working when telemetry coverage is imperfect
- it avoids total failure for a comparison panel

But the frontend still surfaces the actual lap used so users are not misled.

## Frontend behavior

The telemetry page is segment-aware.

That means:

- segment tabs are disabled if a segment has no rows
- drivers who did not reach a segment cannot be selected there
- selected drivers are reconciled when switching segments
- the UI shows the actual lap being used, such as `ANT L8`

This prevents a common UX bug where a user thinks they are viewing `Q2` but the app is silently still showing a `Q3` lap.

## Corner and braking comparison

The qualifying telemetry page now includes a compact corner-analysis stack alongside the sector cards.

That stack is intentionally designed to help users compare driver style, not just raw lap time:

- a performance matrix for sector pace and top speed
- a theoretical lap card for the best combined sectors
- a braking analysis panel that shows corner entry and exit behaviour on the circuit
- a short insight card that summarizes the biggest visible differences between the selected drivers

The braking panel uses the same selected drivers as the telemetry comparison, so it stays aligned with the lap data already pinned by `Q1`, `Q2`, or `Q3`.

## Why this was worth the complexity

The qualifying telemetry view is only trustworthy if the whole chain agrees:

- ingestion
- database
- segment summary endpoint
- telemetry compare endpoint
- frontend selection state

If any one of those layers is out of sync, the UI can look correct while showing the wrong lap.

Persisting `quali_segment` and using pinned lap requests makes the comparison path explicit and testable.

## Contributor guidance

If you change qualifying telemetry behavior:

1. check ingestion logic
2. check `lap_times.quali_segment`
3. check `/analysis/quali-segments`
4. check `/telemetry/compare` pinned-lap behavior
5. check frontend disabled-driver and lap-badge behavior

Do not assume the frontend is wrong before verifying which lap numbers the backend is actually returning.

## Related code

- [analysis.py](/Users/abdullahmusharaf/Desktop/F1/Pitwall/apps/backend/src/backend/api/v1/analysis.py)
- [telemetry.py](/Users/abdullahmusharaf/Desktop/F1/Pitwall/apps/backend/src/backend/api/v1/telemetry.py)
- [page.tsx](/Users/abdullahmusharaf/Desktop/F1/Pitwall/apps/frontend/app/sessions/[key]/telemetry/page.tsx)
- [telemetry-quali.ts](/Users/abdullahmusharaf/Desktop/F1/Pitwall/apps/frontend/lib/telemetry-quali.ts)
- [fastf1_client.py](/Users/abdullahmusharaf/Desktop/F1/Pitwall/packages/ingestion/src/ingestion/fastf1_client.py)

## Related docs

- [docs/data-model.md](/Users/abdullahmusharaf/Desktop/F1/Pitwall/docs/data-model.md)
- [docs/ingestion.md](/Users/abdullahmusharaf/Desktop/F1/Pitwall/docs/ingestion.md)
- [README.md](/Users/abdullahmusharaf/Desktop/F1/Pitwall/README.md)
