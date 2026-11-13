"""Tests for the sessions endpoints."""


def test_list_sessions_returns_200(client, seed_session):
    response = client.get("/api/v1/sessions")
    assert response.status_code == 200


def test_list_sessions_returns_list(client, seed_session):
    data = client.get("/api/v1/sessions").get_json()
    assert isinstance(data, list)
    assert len(data) >= 1


def test_list_sessions_shape(client, seed_session):
    """Every session in the list must have these fields."""
    data = client.get("/api/v1/sessions").get_json()
    required_fields = {"session_key", "year", "gp_name", "session_type"}
    for session in data:
        assert required_fields.issubset(session.keys())


def test_get_session_returns_correct_data(client, seed_session):
    data = client.get(f"/api/v1/sessions/{seed_session}").get_json()
    assert data["session_key"] == seed_session
    assert data["gp_name"] == "Test Grand Prix"
    assert data["session_type"] == "Q"


def test_get_session_includes_drivers(client, seed_session):
    data = client.get(f"/api/v1/sessions/{seed_session}").get_json()
    assert "drivers" in data
    assert len(data["drivers"]) == 2
    abbreviations = {d["abbreviation"] for d in data["drivers"]}
    assert abbreviations == {"HAM", "RUS"}


def test_get_session_not_found(client):
    response = client.get("/api/v1/sessions/000000")
    assert response.status_code == 404


def test_list_sessions_reports_whether_laps_are_loaded(client, seed_session):
    """The telemetry picker hides sessions whose laps have not loaded yet."""
    data = client.get("/api/v1/sessions").get_json()
    assert all(isinstance(s["has_laps"], bool) for s in data)
