"""Integration tests for the agent HTTP endpoint (L6)."""

import gzip
import json
from pathlib import Path

from sqlalchemy import text

from backend import auth as auth_module
from backend.agent import orchestrator
from backend.config import settings

SESSION_KEY = 99993

# Any non-empty bearer passes the header check; _fake_auth mocks the verifier.
AUTH_HEADER = {"Authorization": "Bearer test-token"}


def _insert_session_and_driver(db_engine):
    with db_engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO sessions (
                    session_key, year, gp_name, session_type, session_name
                ) VALUES (
                    :sk, 2026, 'Monaco Grand Prix', 'R', 'Race'
                )
                """
            ),
            {"sk": SESSION_KEY},
        )
        conn.execute(
            text(
                """
                INSERT INTO drivers (
                    driver_number, session_key, full_name, abbreviation, team_name, team_colour
                ) VALUES (
                    55, :sk, 'Carlos Sainz', 'SAI', 'Ferrari', '#DC0000'
                )
                """
            ),
            {"sk": SESSION_KEY},
        )


def _insert_laps(db_engine):
    """Laps 1-8; pit stop on lap 5 (pit_in) / lap 6 (pit_out), SOFT -> HARD."""
    with db_engine.begin() as conn:
        for lap, compound, pit_in, pit_out in [
            (1, "SOFT", None, None),
            (2, "SOFT", None, None),
            (3, "SOFT", None, None),
            (4, "SOFT", None, None),
            (5, "SOFT", 123456.0, None),
            (6, "HARD", None, 234567.0),
            (7, "HARD", None, None),
            (8, "HARD", None, None),
        ]:
            conn.execute(
                text(
                    """
                    INSERT INTO lap_times (
                        session_key, driver_number, lap_number, lap_time_ms,
                        compound, pit_in_time_ms, pit_out_time_ms,
                        is_personal_best, deleted, recorded_at
                    ) VALUES (
                        :sk, 55, :lap, 100000, :compound, :pit_in, :pit_out,
                        false, false, NOW()
                    )
                    """
                ),
                {
                    "sk": SESSION_KEY,
                    "lap": lap,
                    "compound": compound,
                    "pit_in": pit_in,
                    "pit_out": pit_out,
                },
            )


def _write_gz_artifact(tmp_path, lap_number, speeds):
    storage_key = f"telemetry/session_{SESSION_KEY}/driver_55/lap_{lap_number}.json.gz"
    path = Path(tmp_path) / storage_key
    path.parent.mkdir(parents=True, exist_ok=True)
    samples = [{"speed_kmh": s, "distance_m": 1.0} for s in speeds]
    with gzip.open(path, "wb") as f:
        f.write(
            json.dumps(
                {
                    "session_key": SESSION_KEY,
                    "driver_number": 55,
                    "lap_number": lap_number,
                    "samples": samples,
                }
            ).encode("utf-8")
        )
    with path.open("rb") as f:
        size = len(f.read())
    return storage_key, size


def _insert_artifacts(db_engine, tmp_path):
    """Artifacts for the before window (2,3,4) and after window (7,8,9)."""
    entries = []
    for lap_number, speeds in [
        (2, [200.0, 210.0]),
        (3, [210.0, 220.0]),
        (4, [220.0, 230.0]),
        (7, [240.0, 250.0]),
        (8, [250.0, 260.0]),
        (9, [260.0, 270.0]),
    ]:
        storage_key, size = _write_gz_artifact(tmp_path, lap_number, speeds)
        entries.append((lap_number, storage_key, size, len(speeds)))
    with db_engine.begin() as conn:
        for lap_number, storage_key, size, count in entries:
            conn.execute(
                text(
                    """
                    INSERT INTO telemetry_artifacts (
                        session_key, driver_number, lap_number,
                        storage_key, storage_backend, format,
                        sample_count, size_bytes, checksum_sha256
                    ) VALUES (
                        :sk, 55, :lap, :key, 'local', 'json.gz', :count, :size, 'test'
                    )
                    """
                ),
                {
                    "sk": SESSION_KEY,
                    "lap": lap_number,
                    "key": storage_key,
                    "count": count,
                    "size": size,
                },
            )


def _cleanup(db_engine):
    with db_engine.begin() as conn:
        conn.execute(
            text(
                """
                DELETE FROM agent_tool_calls
                WHERE run_id IN (
                    SELECT id FROM agent_runs
                    WHERE user_id IN (
                        SELECT id FROM users WHERE clerk_user_id IN ('demo-user', 'user_alpha', 'user_beta', 'admin-user')
                    )
                )
                """
            )
        )
        conn.execute(
            text(
                """
                DELETE FROM agent_messages
                WHERE conversation_id IN (
                    SELECT id FROM agent_conversations
                    WHERE user_id IN (
                        SELECT id FROM users WHERE clerk_user_id IN ('demo-user', 'user_alpha', 'user_beta', 'admin-user')
                    )
                )
                """
            )
        )
        conn.execute(
            text(
                """
                DELETE FROM agent_runs
                WHERE user_id IN (
                    SELECT id FROM users WHERE clerk_user_id IN ('demo-user', 'user_alpha', 'user_beta', 'admin-user')
                )
                """
            )
        )
        conn.execute(
            text(
                """
                DELETE FROM agent_conversations
                WHERE user_id IN (
                    SELECT id FROM users WHERE clerk_user_id IN ('demo-user', 'user_alpha', 'user_beta', 'admin-user')
                )
                """
            )
        )
        conn.execute(
            text(
                "DELETE FROM users WHERE clerk_user_id IN ('demo-user', 'user_alpha', 'user_beta', 'admin-user')"
            )
        )
        conn.execute(
            text("DELETE FROM telemetry_artifacts WHERE session_key = :sk"),
            {"sk": SESSION_KEY},
        )
        conn.execute(
            text("DELETE FROM lap_times WHERE session_key = :sk"), {"sk": SESSION_KEY}
        )
        conn.execute(
            text("DELETE FROM drivers WHERE session_key = :sk"), {"sk": SESSION_KEY}
        )
        conn.execute(
            text("DELETE FROM sessions WHERE session_key = :sk"), {"sk": SESSION_KEY}
        )


def _fake_llm(monkeypatch, intent):
    monkeypatch.setattr(
        orchestrator.llm,
        "route_question",
        lambda q: (
            orchestrator.types.RoutedQuestion(
                intent=orchestrator.types.Intent(intent),
                driver_name="Sainz",
                year=2026,
                gp_name="Monaco",
            ),
            0.0,
        ),
    )
    monkeypatch.setattr(
        orchestrator.llm,
        "compose_answer",
        lambda q, e, **kwargs: ("Sainz pitted across laps 5 and 6.", 0.0),
    )


def _fake_auth(monkeypatch, clerk_user_id="demo-user"):
    """Replace JWKS verification with a stub identity."""
    monkeypatch.setattr(
        auth_module, "verify_session_token", lambda token: clerk_user_id
    )


def test_agent_query_limit_returns_retry_after(client, monkeypatch):
    from backend.agent import persistence

    _fake_auth(monkeypatch)
    monkeypatch.setattr(persistence, "count_runs_today", lambda uid: 99)
    monkeypatch.setattr(settings, "agent_free_daily_limit", 10)

    resp = client.post(
        "/api/v1/agent/query", headers=AUTH_HEADER, json={"question": "Who won?"}
    )
    assert resp.status_code == 429
    assert "Retry-After" in resp.headers
    assert resp.headers["Retry-After"].isdigit()


def _fake_bad_auth(monkeypatch):
    def boom(token):
        raise auth_module.ClerkAuthError("signature verification failed")

    monkeypatch.setattr(auth_module, "verify_session_token", boom)


def test_agent_query_happy_path(app, client, db_engine, monkeypatch, tmp_path):
    _fake_auth(monkeypatch)
    _insert_session_and_driver(db_engine)
    _insert_laps(db_engine)
    _insert_artifacts(db_engine, tmp_path)
    monkeypatch.setattr(settings, "telemetry_artifact_dir", str(tmp_path))
    _fake_llm(monkeypatch, "pit_stop_speed_delta")

    try:
        resp = client.post(
            "/api/v1/agent/query",
            headers=AUTH_HEADER,
            json={
                "question": "On which lap did Sainz pit and what was his avg speed before and after?"
            },
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["intent"] == "pit_stop_speed_delta"
        assert body["refusals"] == []
        assert isinstance(body.get("run_id"), int)
        assert body["pit_stop"]["pit_in_lap"] == 5
        assert body["pit_stop"]["pit_out_lap"] == 6
        assert body["speed_window"]["before_avg_speed_kmh"] == 215.0
        assert body["speed_window"]["after_avg_speed_kmh"] == 255.0
        assert body["speed_window"]["delta_kmh"] == 40.0
        assert len(body["trace"]) == 6
        assert body["trace"][0]["tool_name"] == "resolve_session"
        assert body["trace"][0]["status"] == "ok"
        assert body["trace_visibility"] == "evidence"
        assert body["trace"][0]["input_summary"] == ""
    finally:
        _cleanup(db_engine)


def test_agent_query_admin_receives_full_trace(
    app, client, db_engine, monkeypatch, tmp_path
):
    _fake_auth(monkeypatch, "admin-user")
    monkeypatch.setattr(settings, "clerk_admin_user_ids", "admin-user")
    _insert_session_and_driver(db_engine)
    _insert_laps(db_engine)
    _insert_artifacts(db_engine, tmp_path)
    monkeypatch.setattr(settings, "telemetry_artifact_dir", str(tmp_path))
    _fake_llm(monkeypatch, "pit_stop_speed_delta")

    try:
        resp = client.post(
            "/api/v1/agent/query",
            headers=AUTH_HEADER,
            json={
                "question": "On which lap did Sainz pit and what was his avg speed before and after?"
            },
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["trace_visibility"] == "full"
        assert body["trace"][0]["input_summary"]
        assert body["trace"][0]["output_summary"]
    finally:
        _cleanup(db_engine)


def test_agent_query_stream_emits_progress_and_final(
    app, client, db_engine, monkeypatch, tmp_path
):
    _fake_auth(monkeypatch)
    _insert_session_and_driver(db_engine)
    _insert_laps(db_engine)
    _insert_artifacts(db_engine, tmp_path)
    monkeypatch.setattr(settings, "telemetry_artifact_dir", str(tmp_path))
    _fake_llm(monkeypatch, "pit_stop_speed_delta")

    try:
        resp = client.post(
            "/api/v1/agent/query/stream",
            headers=AUTH_HEADER,
            json={
                "question": "On which lap did Sainz pit and what was his avg speed before and after?"
            },
        )
        assert resp.status_code == 200
        body = resp.get_data(as_text=True)
        assert "event: progress" in body
        assert "event: final" in body
        assert "resolve_session" in body
        assert '"trace_visibility": "evidence"' in body
        assert '"run_id":' in body
    finally:
        _cleanup(db_engine)


def test_agent_query_missing_question(client, monkeypatch):
    _fake_auth(monkeypatch)
    resp = client.post("/api/v1/agent/query", headers=AUTH_HEADER, json={})
    assert resp.status_code == 400
    assert "question" in resp.get_json()["error"]


def test_agent_query_unsupported(client, monkeypatch):
    _fake_auth(monkeypatch)
    _fake_llm(monkeypatch, "unsupported")
    resp = client.post(
        "/api/v1/agent/query",
        headers=AUTH_HEADER,
        json={"question": "What is the weather?"},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["intent"] == "unsupported"
    assert body["refusals"] == ["unsupported question"]


def test_agent_query_persists_run_and_tool_calls(
    app, client, db_engine, monkeypatch, tmp_path
):
    _fake_auth(monkeypatch)
    _insert_session_and_driver(db_engine)
    _insert_laps(db_engine)
    _insert_artifacts(db_engine, tmp_path)
    monkeypatch.setattr(settings, "telemetry_artifact_dir", str(tmp_path))
    _fake_llm(monkeypatch, "pit_stop_speed_delta")

    try:
        resp = client.post(
            "/api/v1/agent/query",
            headers=AUTH_HEADER,
            json={
                "question": "On which lap did Sainz pit and what was his avg speed before and after?"
            },
        )
        assert resp.status_code == 200

        with db_engine.connect() as conn:
            run = conn.execute(
                text(
                    """
                    SELECT r.status, r.error, r.completed_at IS NOT NULL AS has_completed,
                           COUNT(t.id) AS tool_count
                    FROM agent_runs r
                    LEFT JOIN agent_tool_calls t ON t.run_id = r.id
                    GROUP BY r.id
                    ORDER BY r.id DESC
                    LIMIT 1
                    """
                )
            ).first()
            assert run is not None
            assert run.status == "completed"
            assert run.error is None
            assert run.has_completed
            assert run.tool_count == 6

            call = conn.execute(
                text(
                    """
                    SELECT tool_name, status, duration_ms, input_json, output_summary_json
                    FROM agent_tool_calls
                    ORDER BY id ASC
                    LIMIT 1
                    """
                )
            ).first()
            assert call.tool_name == "resolve_session"
            assert call.status == "ok"
            assert call.duration_ms is not None
            assert call.input_json["summary"]
            assert call.output_summary_json["summary"]
    finally:
        _cleanup(db_engine)


def test_agent_query_persists_refused_run(client, db_engine, monkeypatch):
    _fake_auth(monkeypatch)
    _fake_llm(monkeypatch, "unsupported")
    resp = client.post(
        "/api/v1/agent/query",
        headers=AUTH_HEADER,
        json={"question": "What is the weather?"},
    )
    assert resp.status_code == 200

    with db_engine.connect() as conn:
        row = conn.execute(
            text("SELECT status, error FROM agent_runs ORDER BY id DESC LIMIT 1")
        ).first()
        assert row is not None
        assert row.status == "refused"
        assert row.error == "unsupported question"

    _cleanup(db_engine)


def test_agent_query_daily_limit_blocks_immediately(client, monkeypatch):
    _fake_auth(monkeypatch)
    monkeypatch.setattr(settings, "agent_free_daily_limit", 0)
    _fake_llm(monkeypatch, "pit_stop_speed_delta")

    resp = client.post(
        "/api/v1/agent/query", headers=AUTH_HEADER, json={"question": "Who won?"}
    )
    assert resp.status_code == 429
    assert "limit" in resp.get_json()["error"].lower()


def test_agent_query_daily_limit_allows_then_blocks(client, db_engine, monkeypatch):
    _fake_auth(monkeypatch)
    monkeypatch.setattr(settings, "agent_free_daily_limit", 1)
    _fake_llm(monkeypatch, "unsupported")

    try:
        first = client.post(
            "/api/v1/agent/query", headers=AUTH_HEADER, json={"question": "First?"}
        )
        assert first.status_code == 200

        second = client.post(
            "/api/v1/agent/query", headers=AUTH_HEADER, json={"question": "Second?"}
        )
        assert second.status_code == 429
    finally:
        _cleanup(db_engine)


def test_agent_query_rejects_missing_token(app):
    resp = app.test_client().post("/api/v1/agent/query", json={"question": "Who won?"})
    assert resp.status_code == 401
    assert "bearer" in resp.get_json()["error"].lower()


def test_agent_query_rejects_invalid_token(client, monkeypatch):
    _fake_bad_auth(monkeypatch)
    resp = client.post(
        "/api/v1/agent/query",
        json={"question": "Who won?"},
        headers={"Authorization": "Bearer not-a-real-jwt"},
    )
    assert resp.status_code == 401
    assert "invalid token" in resp.get_json()["error"].lower()


def test_agent_query_limit_is_per_user(client, db_engine, monkeypatch):
    _fake_llm(monkeypatch, "pit_stop_speed_delta")
    _insert_session_and_driver(db_engine)
    _insert_laps(db_engine)
    monkeypatch.setattr(settings, "agent_free_daily_limit", 1)

    try:
        alpha_headers = {"Authorization": "Bearer alpha"}
        beta_headers = {"Authorization": "Bearer beta"}

        _fake_auth(monkeypatch, "user_alpha")
        first = client.post(
            "/api/v1/agent/query", json={"question": "Q?"}, headers=alpha_headers
        )
        assert first.status_code == 200

        blocked = client.post(
            "/api/v1/agent/query", json={"question": "Q?"}, headers=alpha_headers
        )
        assert blocked.status_code == 429

        _fake_auth(monkeypatch, "user_beta")
        fresh = client.post(
            "/api/v1/agent/query", json={"question": "Q?"}, headers=beta_headers
        )
        assert fresh.status_code == 200
    finally:
        _cleanup(db_engine)


# ── Conversation persistence tests (L16) ────────────────────────────────────


def test_agent_query_creates_conversation_and_messages(
    app, client, db_engine, monkeypatch
):
    _fake_auth(monkeypatch)
    _fake_llm(monkeypatch, "unsupported")

    try:
        resp = client.post(
            "/api/v1/agent/query",
            headers=AUTH_HEADER,
            json={"question": "What is the weather?"},
        )
        assert resp.status_code == 200
        body = resp.get_json()
        conv_id = body.get("conversation_id")
        assert conv_id is not None
        assert isinstance(conv_id, int)

        # Verify conversation exists in DB.
        with db_engine.connect() as conn:
            conv = conn.execute(
                text("SELECT title FROM agent_conversations WHERE id = :id"),
                {"id": conv_id},
            ).first()
            assert conv is not None
            assert "weather" in conv.title.lower()

            # Verify two messages were stored.
            messages = conn.execute(
                text(
                    "SELECT role, content FROM agent_messages "
                    "WHERE conversation_id = :cid ORDER BY id ASC"
                ),
                {"cid": conv_id},
            ).fetchall()
            assert len(messages) == 2
            assert messages[0].role == "user"
            assert messages[0].content == "What is the weather?"
            assert messages[1].role == "assistant"
            assert len(messages[1].content) > 0

            # Verify run is linked to the conversation.
            run = conn.execute(
                text(
                    "SELECT conversation_id FROM agent_runs "
                    "WHERE conversation_id = :cid LIMIT 1"
                ),
                {"cid": conv_id},
            ).first()
            assert run is not None
            assert run.conversation_id == conv_id
    finally:
        _cleanup(db_engine)


def test_agent_query_reuses_conversation(app, client, db_engine, monkeypatch):
    _fake_auth(monkeypatch)
    _fake_llm(monkeypatch, "unsupported")

    try:
        # First question — creates a new conversation.
        resp1 = client.post(
            "/api/v1/agent/query",
            headers=AUTH_HEADER,
            json={"question": "First question"},
        )
        assert resp1.status_code == 200
        conv_id = resp1.get_json()["conversation_id"]

        # Second question — reuses the same conversation.
        resp2 = client.post(
            "/api/v1/agent/query",
            headers=AUTH_HEADER,
            json={"question": "Second question", "conversation_id": conv_id},
        )
        assert resp2.status_code == 200
        assert resp2.get_json()["conversation_id"] == conv_id

        # Verify four messages in the conversation (2 user + 2 assistant).
        with db_engine.connect() as conn:
            count = conn.execute(
                text(
                    "SELECT COUNT(*) FROM agent_messages WHERE conversation_id = :cid"
                ),
                {"cid": conv_id},
            ).scalar_one()
            assert count == 4
    finally:
        _cleanup(db_engine)


def test_agent_query_rejects_wrong_conversation_owner(
    app, client, db_engine, monkeypatch
):
    _fake_llm(monkeypatch, "unsupported")

    try:
        # Create a conversation as alpha.
        _fake_auth(monkeypatch, "user_alpha")
        resp1 = client.post(
            "/api/v1/agent/query",
            headers={"Authorization": "Bearer alpha"},
            json={"question": "Alpha's question"},
        )
        conv_id = resp1.get_json()["conversation_id"]

        # Try to post to that conversation as beta — should 404.
        _fake_auth(monkeypatch, "user_beta")
        resp2 = client.post(
            "/api/v1/agent/query",
            headers={"Authorization": "Bearer beta"},
            json={"question": "Beta hijack", "conversation_id": conv_id},
        )
        assert resp2.status_code == 404
    finally:
        _cleanup(db_engine)


def test_list_conversations(app, client, db_engine, monkeypatch):
    _fake_auth(monkeypatch)
    _fake_llm(monkeypatch, "unsupported")

    try:
        # Create two conversations.
        client.post(
            "/api/v1/agent/query",
            headers=AUTH_HEADER,
            json={"question": "First topic"},
        )
        client.post(
            "/api/v1/agent/query",
            headers=AUTH_HEADER,
            json={"question": "Second topic"},
        )

        resp = client.get("/api/v1/agent/conversations", headers=AUTH_HEADER)
        assert resp.status_code == 200
        convs = resp.get_json()
        assert len(convs) >= 2
        assert convs[0]["title"] == "Second topic"
        assert convs[1]["title"] == "First topic"
        for c in convs:
            assert "id" in c
            assert "message_count" in c
    finally:
        _cleanup(db_engine)


def test_get_conversation_messages(app, client, db_engine, monkeypatch):
    _fake_auth(monkeypatch)
    _fake_llm(monkeypatch, "unsupported")

    try:
        # Create a conversation.
        resp = client.post(
            "/api/v1/agent/query",
            headers=AUTH_HEADER,
            json={"question": "Tell me about pit stops"},
        )
        conv_id = resp.get_json()["conversation_id"]

        # Fetch the conversation messages.
        resp = client.get(f"/api/v1/agent/conversations/{conv_id}", headers=AUTH_HEADER)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["id"] == conv_id
        assert len(data["messages"]) == 2
        assert data["messages"][0]["role"] == "user"
        assert data["messages"][1]["role"] == "assistant"
    finally:
        _cleanup(db_engine)


def test_get_conversation_messages_not_found(app, client, monkeypatch):
    _fake_auth(monkeypatch)
    resp = client.get("/api/v1/agent/conversations/999999", headers=AUTH_HEADER)
    assert resp.status_code == 404
