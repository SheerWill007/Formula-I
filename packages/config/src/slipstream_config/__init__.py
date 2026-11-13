"""
Shared runtime settings for every Pitwall service.

Database, Redis, Kafka, MLflow, and R2/telemetry configuration live here so
each setting is defined exactly once. Every service subclasses
``CommonSettings`` and declares only the fields it owns.

Values are read from the environment first (then a local ``.env`` file). In
production (``FLASK_ENV=production``) insecure localhost/development defaults
fail fast instead of silently shipping to a hosted deployment.
"""

from __future__ import annotations

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEV_SECRET_KEY = "dev-secret-change-in-production"
DEV_DATABASE_URL = "postgresql+psycopg://pitwall:pitwall@localhost:5432/pitwall"


class CommonSettings(BaseSettings):
    # Runtime environment: development | staging | production | testing
    flask_env: str = "development"

    # Normalize provider-specific Postgres URL schemes for SQLAlchemy.
    database_url: str = DEV_DATABASE_URL

    # Redis + Kafka — optional, not required for the core app
    redis_url: str = "redis://localhost:6379/0"
    kafka_bootstrap_servers: str = "localhost:9092"

    # MLflow
    mlflow_tracking_uri: str = "http://localhost:5001"

    # FastF1 on-disk cache (used by ingestion and backend fallback paths)
    fastf1_cache_dir: str = "./fastf1_cache"

    # Raw telemetry artifacts. In cheap hosted deployments, Postgres stores
    # only metadata while compressed lap traces live outside the DB.
    telemetry_artifact_dir: str = "./telemetry_artifacts"
    telemetry_artifact_backend: str = "local"
    telemetry_artifact_bucket: str = ""
    r2_endpoint_url: str = ""
    r2_access_key_id: str = ""
    r2_secret_access_key: str = ""

    # Strategy documents (Task 7): original files/transcripts live outside
    # Postgres; only metadata + chunks are stored in the database.
    strategy_document_dir: str = "./strategy_documents"
    strategy_document_backend: str = "local"
    strategy_document_bucket: str = ""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @model_validator(mode="after")
    def _reject_insecure_production_defaults(self) -> "CommonSettings":
        if (
            self.flask_env.lower() == "production"
            and self.database_url == DEV_DATABASE_URL
        ):
            raise ValueError(
                "DATABASE_URL must be set in production (refusing the localhost default)"
            )
        return self

    @property
    def db_url(self) -> str:
        """
        Normalise DATABASE_URL for SQLAlchemy.
        Convert common PostgreSQL URL schemes to the SQLAlchemy psycopg driver.
        """
        url = self.database_url
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql+psycopg://", 1)
        elif url.startswith("postgresql://") and "+psycopg" not in url:
            url = url.replace("postgresql://", "postgresql+psycopg://", 1)
        return url


__all__ = ["CommonSettings", "DEV_DATABASE_URL", "DEV_SECRET_KEY"]
