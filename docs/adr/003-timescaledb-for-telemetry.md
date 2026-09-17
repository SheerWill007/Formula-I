# ADR 003: TimescaleDB for Time-Series Telemetry

**Date:** 2026-03-01
**Status:** Accepted

## Context

F1 telemetry is inherently time-series data: thousands of data points per
second per car, queried almost exclusively by time range and driver.
We need a database that handles this efficiently at zero cost.

## Decision

Use **TimescaleDB** — a PostgreSQL extension that adds time-series hypertables,
automatic time-based partitioning, and columnar compression.

It runs as a drop-in replacement for PostgreSQL (same wire protocol, same
SQLAlchemy connection string, same Alembic migrations). No new database
client libraries required.

## Consequences

- `SELECT create_hypertable('telemetry', 'recorded_at')` is the only
  extra step vs. a regular PostgreSQL table
- Queries over time ranges (e.g., lap 20 to lap 35) are 10-100x faster
  than unpartitioned PostgreSQL for large datasets
- Compression reduces telemetry storage by ~90% with no query API changes
- Free, self-hosted, runs in Docker alongside regular PostgreSQL tables
