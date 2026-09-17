# ADR 002: Apache Kafka as Central Event Bus

**Date:** 2026-03-01
**Status:** Accepted

## Context

Pitwaal has multiple producers (ingestion workers) and multiple consumers
(stream processors, ML pipeline, WebSocket bridge, database writers).
We need a way to decouple these services so each can be developed,
scaled, and restarted independently.

## Decision

Use **Apache Kafka** (KRaft mode — no ZooKeeper) as the central event bus.
All data flows through Kafka topics. No service calls another service directly
for data — it produces to or consumes from Kafka.

Run locally via Docker. No managed Kafka service required (zero cost).

## Consequences

- Services are fully decoupled: a consumer restarting doesn't lose messages
  (Kafka retains them for the configured retention period)
- Messages can be replayed from any offset — useful for reprocessing
  historical data or recovering from bugs
- Kafka UI (provectuslabs/kafka-ui) provides full visibility into topics,
  consumer group lag, and message inspection during development
- Adds operational complexity vs. direct service calls — justified by the
  number of independent consumers in this system
