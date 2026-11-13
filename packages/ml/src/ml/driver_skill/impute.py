"""Missing and unusable Q1 laps: how much do they matter?

About 1-2% of drivers have no Q1 time (crash, withdrawn) and ~1% post a lap that
is not representative (more than ``OUTLIER_PCT`` slower than the fastest). Both
are dropped by default (complete-case analysis).

Why not just fill them in with the model's prediction? For a Gaussian model that
is *missing at random*, imputing the conditional mean leaves the estimates exactly
where complete-case put them (it is the EM fixed point), so it would prove nothing.
The real worry is that they are **missing not at random**: a driver who crashed in
Q1 was probably slower than the model expected. So we run a pattern-mixture
sensitivity analysis: impute each missing or outlier row as ``prediction + delta``
with delta in {0, 1, 3} percent, refit, and see how far the skill estimates move.
If they hardly move, the conclusions do not depend on how we treat missingness.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .model import Hyper, SkillModel


def missingness_table(df: pd.DataFrame, model: SkillModel) -> pd.DataFrame:
    """Per year: share missing / outlier, and whether they come from slower cars than average (MNAR hint)."""
    d = df.copy()
    d["pred"] = model.predict(d)
    rows = []
    for y, g in d.groupby("year"):
        bad = g[g["status"] != "ok"]
        good = g[g["status"] == "ok"]
        rows.append(
            {
                "year": int(y),
                "rows": len(g),
                "missing": int((g["status"] == "missing").sum()),
                "outlier": int((g["status"] == "outlier").sum()),
                "share_unusable": float(len(bad) / len(g)),
                "pred_gap_unusable": float(bad["pred"].mean()) if len(bad) else np.nan,
                "pred_gap_usable": float(good["pred"].mean()),
            }
        )
    return pd.DataFrame(rows)


def imputed_frame(df: pd.DataFrame, base: SkillModel, delta: float) -> pd.DataFrame:
    d = df.copy()
    bad = d["status"] != "ok"
    pred = base.predict(d[bad])
    d.loc[bad, "gap"] = np.maximum(pred + delta, 0.0)
    return d


def sensitivity(df: pd.DataFrame, hyper: Hyper, deltas=(0.0, 1.0, 3.0)) -> tuple[pd.DataFrame, dict[float, pd.DataFrame]]:
    """Refit under each delta. Returns a summary table and the driver tables."""
    base = SkillModel(hyper).fit(df)
    ref = base.driver_table().set_index(["driver_id", "year"])["skill"]
    tables, rows = {}, []
    for dl in deltas:
        m = SkillModel(hyper).fit(imputed_frame(df, base, dl))
        t = m.driver_table()
        tables[dl] = t
        s = t.set_index(["driver_id", "year"])["skill"]
        # centre each season so only the ordering of drivers is compared, not a shared level shift
        yr = s.index.get_level_values("year")
        sc = s - s.groupby(yr).transform("mean")
        rc = ref - ref.groupby(ref.index.get_level_values("year")).transform("mean")
        common = sc.index.intersection(rc.index)  # imputation can add driver-seasons the reference lacks
        sc, rcc = sc.loc[common], rc.loc[common]
        diff = (sc - rcc).abs()
        rows.append(
            {
                "delta_pct": dl,
                "corr_with_complete_case": float(np.corrcoef(sc, rcc)[0, 1]),
                "mean_abs_change": float(diff.mean()),
                "max_abs_change": float(diff.max()),
                "rows_imputed": int((df["status"] != "ok").sum()),
            }
        )
    return pd.DataFrame(rows), tables
