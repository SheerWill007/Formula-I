"""Run the whole driver-skill study and write one JSON of results.

    DATABASE_URL=... python -m ml.driver_skill.run --out results.json

Read-only against the database. Steps: load -> tune (early folds) -> evaluate (late
folds) -> season-ahead drift stress test -> drift tables -> imputation sensitivity ->
final fit -> export.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import warnings

import numpy as np
import pandas as pd

from . import cv, data, drift, impute
from .baselines import CarOnly, DriverOnly, GlobalMean, TeammateDelta
from .model import SkillModel

TUNE_YEARS = list(range(2010, 2018))
TEST_YEARS = list(range(2018, 2027))
AHEAD_YEARS = list(range(2008, 2027))
BRAZIL, BRAZIL_KEY = "2026-20", 11408
PCT_TO_TENTHS = 9.0  # 1% of a 90 s lap = 0.9 s = 9 tenths
PEERS = ["alonso", "max_verstappen", "hamilton", "vettel", "michael_schumacher", "raikkonen", "button", "leclerc", "norris", "russell", "rosberg", "stroll"]


def _neural():
    try:
        from .neural import NeuralSkill

        return NeuralSkill
    except Exception:  # torch missing
        return None


def _clean(x):
    """NaN is not valid JSON: turn it (and inf) into null, recursively."""
    if isinstance(x, dict):
        return {k: _clean(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_clean(v) for v in x]
    if isinstance(x, float) and not np.isfinite(x):
        return None
    return x


def _centre(table: pd.DataFrame) -> pd.DataFrame:
    """Express skill relative to the average driver of the same season (negative = faster)."""
    t = table.copy()
    t["rel"] = t["skill"] - t.groupby("year")["skill"].transform("mean")
    return t


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    warnings.filterwarnings("ignore")

    import psycopg

    url = re.sub(r"\+\w+://", "://", os.environ["DATABASE_URL"])
    with psycopg.connect(url, options="-c default_transaction_read_only=on") as conn:
        raw = data.load_quali(conn)
        df = data.build_gaps(raw)
        df = data.fill_from_session_results(df, conn, BRAZIL, BRAZIL_KEY)
    names = raw.sort_values("year").groupby("driver_id")["driver_name"].last().to_dict()

    # 1. tune on early folds only
    best, tune_table = cv.tune(df, TUNE_YEARS)
    best, carry_table = cv.tune_carry(df, list(range(2008, 2018)), best)
    print("best hyper:", best)

    # 2. in-season walk-forward on later folds
    NN = _neural()
    makers = {
        "Dynamic skill model": lambda: SkillModel(best),
        "Teammate delta": TeammateDelta,
        "Car only": CarOnly,
        "Driver only": DriverOnly,
        "Global mean": GlobalMean,
    }
    if NN:
        makers["Neural (embeddings + MLP)"] = NN
    in_season = pd.concat([cv.evaluate(mk, df, TEST_YEARS, cv.in_season_split, name=n) for n, mk in makers.items()])
    print(cv.pooled(in_season).round(3).to_string())

    # 3. season-ahead: new cars are unseen, so this is the concept-drift test
    ahead_makers = {k: v for k, v in makers.items() if k != "Global mean"}
    ahead = pd.concat([cv.evaluate(mk, df, AHEAD_YEARS, cv.season_ahead_split, name=n) for n, mk in ahead_makers.items()])
    ahead_pooled = cv.pooled(ahead[ahead["year"].isin(TEST_YEARS)])
    print(ahead_pooled.round(3).to_string())

    # 4. drift
    dr = drift.drift_table(df)
    dr_ahead = ahead.merge(dr, on="year", how="left")
    link = drift.drift_vs_error(dr, ahead, "Dynamic skill model")
    print("drift vs error:", link)

    # 5. missing data
    full = SkillModel(best).fit(df)
    miss = impute.missingness_table(df, full)
    sens, _ = impute.sensitivity(df, best)
    print(sens.round(3).to_string())

    # 6. final model + exports
    dt = _centre(full.driver_table())
    dt["name"] = dt["driver_id"].map(names)
    ct = full.car_table()

    ranking = []
    for drv, g in dt.groupby("driver_id"):
        if len(g) < 8:
            continue
        w = 1.0 / g["sd"] ** 2
        mean = float((g["rel"] * w).sum() / w.sum())
        peak = g.loc[g["rel"].idxmin()]
        ranking.append(
            {"driver": names[drv], "driver_id": drv, "seasons": int(len(g)), "career_pct": mean, "se_pct": float(1 / np.sqrt(w.sum())),
             "peak_pct": float(peak["rel"]), "peak_year": int(peak["year"])}
        )
    ranking.sort(key=lambda r: r["career_pct"])

    trajectories = {
        drv: [{"year": int(r.year), "pct": float(r.rel), "sd": float(r.sd)} for r in dt[dt["driver_id"] == drv].itertuples()]
        for drv in PEERS
        if drv in set(dt["driver_id"])
    }

    # Brazil 2026 quali, predicted without ever seeing that session. The z-score uses that
    # session's own noise level (a wet session is noisier than a typical dry one).
    held = SkillModel(best).fit(df[df["session"] != BRAZIL])
    b = df[(df["session"] == BRAZIL) & df["gap"].notna()].copy()
    b["pred"], b["pred_sd"] = held.predict(b, return_sd=True)
    s_sd = full.session_sd[BRAZIL]
    b["z"] = (b["gap"] - b["pred"]) / np.sqrt(s_sd**2 + b["pred_sd"] ** 2 - held.sigma**2)
    brazil_rows = [
        {"driver": r.driver_id, "team": r.constructor_id, "actual_gap": float(r.gap), "pred_gap": float(r.pred),
         "resid": float(r.gap - r.pred), "z": float(r.z)}
        for r in b.sort_values("z").itertuples()
    ]
    brazil_meta = {"session_sd_pct": float(s_sd), "typical_sd_pct": float(full.sigma)}
    car26 = ct[ct["team_season"].str.endswith(":2026")].copy()
    car26["team"] = car26["team_season"].str.split(":").str[0]

    out = {
        "meta": {
            "rows": int(len(df)),
            "ok": int((df["status"] == "ok").sum()),
            "missing": int((df["status"] == "missing").sum()),
            "outlier": int((df["status"] == "outlier").sum()),
            "years": [int(df["year"].min()), int(df["year"].max())],
            "sessions": int(df["session"].nunique()),
            "tune_years": [TUNE_YEARS[0], TUNE_YEARS[-1]],
            "test_years": [TEST_YEARS[0], TEST_YEARS[-1]],
            "best_hyper": best.__dict__,
            "sigma_pct": float(full.sigma),
            "pct_to_tenths": PCT_TO_TENTHS,
            "neural": bool(NN),
        },
        "tuning": tune_table.round(4).to_dict("records"),
        "tuning_carry": carry_table.round(4).to_dict("records"),
        "in_season": cv.pooled(in_season).round(4).to_dict("records"),
        "in_season_by_year": in_season.round(4).to_dict("records"),
        "season_ahead": ahead_pooled.round(4).to_dict("records"),
        "season_ahead_by_year": dr_ahead.round(4).to_dict("records"),
        "drift": dr.round(4).to_dict("records"),
        "drift_vs_error": link,
        "missingness": miss.round(4).to_dict("records"),
        "imputation_sensitivity": sens.round(4).to_dict("records"),
        "ranking": ranking,
        "trajectories": trajectories,
        "brazil_2026_holdout": brazil_rows,
        "brazil_2026_meta": brazil_meta,
        "car_2026": car26[["team", "car", "sd"]].round(3).to_dict("records"),
    }
    with open(args.out, "w") as f:
        json.dump(_clean(out), f, separators=(",", ":"), default=float, allow_nan=False)
    print("wrote", args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
