"""
Configuration for the ingestion service.

Shared values (database, Kafka, telemetry/R2 artifacts) come from
``slipstream_config.CommonSettings``; this module adds only the ingestion
service's own settings.

pydantic-settings reads these values from environment variables automatically.
On your laptop they come from .env — in production from real environment
variables. The variable names match exactly what's in .env.example.
"""

from __future__ import annotations

from slipstream_config import CommonSettings


class Settings(CommonSettings):
    # OpenF1 live-feed metadata (team radio)
    openf1_base_url: str = "https://api.openf1.org"
    openf1_timeout_seconds: int = 10

    # Jolpica (Ergast successor) historical results
    jolpica_base_url: str = "https://api.jolpi.ca/ergast/f1"

    # How many rows to insert at once (batching is faster than one-by-one)
    db_batch_size: int = 500

    # Raw telemetry can be expensive in hosted Postgres. Keep "database" for
    # local/Timescale workflows, or use "files" to store compressed lap traces
    # outside Postgres and keep only metadata in the DB.
    telemetry_storage_mode: str = "database"


# Single instance used across the whole package
settings = Settings()
