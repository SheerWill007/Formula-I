"""Outbound host guard, run concurrency guard, question caps."""

import urllib.request

import pytest

from backend.agent import concurrency
from backend.net import safe_urlopen


def test_safe_urlopen_blocks_unlisted_host():
    req = urllib.request.Request("https://evil.example.com/x")
    with pytest.raises(ValueError):
        safe_urlopen(req, timeout=1)


def test_safe_urlopen_blocks_plain_http_and_internal_addresses():
    for url in ("http://openrouter.ai/x", "https://169.254.169.254/latest/meta-data"):
        with pytest.raises(ValueError):
            safe_urlopen(urllib.request.Request(url), timeout=1)


def test_one_active_run_per_user():
    assert concurrency.try_acquire("u1") is True
    assert concurrency.try_acquire("u1") is False
    assert concurrency.try_acquire("u2") is True
    concurrency.release("u1")
    assert concurrency.try_acquire("u1") is True
    concurrency.release("u1")
    concurrency.release("u2")


def test_overlong_question_is_rejected(client):
    resp = client.post("/api/v1/agent/query", json={"question": "x" * 501})
    assert resp.status_code == 400
    assert "too long" in resp.get_json()["error"].lower()


def test_conversation_id_must_be_integer(client):
    resp = client.post(
        "/api/v1/agent/query", json={"question": "hi", "conversation_id": "1; DROP"}
    )
    assert resp.status_code == 400
