# Docs Index

This folder contains the deeper technical and operational documentation for Slipstream.

Use this page as the starting point if you are contributing, deploying, or trying to understand how the system works internally.

## Core guides

- [architecture.md](/Users/abdullahmusharaf/Desktop/F1/Pitwall/docs/architecture.md)
  System overview across ingestion, database, backend, frontend, workers, and ML.

- [data-model.md](/Users/abdullahmusharaf/Desktop/F1/Pitwall/docs/data-model.md)
  Core tables, important columns, and why some data is compact while telemetry is selective.

- [ingestion.md](/Users/abdullahmusharaf/Desktop/F1/Pitwall/docs/ingestion.md)
  Session ingestion behavior, reruns, telemetry policy, and common ingestion failures.

- [local-development.md](/Users/abdullahmusharaf/Desktop/F1/Pitwall/docs/local-development.md)
  Safe local setup, migrations, test habits, env handling, and reset recipes.

- [deployment.md](/Users/abdullahmusharaf/Desktop/F1/Pitwall/docs/deployment.md)
  Railway/Vercel deploy order, migrations, re-ingest steps, and operational safeguards.

- [testing.md](/Users/abdullahmusharaf/Desktop/F1/Pitwall/docs/testing.md)
  Backend/frontend testing approach and the rule to avoid Railway for tests.

## ML

- [ml-race-prediction.md](/Users/abdullahmusharaf/Desktop/F1/Pitwall/docs/ml-race-prediction.md)
  What session data the prediction pipeline needs, how features are sourced, and ML-specific failure modes.

## Concepts

- [concepts/qualifying-telemetry.md](/Users/abdullahmusharaf/Desktop/F1/Pitwall/docs/concepts/qualifying-telemetry.md)
  Why `Q1/Q2/Q3` telemetry is special, how `quali_segment` works, how pinned laps flow through the stack, and how the corner/braking comparison panels interpret segment-best laps.

## Launch and operations

- [release-checklist.md](/Users/abdullahmusharaf/Desktop/F1/Pitwall/docs/release-checklist.md)
  Pre-public launch checklist, including a storage-aware Railway plan for a 400 MB database budget.

## ADRs

Architectural decision records live under [docs/adr](/Users/abdullahmusharaf/Desktop/F1/Pitwall/docs/adr).

These explain why major technical decisions were made, such as:

- monorepo structure
- Kafka/event bus direction
- TimescaleDB for telemetry
