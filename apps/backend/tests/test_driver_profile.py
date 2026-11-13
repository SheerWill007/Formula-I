"""Tests for the driver profile endpoint."""


def test_profile_rejects_invalid_code(client):
    assert client.get("/api/v1/drivers/12345/profile").status_code == 400


def test_profile_is_public(app):
    assert app.test_client().get("/api/v1/drivers/SAI/profile").status_code != 401
