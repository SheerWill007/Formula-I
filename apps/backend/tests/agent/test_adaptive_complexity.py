from backend.agent import llm, planner, types


def _dst(complexity: int):
    """Synthetic DAG: session -> driver, plus an un-consumed heavy telemetry leaf."""
    nodes = (
        types.DAGNode(id="s", tool_name=types.ToolName.RESOLVE_SESSION, label="s"),
        types.DAGNode(
            id="d",
            tool_name=types.ToolName.RESOLVE_DRIVER,
            label="d",
            depends_on=("s",),
        ),
        types.DAGNode(
            id="t",
            tool_name=types.ToolName.TELEMETRY_INSPECTOR,
            label="t",
            depends_on=("s", "d"),
        ),
        types.DAGNode(
            id="v",
            tool_name=types.ToolName.VERIFY_EVIDENCE,
            label="v",
            depends_on=("d",),
        ),
    )
    edges = tuple(
        types.DAGEdge(source=dep, target=node.id)
        for node in nodes
        for dep in node.depends_on
    )
    return types.ExecutionDAG(nodes=nodes, edges=edges)


def _pruned(complexity: int):
    routed = types.RoutedQuestion(
        intent=types.Intent.PIT_STOP_SPEED_DELTA, complexity=complexity
    )
    return planner.prune_dag(_dst(complexity), routed)


def test_simple_question_drops_heavy_leaf():
    dag = _pruned(1)
    names = {n.tool_name for n in dag.nodes}
    assert types.ToolName.TELEMETRY_INSPECTOR not in names


def test_verify_always_survives():
    for complexity in (1, 5):
        dag = _pruned(complexity)
        assert types.ToolName.VERIFY_EVIDENCE in {n.tool_name for n in dag.nodes}


def test_compound_keeps_heavy_leaf():
    dag = _pruned(5)
    assert types.ToolName.TELEMETRY_INSPECTOR in {n.tool_name for n in dag.nodes}


def _telemetry_comparison_dag():
    nodes = (
        types.DAGNode(id="s", tool_name=types.ToolName.RESOLVE_SESSION, label="s"),
        types.DAGNode(
            id="d",
            tool_name=types.ToolName.RESOLVE_DRIVER,
            label="d",
            depends_on=("s",),
        ),
        types.DAGNode(
            id="dc",
            tool_name=types.ToolName.RESOLVE_DRIVER,
            label="dc",
            depends_on=("s",),
        ),
        types.DAGNode(
            id="t",
            tool_name=types.ToolName.TELEMETRY_INSPECTOR,
            label="t",
            depends_on=("s", "d", "dc"),
        ),
        types.DAGNode(
            id="v",
            tool_name=types.ToolName.VERIFY_EVIDENCE,
            label="v",
            depends_on=("s", "d", "dc"),
        ),
    )
    edges = tuple(
        types.DAGEdge(source=dep, target=node.id)
        for node in nodes
        for dep in node.depends_on
    )
    return types.ExecutionDAG(nodes=nodes, edges=edges)


def _tyre_degradation_dag():
    nodes = (
        types.DAGNode(id="s", tool_name=types.ToolName.RESOLVE_SESSION, label="s"),
        types.DAGNode(
            id="d",
            tool_name=types.ToolName.RESOLVE_DRIVER,
            label="d",
            depends_on=("s",),
        ),
        types.DAGNode(
            id="st",
            tool_name=types.ToolName.STINT_DEGRADATION_SCANNER,
            label="st",
            depends_on=("s", "d"),
        ),
        types.DAGNode(
            id="v",
            tool_name=types.ToolName.VERIFY_EVIDENCE,
            label="v",
            depends_on=("s", "d"),
        ),
    )
    edges = tuple(
        types.DAGEdge(source=dep, target=node.id)
        for node in nodes
        for dep in node.depends_on
    )
    return types.ExecutionDAG(nodes=nodes, edges=edges)


def test_simple_telemetry_comparison_keeps_core_telemetry():
    dag = planner.prune_dag(
        _telemetry_comparison_dag(),
        types.RoutedQuestion(intent=types.Intent.TELEMETRY_COMPARISON, complexity=1),
    )
    assert types.ToolName.TELEMETRY_INSPECTOR in {n.tool_name for n in dag.nodes}


def test_simple_tyre_degradation_keeps_stints():
    dag = planner.prune_dag(
        _tyre_degradation_dag(),
        types.RoutedQuestion(
            intent=types.Intent.TYRE_DEGRADATION_ANALYSIS, complexity=1
        ),
    )
    assert types.ToolName.STINT_DEGRADATION_SCANNER in {n.tool_name for n in dag.nodes}


def test_score_complexity_ranks_compound_higher():
    trivial = llm._score_complexity(
        "Where was Hamilton after his pit stop?",
        types.RoutedQuestion(intent=types.Intent.POSITION_GAP_TRACKING),
    )
    compound = llm._score_complexity(
        "why did rain affect tyre degradation over the weekend?",
        types.RoutedQuestion(
            intent=types.Intent.WEATHER_CORRELATION,
            compare_driver_name="Leclerc",
            target_lap=34,
        ),
    )
    assert compound > trivial
    assert trivial >= 1 <= 5
    assert 1 <= compound <= 5
