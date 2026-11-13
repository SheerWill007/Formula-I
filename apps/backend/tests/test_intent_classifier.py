"""DB-free unit tests for the local intent classifier (deterministic)."""

from backend.agent.intent_classifier import classify_intent


def test_compute_average():
    r = classify_intent("What was Verstappen's average speed at Monaco?")
    assert r.requires_compute is True
    assert r.requires_prediction is False
    assert r.intent_category == "descriptive"


def test_compute_diagnostic_prompt():
    r = classify_intent("Why did Leclerc lose time on lap 43?")
    assert r.requires_compute is True


def test_prediction():
    r = classify_intent("Will Hamilton need another stop?")
    assert r.requires_prediction is True
    assert r.intent_category == "predictive"


def test_comparative():
    r = classify_intent("How does Antonelli's driving style compare to Hamilton's?")
    assert r.intent_category == "comparative"


def test_chitchat_is_not_compute():
    r = classify_intent("hi who are you")
    assert r.requires_compute is False
    assert r.intent_category == "chitchat"
    assert r.suggested_tools == ()


def test_comparative_suggests_telemetry_tools():
    r = classify_intent("compare Verstappen vs Norris")
    assert "telemetry_inspector" in r.suggested_tools
