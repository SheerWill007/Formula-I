#!/bin/bash
# =============================================================================
# Slipstream — Kafka Topic Initialisation
# =============================================================================
# Run this once after Kafka starts to create all required topics.
# Safe to run multiple times (--if-not-exists flag).
#
# Topic naming convention: f1.<layer>.<name>
#   raw.*       = unprocessed data straight from APIs
#   processed.* = transformed/aggregated data
#   ml.*        = model outputs and AI insights
# =============================================================================

set -e  # exit immediately if any command fails

BOOTSTRAP="localhost:9092"
RETENTION_MS=604800000   # 7 days in milliseconds
CONTAINER="pitwall-kafka"

echo ""
echo "Creating Slipstream Kafka topics..."
echo "Bootstrap server: $BOOTSTRAP"
echo ""

create_topic() {
  local name=$1
  local partitions=$2
  local description=$3

  docker exec "$CONTAINER" kafka-topics \
    --bootstrap-server "$BOOTSTRAP" \
    --create \
    --if-not-exists \
    --topic "$name" \
    --partitions "$partitions" \
    --replication-factor 1 \
    --config retention.ms="$RETENTION_MS"

  echo "  ✅ $name ($partitions partition/s) — $description"
}

echo "── RAW LAYER (data straight from APIs) ──────────────────────────────"
create_topic "f1.raw.telemetry"       3  "Per-car telemetry: speed, brake, throttle, gear, RPM"
create_topic "f1.raw.timing"          3  "Lap times, sector times, intervals, gap to leader"
create_topic "f1.raw.positions"       2  "Car X/Y track positions per timestamp"
create_topic "f1.raw.session_status"  1  "Safety car, VSC, red flag, session state changes"

echo ""
echo "── PROCESSED LAYER (transformed by stream processor) ────────────────"
create_topic "f1.processed.driver_stats" 2  "Aggregated per-driver per-lap statistics"
create_topic "f1.processed.stint_data"   2  "Tyre compound, stint length, degradation rate"

echo ""
echo "── ML LAYER (model outputs and AI insights) ─────────────────────────"
create_topic "f1.ml.predictions"  1  "Podium probabilities, race winner confidence"
create_topic "f1.ml.anomalies"    1  "Pace drops, tyre cliffs, unusual behaviour detected"

echo ""
echo "── SYSTEM LAYER ─────────────────────────────────────────────────────"
create_topic "f1.alerts"  1  "Human-readable insight strings pushed to frontend"
create_topic "f1.dlq"     1  "Dead letter queue — invalid messages that failed validation"

echo ""
echo "All topics created. Listing:"
echo ""
docker exec "$CONTAINER" kafka-topics \
  --bootstrap-server "$BOOTSTRAP" \
  --list
echo ""
