from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd
from sklearn.inspection import permutation_importance
from sklearn.metrics import precision_score, recall_score

from ml.features import FEATURE_COLS, FEATURE_STREAMS, TARGET_COL


def _safe_float(value: Any, ndigits: int = 3) -> float | None:
    try:
        if value is None or not math.isfinite(float(value)):
            return None
        return round(float(value), ndigits)
    except (TypeError, ValueError):
        return None


def feature_stream_for(feature: str) -> str:
    for stream, features in FEATURE_STREAMS.items():
        if feature in features:
            return stream
    return "other"


def stream_label(stream: str) -> str:
    return {
        "car_pace": "Car pace",
        "tyre_strategy": "Tyre / strategy",
        "driver_team_form": "Driver / team form",
        "circuit_context": "Circuit context",
        "other": "Other",
    }.get(stream, stream.replace("_", " ").title())


def compute_stream_attribution(feature_values: dict[str, float]) -> list[dict]:
    """Simple feature-value magnitude attribution used when SHAP is unavailable."""
    totals = {stream: 0.0 for stream in FEATURE_STREAMS}
    for feature in FEATURE_COLS:
        value = feature_values.get(feature, 0.0)
        stream = feature_stream_for(feature)
        if stream in totals:
            try:
                totals[stream] += abs(float(value))
            except (TypeError, ValueError):
                pass

    total = sum(totals.values()) or 1.0
    return [
        {
            "stream": stream,
            "label": stream_label(stream),
            "share": round(value / total, 3),
            "score": round(value, 3),
        }
        for stream, value in sorted(totals.items(), key=lambda item: item[1], reverse=True)
    ]


def compute_validation_report(df: pd.DataFrame, model=None) -> dict:
    if df.empty or TARGET_COL not in df:
        return {
            "available": False,
            "caveat": "No training feature matrix was available for validation.",
            "feature_tests": [],
            "vif": [],
            "permutation_importance": [],
        }

    podium = df[TARGET_COL] <= 3
    report = {
        "available": True,
        "caveat": (
            "p-values are screening diagnostics, not proof. For small F1 datasets, "
            "effect size, leakage control, and baseline comparison matter more."
        ),
        "feature_tests": _feature_tests(df, podium),
        "vif": _vif_report(df),
        "permutation_importance": _permutation_report(df, model),
    }
    return report


def compute_podium_metrics(y_true, predicted_positions, podium_probabilities, grid_positions=None) -> dict:
    y_true = np.asarray(y_true)
    predicted_positions = np.asarray(predicted_positions)
    podium_probabilities = np.asarray(podium_probabilities)
    actual = y_true <= 3
    predicted = predicted_positions <= 3
    grid_positions = np.asarray(grid_positions) if grid_positions is not None else np.arange(1, len(y_true) + 1)
    baseline = grid_positions <= 3
    brier = np.mean((podium_probabilities - actual.astype(float)) ** 2)

    return {
        "top3_hit_rate": _safe_float(len(set(np.where(actual)[0]) & set(np.where(predicted)[0])) / 3.0),
        "podium_precision": _safe_float(precision_score(actual, predicted, zero_division=0)),
        "podium_recall": _safe_float(recall_score(actual, predicted, zero_division=0)),
        "brier_score": _safe_float(brier),
        "grid_baseline_top3_hit_rate": _safe_float(
            len(set(np.where(actual)[0]) & set(np.where(baseline)[0])) / 3.0
        ),
    }


def _feature_tests(df: pd.DataFrame, podium: pd.Series) -> list[dict]:
    try:
        from scipy import stats
    except Exception:
        stats = None

    rows = []
    for feature in FEATURE_COLS:
        if feature not in df:
            continue
        podium_vals = pd.to_numeric(df.loc[podium, feature], errors="coerce").dropna()
        field_vals = pd.to_numeric(df.loc[~podium, feature], errors="coerce").dropna()
        if len(podium_vals) < 3 or len(field_vals) < 3:
            continue

        pooled = math.sqrt(
            ((len(podium_vals) - 1) * podium_vals.var(ddof=1) + (len(field_vals) - 1) * field_vals.var(ddof=1))
            / max(len(podium_vals) + len(field_vals) - 2, 1)
        )
        cohen_d = 0.0 if pooled == 0 else (podium_vals.mean() - field_vals.mean()) / pooled
        p_value = None
        spearman = None
        if stats is not None:
            try:
                p_value = stats.ttest_ind(podium_vals, field_vals, equal_var=False, nan_policy="omit").pvalue
            except Exception:
                p_value = None
            try:
                corr = stats.spearmanr(pd.to_numeric(df[feature], errors="coerce"), df[TARGET_COL], nan_policy="omit")
                spearman = corr.correlation
            except Exception:
                spearman = None

        rows.append({
            "feature": feature,
            "stream": feature_stream_for(feature),
            "stream_label": stream_label(feature_stream_for(feature)),
            "cohens_d": _safe_float(cohen_d),
            "p_value": _safe_float(p_value, 5),
            "spearman_r": _safe_float(spearman),
        })

    rows.sort(key=lambda row: abs(row["cohens_d"] or 0), reverse=True)
    return rows[:12]


def _vif_report(df: pd.DataFrame) -> list[dict]:
    numeric = df[FEATURE_COLS].apply(pd.to_numeric, errors="coerce").fillna(0)
    if len(numeric) < 10:
        return []

    rows = []
    for feature in FEATURE_COLS:
        y = numeric[feature].to_numpy(dtype=float)
        x = numeric[[col for col in FEATURE_COLS if col != feature]].to_numpy(dtype=float)
        if np.std(y) == 0 or x.shape[1] == 0:
            continue
        try:
            coef, *_ = np.linalg.lstsq(np.column_stack([np.ones(len(x)), x]), y, rcond=None)
            pred = np.column_stack([np.ones(len(x)), x]) @ coef
            ss_res = float(np.sum((y - pred) ** 2))
            ss_tot = float(np.sum((y - y.mean()) ** 2))
            r2 = 0.0 if ss_tot == 0 else max(0.0, min(0.999, 1 - ss_res / ss_tot))
            vif = 1 / max(1 - r2, 0.001)
        except Exception:
            continue
        rows.append({"feature": feature, "vif": _safe_float(vif)})

    rows.sort(key=lambda row: row["vif"] or 0, reverse=True)
    return rows[:10]


def _permutation_report(df: pd.DataFrame, model) -> list[dict]:
    if model is None or len(df) < 20:
        return []
    try:
        result = permutation_importance(
            model,
            df[FEATURE_COLS],
            df[TARGET_COL],
            scoring="neg_mean_absolute_error",
            n_repeats=5,
            random_state=42,
        )
    except Exception:
        return []

    rows = [
        {
            "feature": feature,
            "importance": _safe_float(result.importances_mean[idx]),
            "std": _safe_float(result.importances_std[idx]),
            "stream": feature_stream_for(feature),
            "stream_label": stream_label(feature_stream_for(feature)),
        }
        for idx, feature in enumerate(FEATURE_COLS)
    ]
    rows.sort(key=lambda row: row["importance"] or 0, reverse=True)
    return rows[:10]
