from backend.agent import orchestrator, types
from backend.agent.tools import _build_style_summary, _percentile_rank


def test_percentile_rank():
    assert _percentile_rank(10.0, [1.0, 5.0, 10.0, 20.0]) == 75.0
    assert _percentile_rank(None, [1.0, 2.0]) is None


def test_style_summary_compares_archetypes():
    a = types.DriverStyleProfile(
        driver_number=1,
        full_name="Charles Leclerc",
        abbreviation="LEC",
        archetype="Late Braker",
        traits=(),
    )
    b = types.DriverStyleProfile(
        driver_number=2,
        full_name="Lewis Hamilton",
        abbreviation="HAM",
        archetype="Smooth Operator",
        traits=(),
    )
    s = _build_style_summary(a, b)
    assert "Late Braker" in s and "Smooth Operator" in s


def test_template_dag_skips_session_for_style():
    routed = types.RoutedQuestion(
        intent=types.Intent.DRIVER_STYLE_COMPARISON,
        question="How does Antonelli compare to Hamilton?",
        driver_name="Antonelli",
        compare_driver_name="Hamilton",
    )
    dag = orchestrator.build_dag(routed)
    assert [n.id for n in dag.nodes] == ["style"]
    assert dag.edges == ()
