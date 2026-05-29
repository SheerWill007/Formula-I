"""
Race prediction inference.

Given a qualifying session key, loads the trained model and returns
predicted finishing positions with win probabilities for each driver.

Win probability is computed by running 1000 bootstrap samples with
noise added to simulate race uncertainty (crashes, strategy, weather).
"""
from __future__ import annotations
import pickle
import threading
import numpy as np
import structlog
from sqlalchemy import text

from ml.features import (
    FEATURE_COLS,
    build_inference_features,
    compute_weekend_inputs_used,
    get_engine,
)
from ml.model_store import GLOBAL_MODEL_PATH, gp_model_path
from ml.validation import compute_stream_attribution, feature_stream_for, stream_label

log       = structlog.get_logger()
_train_lock = threading.Lock()


def ensure_model_available(gp_name: str | None = None) -> None:
    model_path = gp_model_path(gp_name) if gp_name else GLOBAL_MODEL_PATH
    if gp_name and not model_path.exists() and GLOBAL_MODEL_PATH.exists():
        return
    if model_path.exists():
        return

    with _train_lock:
        model_path = gp_model_path(gp_name) if gp_name else GLOBAL_MODEL_PATH
        if gp_name and not model_path.exists() and GLOBAL_MODEL_PATH.exists():
            return
        if model_path.exists():
            return

        log.info("model.train_on_demand.start", gp_name=gp_name)
        from ml.train import main as train_main
        train_main()
        log.info("model.train_on_demand.done", gp_name=gp_name)


def load_model(gp_name: str | None = None):
    model_path = gp_model_path(gp_name) if gp_name else GLOBAL_MODEL_PATH

    if gp_name and not model_path.exists():
        log.warning("model.gp_missing", gp_name=gp_name, fallback=str(GLOBAL_MODEL_PATH))
        model_path = GLOBAL_MODEL_PATH

    if not model_path.exists():
        raise FileNotFoundError(
            f"No model found at {model_path}. Run: uv run python -m ml.train"
        )

    with open(model_path, 'rb') as f:
        return pickle.load(f)


def _predict_with_current_features(model, X, gp_name: str | None):
    try:
        return model.predict(X), model
    except Exception as e:
        message = str(e).lower()
        if "feature" not in message and "shape" not in message and "columns" not in message:
            raise
        log.warning("model.feature_mismatch_retrain", gp_name=gp_name, error=str(e))
        with _train_lock:
            from ml.train import main as train_main
            train_main()
        model = load_model(gp_name)
        return model.predict(X), model


def predict_race(quali_session_key: int, n_simulations: int = 1000) -> list[dict]:
    """
    Predict race finishing order from qualifying data.

    Returns list of dicts sorted by predicted position:
    [
        {
            "driver_number": 63,
            "abbreviation": "RUS",
            "team_name": "Mercedes",
            "predicted_position": 1,
            "win_probability": 0.34,
            "podium_probability": 0.67,
            "position_probabilities": {1: 0.34, 2: 0.21, 3: 0.12, ...}
        },
        ...
    ]
    """
    features = build_inference_features(quali_session_key)
    gp_name = str(features['gp_name'].iloc[0]) if 'gp_name' in features.columns and not features.empty else None
    ensure_model_available(gp_name)
    model = load_model(gp_name)

    X          = features[FEATURE_COLS]
    base_preds, model = _predict_with_current_features(model, X, gp_name)

    circuit_noise = 1.35 + float(features["sc_probability"].iloc[0]) * 0.95
    overtake_noise = float(features["overtake_difficulty"].iloc[0]) * 0.45
    dnf_rate = float(features["dnf_rate_circuit"].iloc[0])
    n_drivers   = len(features)
    sim_results = np.zeros((n_simulations, n_drivers))

    for i in range(n_simulations):
        noise = np.random.normal(0, circuit_noise, n_drivers)
        grid_anchor = features["grid_position"].to_numpy(dtype=float)
        noisy = (base_preds * (1 - overtake_noise)) + (grid_anchor * overtake_noise) + noise
        dnf_hits = np.random.random(n_drivers) < dnf_rate
        if np.any(dnf_hits):
            noisy = noisy + (dnf_hits.astype(float) * np.random.uniform(8, 16, n_drivers))
        # Convert noisy predictions to positions (rank them)
        ranks = noisy.argsort().argsort() + 1
        sim_results[i] = ranks

    # Compute probability distributions from simulations
    results = []
    for idx, row in features.iterrows():
        driver_sims     = sim_results[:, list(features.index).index(idx)]
        pos_probs       = {}
        for pos in range(1, n_drivers + 1):
            pos_probs[pos] = round(float(np.mean(driver_sims == pos)), 3)

        win_prob    = pos_probs.get(1, 0)
        p2_prob     = pos_probs.get(2, 0)
        p3_prob     = pos_probs.get(3, 0)
        podium_prob = sum(pos_probs.get(p, 0) for p in [1, 2, 3])
        feature_values = {feature: row.get(feature, 0.0) for feature in FEATURE_COLS}

        results.append({
            "driver_number":         int(row['driver_number']),
            "abbreviation":          row['abbreviation'],
            "team_name":             row['team_name'],
            "grid_position":         int(row['grid_position']),
            "predicted_position":    int(round(base_preds[list(features.index).index(idx)])),
            "p1_probability":        round(win_prob, 3),
            "p2_probability":        round(p2_prob, 3),
            "p3_probability":        round(p3_prob, 3),
            "win_probability":       round(win_prob, 3),
            "podium_probability":    round(podium_prob, 3),
            "position_probabilities":pos_probs,
            "feature_streams":       compute_stream_attribution(feature_values),
        })

    results.sort(key=lambda x: (-x['podium_probability'], x['predicted_position']))
    return results


