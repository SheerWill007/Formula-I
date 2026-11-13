from types import SimpleNamespace

import pandas as pd

from ml import features
from ml.features import _shrink, compute_circuit_priors


class _FakeConn:
    def __init__(self, sc, dnf):
        self._rows = [sc, dnf]
        self.calls = []

    def execute(self, sql, params=None):
        self.calls.append((str(sql), params))
        return SimpleNamespace(one=lambda row=self._rows.pop(0): row)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class _FakeEngine:
    def __init__(self, sc, dnf):
        self.sc, self.dnf = sc, dnf
        self.conns = []

    def connect(self):
        conn = _FakeConn(self.sc, self.dnf)
        self.conns.append(conn)
        return conn


class _BrokenEngine:
    def connect(self):
        raise RuntimeError("relation track_status_periods does not exist")


BEFORE = pd.Timestamp("2025-06-01", tz="UTC")


def test_shrink_moves_toward_data_as_sample_grows():
    assert _shrink(0, 0, 0.5) == 0.5  # no data -> prior
    assert abs(_shrink(1, 1, 0.5) - 0.625) < 1e-9  # one SC race barely moves it
    assert _shrink(10, 10, 0.5) > 0.88  # ten of ten -> mostly data


def test_without_engine_returns_hand_set_priors():
    p = compute_circuit_priors("Monaco Grand Prix")
    assert p["sc_probability"] == 0.80 and p["dnf_rate_circuit"] == 0.18


def test_observed_rates_override_prior_with_shrinkage():
    engine = _FakeEngine(
        SimpleNamespace(races=4, sc_races=0),  # 4 prior races, never an SC
        SimpleNamespace(entries=80, dnfs=0),
    )
    p = compute_circuit_priors("Monaco Grand Prix", engine, BEFORE)
    calls = engine.conns[0].calls
    assert len(calls) == 2
    for sql, params in calls:  # point-in-time and per-circuit, bound not interpolated
        assert "s.gp_name = :gp" in sql and "s.date_start < :before" in sql
        assert params["gp"] == "Monaco Grand Prix"
        assert params["before"] == BEFORE.to_pydatetime()
    assert "Disqualified" in calls[1][0]  # a DSQ is not a reliability retirement
    assert p["sc_probability"] < 0.80  # pulled down by data
    assert p["sc_probability"] > 0.0  # but not all the way
    assert p["dnf_rate_circuit"] < 0.18
    assert p["overtake_difficulty"] == 0.95  # untouched


def test_no_ingested_history_keeps_prior():
    engine = _FakeEngine(
        SimpleNamespace(races=0, sc_races=0), SimpleNamespace(entries=0, dnfs=0)
    )
    assert compute_circuit_priors("Monaco Grand Prix", engine, BEFORE)[
        "sc_probability"
    ] == 0.80


def test_missing_tables_fall_back_to_prior():
    p = compute_circuit_priors("Monaco Grand Prix", _BrokenEngine(), BEFORE)
    assert p["sc_probability"] == 0.80
    assert features  # module imported
