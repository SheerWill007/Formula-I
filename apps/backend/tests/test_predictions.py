"""Predictions API contract tests (T1.3).

A missing model must produce a fast, explicit 503 with
`{"error": "model_unavailable"}` and must never trigger training from the
HTTP request. Training happens only via the one-shot job / worker task.
"""

import ml.predict
import ml.features
from ml.predict import ModelUnavailableError


def test_predictions_missing_model_returns_503(client, seed_session, monkeypatch):
    """ModelUnavailableError -> fast 503 with the model_unavailable contract."""

    def boom(session_key):
        raise ModelUnavailableError(
            "No trained model found at ./ml_models/race_predictor.pkl"
        )

    monkeypatch.setattr(ml.predict, "predict_race", boom)

    resp = client.get("/api/v1/sessions/99999/predictions")

    assert resp.status_code == 503
    body = resp.get_json()
    assert body["error"] == "model_unavailable"
    assert "No trained model found" in body["detail"]
    assert "retraining" not in body


def test_predictions_does_not_train_from_http():
    """T1.3: the web path offers no training trigger."""
    assert not hasattr(ml.predict, "schedule_training")


def test_predictions_success_path_returns_200(client, seed_session, monkeypatch):
    """With a model, predictions render end-to-end (stubbed inference)."""
    predictions = [
        {
            "driver_number": 63,
            "abbreviation": "RUS",
            "team_name": "Mercedes",
            "predicted_position": 1,
            "win_probability": 0.51,
            "podium_probability": 0.92,
            "position_probabilities": {1: 0.51},
        },
        {
            "driver_number": 44,
            "abbreviation": "HAM",
            "team_name": "Mercedes",
            "predicted_position": 2,
            "win_probability": 0.32,
            "podium_probability": 0.85,
            "position_probabilities": {1: 0.32},
        },
    ]

    monkeypatch.setattr(ml.predict, "predict_race", lambda sk: predictions)
    monkeypatch.setattr(ml.predict, "explain_prediction", lambda sk: [])
    monkeypatch.setattr(ml.features, "compute_weekend_inputs_used", lambda *a, **k: {})

    resp = client.get("/api/v1/sessions/99999/predictions")

    assert resp.status_code == 200
    body = resp.get_json()
    assert body["session_key"] == 99999
    assert len(body["predictions"]) == 2
    assert body["predictions"][0]["driver_number"] == 63
    assert body["predictions"][0]["team_colour"]
    assert body["predictions"][0]["factors"] == []
