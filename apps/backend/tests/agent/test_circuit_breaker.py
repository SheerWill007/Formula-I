import urllib.error
import urllib.request

from backend.agent import circuit_breaker, orchestrator
from backend.agent.circuit_breaker import BreakerState, CircuitBreaker
from backend.config import settings


def _fresh(**kw) -> CircuitBreaker:
    return CircuitBreaker(**kw)


def test_starts_closed():
    cb = _fresh()
    assert cb.state is BreakerState.CLOSED
    assert cb.allow_request()


def test_threshold_of_consecutive_failures_opens():
    cb = _fresh(failure_threshold=2)
    cb.record_failure()
    assert cb.state is BreakerState.CLOSED
    cb.record_failure()
    assert cb.state is BreakerState.OPEN
    assert not cb.allow_request()


def test_success_resets_failure_count():
    cb = _fresh(failure_threshold=2)
    cb.record_failure()
    cb.record_success()
    cb.record_failure()
    assert cb.state is BreakerState.CLOSED


def test_open_stays_blocked_until_timeout_then_one_probe(monkeypatch):
    cb = _fresh(failure_threshold=1, open_timeout_seconds=60)
    clock = [1000.0]

    def fake_monotonic():
        return clock[0]

    monkeypatch.setattr(circuit_breaker.time, "monotonic", fake_monotonic)
    cb.record_failure()
    assert cb.state is BreakerState.OPEN

    clock[0] = 1060.0 - 1
    assert not cb.allow_request()

    clock[0] = 1060.0 + 1
    assert cb.allow_request()
    assert not cb.allow_request()


def test_half_open_probe_success_recloses():
    cb = _fresh(failure_threshold=1, open_timeout_seconds=-1)
    cb.record_failure()
    assert cb.state is BreakerState.HALF_OPEN
    assert cb.allow_request()
    cb.record_success()
    assert cb.state is BreakerState.CLOSED
    assert cb.allow_request()


def test_half_open_probe_failure_reopens(monkeypatch):
    cb = _fresh(failure_threshold=1, open_timeout_seconds=3600)
    clock = [1000.0]
    monkeypatch.setattr(circuit_breaker.time, "monotonic", lambda: clock[0])

    cb.record_failure()  # OPEN at t=1000
    assert cb.state is BreakerState.OPEN

    clock[0] = 1000.0 + 3601  # window elapsed -> probe allowed
    assert cb.allow_request()

    clock[0] = 1000.0 + 3602.0
    cb.record_failure()  # probe failed -> re-OPEN at t=3602
    assert cb.state is BreakerState.OPEN  # new window has NOT elapsed yet

    clock[0] = 1000.0 + 3700.0  # still inside the new 3600s window
    assert not cb.allow_request()


def test_provider_outage_opens_breaker_then_short_circuits(monkeypatch):
    """Outage -> breaker opens -> later requests are served FAST degraded
    instead of each one re-hitting the dead provider and timing out."""
    monkeypatch.setattr(settings, "openrouter_api_key", "sk-test")
    provider_calls = {"n": 0}

    def boom(request, **kwargs):
        provider_calls["n"] += 1
        raise urllib.error.URLError("simulated provider outage")

    monkeypatch.setattr("backend.agent.llm.safe_urlopen", boom)

    breaker = _fresh(failure_threshold=2, open_timeout_seconds=3600)
    monkeypatch.setattr(circuit_breaker, "breaker", breaker)

    first = orchestrator.run("why was lap 5 slow?")
    assert first.refusals == ("llm_router_unavailable",)
    assert provider_calls["n"] == 1

    second = orchestrator.run("why was lap 5 slow?")
    assert second.refusals == ("llm_router_unavailable",)
    assert provider_calls["n"] == 2

    third = orchestrator.run("why was lap 5 slow?")
    assert third.refusals == ("llm_provider_unavailable",)
    assert provider_calls["n"] == 2
