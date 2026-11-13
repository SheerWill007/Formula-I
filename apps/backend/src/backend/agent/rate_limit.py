from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timedelta
from flask import jsonify, make_response

from backend.agent import persistence
from backend.config import settings


@dataclass(frozen=True)
class LimitDecision:
    rejected: bool
    error: str | None = None
    retry_after_seconds: int | None = None


def _seconds_until_midnight() -> int:
    now = datetime.now()
    midnight = (now + timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    return max(int((midnight - now).total_seconds()), 1)


def check_limits(clerk_user_id: str) -> LimitDecision:
    if persistence.count_runs_today(clerk_user_id) >= settings.agent_free_daily_limit:
        return LimitDecision(
            rejected=True,
            error="Daily question limit reached. Try again tomorrow.",
            retry_after_seconds=_seconds_until_midnight(),
        )

    if persistence.sum_cost_today(clerk_user_id) >= settings.agent_free_daily_cost_usd:
        return LimitDecision(
            rejected=True,
            error="Daily usage cost limit reached. Try again tomorrow.",
            retry_after_seconds=_seconds_until_midnight(),
        )

    return LimitDecision(rejected=False)


def limit_response(clerk_user_id: str):
    decision = check_limits(clerk_user_id)
    if not decision.rejected:
        return None
    response = make_response(jsonify({"error": decision.error}), 429)
    if decision.retry_after_seconds is not None:
        response.headers["Retry-After"] = str(decision.retry_after_seconds)
    return response
