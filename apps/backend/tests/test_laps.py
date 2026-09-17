"""Tests for the laps endpoints."""


def test_list_laps_returns_200(client, seed_session):
    response = client.get(f"/api/v1/sessions/{seed_session}/laps")
    assert response.status_code == 200


def test_list_laps_returns_all_drivers(client, seed_session):
    data = client.get(f"/api/v1/sessions/{seed_session}/laps").get_json()
    driver_nums = {row["driver_number"] for row in data}
    assert driver_nums == {44, 63}


def test_list_laps_filter_by_driver(client, seed_session):
    data = client.get(
        f"/api/v1/sessions/{seed_session}/laps?driver=44"
    ).get_json()
    assert all(row["driver_number"] == 44 for row in data)


def test_driver_laps_returns_laps_and_theoretical(client, seed_session):
    data = client.get(
        f"/api/v1/sessions/{seed_session}/drivers/44/laps"
    ).get_json()
    assert "laps" in data
    assert "theoretical_best" in data
    assert len(data["laps"]) == 2


def test_theoretical_best_is_sum_of_sectors(client, seed_session):
    data = client.get(
        f"/api/v1/sessions/{seed_session}/drivers/44/laps"
    ).get_json()
    tb = data["theoretical_best"]
    # Best S1=27500, S2=35000, S3=25500 → sum=88000
    assert tb["theoretical_best_ms"] == 88000.0


def test_fastest_laps_ordered_by_time(client, seed_session):
    resp = client.get(
        f"/api/v1/sessions/{seed_session}/fastest"
    ).get_json()
    data = resp["laps"]
    times = [row["lap_time_ms"] for row in data]
    assert times == sorted(times)


def test_fastest_laps_one_per_driver(client, seed_session):
    resp = client.get(
        f"/api/v1/sessions/{seed_session}/fastest"
    ).get_json()
    data = resp["laps"]
    driver_nums = [row["driver_number"] for row in data]
    # No duplicate drivers
    assert len(driver_nums) == len(set(driver_nums))
