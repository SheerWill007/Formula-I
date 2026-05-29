"""
Configuration for the ingestion service.

pydantic-settings reads these values from environment variables automatically.
On your laptop they come from .env — in production from real environment variables.
The variable names match exactly what's in .env.example.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql+psycopg://pitwall:pitwall@localhost:5432/pitwall"

    # Kafka
    kafka_bootstrap_servers: str = "localhost:9092"

    # FastF1
    fastf1_cache_dir: str = "./fastf1_cache"

    # How many rows to insert at once (batching is faster than one-by-one)
    db_batch_size: int = 500

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",   # ignore unknown env vars instead of crashing
    )


# Single instance used across the whole package
settings = Settings()
