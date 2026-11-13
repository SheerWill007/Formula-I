"""
T1.1 validation contract -- run with: python -m pytest tests/agent/test_planner.py -v

These tests exercise the validation / cycle-detection / topo_sort logic against a
small FAKE registry -- they don't need the real LLM client or real tools.py wired up.

They ARE the contract: once call_llm_json() is wired to the real LLM client, these
should still all pass unmodified. If a change to planner.py breaks one of these,
that's a signal to stop and reconsider, not to edit the test to match.

NOTE: the bind_params (T1.3) and run_agentic_dag (T1.2) tests from the v3 architecture
doc are NOT included here -- they live with the binding.py / agentic_loop.py modules
those tiers create. This file is scoped to T1.1's planner validation only.
"""

import dataclasses
import pytest

from backend.agent.planner import (
    ToolSpec,
    PlanValidationError,
    validate_plan,
    topo_sort,
    MAX_DAG_NODES,
)


# ---------------------------------------------------------------------------
# Fake registry for testing
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class _ResolveSessionInput:
    year: int
    gp_name: str


@dataclasses.dataclass(frozen=True)
class _GetLapsInput:
    session_key: str
    driver: str = "VER"  # optional, has a default


REGISTRY = {
    "resolve_session": ToolSpec.from_dataclass(
        "resolve_session",
        "Find a session.",
        _ResolveSessionInput,
        "Returns session_key.",
    ),
    "get_laps": ToolSpec.from_dataclass(
        "get_laps", "Get lap times.", _GetLapsInput, "Returns lap times list."
    ),
}


# ---------------------------------------------------------------------------
# validate_plan -- happy path
# ---------------------------------------------------------------------------


def test_valid_plan_passes():
    raw = {
        "nodes": [
            {
                "id": "n1",
                "tool": "resolve_session",
                "params": {"year": 2024, "gp_name": "Spa"},
                "depends_on": [],
            },
            {
                "id": "n2",
                "tool": "get_laps",
                "params": {"session_key": "spa2024"},
                "depends_on": ["n1"],
            },
        ]
    }
    dag = validate_plan(raw, REGISTRY)
    assert len(dag.nodes) == 2
    assert topo_sort(dag) == ["n1", "n2"]


def test_optional_param_can_be_omitted():
    raw = {
        "nodes": [
            {
                "id": "n1",
                "tool": "get_laps",
                "params": {"session_key": "spa2024"},
                "depends_on": [],
            },
        ]
    }
    dag = validate_plan(raw, REGISTRY)
    assert dag.nodes[0].params == {"session_key": "spa2024"}


# ---------------------------------------------------------------------------
# validate_plan -- rejections
# ---------------------------------------------------------------------------


def test_unknown_tool_rejected():
    raw = {
        "nodes": [
            {"id": "n1", "tool": "delete_database", "params": {}, "depends_on": []}
        ]
    }
    with pytest.raises(PlanValidationError, match="unknown tool"):
        validate_plan(raw, REGISTRY)


def test_missing_required_param_rejected():
    raw = {
        "nodes": [
            {
                "id": "n1",
                "tool": "resolve_session",
                "params": {"year": 2024},
                "depends_on": [],
            }
        ]
    }
    with pytest.raises(PlanValidationError, match="missing required params"):
        validate_plan(raw, REGISTRY)


def test_missing_required_param_covered_by_ref_is_allowed():
    raw = {
        "nodes": [
            {
                "id": "n1",
                "tool": "resolve_session",
                "params": {"year": 2024},
                "depends_on": [],
                "input_param_refs": {"gp_name": "n0.gp_name"},
            }
        ]
    }
    dag = validate_plan(raw, REGISTRY, known_node_ids={"n0"})
    assert dag.nodes[0].input_param_refs == {"gp_name": "n0.gp_name"}


def test_unknown_param_rejected():
    raw = {
        "nodes": [
            {
                "id": "n1",
                "tool": "resolve_session",
                "params": {"year": 2024, "gp_name": "Spa", "sabotage": True},
                "depends_on": [],
            }
        ]
    }
    with pytest.raises(PlanValidationError, match="not in .* schema"):
        validate_plan(raw, REGISTRY)


def test_dangling_dependency_rejected():
    raw = {
        "nodes": [
            {
                "id": "n1",
                "tool": "resolve_session",
                "params": {"year": 2024, "gp_name": "Spa"},
                "depends_on": ["ghost_node"],
            }
        ]
    }
    with pytest.raises(PlanValidationError, match="doesn't exist"):
        validate_plan(raw, REGISTRY)


def test_cycle_rejected():
    raw = {
        "nodes": [
            {
                "id": "n1",
                "tool": "get_laps",
                "params": {"session_key": "x"},
                "depends_on": ["n2"],
            },
            {
                "id": "n2",
                "tool": "get_laps",
                "params": {"session_key": "y"},
                "depends_on": ["n1"],
            },
        ]
    }
    with pytest.raises(PlanValidationError, match="cycle"):
        validate_plan(raw, REGISTRY)


def test_node_cap_enforced():
    raw = {
        "nodes": [
            {
                "id": f"n{i}",
                "tool": "get_laps",
                "params": {"session_key": "x"},
                "depends_on": [],
            }
            for i in range(MAX_DAG_NODES + 1)
        ]
    }
    with pytest.raises(PlanValidationError, match="cap is"):
        validate_plan(raw, REGISTRY)


def test_cross_round_dependency_allowed_via_known_node_ids():
    # simulates T1.2: a second-round plan referencing a node that already ran
    raw = {
        "nodes": [
            {
                "id": "n2",
                "tool": "get_laps",
                "params": {"session_key": "x"},
                "depends_on": ["n1"],
            },
        ]
    }
    dag = validate_plan(raw, REGISTRY, known_node_ids={"n1"})
    assert dag.nodes[0].depends_on == ["n1"]


def test_cross_round_dependency_rejected_if_truly_unknown():
    raw = {
        "nodes": [
            {
                "id": "n2",
                "tool": "get_laps",
                "params": {"session_key": "x"},
                "depends_on": ["never_existed"],
            },
        ]
    }
    with pytest.raises(PlanValidationError, match="doesn't exist"):
        validate_plan(
            raw, REGISTRY, known_node_ids={"n1"}
        )  # n1 exists, never_existed doesn't
