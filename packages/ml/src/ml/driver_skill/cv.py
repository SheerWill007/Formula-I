"""Temporal cross-validation. Never shuffles: every test row is later than every training row.

Two protocols, because they answer different questions:

``in_season``  (walk-forward, one fold per season)
    Train on every earlier season plus the first half of season T; predict the
    second half. "Given what we know mid-year, how well do we forecast the rest?"
    The team-season is always known, so this mostly tests the *driver* side.

``season_ahead`` (rolling origin, one fold per season)
    Train on seasons before T; predict all of T. A new car is unknown, so this is
    where regulation changes hurt. It is the concept-drift stress test.

Hyperparameters are tuned on early folds and reported on later ones, so the
reported error never comes from folds that chose the settings.
"""
from __future__ import annotations

from itertools import product
from typing import Callable

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from .model import Hyper, SkillModel


def in_season_split(df: pd.DataFrame, year: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    rounds = df.loc[df["year"] == year, "round"]
    cut = int(rounds.median())
    train = df[(df["year"] < year) | ((df["year"] == year) & (df["round"] <= cut))]
    test = df[(df["year"] == year) & (df["round"] > cut)]
    assert train["session"].max() < test["session"].min(), "temporal leak"
    return train, test.dropna(subset=["gap"])


def season_ahead_split(df: pd.DataFrame, year: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    train, test = df[df["year"] < year], df[df["year"] == year]
    assert train["session"].max() < test["session"].min(), "temporal leak"
    return train, test.dropna(subset=["gap"])


def score(test: pd.DataFrame, pred: np.ndarray, sd: np.ndarray | None = None) -> dict:
    err = test["gap"].to_numpy() - pred
    rho = []
    for _, g in test.assign(pred=pred).groupby("session"):
        if len(g) > 3 and g["pred"].nunique() > 1:
            rho.append(spearmanr(g["pred"], g["gap"]).statistic)
    out = {"rmse": float(np.sqrt(np.mean(err**2))), "mae": float(np.mean(np.abs(err))), "spearman": float(np.mean(rho)) if rho else float("nan"), "n": len(test)}
    if sd is not None:
        out["cover80"] = float(np.mean(np.abs(err) <= 1.2816 * sd))
    return out


def evaluate(make: Callable[[], object], df: pd.DataFrame, years: list[int], split=in_season_split, name: str | None = None) -> pd.DataFrame:
    rows = []
    for y in years:
        train, test = split(df, y)
        if test.empty:
            continue
        m = make().fit(train)
        try:
            pred, sd = m.predict(test, return_sd=True)
        except TypeError:
            pred, sd = m.predict(test), None
        rows.append({"model": name or getattr(m, "name", type(m).__name__), "year": y, **score(test, pred, sd)})
    return pd.DataFrame(rows)


GRID = {"tau_walk": [0.1, 0.2, 0.35], "tau_car": [1.0, 2.0], "tau_driver0": [0.4, 0.8]}


def tune(df: pd.DataFrame, years: list[int], grid: dict | None = None) -> tuple[Hyper, pd.DataFrame]:
    """Grid search on ``years`` only (in-season folds). Returns the best Hyper and the whole table."""
    grid = grid or GRID
    rows = []
    for combo in product(*grid.values()):
        h = Hyper(**dict(zip(grid.keys(), combo)))
        res = evaluate(lambda h=h: SkillModel(h), df, years)
        rows.append({**dict(zip(grid.keys(), combo)), "rmse": float(np.sqrt((res["rmse"] ** 2 * res["n"]).sum() / res["n"].sum()))})
    table = pd.DataFrame(rows).sort_values("rmse").reset_index(drop=True)
    best = table.iloc[0]
    return Hyper(**{k: float(best[k]) for k in grid}), table


def tune_carry(df: pd.DataFrame, years: list[int], base: Hyper, grid=(0.3, 0.5, 0.7, 0.85, 0.95)) -> tuple[Hyper, pd.DataFrame]:
    """car_carry only matters for a team-season not seen in training, i.e. the season-ahead protocol."""
    from dataclasses import replace

    rows = []
    for rho in grid:
        h = replace(base, car_carry=rho)
        res = evaluate(lambda h=h: SkillModel(h), df, years, season_ahead_split)
        rows.append({"car_carry": rho, "rmse": float(np.sqrt((res["rmse"] ** 2 * res["n"]).sum() / res["n"].sum()))})
    table = pd.DataFrame(rows).sort_values("rmse").reset_index(drop=True)
    return replace(base, car_carry=float(table.iloc[0]["car_carry"])), table


def pooled(res: pd.DataFrame) -> pd.DataFrame:
    """Row-weighted RMSE/MAE per model over folds."""
    out = []
    for m, g in res.groupby("model"):
        n = g["n"].sum()
        row = {"model": m, "rmse": float(np.sqrt((g["rmse"] ** 2 * g["n"]).sum() / n)), "mae": float((g["mae"] * g["n"]).sum() / n), "spearman": float(g["spearman"].mean()), "folds": len(g)}
        if "cover80" in g and g["cover80"].notna().any():
            row["cover80"] = float((g["cover80"] * g["n"]).sum() / n)
        out.append(row)
    return pd.DataFrame(out).sort_values("rmse").reset_index(drop=True)
