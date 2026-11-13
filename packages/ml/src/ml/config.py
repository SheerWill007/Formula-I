"""
ML configuration via pydantic-settings.

Shared values (database, MLflow, telemetry artifacts) come from
``slipstream_config.CommonSettings``; this module adds only the ML service's
own settings.
"""

from __future__ import annotations

from slipstream_config import CommonSettings


class Settings(CommonSettings):
    model_name: str = "slipstream-race-predictor"
    ml_models_dir: str = "./ml_models"


settings = Settings()
