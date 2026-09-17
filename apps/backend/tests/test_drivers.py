"""Tests for the drivers endpoints."""


def test_list_drivers_returns_200(client, seed_session):
    response = client.get(f"/api/v1/sessions/{seed_session}/drivers")
    assert response.status_code == 200


def test_list_drivers_ordered_by_best_lap(client, seed_session):
    data = client.get(
        f"/api/v1/sessions/{seed_session}/drivers"
    ).get_json()
    times = [d["best_lap_ms"] for d in data if d["best_lap_ms"]]
    assert times == sorted(times)


def test_compare_requires_drivers_param(client, seed_session):
    response = client.get(
        f"/api/v1/sessions/{seed_session}/drivers/compare"
    )
    assert response.status_code == 400


def test_compare_requires_at_least_two_drivers(client, seed_session):
    response = client.get(
        f"/api/v1/sessions/{seed_session}/drivers/compare?drivers=44"
    )
    assert response.status_code == 400


def test_compare_returns_gap_to_fastest(client, seed_session):
    data = client.get(
        f"/api/v1/sessions/{seed_session}/drivers/compare?drivers=44,63"
    ).get_json()
    gaps = [d["gap_to_fastest_ms"] for d in data]
    # Fastest driver always has gap 0
    assert 0.0 in gaps


def test_compare_fastest_driver_has_zero_gap(client, seed_session):
    data = client.get(
        f"/api/v1/sessions/{seed_session}/drivers/compare?drivers=44,63"
    ).get_json()
    # RUS best=87000, HAM best=88000 → RUS has gap 0
    rus = next(d for d in data if d["abbreviation"] == "RUS")
    assert rus["gap_to_fastest_ms"] == 0.0


def test_compare_theoretical_best_is_sector_sum(client, seed_session):
    data = client.get(
        f"/api/v1/sessions/{seed_session}/drivers/compare?drivers=44,63"
    ).get_json()
    ham = next(d for d in data if d["abbreviation"] == "HAM")
    # HAM: best S1=27500, S2=35000, S3=25500 → 88000
    assert ham["theoretical_best_ms"] == 88000.0
