---
title: Our F1 agent said Hamilton's tyres were improving. The fuel was doing the work.
summary: We built an agent that writes and runs its own analysis, then checked every answer against the database by hand. On simple questions it went from 1 of 10 to 7 of 10. On harder ones a larger model got 4 of 8 right, with no confident wrong answers. Here is what it gets right, what it still gets wrong, and what we could not measure.
date: 2026-11-07
tag: Build notes
kicker: BUILDING PITWALL 01 / RACE ANALYSIS
emphasis: The fuel was doing the work.
---

At the 2026 Singapore Grand Prix, our first agent looked at Lewis Hamilton's lap times and reported a degradation of **−126.5 ms per lap**. Negative degradation means the tyres were getting faster. They were not. The car was burning fuel, getting lighter every lap, and that alone made every lap quicker. The old method did not remove the fuel effect, so the lighter car's speed-up showed up as tyre improvement.

This post is about fixing that kind of error, and about the errors we did not fix. We built a new agent for Pitwall, our F1 analysis app. It writes Python, runs it in a sandbox, and answers from the output. We checked its answers against the database ourselves, because a scorer that only looks at words had passed wrong answers and failed right ones.

## Where the first agent stood

Our first agent sent each question through a router that picked one of fourteen fixed recipes. We ran 22 questions in three tiers: supported, analytical and trap, where the agent should refuse because the data is not stored.

| Tier | Passed | What it tests |
|---|---|---|
| Supported | 2 of 8 | Things the agent should already handle |
| Analytical | 0 of 10 | Strategy, what-if and multi-step analysis |
| Trap | 4 of 4 | Data we do not hold; the right answer is a refusal |

That is 6 of 22 (27%) on `gpt-4o-mini`. The trap tier was the only one it passed comfortably, because it refuses a lot. Six of the failures were refusals that came before any analysis ran: the router demanded a driver or a race the question did not need.

*Source: our eval set, `apps/backend/evals/questions.json`, run on 7 November 2026.*

## A number nobody measured

The new agent computes the degradation itself, and removing the fuel effect changes the answer. Here are Hamilton's Singapore stints, cleaned of out-laps, safety-car laps and slow outliers, with the fuel effect taken out:

