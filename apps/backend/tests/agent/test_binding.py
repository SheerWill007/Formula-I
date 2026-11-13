"""T1.3 -- parameter binding tests.

Covers binding.resolve_ref and binding.bind_params with a fake node and env.
No real tools, no LLM, no DB. This is the contract for the binding layer.
"""

import pytest

from backend.agent import orchestrator, types
from backend.agent.binding import BindError, bind_params, resolve_ref
from backend.agent.planner import PlannerDAGNode


def _node(**overrides):
    base = {
        "node_id": "n2",
        "tool": types.ToolName.RESOLVE_SESSION.value,
        "params": {},
        "depends_on": ["n1"],
        "round": 1,
        "input_param_refs": {},
    }
    base.update(overrides)
    return PlannerDAGNode(**base)


def test_resolve_ref_nested_dict():
    env = {"n1": {"session_key": 1, "meta": {"gp": "Monaco"}}}
    assert resolve_ref("n1.session_key", env) == 1
    assert resolve_ref("n1.meta.gp", env) == "Monaco"


def test_resolve_ref_attribute_lookup():
    class _Out:
        driver_id = 44

    env = {"n1": _Out()}
    assert resolve_ref("n1.driver_id", env) == 44


def test_resolve_ref_missing_node_raises():
    with pytest.raises(BindError):
        resolve_ref("nope.field", {})


def test_resolve_ref_missing_field_raises():
    env = {"n1": {"session_key": 1}}
    with pytest.raises(BindError):
        resolve_ref("n1.gp_name", env)


def test_resolve_ref_malformed_ref_fails_closed():
    env = {"n1": {"session_key": 1}}
    with pytest.raises(BindError):
        resolve_ref("n1.missing.deep", env)


def test_ref_overwrites_explicit_param(monkeypatch):
    captured = {}

    def fake_bind(tool_name, merged, env):
        captured["merged"] = merged
        captured["tool"] = tool_name
        return merged

    monkeypatch.setattr("backend.agent.orchestrator._bind", fake_bind)

    node = _node(
        params={"year": 2025, "gp_name": "X"},
        input_param_refs={"gp_name": "n1.gp_name", "year": "n1.year"},
    )
    env = {"n1": {"gp_name": "Monaco", "year": 2026}}

    bind_params(node, env, types.ToolName.RESOLVE_SESSION)

    assert captured["merged"]["gp_name"] == "Monaco"
    assert captured["merged"]["year"] == 2026


def test_explicit_param_used_when_no_ref(monkeypatch):
    captured = {}

    def fake_bind(tool_name, merged, env):
        captured["merged"] = merged
        return merged

    monkeypatch.setattr("backend.agent.orchestrator._bind", fake_bind)

    node = _node(params={"year": 2025, "gp_name": "Monaco"})
    env = {"n1": {"gp_name": "X", "year": 99}}

    bind_params(node, env, types.ToolName.RESOLVE_SESSION)
    assert captured["merged"]["gp_name"] == "Monaco"
    assert captured["merged"]["year"] == 2025


def test_missing_ref_with_no_fallback_raises(monkeypatch):
    def fake_bind(tool_name, merged, env):
        return merged

    monkeypatch.setattr("backend.agent.orchestrator._bind", fake_bind)

    node = _node(
        params={},
        input_param_refs={"gp_name": "nope.gp_name"},
    )
    with pytest.raises(BindError):
        bind_params(node, {"n1": {}}, types.ToolName.RESOLVE_SESSION)


def test_every_tool_has_a_binder():
    """Every dispatchable tool must have a parameter binder.

    Prevents regressions like the missing ``@_register`` on ``_bind_gap``,
    which made POSITION_GAP_TRACKING nodes raise ``KeyError`` at bind time.
    """
    missing = set(orchestrator._TOOLS) - set(orchestrator._BINDERS)
    assert not missing, f"tools without a binder: {sorted(t.value for t in missing)}"