def weekend_inputs_used(quali_session_key: int) -> dict:
    features = build_inference_features(quali_session_key)
    gp_name = str(features['gp_name'].iloc[0])
    with get_engine().connect() as conn:
        row = conn.execute(
            text("SELECT year FROM sessions WHERE session_key = :session_key"),
            {"session_key": quali_session_key},
        ).first()
    year = int(row[0]) if row else 0
    return compute_weekend_inputs_used(get_engine(), gp_name, year)


def explain_prediction(quali_session_key: int) -> list[dict]:
    """
    SHAP values for each driver's prediction.
    Returns top 3 most influential features per driver.
    """
    try:
        import shap
    except ImportError:
        log.warning("shap.not_installed")
        return []

    features = build_inference_features(quali_session_key)
    gp_name = str(features['gp_name'].iloc[0]) if 'gp_name' in features.columns and not features.empty else None
    ensure_model_available(gp_name)
    model = load_model(gp_name)
    X        = features[FEATURE_COLS]

    try:
        explainer  = shap.Explainer(model.model.estimator, X)
        shap_values = explainer(X)
    except Exception as e:
        log.warning("shap.failed", error=str(e))
        return []

    results = []
    for idx, row in features.iterrows():
        i          = list(features.index).index(idx)
        sv         = shap_values[i].values
        # Get top 3 features by absolute SHAP value
        top_indices = np.argsort(np.abs(sv))[-3:][::-1]
        factors = []
        stream_totals: dict[str, float] = {}
        for fi, shap_component in enumerate(sv):
            feat_name = FEATURE_COLS[fi]
            stream = feature_stream_for(feat_name)
            stream_totals[stream] = stream_totals.get(stream, 0.0) + abs(float(shap_component))

        for fi in top_indices:
            feat_name  = FEATURE_COLS[fi]
            shap_val   = float(sv[fi])
            stream = feature_stream_for(feat_name)
            # Positive SHAP = pushes position higher (worse)
            # Negative SHAP = pushes position lower (better)
            direction  = "+" if shap_val < 0 else "-"
            label      = _feature_label(feat_name, shap_val)
            factors.append({
                "feature":   feat_name,
                "stream":    stream,
                "stream_label": stream_label(stream),
                "shap_value":round(shap_val, 3),
                "label":     f"{direction} {label}",
                "positive":  shap_val < 0,  # negative shap = good for position
            })

        total = sum(stream_totals.values()) or 1.0
        stream_attr = [
            {
                "stream": stream,
                "label": stream_label(stream),
                "share": round(value / total, 3),
                "score": round(value, 3),
            }
            for stream, value in sorted(stream_totals.items(), key=lambda item: item[1], reverse=True)
        ]

        results.append({
            "driver_number": int(row['driver_number']),
            "abbreviation":  row['abbreviation'],
            "factors":       factors,
            "feature_streams": stream_attr,
        })

    return results


def _feature_label(feature: str, shap_val: float) -> str:
    labels = {
        "grid_position":         "Grid position advantage" if shap_val < 0 else "Grid position disadvantage",
        "quali_gap_ms":          "Strong quali pace" if shap_val < 0 else "Quali pace gap",
        "s1_gap_ms":             "Sector 1 strength" if shap_val < 0 else "Sector 1 weakness",
        "s2_gap_ms":             "Sector 2 strength" if shap_val < 0 else "Sector 2 weakness",
        "s3_gap_ms":             "Sector 3 strength" if shap_val < 0 else "Sector 3 weakness",
        "s1_rank":               "Top sector 1 performer",
        "s2_rank":               "Top sector 2 performer",
        "s3_rank":               "Top sector 3 performer",
        "quali_compound_soft":   "Soft tyre qualifier",
        "quali_compound_inter":  "Intermediate tyre qualifier",
        "speed_st_rank":         "Straight-line setup strength" if shap_val < 0 else "Speed trap deficit",
        "speed_st_delta_kmh":    "Low-drag top speed" if shap_val < 0 else "Top speed loss",
        "fp1_deg_rate_ms_lap":   "Tyre degradation signal" if shap_val < 0 else "Tyre degradation concern",
        "fp1_long_run_pace_ms":  "FP1 long-run pace" if shap_val < 0 else "FP1 long-run deficit",
        "sprint_finish_position": "Sprint race form" if shap_val < 0 else "Sprint result drag",
        "sprint_position_delta": "Sprint momentum" if shap_val < 0 else "Sprint position loss",
        "sc_probability":        "Safety-car volatility",
        "overtake_difficulty":   "Track position premium",
        "dnf_rate_circuit":      "Circuit reliability risk",
    }
    return labels.get(feature, feature)
