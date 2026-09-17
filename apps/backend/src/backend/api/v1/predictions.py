"""
ML race predictions API.
Requires the model to be trained first: uv run python -m ml.train
"""
from flask import Blueprint, jsonify, redirect, url_for
from sqlalchemy import text
from backend import extensions

predictions_bp = Blueprint("predictions", __name__)


@predictions_bp.get("/sessions/<int:session_key>/predictions")
def race_predictions(session_key: int):
    """
    Run ML predictions for a qualifying session.
    Returns predicted finishing order with win/podium probabilities + SHAP factors.
    """
    # Verify session exists and is qualifying
    with extensions.engine.connect() as conn:
        row = conn.execute(text("""
            SELECT session_type, gp_name, year
            FROM sessions WHERE session_key = :sk
        """), {"sk": session_key}).first()

    if not row:
        return jsonify({"error": "Session not found"}), 404
    if row[0] not in ('Q', 'SQ'):
        return jsonify({"error": "Predictions only available for qualifying sessions"}), 400

    try:
        from ml.features import compute_weekend_inputs_used
        from ml.predict import predict_race, explain_prediction
        from ml.model_store import global_metadata_path, gp_metadata_path, load_metadata
    except ImportError:
        return jsonify({"error": "ML package not available — check uv workspace"}), 503

    try:
        predictions  = predict_race(session_key)
        explanations = explain_prediction(session_key)
    except FileNotFoundError:
        return jsonify({"error": "Model training did not produce a readable model file"}), 503
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    # Merge SHAP factors
    shap_map = {e["driver_number"]: e for e in explanations}
    for p in predictions:
        shap_entry = shap_map.get(p["driver_number"], {})
        p["factors"] = shap_entry.get("factors", [])
        if shap_entry.get("feature_streams"):
            p["feature_streams"] = shap_entry["feature_streams"]

    # Add team colours from DB
    with extensions.engine.connect() as conn:
        drivers = conn.execute(text("""
            SELECT driver_number, team_colour, team_name
            FROM drivers WHERE session_key = :sk
        """), {"sk": session_key}).mappings().all()
    from backend.api.v1.strategy import _resolve
    colour_map = {r["driver_number"]: _resolve(r["team_colour"], r["team_name"]) for r in drivers}
    for p in predictions:
        p["team_colour"] = colour_map.get(p["driver_number"], "666666")

    gp_metadata = load_metadata(gp_metadata_path(row[1]))
    global_metadata = load_metadata(global_metadata_path())
    model_metadata = gp_metadata or global_metadata or {}
    validation_report = model_metadata.get("validation_report") or {
        "available": False,
        "caveat": "Train the v1.5 model to populate statistical validation artifacts.",
        "feature_tests": [],
        "vif": [],
        "permutation_importance": [],
    }
    model_baselines = {
        "grid_top3_accuracy": model_metadata.get("grid_baseline_top3_accuracy_mean"),
        "model_top3_accuracy": model_metadata.get("cv_top3_accuracy_mean"),
        "podium_precision": model_metadata.get("cv_podium_precision_mean"),
        "podium_recall": model_metadata.get("cv_podium_recall_mean"),
        "podium_brier": model_metadata.get("cv_podium_brier_mean"),
    }
    weekend_inputs = compute_weekend_inputs_used(extensions.engine, row[1], row[2])

    return jsonify({
        "session_key": session_key,
        "gp_name":     row[1],
        "year":        row[2],
        "predictions": predictions,
        "validation_report": validation_report,
        "model_baselines": model_baselines,
        "weekend_inputs_used": weekend_inputs,
        "model": {
            "scope": model_metadata.get("model_scope", "global"),
            "best_estimator": model_metadata.get("best_estimator"),
            "cv_mae_mean": model_metadata.get("cv_mae_mean"),
            "cv_mae_std": model_metadata.get("cv_mae_std"),
            "cv_top3_accuracy_mean": model_metadata.get("cv_top3_accuracy_mean"),
            "cv_podium_precision_mean": model_metadata.get("cv_podium_precision_mean"),
            "cv_podium_recall_mean": model_metadata.get("cv_podium_recall_mean"),
            "cv_podium_brier_mean": model_metadata.get("cv_podium_brier_mean"),
            "grid_baseline_top3_accuracy_mean": model_metadata.get("grid_baseline_top3_accuracy_mean"),
            "cv_folds": model_metadata.get("cv_folds"),
            "n_training_rows": model_metadata.get("n_training_rows"),
            "years": model_metadata.get("years", []),
            "gp_name": model_metadata.get("gp_name", row[1] if gp_metadata else None),
        },
    })


@predictions_bp.get("/predictions/latest")
def latest_predictions():
    """Predictions for the most recent qualifying session."""
    with extensions.engine.connect() as conn:
        row = conn.execute(text("""
            SELECT session_key FROM sessions
            WHERE session_type = 'Q'
            ORDER BY date_start DESC NULLS LAST
            LIMIT 1
        """)).first()

    if not row:
        return jsonify({"error": "No qualifying sessions found"}), 404

    return redirect(url_for("predictions.race_predictions", session_key=row[0]))
