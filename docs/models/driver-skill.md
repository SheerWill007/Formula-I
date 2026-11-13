# Driver skill model (qualifying pace)

A dynamic model that separates a driver's skill from the car's speed, built for the
Alonso / Brazil 2026 post. Code: `packages/ml/src/ml/driver_skill/`. Tests:
`packages/ml/tests/test_driver_skill.py`. Results the blog reads:
`apps/frontend/content/blog/data/driver-skill.json`.

## Question

How much of a qualifying result is the car, and how much is the driver, and does the
driver part change over a career? "Places ahead of a teammate" answers a smaller question
(one comparison, one season, and it counts retirements) and cannot forecast anything.

## Data

`historical_results` (Jolpica), kind `Q`, seasons 2006 to 2026: 8,804 driver-sessions in
419 sessions. Brazil 2026 Q1 times are filled from our own `session_results` because
Jolpica lagged the weekend.

**Target.** `gap = 100 * (Q1 time / fastest Q1 time in the session - 1)`, in percent of a
lap. Only Q1 is used: every driver enters it, whereas Q2 and Q3 are censored by knockout
(slow cars never reach Q3, so a model fitted on Q3 times would be biased toward fast cars).
Seasons before 2006 had a different qualifying format and are excluded.

| Status | Rows | Meaning |
|---|---|---|
| ok | 8,627 | used |
| missing | 106 | no Q1 time (crash, withdrawn) |
| outlier | 71 | more than 7% slower than the fastest lap, not a representative lap |

## Model

For driver `i` in session `s` of season `y`, driving team-season `c`:

```
gap[s, i] = session[s] + car[c] + skill[i, y] + noise
skill[i, y] = skill[i, y-1] + N(0, tau_walk^2 * years_between)      # random walk
car[c]      ~ N(0, tau_car^2)                                        # one per team-season
```

* `skill` is the temporal part: it follows a random walk over a driver's seasons, so an
  estimate is pulled toward the neighbouring seasons and can rise or fall over a career.
* A car is rebuilt each year, so `car` has no link between seasons; this is where regulation
  and team changes show up as drift (see below).
* `session` absorbs weather and track evolution, which move every car together.
* Noise differs a lot between a dry and a wet session, so each session has its own noise sd,
  re-estimated from its robust residual spread (3 iterations, shrunk to the global value).

All priors are Gaussian, so the MAP estimate is one sparse linear solve and each effect has a
posterior standard deviation (reported as the ± everywhere). The model is linear and fits in
about 0.1 s.

**Identification.** A car and a driver are separated only through teammates and drivers who
change team. A shared level shift between all drivers and all cars is not identifiable, so
skill is always reported relative to the average driver of the same season.

**Units.** 1% of a lap is 0.9 s on a 90 s lap, i.e. 9 tenths of a second. The blog quotes
tenths per lap.

**Hyperparameters** (tuned, see below): `tau_car` 2.0, `tau_driver0` 0.8, `tau_walk` 0.2
(about 1.8 tenths of yearly drift), `car_carry` 0.95. Estimated noise 0.40% of a lap.

## Validation

Everything is temporal. Nothing is shuffled and a test asserts that every training session
precedes every test session.

| Protocol | Train | Predict | Question |
|---|---|---|---|
| Mid-season (walk-forward) | all earlier seasons plus the first half of season T | second half of T | Given what we know mid-year, how well do we forecast the rest? |
| Next-season (rolling origin) | seasons before T | all of T | How well does it carry over to a new car? Concept-drift stress test. |

Hyperparameters were tuned on 2010 to 2017 folds only; results are reported on 2018 to 2026,
so the reported error never comes from folds that chose the settings. `car_carry` only
matters for an unseen team-season, so it was tuned on the next-season protocol (2008 to
2017). Its best value (0.95) is at the edge of the grid, which we note as a limitation.

### Results, held-out 2018 to 2026 (RMSE, % of lap, lower is better)

