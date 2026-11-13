from backend.agent import orchestrator, types
from backend.config import settings


def _routed(intent):
    return types.RoutedQuestion(
        intent=types.Intent(intent),
        driver_name="Hamilton",
        gp_name="Monaco",
        year=2026,
    )


def _tool_sequence(dag):
    order = orchestrator.topo_sort(dag)
    node_map = {n.id: n for n in dag.nodes}
    return [node_map[nid].tool_name.value for nid in order]


def test_flag_defaults_to_template():
    assert settings.agent_planner_mode == "template"


def test_template_mode_keeps_today_s_dag():
    routed = _routed("tyre_degradation_analysis")
    actual = _tool_sequence(orchestrator.build_dag(routed))
    expected = _tool_sequence(orchestrator._build_template_dag(routed))
    assert actual == expected


def test_llm_mode_without_planner_falls_back_to_template(monkeypatch):
    monkeypatch.setattr(settings, "agent_planner_mode", "llm")
    routed = _routed("tyre_degradation_analysis")
    actual = _tool_sequence(orchestrator.build_dag(routed))
    assert actual == _tool_sequence(orchestrator._build_template_dag(routed))


def test_llm_mode_build_dag_uses_template(monkeypatch):
    """T1.2 moved the LLM/agentic planner out of build_dag() and into run().
    build_dag() is now the T0.1 golden-eval baseline and ALWAYS returns the
    template DAG, regardless of mode. The agentic loop owns execution and is
    dispatched in run(), not here."""
    monkeypatch.setattr(settings, "agent_planner_mode", "llm")
    routed = _routed("tyre_degradation_analysis")
    assert _tool_sequence(orchestrator.build_dag(routed)) == _tool_sequence(
        orchestrator._build_template_dag(routed)
    )


def test_run_agentic_dispatches_to_agentic_loop(monkeypatch):
    """The llm-mode entry point (run -> _run_agentic) must invoke the T1.2
    agentic loop and pass it the planner's tool registry."""
    captured = {}

    def fake_run_agentic_dag(question, routed, registry):
        captured["registry"] = registry
        return {"routed": routed, "n1": {"session_key": 1}}

    from backend.agent import agentic_loop, planner

    monkeypatch.setattr(agentic_loop, "run_agentic_dag", fake_run_agentic_dag)

    routed = _routed("tyre_degradation_analysis")
    env = orchestrator._run_agentic("Did rain affect degradation?", routed)

    assert env is not None
    assert captured["registry"] is planner.TOOL_REGISTRY
