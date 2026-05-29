"""
FLAML AutoML training for race position prediction.

Run with:
    uv run python -m ml.train
"""
from __future__ import annotations
from contextlib import nullcontext
import json
import os
import pickle
import tempfile

import mlflow
import numpy as np
import pandas as pd
from flaml import AutoML
from sklearn.metrics import mean_absolute_error
import structlog

from ml.config import settings
from ml.features import build_feature_matrix, FEATURE_COLS, TARGET_COL
from ml.model_store import (
    GLOBAL_MODEL_PATH,
    global_metadata_path,
    gp_metadata_path,
    gp_model_path,
    save_metadata,
)
from ml.validation import compute_podium_metrics, compute_validation_report

log = structlog.get_logger()

# Disable FLAML's built-in MLflow auto-logging — we do it ourselves
os.environ["FLAML_MAX_ITER"] = "0"  # no-op, just ensuring env is set


def cross_validate(df: pd.DataFrame) -> dict:
    """Leave-one-year-out cross validation."""
    years     = sorted(df['year'].unique())
    errors    = []
    top3_hits = []
    podium_precision = []
    podium_recall = []
    brier_scores = []
    grid_top3_hits = []

    log.info("cv.start", years=list(years))

    for test_year in years:
        train_df = df[df['year'] != test_year]
        test_df  = df[df['year'] == test_year]

        if len(train_df) < 10:
            log.warning("cv.skip", year=test_year, reason="not enough training data")
            continue

        X_train = train_df[FEATURE_COLS]
        y_train = train_df[TARGET_COL]
        X_test  = test_df[FEATURE_COLS]
        y_test  = test_df[TARGET_COL]

        model = AutoML()
        model.fit(
            X_train, y_train,
            task="regression",
            time_budget=30,
            metric="mae",
            verbose=0,
            mlflow_logging=False,   # ← key: disable FLAML's own MLflow calls
        )

        preds = model.predict(X_test)
        mae   = mean_absolute_error(y_test, preds)
        errors.append(mae)

        actual_top3 = set(test_df.nsmallest(3, TARGET_COL)['driver_number'])
        pred_series = pd.Series(preds, index=test_df.index)
        pred_top3   = set(test_df.loc[pred_series.nsmallest(3).index, 'driver_number'])
        overlap     = len(actual_top3 & pred_top3)
        top3_hits.append(overlap / 3.0)

        pred_ranks = pred_series.rank(method="first").to_numpy()
        podium_probs = np.clip((4.5 - pred_ranks) / 3.0, 0.05, 0.95)
        metrics = compute_podium_metrics(
            test_df[TARGET_COL].to_numpy(),
            pred_ranks,
            podium_probs,
            test_df["grid_position"].to_numpy(),
        )
        if metrics["podium_precision"] is not None:
            podium_precision.append(metrics["podium_precision"])
        if metrics["podium_recall"] is not None:
            podium_recall.append(metrics["podium_recall"])
        if metrics["brier_score"] is not None:
            brier_scores.append(metrics["brier_score"])
        if metrics["grid_baseline_top3_hit_rate"] is not None:
            grid_top3_hits.append(metrics["grid_baseline_top3_hit_rate"])

        log.info("cv.fold",
                 test_year=int(test_year),
                 mae=round(mae, 2),
                 top3_accuracy=round(overlap / 3.0, 2),
                 best_model=model.best_estimator)

    if not errors:
        return {
            "mae_mean": None,
            "mae_std": None,
            "top3_accuracy_mean": None,
            "podium_precision_mean": None,
            "podium_recall_mean": None,
            "podium_brier_mean": None,
            "grid_baseline_top3_accuracy_mean": None,
            "n_folds": 0,
        }

    return {
        "mae_mean":           round(float(np.mean(errors)), 3),
        "mae_std":            round(float(np.std(errors)),  3),
        "top3_accuracy_mean": round(float(np.mean(top3_hits)), 3),
        "podium_precision_mean": round(float(np.mean(podium_precision)), 3) if podium_precision else None,
        "podium_recall_mean": round(float(np.mean(podium_recall)), 3) if podium_recall else None,
        "podium_brier_mean": round(float(np.mean(brier_scores)), 3) if brier_scores else None,
        "grid_baseline_top3_accuracy_mean": round(float(np.mean(grid_top3_hits)), 3) if grid_top3_hits else None,
        "n_folds":            len(errors),
    }


