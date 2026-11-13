---
title: The slowest car on the grid started P9. How much was Alonso?
summary: Aston Martin has the slowest car of 2026, and Fernando Alonso still qualified P9 in the Brazil rain. We built a model that separates driver from car, tested it forward in time, and checked what it can and cannot tell us.
date: 2026-11-08
tag: Race breakdown
kicker: BRAZIL 2026 / QUALIFYING
emphasis: How much was Alonso?
---

Brazil qualifying was wet, then drying, and the order kept changing. Norris took pole for McLaren, Mercedes took P2 and P3 with Russell and Antonelli, and in P9 sat Fernando Alonso in an Aston Martin. His teammate, Lance Stroll, was P19 and out in Q1.

A good result in a bad car is easy to say and hard to measure. This post tries to measure it, and to be clear about where the measurement stops.

## How slow is the Aston Martin?

We took every 2026 qualifying session before Brazil, found each team's best lap, and measured its gap to pole as a percentage. Averaged over 16 sessions, Aston Martin is last of 11 teams, 4.12% off pole. Cadillac is next at 3.95%, and Mercedes is 0.08%.

```chart
team-pace
```

## The track changed under everyone

In Q1 every lap was on wet tyres. In Q2 the drivers switched to intermediates part way through. In Q3 everyone was on intermediates. Alonso's best lap came in Q2, on intermediates: 1:29.072. His Q3 lap was 1:30.311, 1.2 seconds slower, while the pole lap was 1:27.470.

```chart
brazil-quali
```

## What the model expected

To judge a result you need an expectation. We fitted a model on qualifying from 2006 to 2026 (the details are below), left Brazil out completely, and asked it to predict each driver's Q1 lap from the car's pace this season and the driver's estimated skill. Then we compared the prediction with what happened.

```chart
brazil-expected
```

Alonso beat the model's expectation by more than anyone: 1.27% off the fastest lap against an expected 2.76%. That is about 1.4 seconds a lap on a 92-second lap. Stroll, in the same car, landed almost exactly where expected.

Here is the caution. Brazil Q1 was wet, which makes every lap noisier, and the model's own uncertainty for that session puts Alonso at 1.9 standard deviations from expectation. If you check 22 drivers, the most extreme one is often around that far out. So this is the biggest over-performance on the day, and it is consistent with a driver having a very good session. It is not proof of anything on its own.

## Separating the driver from the car

One session cannot settle it, so the model uses all of them. For each lap it splits the gap to the fastest car into three parts: the session (weather, track), the car (one value per team per season), and the driver. The driver part is allowed to drift over a career, which is the temporal piece: a driver's skill this year is close to last year's, but not forced to be the same.

```chart
skill-trajectory
```

On this estimate Alonso peaked in 2010 at about 6.7 tenths of a second a lap faster than the average driver, the highest peak of the 22 drivers with at least eight seasons, although the uncertainty on that single season is about ±1.8 tenths. He has declined since: his 2026 estimate is about 2.0 tenths, ±2.9. That uncertainty is wide, and the band in the chart shows it. The model says he is probably still above average, but it cannot say by how much.

Averaged over his whole career he ranks second:

```chart
skill-ranking
```

Verstappen is first at 4.0 ± 0.5 tenths, Alonso second at 3.4 ± 0.5, then Massa and Hamilton. The gap between the first two is smaller than the uncertainty, so we cannot call it. What the data does support is that Alonso is in the very top group, and that he has been there across 19 seasons and several teams.

## Did we test it properly?

A model like this is easy to fool yourself with, so the evaluation is built around time. Nothing is shuffled. Every test lap comes after every training lap, and a test checks that.

We ran two forecasts, tuned the settings on 2010 to 2017 only, and report results on 2018 to 2026:

- **Mid-season:** train on everything up to half way through a season, predict the second half.
- **Next-season:** train through last year, predict the whole of the new season, where cars are new.

```chart
model-comparison
```

The result is less flattering than the chart of Alonso. Mid-season, the dynamic model is tied with the simple teammate baseline (0.705 vs 0.701) and a little better than looking at the car alone (0.710). Lap-to-lap noise is about 0.4% of a lap, which is larger than most differences between drivers, so no model can predict one session much better than that. Next-season, simply assuming a team's car is as quick as last year beats our model (0.807 vs 0.866).

So the model's value is not that it predicts better. It is that it says how much of a result is the driver, and how sure we are.

We also tried deep learning: learned embeddings for every driver and car, fed to a small neural network. It did much worse (1.07, worse than guessing the average). With about 8,600 laps and noise this large, there is not enough signal for it to learn anything the simple additive model does not already capture. A first run was even worse because of a bug in our early-stopping split, which we fixed and re-ran. We would rather say that than leave the neural result out.

## Drift

F1 changes under a model's feet, so we checked two kinds of drift.

```chart
drift
```

The spread of the field has changed a lot: the gaps between cars were about 1.8% of a lap in 2010 and about 0.5% in 2025, so the shape of the data shifts enough to cross the usual 0.25 threshold in 2008, 2009, 2010, 2023, 2025 and 2026. But it did not make forecasts worse. Regulation-change years were no harder to forecast than others (0.99 vs 1.07), and the drift score did not predict error. The hardest season was 2010, when 42% of the cars were from new teams. New constructors hurt more than new rules.

## Missing laps

About 2% of driver-sessions have no usable Q1 lap, because of a crash, a withdrawal or a lap that was not representative. They are not random: the model expects them to be 2.2% off the fastest lap, against 1.4% for everyone else, so they come mostly from slower cars.

Filling them in with the model's own prediction would change nothing, so instead we tried deliberately pessimistic fills: assume each of those drivers was 1% or 3% slower than expected, refit, and compare.

| Assumption | Correlation with the original skills | Mean change |
|---|---|---|
| Neutral | 0.96 | 0.05% of a lap |
| 1% slower | 0.97 | 0.05% of a lap |
| 3% slower | 0.94 | 0.07% of a lap |

The skill estimates barely move, about half a tenth of a second. A single driver-season can shift by about six tenths, so we treat any one season with caution. The career-level picture is unchanged.

## What this does not tell us

- **It is qualifying pace, not racing.** Tyre management, race craft and strategy are not in the model. That is a separate post.
- **Q1 is noisy.** Traffic and track evolution matter, and a wet session is noisier than a dry one. We account for that per session but cannot remove it.
- **Skill is identified through teammates and team changes.** A driver who always has a weak teammate is estimated less precisely.
- **We cannot separate chassis from engine.** The 2026 data has no speed-trap or car telemetry, so we make no claim about where Aston Martin loses time. The result is about the car as a whole.
- **This is not "the greatest driver".** It is estimated qualifying pace compared with the grid, with an error bar. On that measure Alonso is near the top for a longer time than anyone in the set.

## Try it yourself

The model, tests and a full write-up, including the tuning, cross-validation and drift checks, are in the repository under `docs/models/driver-skill.md`. Every number comes from the BoxUp database. A question like "how did Alonso's qualifying compare with Stroll's in Brazil?" is the kind of thing the upcoming analyst will answer. The code is on [GitHub](https://github.com/SheerWill007/Formula-I).
