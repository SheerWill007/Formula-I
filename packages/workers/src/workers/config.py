"""
Worker configuration via pydantic-settings.

The workers only need the shared runtime settings (database, Redis, MLflow);
those are defined once in ``slipstream_config.CommonSettings``.
"""

from __future__ import annotations

from slipstream_config import CommonSettings


class Settings(CommonSettings):
    pass


settings = Settings()
