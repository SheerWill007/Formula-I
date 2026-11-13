import pytest

from backend.agent import orchestrator, tools, types


def test_all_template_dags_sit_under_the_cap():
    # today's hardcoded planner must never trip its own guard
    for intent in types.Intent:
        if intent is types.Intent.UNSUPPORTED:
            continue
        dag = orchestrator.build_dag(
            types.RoutedQuestion(
                intent=intent, driver_name="Hamilton", gp_name="Monaco", year=2026
            )
        )
        assert len(dag.nodes) <= orchestrator.MAX_DAG_NODES, intent


def test_build_dag_rejects_plan_over_the_cap(monkeypatch):
    # shrink the cap so pit_stop_speed_delta (6 nodes) blows past it
    monkeypatch.setattr(orchestrator, "MAX_DAG_NODES", 3)
    with pytest.raises(types.DataError, match="MAX_DAG_NODES"):
        orchestrator.build_dag(
            types.RoutedQuestion(
                intent=types.Intent.PIT_STOP_SPEED_DELTA,
                driver_name="Hamilton",
                gp_name="Monaco",
                year=2026,
            )
        )


def test_run_falls_back_to_refusal_when_plan_too_large(monkeypatch):
    monkeypatch.setattr(
        orchestrator.llm,
        "route_question",
        lambda q: (
            types.RoutedQuestion(
                intent=types.Intent.PIT_STOP_SPEED_DELTA,
                driver_name="Hamilton",
                gp_name="Monaco",
                year=2026,
            ),
            0.0,
        ),
    )
    monkeypatch.setattr(orchestrator, "MAX_DAG_NODES", 3)
    answer = orchestrator.run("Why did Hamilton pit early?")
    assert answer.refusals == ("plan_too_large",)
    assert answer.trace == ()


def test_telemetry_inspector_rejects_too_many_laps():
    inp = types.TelemetryInspectorInput(
        session_key=99999,
        driver_number=44,
        lap_numbers=tuple(range(1, tools.MAX_LAPS_PER_CALL + 2)),
    )
    with pytest.raises(types.DataError, match="cap is"):
        tools.telemetry_inspector(inp)
