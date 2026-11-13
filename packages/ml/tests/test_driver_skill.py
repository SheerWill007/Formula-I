import numpy as np
import pandas as pd
import pytest

from ml.driver_skill import cv, data, drift
from ml.driver_skill.model import Hyper, SkillModel


def test_parse_laptime():
    assert data.parse_laptime("1:27.470") == pytest.approx(87.47)
    assert data.parse_laptime("59.9") == pytest.approx(59.9)
    assert np.isnan(data.parse_laptime(None))
    assert np.isnan(data.parse_laptime(""))
    assert np.isnan(data.parse_laptime("no time"))


def _raw(rows):
    return pd.DataFrame(rows, columns=["year", "round", "race_name", "driver_id", "driver_name", "constructor_id", "q1"])


def test_build_gaps_flags_missing_and_outliers():
    raw = _raw(
        [
            (2024, 1, "A", "a", "A", "x", "1:30.000"),
            (2024, 1, "A", "b", "B", "x", "1:31.000"),  # 1.11% slower: ok
            (2024, 1, "A", "c", "C", "y", None),  # no lap
            (2024, 1, "A", "d", "D", "y", "1:45.000"),  # 16.7% slower: not a representative lap
        ]
    )
    df = data.build_gaps(raw).set_index("driver_id")
    assert df.loc["a", "gap"] == pytest.approx(0.0)
    assert df.loc["b", "gap"] == pytest.approx(100 * (91 / 90 - 1))
    assert df.loc["c", "status"] == "missing" and np.isnan(df.loc["c", "gap"])
    assert df.loc["d", "status"] == "outlier" and np.isnan(df.loc["d", "gap"])
    assert df.loc["d", "raw_gap"] > data.OUTLIER_PCT  # the raw value is kept


def _synthetic(seed=0, n_drivers=16, years=range(2010, 2018), rounds=10):
    """Teams of two. Drivers' skill follows a random walk and they swap teams, so cars and drivers are identifiable."""
    rng = np.random.default_rng(seed)
    n_teams = n_drivers // 2
    skill = {(d, y): 0.0 for d in range(n_drivers) for y in years}
    for d in range(n_drivers):
        level = rng.normal(0, 0.5)
        for y in years:
            level += rng.normal(0, 0.15)
            skill[(d, y)] = level
    rows = []
    for y in years:
        car = rng.normal(0, 1.5, n_teams)
        order = rng.permutation(n_drivers)  # reshuffle who drives for whom each year
        for r in range(1, rounds + 1):
            sess = rng.normal(1.0, 0.3)
            for slot, d in enumerate(order):
                t = slot // 2
                rows.append((y, r, f"r{r}", f"d{d}", f"d{d}", f"t{t}", sess + car[t] + skill[(d, y)] + rng.normal(0, 0.3), d))
    df = pd.DataFrame(rows, columns=["year", "round", "race_name", "driver_id", "driver_name", "constructor_id", "gap", "d"])
    df["session"] = df["year"].astype(str) + "-" + df["round"].astype(str).str.zfill(2)
    df["team_season"] = df["constructor_id"] + ":" + df["year"].astype(str)
    df["status"] = "ok"
    return df, skill


def test_model_recovers_known_skill():
    df, skill = _synthetic()
    m = SkillModel(Hyper(tau_car=1.5, tau_driver0=0.6, tau_walk=0.15)).fit(df)
    t = m.driver_table()
    est = t.assign(true=[skill[(int(r.driver_id[1:]), r.year)] for r in t.itertuples()])
    # compare within a season: a shared level shift between skill and car is not identifiable
    est["est_c"] = est["skill"] - est.groupby("year")["skill"].transform("mean")
    est["true_c"] = est["true"] - est.groupby("year")["true"].transform("mean")
    assert np.corrcoef(est["est_c"], est["true_c"])[0, 1] > 0.85


def test_posterior_sd_is_positive_and_shrinks_with_data():
    df, _ = _synthetic()
    full = SkillModel().fit(df).driver_table()
    half = SkillModel().fit(df[df["round"] <= 3]).driver_table()
    assert (full["sd"] > 0).all()
    assert full["sd"].mean() < half["sd"].mean()


def test_splits_never_leak_the_future():
    df, _ = _synthetic()
    for split in (cv.in_season_split, cv.season_ahead_split):
        for y in (2013, 2016):
            train, test = split(df, y)
            assert len(test) > 0
            assert train["session"].max() < test["session"].min()


def test_in_season_cv_beats_global_mean():
    df, _ = _synthetic()
    res = cv.evaluate(lambda: SkillModel(), df, [2014, 2015, 2016])
    base = cv.evaluate(lambda: __import__("ml.driver_skill.baselines", fromlist=["GlobalMean"]).GlobalMean(), df, [2014, 2015, 2016], name="g")
    assert res["rmse"].mean() < base["rmse"].mean()


def test_psi_is_zero_for_same_distribution_and_grows_with_shift():
    rng = np.random.default_rng(1)
    a = rng.normal(0, 1, 5000)
    assert drift.psi(a, rng.normal(0, 1, 5000)) < 0.05
    assert drift.psi(a, rng.normal(1.5, 1, 5000)) > 0.25
