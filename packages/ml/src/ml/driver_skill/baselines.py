"""Simple baselines the dynamic model has to beat. All share fit(df) / predict(df)."""
from __future__ import annotations

import numpy as np
import pandas as pd


class GlobalMean:
    name = "Global mean"

    def fit(self, df: pd.DataFrame):
        self.mu = float(df["gap"].mean())
        return self

    def predict(self, df: pd.DataFrame) -> np.ndarray:
        return np.full(len(df), self.mu)


class CarOnly:
    """Mean gap of the same team-season in training. Unseen team-season: last year's mean, else global."""

    name = "Car only"

    def fit(self, df: pd.DataFrame):
        d = df.dropna(subset=["gap"])
        self.mu = float(d["gap"].mean())
        self.by_ts = d.groupby("team_season")["gap"].mean().to_dict()
        return self

    def predict(self, df: pd.DataFrame) -> np.ndarray:
        out = []
        for r in df.itertuples(index=False):
            v = self.by_ts.get(r.team_season)
            if v is None:
                v = self.by_ts.get(f"{r.constructor_id}:{r.year - 1}", self.mu)
            out.append(v)
        return np.array(out)


class DriverOnly:
    """Mean of the driver's last ``k`` training gaps, ignoring the car."""

    name = "Driver only"

    def __init__(self, k: int = 6):
        self.k = k

    def fit(self, df: pd.DataFrame):
        d = df.dropna(subset=["gap"]).sort_values("session")
        self.mu = float(d["gap"].mean())
        self.recent = d.groupby("driver_id")["gap"].apply(lambda s: s.tail(self.k).mean()).to_dict()
        return self

    def predict(self, df: pd.DataFrame) -> np.ndarray:
        return np.array([self.recent.get(r.driver_id, self.mu) for r in df.itertuples(index=False)])


class TeammateDelta:
    """The old 'places ahead of teammate' idea made predictive.

    prediction = team-season mean + half of the driver's mean gap to his teammate that season.
    """

    name = "Teammate delta"

    def fit(self, df: pd.DataFrame):
        d = df.dropna(subset=["gap"])
        self.mu = float(d["gap"].mean())
        self.team = d.groupby("team_season")["gap"].mean().to_dict()
        tm = d.groupby(["session", "team_season"])["gap"].transform(lambda s: (s.sum() - s) / (len(s) - 1) if len(s) > 1 else np.nan)
        delta = (d["gap"] - tm).groupby([d["driver_id"], d["team_season"]]).mean()
        self.delta = delta.dropna().to_dict()
        return self

    def predict(self, df: pd.DataFrame) -> np.ndarray:
        out = []
        for r in df.itertuples(index=False):
            base = self.team.get(r.team_season)
            if base is None:
                base = self.team.get(f"{r.constructor_id}:{r.year - 1}", self.mu)
            out.append(base + 0.5 * self.delta.get((r.driver_id, r.team_season), 0.0))
        return np.array(out)
