from backend.agent import persistence
from backend.agent import rate_limit
from backend.config import settings


def test_under_both_limits_allowed(monkeypatch):
    monkeypatch.setattr(persistence, "count_runs_today", lambda uid: 1)
    monkeypatch.setattr(persistence, "sum_cost_today", lambda uid: 0.10)
    monkeypatch.setattr(settings, "agent_free_daily_limit", 10)
    monkeypatch.setattr(settings, "agent_free_daily_cost_usd", 0.50)
    decision = rate_limit.check_limits("user")
    assert decision.rejected is False


def test_count_breach_rejected_with_retry_after(monkeypatch):
    monkeypatch.setattr(persistence, "count_runs_today", lambda uid: 10)
    monkeypatch.setattr(settings, "agent_free_daily_limit", 10)
    decision = rate_limit.check_limits("user")
    assert decision.rejected
    assert "question limit" in decision.error.lower()
    assert decision.retry_after_seconds is not None
    assert decision.retry_after_seconds >= 1


def test_cost_breach_rejected(monkeypatch):
    monkeypatch.setattr(persistence, "count_runs_today", lambda uid: 0)
    monkeypatch.setattr(persistence, "sum_cost_today", lambda uid: 2.0)
    monkeypatch.setattr(settings, "agent_free_daily_cost_usd", 1.0)
    decision = rate_limit.check_limits("user")
    assert decision.rejected
    assert "cost" in decision.error.lower()


def test_count_breach_checked_before_cost(monkeypatch):
    monkeypatch.setattr(persistence, "count_runs_today", lambda uid: 10)
    monkeypatch.setattr(persistence, "sum_cost_today", lambda uid: 999.0)
    monkeypatch.setattr(settings, "agent_free_daily_limit", 10)
    monkeypatch.setattr(settings, "agent_free_daily_cost_usd", 5.0)
    decision = rate_limit.check_limits("user")
    assert "question limit" in decision.error.lower()