def train_final_model(df: pd.DataFrame) -> AutoML:
    """Train on all available data for production inference."""
    X = df[FEATURE_COLS]
    y = df[TARGET_COL]

    model = AutoML()
    model.fit(
        X, y,
        task="regression",
        time_budget=60,
        metric="mae",
        verbose=1,
        mlflow_logging=False,   # ← disable here too
    )

    log.info("model.trained",
             best_estimator=model.best_estimator,
             best_config=str(model.best_config))
    return model


def train_gp_models(df: pd.DataFrame) -> dict[str, str]:
    """Train one model per GP so live predictions can use circuit-specific history."""
    gp_models: dict[str, str] = {}

    for gp_name, gp_df in df.groupby("gp_name"):
        if len(gp_df) < 20:
            log.warning("gp_model.skip", gp_name=gp_name, rows=len(gp_df), reason="not enough rows")
            continue

        log.info("gp_model.train_start", gp_name=gp_name, rows=len(gp_df))
        model = train_final_model(gp_df)
        model_path = gp_model_path(gp_name)
        metadata_path = gp_metadata_path(gp_name)

        with open(model_path, "wb") as f:
            pickle.dump(model, f)

        gp_cv_metrics = cross_validate(gp_df)
        save_metadata(metadata_path, {
            "model_scope": "gp",
            "gp_name": gp_name,
            "best_estimator": model.best_estimator,
            "n_training_rows": len(gp_df),
            "years": sorted(int(y) for y in gp_df['year'].unique()),
            "cv_mae_mean": gp_cv_metrics["mae_mean"],
            "cv_mae_std": gp_cv_metrics["mae_std"],
            "cv_top3_accuracy_mean": gp_cv_metrics["top3_accuracy_mean"],
            "cv_podium_precision_mean": gp_cv_metrics["podium_precision_mean"],
            "cv_podium_recall_mean": gp_cv_metrics["podium_recall_mean"],
            "cv_podium_brier_mean": gp_cv_metrics["podium_brier_mean"],
            "grid_baseline_top3_accuracy_mean": gp_cv_metrics["grid_baseline_top3_accuracy_mean"],
            "cv_folds": gp_cv_metrics["n_folds"],
            "validation_report": compute_validation_report(gp_df, model),
        })

        gp_models[gp_name] = str(model_path)
        log.info("gp_model.saved", gp_name=gp_name, path=str(model_path), metadata=str(metadata_path))

    return gp_models


