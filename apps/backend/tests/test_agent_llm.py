"""DB-free unit tests for the OpenRouter adapter (L9)."""

import pytest

from backend.agent import llm, types
from backend.agent.semantic_cache import SemanticCache
from backend.config import settings


@pytest.fixture(autouse=True)
def _isolate_cache(monkeypatch):
    """The semantic cache is a module-level singleton shared across tests;
    one test storing a query silently contaminates the next. Give each test
    a fresh cache so order can never decide outcomes."""
    monkeypatch.setattr(llm, "semantic_cache", SemanticCache())


def _fake_payload(content, usage=None):
    return {
        "choices": [{"message": {"content": content}}],
        "usage": usage
        or {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    }


def _set_key(monkeypatch, value="test-key"):
    monkeypatch.setattr(settings, "openrouter_api_key", value)


def test_route_question_extracts_entities(monkeypatch):
    _set_key(monkeypatch)
    monkeypatch.setattr(
        llm,
        "_post",
        lambda messages, model, temperature: _fake_payload(
            '{"intent": "pit_stop_speed_delta", "driver": "Sainz", '
            '"year": 2026, "gp_name": "Monaco", "laps_window": 3}'
        ),
    )
    routed, cost = llm.route_question("On which lap did Sainz pit in Monaco 2026?")
    assert routed.intent is types.Intent.PIT_STOP_SPEED_DELTA
    assert routed.driver_name == "Sainz"
    assert routed.year == 2026
    assert routed.gp_name == "Monaco"
    assert isinstance(cost, float)


def test_route_question_unsupported_has_null_entities(monkeypatch):
    _set_key(monkeypatch)
    monkeypatch.setattr(
        llm,
        "_post",
        lambda messages, model, temperature: _fake_payload(
            '{"intent": "unsupported", "driver": null, "year": null, '
            '"gp_name": null, "laps_window": null}'
        ),
    )
    routed, cost = llm.route_question("What is the weather?")
    assert routed.intent is types.Intent.UNSUPPORTED
    assert routed.driver_name is None
    assert routed.year is None
    assert routed.gp_name is None
    assert routed.laps_window == 3


def test_route_question_unparseable_raises(monkeypatch):
    _set_key(monkeypatch)
    monkeypatch.setattr(
        llm,
        "_post",
        lambda messages, model, temperature: _fake_payload("hello world"),
    )
    with pytest.raises(types.LLMError):
        llm.route_question("when did he pit?")


def test_route_question_unknown_intent_raises(monkeypatch):
    _set_key(monkeypatch)
    monkeypatch.setattr(
        llm,
        "_post",
        lambda messages, model, temperature: _fake_payload('{"intent": "weather"}'),
    )
    with pytest.raises(types.LLMError):
        llm.route_question("when did he pit?")


def test_chat_raises_when_no_api_key(monkeypatch):
    _set_key(monkeypatch, value="")
    with pytest.raises(types.LLMError):
        llm._chat([{"role": "user", "content": "hi"}])


def test_estimate_cost_uses_known_prices():
    usage = {"prompt_tokens": 1_000_000, "completion_tokens": 1_000_000}
    assert llm._estimate_cost("openai/gpt-4o-mini", usage) == pytest.approx(0.75)


def test_estimate_cost_uses_openrouter_cost():
    usage = {"cost": 0.0042, "prompt_tokens": 10, "completion_tokens": 5}
    assert llm._estimate_cost("unknown/model", usage) == pytest.approx(0.0042)


def test_estimate_cost_unknown_model_is_zero():
    usage = {"prompt_tokens": 100, "completion_tokens": 100}
    assert llm._estimate_cost("unknown/model", usage) == 0.0


def test_compose_answer(monkeypatch):
    _set_key(monkeypatch)
    monkeypatch.setattr(
        llm,
        "_post",
        lambda messages, model, temperature: _fake_payload(
            "Verstappen pitted on lap 22."
        ),
    )
    out, cost = llm.compose_answer("when did he pit?", {"pit_lap": 22})
    assert out == "Verstappen pitted on lap 22."
    assert isinstance(cost, float)


def test_compose_answer_uses_final_model(monkeypatch):
    _set_key(monkeypatch)
    seen = {}

    def fake_post(messages, model, temperature):
        seen["model"] = model
        return _fake_payload("ok")

    monkeypatch.setattr(llm, "_post", fake_post)
    llm.compose_answer("when?", {})
    assert seen["model"] == settings.openrouter_final_model


def test_compose_answer_stays_cheap_for_factual_intent(monkeypatch):
    _set_key(monkeypatch)
    monkeypatch.setattr(settings, "openrouter_capable_model", "openai/gpt-4o")
    seen = {}

    def fake_post(messages, model, temperature):
        seen["model"] = model
        return _fake_payload("ok")

    monkeypatch.setattr(llm, "_post", fake_post)
    llm.compose_answer(
        "when did he pit?",
        {},
        intent=types.Intent.PIT_STOP_SPEED_DELTA,
        complexity=5,
    )
    assert seen["model"] == settings.openrouter_final_model


def test_compose_answer_escalates_complex_analytical_intent(monkeypatch):
    _set_key(monkeypatch)
    monkeypatch.setattr(settings, "openrouter_capable_model", "openai/gpt-4o")
    seen = {}

    def fake_post(messages, model, temperature):
        seen["model"] = model
        return _fake_payload("ok")

    monkeypatch.setattr(llm, "_post", fake_post)
    llm.compose_answer(
        "did the heat hurt his tyres?",
        {},
        intent=types.Intent.TYRE_DEGRADATION_ANALYSIS,
        complexity=4,
    )
    assert seen["model"] == "openai/gpt-4o"


def test_compose_answer_simple_analytical_stays_cheap(monkeypatch):
    _set_key(monkeypatch)
    monkeypatch.setattr(settings, "openrouter_capable_model", "openai/gpt-4o")
    seen = {}

    def fake_post(messages, model, temperature):
        seen["model"] = model
        return _fake_payload("ok")

    monkeypatch.setattr(llm, "_post", fake_post)
    llm.compose_answer(
        "telemetry pls",
        {},
        intent=types.Intent.TELEMETRY_COMPARISON,
        complexity=2,
    )
    assert seen["model"] == settings.openrouter_final_model


def test_route_question_coerces_string_year(monkeypatch):
    _set_key(monkeypatch)
    monkeypatch.setattr(
        llm,
        "_post",
        lambda messages, model, temperature: _fake_payload(
            '{"intent": "pit_stop_speed_delta", "driver": "HAM", "year": "2018"}'
        ),
    )
    routed, _ = llm.route_question("q?")
    assert routed.year == 2018


def test_route_question_bad_year_raises(monkeypatch):
    _set_key(monkeypatch)
    monkeypatch.setattr(
        llm,
        "_post",
        lambda messages, model, temperature: _fake_payload(
            '{"intent": "pit_stop_speed_delta", "year": "fast"}'
        ),
    )
    with pytest.raises(types.LLMError):
        llm.route_question("q?")


def test_route_question_clamps_window(monkeypatch):
    _set_key(monkeypatch)
    monkeypatch.setattr(
        llm,
        "_post",
        lambda messages, model, temperature: _fake_payload(
            '{"intent": "pit_stop_speed_delta", "laps_window": 99}'
        ),
    )
    routed, _ = llm.route_question("q?")
    assert routed.laps_window == 10


def test_compose_answer_empty_raises(monkeypatch):
    _set_key(monkeypatch)
    monkeypatch.setattr(
        llm, "_post", lambda messages, model, temperature: _fake_payload("   ")
    )
    with pytest.raises(types.LLMError) as exc:
        llm.compose_answer("when?", {})
    assert exc.value.code == "composer_empty"


def test_compose_answer_code_block_raises(monkeypatch):
    _set_key(monkeypatch)
    monkeypatch.setattr(
        llm,
        "_post",
        lambda messages, model, temperature: _fake_payload("```json\n{}\n```"),
    )
    with pytest.raises(types.LLMError) as exc:
        llm.compose_answer("when?", {})
    assert exc.value.code == "composer_code_block"


def test_route_question_non_object_json_raises(monkeypatch):
    _set_key(monkeypatch)
    monkeypatch.setattr(
        llm, "_post", lambda messages, model, temperature: _fake_payload("[1, 2, 3]")
    )
    with pytest.raises(types.LLMError) as exc:
        llm.route_question("when did he pit?")
    assert exc.value.code == "router_unparseable"


def test_route_question_bad_window_raises(monkeypatch):
    _set_key(monkeypatch)
    monkeypatch.setattr(
        llm,
        "_post",
        lambda messages, model, temperature: _fake_payload(
            '{"intent": "pit_stop_speed_delta", "laps_window": "fast"}'
        ),
    )
    with pytest.raises(types.LLMError) as exc:
        llm.route_question("q?")
    assert exc.value.code == "router_bad_window"


def test_route_question_sets_compute_flag(monkeypatch):
    _set_key(monkeypatch)
    monkeypatch.setattr(
        llm,
        "_post",
        lambda messages, model, temperature: _fake_payload(
            '{"intent": "pit_stop_speed_delta", "driver": "Verstappen", '
            '"year": 2026, "gp_name": "Monaco", "laps_window": 3}'
        ),
    )
    routed, _ = llm.route_question(
        "What was the average speed after his stop in Monaco 2026?"
    )
    assert routed.requires_compute is True
    assert routed.intent_category == "descriptive"


def test_route_question_cache_miss_calls_client_exactly_once(monkeypatch):
    """T1.1: a routing cache miss must perform exactly one client call."""
    _set_key(monkeypatch)
    calls = []

    def counting_post(messages, model, temperature):
        calls.append({"messages": messages, "model": model, "temperature": temperature})
        return _fake_payload(
            '{"intent": "pit_stop_speed_delta", "driver": "Sainz", '
            '"year": 2026, "gp_name": "Monaco", "laps_window": 3}'
        )

    monkeypatch.setattr(llm, "_post", counting_post)
    routed, cost = llm.route_question("On which lap did Sainz pit in Monaco 2026?")
    assert len(calls) == 1
    assert routed.intent is types.Intent.PIT_STOP_SPEED_DELTA
    assert cost > 0


def test_route_question_cache_hit_skips_client_call(monkeypatch):
    """T1.1: a routing cache hit must perform zero client calls."""
    _set_key(monkeypatch)
    calls = []

    def counting_post(messages, model, temperature):
        calls.append(model)
        return _fake_payload('{"intent": "unsupported"}')

    monkeypatch.setattr(llm, "_post", counting_post)
    monkeypatch.setattr(
        llm.semantic_cache,
        "get",
        lambda q: {
            "intent": "pit_stop_speed_delta",
            "driver": "Verstappen",
            "year": 2026,
            "gp_name": "Monaco",
            "laps_window": 3,
        },
    )
    routed, cost = llm.route_question(
        "What was the average speed after his stop in Monaco 2026?"
    )
    assert calls == []
    assert routed.intent is types.Intent.PIT_STOP_SPEED_DELTA
    assert cost == 0.0


def test_route_question_cache_hit_keeps_local_flags(monkeypatch):
    """BUG 2: entity parse is cached, but the local flags must survive."""
    _set_key(monkeypatch)
    monkeypatch.setattr(
        llm.semantic_cache,
        "get",
        lambda q: {
            "intent": "pit_stop_speed_delta",
            "driver": "Verstappen",
            "year": 2026,
            "gp_name": "Monaco",
            "laps_window": 3,
        },
    )
    routed, cost = llm.route_question(
        "What was the average speed after his stop in Monaco 2026?"
    )
    assert routed.requires_compute is True
    assert cost == 0.0
