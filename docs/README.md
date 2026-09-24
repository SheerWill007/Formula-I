# Docs Index

This folder contains the deeper technical and operational documentation for BoxUp.

Use this page as the starting point if you are contributing, deploying, or trying to understand how the system works internally.

## Core guides

- [architecture.md](architecture.md)
  System overview across ingestion, database, backend, frontend, workers, and ML.

- [data-model.md](data-model.md)
  Core tables, important columns, and why some data is compact while telemetry is selective.

- [ingestion.md](ingestion.md)
  Session ingestion behavior, reruns, telemetry policy, and common ingestion failures.

- [local-development.md](local-development.md)
  Safe local setup, migrations, test habits, env handling, and reset recipes.

- [deployment.md](deployment.md)
  Railway/Vercel deploy order, migrations, re-ingest steps, and operational safeguards.

- [testing.md](testing.md)
  Backend/frontend testing approach and the rule to avoid Railway for tests.

## ML

- [ml-race-prediction.md](ml-race-prediction.md)
  What session data the prediction pipeline needs, how features are sourced, and ML-specific failure modes.

## Concepts

- [concepts/qualifying-telemetry.md](concepts/qualifying-telemetry.md)
  Why `Q1/Q2/Q3` telemetry is special, how `quali_segment` works, how pinned laps flow through the stack, and how the corner/braking comparison panels interpret segment-best laps.

## Launch and operations

- [release-checklist.md](release-checklist.md)
  Pre-public launch checklist, including a storage-aware Railway plan for a 400 MB database budget.

## ADRs

Architectural decision records live under [docs/adr](adr).

These explain why major technical decisions were made, such as:

- monorepo structure
- Kafka/event bus direction
- TimescaleDB for telemetry

---

**Author**: [William Law II](https://willx.tech)
