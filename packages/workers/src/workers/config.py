from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url:        str = "postgresql+psycopg://boxup:boxup@localhost:5432/boxup"
    redis_url:           str = "redis://localhost:6379/0"
    mlflow_tracking_uri: str = "http://localhost:5001"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