![Hamilton's fuel-corrected lap times by stint at the 2026 Singapore Grand Prix, with a fitted line per stint](/blog/hamilton-singapore-degradation.svg)

| Stint | Compound | Clean laps | Raw slope | Fuel-corrected slope | R² |
|---|---|---|---|---|---|
| 1 | Medium | 14 | −0.005 s/lap | **+0.045 s/lap** | 0.23 |
| 2 | Soft | 39 | +0.062 s/lap | **+0.112 s/lap** | 0.72 |

*Source: lap times from our database for session 11388. The fuel effect is an assumption of 0.05 s per lap of fuel. We have not measured it.*

The Medium fit is weak, so we would not quote its number on its own. The Soft fit is reasonable. The fuel effect is the main assumption, and a different value moves both slopes by the same amount. Calibrating it per circuit is on our list.

The same method gave us green-flag pit losses that look plausible. Singapore's median was 23.9 s over 20 stops, and Spain's was 26.6 s over 13. The older estimator gave 41.5 s for Spain, which is not a plausible green-flag loss, so we replaced it. We have not traced exactly why it was high. Our guess is that it counted virtual-safety-car stops as green.

## Two safety cars it could not see

We asked the first agent about safety cars in the 2026 Azerbaijan Grand Prix. The race-control data holds four rows that say "SAFETY CAR" and two that say "VSC". The agent read the `flag` column, found only yellows and greens there, and answered that no safety car had been deployed.

The fix was to tell the model where safety cars live: in the `category` column, as `SafetyCar`. Once we did, the larger model reported two deployments and no VSC. The race-control rows have no lap numbers, so the laps we give are estimates from where pit stops bunched up.

*Source: race-control events for session 11377, from our database.*

## Telling the model the race first

The second mistake came from a different cause. In Singapore we asked whether Verstappen could have undercut the car ahead. The small model compared the wrong laps and said he spent sixty laps in traffic.

The larger model got it right, but only after we added a `race_summary` tool. It gives each driver's final order, stops, pit loss, position before each stop and median clean lap, before the model loads any laps. With it, the answer became that Verstappen led every lap, so there was no car ahead to undercut. The question's premise was wrong, and the model said so.

We also learned that a summary can be wrong in its own way. For a while the summary counted a driver's laps in traffic even when most of their gaps were unknown, because a missing lap time had silently broken the chain. We now show "unknown" in that case rather than a number.

## Simple questions: 1 of 10 against 7 of 10

The questions people will actually ask are often simple: what happened on one lap, who won, which tyres were used. We wrote ten of them and checked each answer against the database.

| | Original agent | Analyst with `gpt-4o-mini` |
|---|---|---|
| Correct | 1 | **7** |
| Partly right | 0 | 1 |
| Wrong | 2 | 2 |
| Refused | **7** | 0 |
| Median time | 2.1 s | 15.5 s |
| Cost for all ten | $0.015 | $0.019 |

The original agent refused seven of the ten, most with "unsupported question" or "missing driver". It is fast, and for simple lookups it is the right tool. It just does not understand a question that asks for a comparison.

The analyst got seven right. It was wrong twice. It said Antonelli led Canada on lap 20, when the data says Russell did. It also reported 52 laps for Hadjar's race, when it was 53. Both errors were confident. Our number-checker did not catch them, because the wrong numbers did appear in the tool output at some point. The checker only confirms that a number came from somewhere, not that it is the right number.

*Source: ten simple questions with facts from direct SQL queries, run on 7 November 2026.*

## A larger model is better and five times the price

On the eight harder questions we compared `gpt-4o-mini` with `qwen3.7-plus`, a larger model, and checked each answer by hand:

| | `gpt-4o-mini` | `qwen3.7-plus` |
|---|---|---|
| Correct | 1 | **4** |
| Partly right | 5 | 2 |
| No answer | 0 | 2 |
| Wrong | 2 | **0** |
| Cost per question | about $0.003 | about $0.014 |
| Median time | about 28 s | about 118 s |

The larger model found the Verstappen premise and gave the right Hamilton degradation numbers. Its two non-answers hit the step limit and returned nothing, which we have now changed so the run shows what it computed.

Two cautions. This is one run per model, on eight questions, and we wrote the expected facts after seeing early answers. And at about two minutes a question, the larger model is too slow to be a default for live chat.

*Source: hand check of the eight answers against the database, 7 November 2026.*

## What helps

Some of these were discovered by running real questions, and each one is now in the code:

- **Check every number.** Each figure with a decimal point or a unit must appear in a tool's output. An answer with an untraceable number goes back once, then is marked "unverified".
- **Show what the data holds.** Loaders list each text column's values and where data is missing. This is what would have surfaced the `SafetyCar` category.
- **Give a summary before the detail.** `race_summary` lets the model check a question's premise first.
- **Do not accept a sample as a result.** A model once reported the first row of a weather file as the race average.
- **Show partial results at the limit.** An answer that runs out of steps now shows what it computed, labelled "Analysis incomplete", rather than an empty box.
- **Run independent loads together.** Two drivers' laps and the race context are fetched at once. We added this last, and it is the reason for the parallel steps on the canvas.

## Open gaps

We have not measured these, and some we cannot yet measure at all.

- **Corners, braking and lateral g.** The tools exist, and an estimate of peak lateral g for Hamilton in Singapore came out around 4 to 5 g. The analyst has not been tested on these questions, so we do not claim it answers them.
- **Throttle and tyre temperature.** We could not find a throttle channel in the stored telemetry. The original agent reported "0% throttle" for that reason. Tyre temperature is not stored at all.
- **Traffic.** We use 1.35 s behind the car ahead as the threshold for traffic. It comes from a simulation of one circuit (Bahrain) in a paper on multi-agent race strategy. We have not checked it on our data, and for several races the gaps are unknown because a lap time is missing.
- **The scorer.** It still passes some wrong answers and fails some right ones. Any result here needs a hand check.
- **Sample size.** Eight and ten questions are too few for a benchmark. They are enough to show where the agent fails.
- **Routing.** We do not yet send simple questions to the cheap path and hard ones to the larger model. This is the next thing to build.
- **Trap tier.** The analyst has not been run on the four questions where the correct answer is a refusal.

We did not search for existing benchmarks of this kind, so we cannot say how this compares with them. The eval is small enough that a published one would be a better comparison.

## References

1. Fieni, G., Wüthrich, J., Neumann, M.-P. and Onder, C. H. *Learning-based Multi-agent Race Strategies in Formula 1.* arXiv:2602.23056, 2026. [arxiv.org/abs/2602.23056](https://arxiv.org/abs/2602.23056). Source of the 1.35 s traffic threshold, from a simulation at one circuit.
2. Zhou, P. et al. *Agent-as-a-Router: Agentic Model Routing for Coding Tasks.* arXiv:2606.22902, 2026. [arxiv.org/abs/2606.22902](https://arxiv.org/abs/2606.22902). Finds that a router short of execution-based information is the main bottleneck, on coding tasks. Not a data-analysis study.
3. Nam, J. et al. *DS-STAR: Data Science Agent via Iterative Planning and Verification.* arXiv:2509.21825, 2025. [arxiv.org/abs/2509.21825](https://arxiv.org/abs/2509.21825). A verifier that judges whether a plan is sufficient, which we have not yet built.
4. Lucaciu, R. C. and Győrödi, C. A. *Artificial Intelligence in Motorsport: A Scoping Review.* International Journal of Advanced Computer Science and Applications, 17(5), 2026. [Full text](https://pdfs.semanticscholar.org/3fd2/71ffc72994e47c885397b9b3abb6edd3cfd4.pdf). Of 50 included sources, 4 covered telemetry and race data analysis.
