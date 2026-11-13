from types import SimpleNamespace

from backend.agent import orchestrator, types


def _single_node_dag():
    return types.ExecutionDAG(
        nodes=(
            types.DAGNode(
                id="a",
                tool_name=types.ToolName.RESOLVE_SESSION,
                label="",
                input_params={"year": 2026, "gp_name": "Monaco"},
            ),
        )
    )


def _routed():
    return types.RoutedQuestion(
        intent=types.Intent.PIT_STOP_SPEED_DELTA,
        driver_name="Hamilton",
        gp_name="Monaco",
        year=2026,
    )


def test_transient_succeeds_on_third_attempt(monkeypatch):
    calls = {"n": 0}

    def flaky_tool(inp):
        calls["n"] += 1
        if calls["n"] < 3:
            raise types.RetryableError("blip")
        return SimpleNamespace(session_key=1)

    monkeypatch.setitem(orchestrator._TOOLS, types.ToolName.RESOLVE_SESSION, flaky_tool)

    trace, env, failed = orchestrator._execute_dag(_single_node_dag(), _routed())
    assert calls["n"] == 3
    assert failed == set()
    assert len(trace) == 1
    assert trace[0].status == "ok"


def test_not_found_error_never_retried(monkeypatch):
    calls = {"n": 0}

    def missing_data(inp):
        calls["n"] += 1
        raise types.NotFoundError("no such session")

    monkeypatch.setitem(
        orchestrator._TOOLS, types.ToolName.RESOLVE_SESSION, missing_data
    )

    trace, env, failed = orchestrator._execute_dag(_single_node_dag(), _routed())
    assert calls["n"] == 1
    assert "a" in failed
    assert trace[0].status == "error"


def test_data_error_never_retried(monkeypatch):
    calls = {"n": 0}

    def bad_data(inp):
        calls["n"] += 1
        raise types.DataError("unusable")

    monkeypatch.setitem(orchestrator._TOOLS, types.ToolName.RESOLVE_SESSION, bad_data)

    _, _, failed = orchestrator._execute_dag(_single_node_dag(), _routed())
    assert calls["n"] == 1
    assert "a" in failed


def test_persistent_transient_fails_after_three_attempts(monkeypatch):
    calls = {"n": 0}

    def always_blip(inp):
        calls["n"] += 1
        raise types.RetryableError("down for good")

    monkeypatch.setitem(
        orchestrator._TOOLS, types.ToolName.RESOLVE_SESSION, always_blip
    )

    trace, _, failed = orchestrator._execute_dag(_single_node_dag(), _routed())
    assert calls["n"] == 3
    assert "a" in failed
    assert trace[0].error == "down for good"
