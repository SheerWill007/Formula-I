"""Tests for the agent run feedback endpoints"""

from sqlalchemy import text

from backend import auth as auth_module
from backend import extensions

AUTH_HEADER = {"Authorization": "Bearer test-token"}


def _fake_auth(monkeypatch, clerk_user_id="demo-user"):
    monkeypatch.setattr(
        auth_module, "verify_session_token", lambda token: clerk_user_id
    )


def _insert_run(clerk_user_id="demo-user") -> int:
    """Seed a user + conversation + completed run directly, skipping the
    query pipeline. Returns the run id."""
    with extensions.engine.begin() as conn:
        user = conn.execute(
            text(
                """
                INSERT INTO users (clerk_user_id, email, name)
                VALUES (:uid, 'demo@pitwall.local', 'Demo')
                ON CONFLICT (clerk_user_id) DO NOTHING
                RETURNING id
                """
            ),
            {"uid": clerk_user_id},
        ).first()
        user_id = (
            user.id
            if user
            else conn.execute(
                text("SELECT id FROM users WHERE clerk_user_id = :uid"),
                {"uid": clerk_user_id},
            ).scalar_one()
        )

        conv = conn.execute(
            text(
                "INSERT INTO agent_conversations (user_id, title) "
                "VALUES (:uid, 'test') RETURNING id"
            ),
            {"uid": user_id},
        ).first()
        run = conn.execute(
            text(
                "INSERT INTO agent_runs (conversation_id, user_id, status, completed_at) "
                "VALUES (:cid, :uid, 'completed', NOW()) RETURNING id"
            ),
            {"cid": conv.id, "uid": user_id},
        ).first()
    return run.id


def _cleanup():
    with extensions.engine.begin() as conn:
        conn.execute(
            text(
                """
                DELETE FROM agent_run_feedback
                WHERE run_id IN (SELECT id FROM agent_runs)
                """
            )
        )
        conn.execute(text("DELETE FROM agent_runs"))
        conn.execute(text("DELETE FROM agent_conversations"))
        conn.execute(text("DELETE FROM users"))


def test_rate_run_happy_path(client, monkeypatch):
    _fake_auth(monkeypatch)
    try:
        run_id = _insert_run()
        resp = client.post(
            f"/api/v1/agent/runs/{run_id}/feedback",
            headers=AUTH_HEADER,
            json={"rating": 1},
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["run_id"] == run_id
        assert body["rating"] == 1

        with extensions.engine.connect() as conn:
            row = conn.execute(
                text("SELECT rating FROM agent_run_feedback WHERE run_id = :rid"),
                {"rid": run_id},
            ).first()
            assert row is not None
            assert row.rating == 1
    finally:
        _cleanup()


def test_rate_run_replaces_previous_vote(client, monkeypatch):
    _fake_auth(monkeypatch)
    try:
        run_id = _insert_run()
        client.post(
            f"/api/v1/agent/runs/{run_id}/feedback",
            headers=AUTH_HEADER,
            json={"rating": 1},
        )
        resp = client.post(
            f"/api/v1/agent/runs/{run_id}/feedback",
            headers=AUTH_HEADER,
            json={"rating": -1},
        )
        assert resp.status_code == 200

        with extensions.engine.connect() as conn:
            count = conn.execute(
                text("SELECT COUNT(*) FROM agent_run_feedback WHERE run_id = :rid"),
                {"rid": run_id},
            ).scalar_one()
            row = conn.execute(
                text("SELECT rating FROM agent_run_feedback WHERE run_id = :rid"),
                {"rid": run_id},
            ).first()
            assert count == 1  # one row, not two — the upsert replaced it
            assert row.rating == -1
    finally:
        _cleanup()


def test_rate_run_rejects_bad_rating(client, monkeypatch):
    _fake_auth(monkeypatch)
    try:
        run_id = _insert_run()
        resp = client.post(
            f"/api/v1/agent/runs/{run_id}/feedback",
            headers=AUTH_HEADER,
            json={"rating": 0},
        )
        assert resp.status_code == 400
    finally:
        _cleanup()


def test_rate_run_not_found_exists(client, monkeypatch):
    _fake_auth(monkeypatch)
    resp = client.post(
        "/api/v1/agent/runs/999999/feedback",
        headers=AUTH_HEADER,
        json={"rating": 1},
    )
    assert resp.status_code == 404


def test_rate_run_rejects_other_users_run(client, monkeypatch):
    _fake_auth(monkeypatch, "user_alpha")
    try:
        run_id = _insert_run(clerk_user_id="user_alpha")

        _fake_auth(monkeypatch, "user_beta")
        resp = client.post(
            f"/api/v1/agent/runs/{run_id}/feedback",
            headers={"Authorization": "Bearer beta"},
            json={"rating": -1},
        )
        assert resp.status_code == 404
    finally:
        _cleanup()


def test_clear_feedback_deletes_vote(client, monkeypatch):
    _fake_auth(monkeypatch)
    try:
        run_id = _insert_run()
        client.post(
            f"/api/v1/agent/runs/{run_id}/feedback",
            headers=AUTH_HEADER,
            json={"rating": 1},
        )
        resp = client.delete(
            f"/api/v1/agent/runs/{run_id}/feedback", headers=AUTH_HEADER
        )
        assert resp.status_code == 200
        assert resp.get_json()["rating"] is None

        with extensions.engine.connect() as conn:
            count = conn.execute(
                text("SELECT COUNT(*) FROM agent_run_feedback WHERE run_id = :rid"),
                {"rid": run_id},
            ).scalar_one()
            assert count == 0
    finally:
        _cleanup()


def test_clear_feedback_not_found(client, monkeypatch):
    _fake_auth(monkeypatch)
    resp = client.delete("/api/v1/agent/runs/999999/feedback", headers=AUTH_HEADER)
    assert resp.status_code == 404


def test_admin_feedback_stats(client, monkeypatch):
    _fake_auth(monkeypatch, "admin-user")
    from backend.config import settings

    monkeypatch.setattr(settings, "clerk_admin_user_ids", "admin-user")
    try:
        run1 = _insert_run(clerk_user_id="admin-user")
        run2 = _insert_run(clerk_user_id="admin-user")
        client.post(
            f"/api/v1/agent/runs/{run1}/feedback",
            headers=AUTH_HEADER,
            json={"rating": 1},
        )
        client.post(
            f"/api/v1/agent/runs/{run2}/feedback",
            headers=AUTH_HEADER,
            json={"rating": -1},
        )
        resp = client.get("/api/v1/agent/admin/feedback", headers=AUTH_HEADER)
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["up"] == 1
        assert body["down"] == 1
    finally:
        _cleanup()


def test_admin_feedback_requires_admin(client, monkeypatch):
    _fake_auth(monkeypatch)  # regular user
    resp = client.get("/api/v1/agent/admin/feedback", headers=AUTH_HEADER)
    assert resp.status_code == 403
