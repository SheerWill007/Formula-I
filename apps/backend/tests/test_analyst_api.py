"""Analyst API tests: scripted model, fake sandbox, real test database."""

import json

import pytest
from sqlalchemy import text

from backend import auth as backend_auth
from backend.analyst.client import Reply, ToolCall
from backend.analyst.sandbox import SandboxResult
from backend.api.v1 import analyst as analyst_api
from backend.config import settings

CHART = {"title": "Deg", "option": {"series": [{"type": "line", "data": [1, 2]}]}}


class FakeSandbox:
    def run(self, code, workspace, *, timeout_s=20):
        return SandboxResult(True, "0.08\n", "", 0.2, charts=[CHART])


class ScriptedLLM:
    def __init__(self):
        self.replies = [
            Reply(
                "Fit it.",
                (ToolCall("c1", "run_python", '{"code": "# Fit\\nprint(0.08)"}'),),
                cost_usd=0.002,
            ),
            Reply(
                "",
                (
                    ToolCall(
                        "c2",
                        "final_answer",
                        '{"markdown": "Degradation is 0.08 s/lap (estimate)."}',
                    ),
                ),
                cost_usd=0.001,
            ),
        ]

    def chat(self, messages, tools):
        return self.replies.pop(0)


@pytest.fixture(autouse=True)
def fakes(monkeypatch, db_engine):
    monkeypatch.setattr(analyst_api, "make_llm", ScriptedLLM)
    monkeypatch.setattr(analyst_api, "make_sandbox", FakeSandbox)
    monkeypatch.setattr(analyst_api, "sandbox_ready", lambda: True)
    yield
    with db_engine.begin() as conn:
        conn.execute(text("DELETE FROM analyst_runs"))
        conn.execute(text("DELETE FROM agent_messages"))
        conn.execute(text("DELETE FROM agent_conversations"))


def _frames(response):
    out = []
    for block in response.get_data(as_text=True).strip().split("\n\n"):
        lines = block.split("\n")
        out.append(
            (
                lines[0].removeprefix("event: "),
                json.loads(lines[1].removeprefix("data: ")),
            )
        )
    return out


def _ask(client, question="How bad was the degradation?"):
    response = client.post("/api/v1/agent/analyst/stream", json={"question": question})
    response.get_data()  # drain the stream so the worker has saved the run
    return response


def test_stream_emits_events_saves_the_run_and_ends(client):
    response = _ask(client)
    assert response.status_code == 200
    frames = _frames(response)
    kinds = [data["type"] for name, data in frames if name == "analyst"]
    assert kinds == ["run_start", "thought", "tool_start", "tool_end", "chart", "final"]
    assert frames[-1][0] == "done"
    saved = next(data for name, data in frames if name == "saved")
    assert saved["run_id"] > 0 and saved["conversation_id"] > 0


def test_saved_run_can_be_replayed(client):
    saved = next(d for n, d in _frames(_ask(client)) if n == "saved")
    run = client.get(f"/api/v1/agent/analyst/runs/{saved['run_id']}").get_json()
    assert run["answer"] == "Degradation is 0.08 s/lap (estimate)."
    assert run["cost_usd"] == pytest.approx(0.003)
    assert [e["type"] for e in run["events"]][-1] == "final"
    chart_event = next(e for e in run["events"] if e["type"] == "chart")
    assert chart_event["option"] == CHART["option"]


def test_runs_are_listed_newest_first(client):
    _ask(client, "first question")
    _ask(client, "second question")
    runs = client.get("/api/v1/agent/analyst/runs").get_json()
    assert [r["question"] for r in runs][:2] == ["second question", "first question"]


def test_another_user_cannot_read_a_run(client, monkeypatch):
    saved = next(d for n, d in _frames(_ask(client)) if n == "saved")
    monkeypatch.setattr(
        backend_auth, "verify_session_token", lambda token: "someone-else"
    )
    assert (
        client.get(f"/api/v1/agent/analyst/runs/{saved['run_id']}").status_code == 404
    )
    assert client.get("/api/v1/agent/analyst/runs").get_json() == []


