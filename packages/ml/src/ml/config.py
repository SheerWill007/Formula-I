from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url:        str = "postgresql+psycopg://pitwall:pitwall@localhost:5432/pitwall"
    mlflow_tracking_uri: str = "http://localhost:5001"
    model_name:          str = "slipstream-race-predictor"

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )

    @property
    def db_url(self) -> str:
        url = self.database_url
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql+psycopg://", 1)
        elif url.startswith("postgresql://") and "+psycopg" not in url:
            url = url.replace("postgresql://", "postgresql+psycopg://", 1)
        return url


settings = Settings()
