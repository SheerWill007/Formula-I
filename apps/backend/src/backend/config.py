"""
Backend configuration via pydantic-settings.

Shared values (database, Redis, Kafka, MLflow, R2/telemetry) are defined once
in ``slipstream_config.CommonSettings``; this module adds only the backend's
own settings. Every value is read from the environment first (then a local
.env file). In production (FLASK_ENV=production) missing secrets or a
localhost DATABASE_URL fail fast instead of silently using insecure defaults.
"""

from __future__ import annotations

from typing import Literal

from pydantic import model_validator
from slipstream_config import DEV_SECRET_KEY, CommonSettings


class Settings(CommonSettings):
    # Flask
    secret_key: str = DEV_SECRET_KEY
    debug: bool = False
    testing: bool = False

    race_vector_index_dir: str = "./lancedb"
    race_vector_table: str = "race_intelligence_events"

    # Task 8 -- Cloudflare Vectorize retrieval for strategy documents.
    # When the account/token/index are unset the vector adapter falls back to a
    # local LanceDB table (development only); production uses Vectorize.
    cloudflare_account_id: str = ""
    cloudflare_vectorize_api_token: str = ""
    cloudflare_vectorize_index: str = ""
    strategy_vector_table: str = "strategy_document_chunks"
    strategy_retrieval_limit: int = 6

    # Embedding provider (OpenAI-compatible). Without a key a deterministic
    # local hash embedding of the configured dimension is used for dev/tests.
    embedding_provider: str = "openai"
    embedding_api_key: str = ""
    embedding_base_url: str = "https://api.openai.com/v1"
    embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = 1536
    embedding_timeout_seconds: int = 30

    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_routing_model: str = "openai/gpt-4o-mini"
    openrouter_final_model: str = "openai/gpt-4o-mini"
    openrouter_capable_model: str = "openai/gpt-4o-mini"
    openrouter_timeout_seconds: int = 30
    agent_free_daily_limit: int = 10
    agent_max_conversations: int = 3
    agent_max_question_chars: int = 500
    cors_origins: str = "http://localhost:3000"
    # Optional regex for extra allowed origins (e.g. Vercel preview deploys).
    cors_origin_regex: str = ""
    outbound_allowed_hosts: str = "openrouter.ai,api.openai.com,api.cloudflare.com"
    agent_free_daily_cost_usd: float = 0.30
    llm_breaker_failure_threshold: int = 3
    llm_breaker_open_timeout_seconds: int = 60

    agent_planner_mode: Literal["template", "llm"] = "template"

    # Analyst engine (backend.analyst): tool-calling loop + sandboxed Python
    analyst_model: str = "openai/gpt-4o-mini"
    analyst_max_steps: int = 10
    analyst_max_cost_usd: float = 0.03
    analyst_sandbox_timeout_seconds: int = 20

    clerk_issuer: str = ""
    clerk_admin_user_ids: str = ""

    @model_validator(mode="after")
    def _reject_dev_secret_in_production(self) -> "Settings":
        if self.flask_env.lower() == "production" and self.secret_key == DEV_SECRET_KEY:
            raise ValueError(
                "SECRET_KEY must be set in production (refusing the dev default)"
            )
        return self


settings = Settings()