def test_missing_question_is_a_400(client):
    assert client.post("/api/v1/agent/analyst/stream", json={}).status_code == 400


def test_unauthenticated_request_is_a_401(app):
    response = app.test_client().post(
        "/api/v1/agent/analyst/stream", json={"question": "q"}
    )
    assert response.status_code == 401


def test_unavailable_sandbox_is_a_503(client, monkeypatch):
    monkeypatch.setattr(analyst_api, "sandbox_ready", lambda: False)
    assert _ask(client).status_code == 503


def test_daily_limit_is_enforced(client, monkeypatch):
    monkeypatch.setattr(settings, "agent_free_daily_limit", 1)
    assert _ask(client).status_code == 200
    second = _ask(client)
    assert second.status_code == 429 and "limit" in second.get_json()["error"]


def test_model_failure_is_saved_as_an_error_run(client, monkeypatch):
    from backend.analyst.client import AnalystLLMError

    class Broken:
        def chat(self, messages, tools):
            raise AnalystLLMError("provider down")

    monkeypatch.setattr(analyst_api, "make_llm", Broken)
    frames = _frames(_ask(client))
    assert any(d.get("type") == "error" for n, d in frames if n == "analyst")
    saved = next(d for n, d in frames if n == "saved")
    run = client.get(f"/api/v1/agent/analyst/runs/{saved['run_id']}").get_json()
    assert run["error"] == "provider down"


def _saved(response):
    return next(d for n, d in _frames(response) if n == "saved")


def test_fourth_new_chat_is_rejected(client, monkeypatch):
    monkeypatch.setattr(settings, "agent_free_daily_limit", 99)
    for _ in range(3):
        assert _ask(client).status_code == 200
    fourth = _ask(client)
    assert fourth.status_code == 429
    assert "chat limit" in fourth.get_json()["error"].lower()


def test_follow_up_in_same_chat_does_not_use_a_new_slot(client, monkeypatch):
    monkeypatch.setattr(settings, "agent_free_daily_limit", 99)
    conv = _saved(_ask(client))["conversation_id"]
    for _ in range(4):
        resp = client.post(
            "/api/v1/agent/analyst/stream",
            json={"question": "another", "conversation_id": conv},
        )
        assert resp.status_code == 200
        resp.get_data()  # finish the stream so the run guard is released


def test_deleting_a_chat_frees_a_slot_but_keeps_usage(client, monkeypatch):
    monkeypatch.setattr(settings, "agent_free_daily_limit", 99)
    convs = [_saved(_ask(client))["conversation_id"] for _ in range(3)]
    assert _ask(client).status_code == 429
    assert client.delete(f"/api/v1/agent/conversations/{convs[0]}").status_code == 200
    assert client.delete(f"/api/v1/agent/conversations/{convs[0]}").status_code == 404
    assert _ask(client).status_code == 200
    # runs of the deleted chat still count toward today's usage
    assert client.get("/api/v1/agent/usage").get_json()["used"] >= 0
    listed = client.get("/api/v1/agent/conversations").get_json()
    assert convs[0] not in [c["id"] for c in listed]


def test_cannot_continue_a_deleted_chat(client, monkeypatch):
    monkeypatch.setattr(settings, "agent_free_daily_limit", 99)
    conv = _saved(_ask(client))["conversation_id"]
    client.delete(f"/api/v1/agent/conversations/{conv}")
    resp = client.post(
        "/api/v1/agent/analyst/stream",
        json={"question": "again", "conversation_id": conv},
    )
    assert resp.status_code == 404


def test_second_run_while_one_is_active_is_rejected(client):
    from backend.agent import concurrency

    assert concurrency.try_acquire("test-clerk-user")
    try:
        assert _ask(client).status_code == 429
    finally:
        concurrency.release("test-clerk-user")