| Model | Mid-season | Next-season |
|---|---|---|
| Teammate delta (the old metric made predictive) | 0.701 | 0.807 |
| **Dynamic skill model** | **0.705** | 0.866 |
| Car only (team mean, last year's if new) | 0.710 | **0.807** |
| Driver only (mean of last 6 laps) | 0.724 | 0.844 |
| Global mean | 0.961 | n/a |
| Neural (embeddings + MLP) | 1.070 | 1.046 |

Honest reading:

* Mid-season the dynamic model **ties** the teammate baseline (0.705 vs 0.701) and is
  slightly better than car-only. Lap-to-lap noise (0.40%, about 0.36 s) dominates, and skill
  effects are 0.1 to 0.7%, so no model can predict one session much better.
* Next-season, plain persistence of the car beats it (0.807 vs 0.866). It wins in
  regulation years such as 2009 and 2022 but loses in most others.
* The 80% prediction intervals cover 88% (mid-season) and 91% (next-season) of outcomes, so
  they are slightly conservative.
* The value of the model is therefore **decomposition and uncertainty**, not forecasting
  accuracy: it says how much of a result is driver and how sure we are.

### Neural comparison

A small PyTorch model (driver and team-season embeddings plus experience, MLP, session
offsets, AdamW, early stopping on the last 10% of training sessions) scores 1.07, worse than
a constant. With about 8,600 rows and a noise floor near 0.4% there is not enough signal to
learn embeddings; the Gaussian model's structure (additive effects, random walk) is the right
inductive bias. An earlier version of this comparison scored 1.12 because of a bug in the
early-stopping split (untrained session embeddings in the validation set); it was fixed and
re-run, and the model is still much worse.

## Data drift and concept drift

* **Data drift.** PSI of the gap distribution against the previous three seasons, plus a KS
  test. PSI is above the conventional 0.25 threshold in 2008, 2009, 2010, 2023, 2025 and
  2026. The driver is the field compressing: the sd of the gap falls from about 1.8% (2010)
  to about 0.5% (2025).
* **Concept drift.** Regulation years are not harder to forecast: next-season RMSE is 0.99 in
  regulation years (2009, 2014, 2017, 2022, 2026) against 1.07 in the others, and PSI does not
  predict error (Spearman -0.14, p = 0.56, 19 seasons). The worst year is 2010 (RMSE 2.4),
  when 42% of the cars were from new teams. New constructors hurt more than new rules.
* **Mitigations built in.** Car effects are per season (no carry across regulation
  breaks except the tuned `car_carry`), skill is a random walk (not a constant), and the
  target is relative to the fastest lap of each session, which cancels most weather and
  fuel/track changes.
* Not done: monitoring for drift on live data (this is an offline analysis).

## Missing data and imputation

177 of 8,804 rows (2.0%) have no usable Q1 lap. They are **not missing at random**: the model
expects them to be 2.20% off the fastest lap against 1.41% for the rest, so they come from
slower cars, and a driver who crashed in Q1 was probably slower than expected.

Imputing the model's own prediction would be pointless: for a Gaussian model that is missing
at random it is the EM fixed point and changes nothing. So we ran a pattern-mixture
sensitivity analysis instead: impute each unusable row as `prediction + delta`, refit, and
compare driver skill (centred within season) with the complete-case fit.

| delta | Correlation with complete case | Mean absolute change | Largest change |
|---|---|---|---|
| 0% | 0.961 | 0.05% | 0.68% |
| +1% | 0.968 | 0.05% | 0.55% |
| +3% | 0.941 | 0.07% | 0.66% |

Typical skill moves by about half a tenth of a second per lap, but one driver-season can
move by about six tenths, so individual season estimates carry that extra uncertainty. The
career-level conclusions do not change.

## Limitations

* Qualifying only, Q1 only. Race pace, tyre and fuel effects are not modelled.
* Q1 is partly a traffic and track-evolution lottery. Wet sessions are noisier (Brazil 2026
  has noise 0.57% against 0.40% typical), handled by per-session noise but not removed.
* Skill is identified through teammates and team switches, so a driver who always has a weak
  teammate is estimated less precisely and can be flattered.
* One lap time per driver per session; no sprint qualifying, no sector or telemetry data.
* The Gaussian random walk cannot represent a sudden step change (injury, retirement and
  comeback), only a gradual drift.
* `car_carry` is at the edge of its grid.
* Not the same quantity as "greatest driver". It is estimated qualifying pace relative to
  the grid, with uncertainty.

## Reproduce

```bash
DATABASE_URL=... PYTHONPATH=packages/ml/src uv run --with pandas --with scipy --with numpy \
  --with torch --with 'psycopg[binary]' python -m ml.driver_skill.run --out results.json
PYTHONPATH=packages/ml/src uv run --with pytest --with pandas --with scipy --with numpy \
  python -m pytest packages/ml/tests/test_driver_skill.py
```

Read-only against the database. A full run takes a few minutes, most of it the neural folds.
