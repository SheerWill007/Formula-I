"""Circuit breaker on LLM provider failures.

CLOSED -> (threshold consecutive failures) -> OPEN -> (open_timeout) -> HALF_OPEN
HALF_OPEN lets exactly one probe through; a success re-closes, a failure re-opens.

While OPEN, llm._post() refuses instantly and orchestrator.run() short-circuits
to a fast degraded answer -- no request individually hangs on a dead provider
(default 30s timeout) while retrying it.
"""

from __future__ import annotations
import enum
import threading
import time

import structlog

from backend.config import settings

log = structlog.get_logger()


class BreakerState(str, enum.Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    """Thread-safe state machine keyed on N *consecutive* failures."""

    def __init__(
        self,
        failure_threshold: int | None = None,
        open_timeout_seconds: float | None = None,
    ):

        self._failure_threshold = (
            failure_threshold
            if failure_threshold is not None
            else settings.llm_breaker_failure_threshold
        )
        self._open_timeout = (
            open_timeout_seconds
            if open_timeout_seconds is not None
            else settings.llm_breaker_open_timeout_seconds
        )
        self._lock = threading.Lock()
        self._reset()

    def _reset(self) -> None:
        self._state = BreakerState.CLOSED
        self._consecutive_failures = 0
        self._opened_at: float | None = None
        self._probe_used = False

    @property
    def state(self) -> BreakerState:
        with self._lock:
            self._refresh()
            return self._state

    def is_open(self) -> bool:
        """Full-OPEN means: skip the provider entirely, serve the fast degrade."""
        with self._lock:
            self._refresh()
            return self._state is BreakerState.OPEN

    def allow_request(self) -> bool:
        """May the caller attempt the real provider call right now?"""
        with self._lock:
            self._refresh()
            if self._state is BreakerState.CLOSED:
                return True
            if self._state is BreakerState.OPEN:
                return False
            if self._probe_used:
                return False
            self._probe_used = True
            return True

    def record_success(self) -> None:
        with self._lock:
            if self._state is BreakerState.HALF_OPEN:
                log.info("agent.breaker.closed", reason="half_open_probe_ok")
            self._state = BreakerState.CLOSED
            self._consecutive_failures = 0
            self._probe_used = False

    def record_failure(self) -> None:
        with self._lock:
            if self._state is BreakerState.HALF_OPEN:
                log.info("agent.breaker.reopened", reason="half_open_probe_failed")
                self._state = BreakerState.OPEN
                self._opened_at = time.monotonic()
                self._probe_used = False
                return
            self._consecutive_failures += 1
            if self._consecutive_failures >= self._failure_threshold:
                log.warning(
                    "agent.breaker.opened",
                    consecutive_failures=self._consecutive_failures,
                )
                self._state = BreakerState.OPEN
                self._opened_at = time.monotonic()

    def _refresh(self) -> None:
        """Lazily roll OPEN -> HALF_OPEN once the open timeout has elapsed."""
        if (
            self._state is BreakerState.OPEN
            and time.monotonic() - self._opened_at >= self._open_timeout
        ):
            self._state = BreakerState.HALF_OPEN
            self._probe_used = False

    def force_open(self) -> None:
        with self._lock:
            self._state = BreakerState.OPEN
            self._opened_at = time.monotonic()

    def reset(self) -> None:
        with self._lock:
            self._reset()


breaker = CircuitBreaker()
