"""Data drift and concept drift diagnostics.

Data drift   : the inputs change. We track the distribution of the gap target (how
               spread out the field is) with PSI and a KS test against the previous
               three seasons, plus how much of the grid is new (cars, drivers).
Concept drift: the *relationship* the model relies on changes. A new car has no
               history, so after a regulation change last year's car effect stops
               being informative. We measure it as the season-ahead error.

Regulation resets (new chassis rules or power units) are listed in ``REG_YEARS``.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import ks_2samp

REG_YEARS = {2009, 2014, 2017, 2022, 2026}


def psi(reference: np.ndarray, current: np.ndarray, bins: int = 10) -> float:
    """Population Stability Index with quantile bins of the reference. <0.1 stable, 0.1-0.25 moderate, >0.25 large."""
    edges = np.unique(np.quantile(reference, np.linspace(0, 1, bins + 1)))
    edges[0], edges[-1] = -np.inf, np.inf
    r = np.histogram(reference, edges)[0] / len(reference)
    c = np.histogram(current, edges)[0] / len(current)
    r, c = np.clip(r, 1e-4, None), np.clip(c, 1e-4, None)
    return float(np.sum((c - r) * np.log(c / r)))


def drift_table(df: pd.DataFrame, lookback: int = 3) -> pd.DataFrame:
    ok = df.dropna(subset=["gap"])
    years = sorted(ok["year"].unique())
    rows = []
    for y in years:
        prev_years = [p for p in years if y - lookback <= p < y]
        if not prev_years:
            continue
        cur = ok[ok["year"] == y]["gap"].to_numpy()
        ref = ok[ok["year"].isin(prev_years)]["gap"].to_numpy()
        ks = ks_2samp(ref, cur)
        this = df[df["year"] == y]
        before = df[df["year"] == y - 1]
        rows.append(
            {
                "year": int(y),
                "psi": psi(ref, cur),
                "ks": float(ks.statistic),
                "ks_p": float(ks.pvalue),
                "field_sd": float(cur.std()),
                "median_gap": float(np.median(cur)),
                "new_cars": float(1 - this["constructor_id"].isin(before["constructor_id"]).mean()) if len(before) else np.nan,
                "new_drivers": float(1 - this["driver_id"].isin(before["driver_id"]).mean()) if len(before) else np.nan,
                "reg_change": y in REG_YEARS,
            }
        )
    return pd.DataFrame(rows)


def drift_vs_error(drift: pd.DataFrame, season_ahead: pd.DataFrame, model: str) -> dict:
    """Does the season-ahead error rise with data drift? Spearman over seasons, and the regulation-year gap."""
    from scipy.stats import spearmanr

    e = season_ahead[season_ahead["model"] == model][["year", "rmse"]].merge(drift, on="year")
    rho = spearmanr(e["psi"], e["rmse"])
    return {
        "spearman_psi_vs_rmse": float(rho.statistic),
        "p": float(rho.pvalue),
        "rmse_reg_years": float(e[e["reg_change"]]["rmse"].mean()),
        "rmse_other_years": float(e[~e["reg_change"]]["rmse"].mean()),
        "n_seasons": int(len(e)),
    }
