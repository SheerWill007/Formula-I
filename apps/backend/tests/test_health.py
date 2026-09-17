"""Tests for the health check endpoint."""


def test_health_returns_ok(client):
    response = client.get("/health")
    assert response.status_code == 200


def test_health_response_shape(client):
    data = client.get("/health").get_json()
    assert "status"   in data
    assert "database" in data
    assert "version"  in data


def test_health_database_is_ok(client):
    data = client.get("/health").get_json()
    assert data["database"] == "ok"
    assert data["status"]   == "ok"