def main():
    mlflow_enabled = True
    mlflow_run = nullcontext()
    try:
        mlflow.set_tracking_uri(settings.mlflow_tracking_uri)
        mlflow.set_experiment("slipstream-race-prediction")
        mlflow_run = mlflow.start_run(run_name="slipstream-race-predictor")
    except Exception as e:
        mlflow_enabled = False
        log.warning(
            "mlflow.unavailable",
            tracking_uri=settings.mlflow_tracking_uri,
            error=str(e),
        )

    log.info("train.start")

    df = build_feature_matrix()
    log.info("train.data",
             rows=len(df),
             years=sorted(int(y) for y in df['year'].unique()),
             drivers=int(df['driver_number'].nunique()))

    if len(df) < 20:
        log.error("train.insufficient_data", rows=len(df))
        return

    print("\n=== Feature Matrix Sample ===")
    print(df[FEATURE_COLS + [TARGET_COL, 'abbreviation', 'year']].head(10).to_string())
    print(f"\nShape: {df.shape}")

    with mlflow_run:

        # Cross validation
        cv_metrics = cross_validate(df)
        print("\n=== Cross Validation Results ===")
        for year in sorted(df['year'].unique()):
            print(f"  {int(year)}: held out as test set")
        print(f"\n  MAE:            {cv_metrics['mae_mean']} ± {cv_metrics['mae_std']} positions")
        if cv_metrics['top3_accuracy_mean'] is not None:
            print(f"  Top-3 accuracy: {cv_metrics['top3_accuracy_mean'] * 100:.1f}%")
        print(f"  Podium precision: {cv_metrics['podium_precision_mean']}")
        print(f"  Podium recall:    {cv_metrics['podium_recall_mean']}")
        print(f"  Podium Brier:     {cv_metrics['podium_brier_mean']}")
        print(f"  Folds:          {cv_metrics['n_folds']}")

        # Train final model on all data
        print("\n=== Training Final Model (all data) ===")
        model = train_final_model(df)

        # Log to MLflow manually (no FLAML auto-logging)
        if mlflow_enabled:
            mlflow.log_params({
                "best_estimator":  model.best_estimator,
                "time_budget":     60,
                "n_training_rows": len(df),
                "n_features":      len(FEATURE_COLS),
                "features":        json.dumps(FEATURE_COLS),
            })
            mlflow.log_metrics({
                "cv_mae_mean":           cv_metrics['mae_mean'],
                "cv_mae_std":            cv_metrics['mae_std'],
                "cv_top3_accuracy_mean": cv_metrics['top3_accuracy_mean'],
                "cv_podium_precision_mean": cv_metrics["podium_precision_mean"],
                "cv_podium_recall_mean": cv_metrics["podium_recall_mean"],
                "cv_podium_brier_mean": cv_metrics["podium_brier_mean"],
                "grid_baseline_top3_accuracy_mean": cv_metrics["grid_baseline_top3_accuracy_mean"],
            })

        # Log feature importance — the most valuable thing to track.
        # WHY: knowing WHICH features the model relies on tells you:
        #   1. Whether your new features are actually being used
        #   2. Whether the model is learning sensible patterns
        #   3. What to focus on in the next feature engineering iteration
        try:
            # XGBoost and ExtraTree both expose feature_importances_
            estimator = model.model.estimator
            if hasattr(estimator, 'feature_importances_'):
                importances = dict(zip(
                    FEATURE_COLS,
                    [round(float(x), 4) for x in estimator.feature_importances_]
                ))
                # Sort by importance descending
                importances_sorted = dict(
                    sorted(importances.items(), key=lambda x: x[1], reverse=True)
                )
                # Log top features as metrics (MLflow shows these in charts)
                for feat, imp in list(importances_sorted.items())[:10]:
                    if mlflow_enabled:
                        mlflow.log_metric(f"importance_{feat}", imp)

                # Log full importance as artifact
                tmp = tempfile.mktemp(suffix=".json")
                with open(tmp, "w") as f:
                    json.dump(importances_sorted, f, indent=2)
                if mlflow_enabled:
                    try:
                        mlflow.log_artifact(tmp)
                    except Exception:
                        pass  # artifact logging optional
                os.unlink(tmp)

                print("\n=== Feature Importance (top 10) ===")
                for feat, imp in list(importances_sorted.items())[:10]:
                    bar = "█" * int(imp * 50)
                    print(f"  {feat:35s} {imp:.4f} {bar}")
        except Exception as e:
            log.warning("feature_importance.failed", error=str(e))

        # Save global fallback model pickle for fast inference
        with open(GLOBAL_MODEL_PATH, 'wb') as f:
            pickle.dump(model, f)

        validation_report = compute_validation_report(df, model)

        save_metadata(global_metadata_path(), {
            "model_scope": "global",
            "best_estimator": model.best_estimator,
            "n_training_rows": len(df),
            "years": sorted(int(y) for y in df['year'].unique()),
            "cv_mae_mean": cv_metrics['mae_mean'],
            "cv_mae_std": cv_metrics['mae_std'],
            "cv_top3_accuracy_mean": cv_metrics['top3_accuracy_mean'],
            "cv_podium_precision_mean": cv_metrics["podium_precision_mean"],
            "cv_podium_recall_mean": cv_metrics["podium_recall_mean"],
            "cv_podium_brier_mean": cv_metrics["podium_brier_mean"],
            "grid_baseline_top3_accuracy_mean": cv_metrics["grid_baseline_top3_accuracy_mean"],
            "cv_folds": cv_metrics['n_folds'],
            "validation_report": validation_report,
        })

        gp_models = train_gp_models(df)
        if mlflow_enabled:
            mlflow.log_metric("gp_model_count", len(gp_models))

        # Also log the pickle as an artifact
        #mlflow.log_artifact(str(GLOBAL_MODEL_PATH), artifact_path="model")

        log.info("model.saved", path=str(GLOBAL_MODEL_PATH), gp_models=len(gp_models))
        print(f"\n✅  Global model saved  → {GLOBAL_MODEL_PATH}")
        if gp_models:
            print(f"✅  GP-specific models saved  → {len(gp_models)}")
        print(f"    Best algorithm: {model.best_estimator}")
        if mlflow_enabled:
            print(f"    MLflow run logged → {settings.mlflow_tracking_uri}")
        else:
            print("    MLflow logging skipped (tracking server unavailable)")


if __name__ == '__main__':
    main()
