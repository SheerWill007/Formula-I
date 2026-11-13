"""Backfill waits out FastF1's hourly request budget instead of failing."""

import pytest

from ingestion import backfill


class RateLimitExceededError(Exception):
    """Same class name FastF1 raises; detection is by name."""


def test_waits_then_retries_after_rate_limit(monkeypatch):
    calls = {"n": 0}

    def fake_ingest(year, gp, session, skip_telemetry=False):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RateLimitExceededError("any API: 500 calls/h")
        return 1234

    sleeps: list[int] = []
    monkeypatch.setattr(backfill, "ingest_session", fake_ingest)

    key, waits = backfill._ingest_with_rate_limit_wait(
        2025, "Monaco", "Race", False, 0, sleep=sleeps.append
    )

    assert key == 1234
    assert waits == 1
    assert sleeps == [backfill.RATE_LIMIT_SLEEP_SECONDS]


def test_gives_up_once_wait_budget_is_spent(monkeypatch):
    def always_limited(*args, **kwargs):
        raise RateLimitExceededError("any API: 500 calls/h")

    monkeypatch.setattr(backfill, "ingest_session", always_limited)

    with pytest.raises(RateLimitExceededError):
        backfill._ingest_with_rate_limit_wait(
            2025, "Monaco", "Race", False, backfill.RATE_LIMIT_MAX_WAITS, sleep=lambda s: None
        )


def test_other_errors_are_not_retried(monkeypatch):
    def boom(*args, **kwargs):
        raise ValueError("bad data")

    sleeps: list[int] = []
    monkeypatch.setattr(backfill, "ingest_session", boom)

    with pytest.raises(ValueError):
        backfill._ingest_with_rate_limit_wait(2025, "Monaco", "Race", False, 0, sleep=sleeps.append)
    assert sleeps == []
