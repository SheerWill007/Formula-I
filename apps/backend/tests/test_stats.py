"""Tests for the public landing page stats endpoint."""

from backend.api.v1 import stats as stats_module


def _reset_cache():
    stats_module._cache.update(at=0.0, body=None)


def test_stats_is_public(app):
    """No bearer token is needed: the landing page is visible when signed out."""
    _reset_cache()
    response = app.test_client().get("/api/v1/stats")
    assert response.status_code == 200


def test_stats_shape(client, seed_session):
    _reset_cache()
    data = client.get("/api/v1/stats").get_json()
    assert set(data) == {"sessions", "seasons", "first_season", "last_season", "laps"}
    assert data["sessions"] >= 1
    assert data["seasons"] >= 1
    assert data["first_season"] <= data["last_season"]
    assert data["laps"] >= 0


def test_stats_are_cached(client, seed_session):
    _reset_cache()
    first = client.get("/api/v1/stats").get_json()
    stats_module._cache["body"] = {**first, "sessions": 9999}
    assert client.get("/api/v1/stats").get_json()["sessions"] == 9999
    _reset_cache()
