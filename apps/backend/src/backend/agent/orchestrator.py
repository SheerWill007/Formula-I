"""
Agent orchestrator — routes with the LLM, executes read-only tools, composes.

Pipeline: route -> plan -> execute -> verify -> compose.
Every tool call is recorded in the trace for debugging and the future UI.
"""

from __future__ import annotations
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from dataclasses import asdict, replace
import time
from typing import Any, Callable

from backend.agent import circuit_breaker, context as agent_context
from backend.agent import llm, tools, types
from backend.config import settings
from backend.agent.nodes import compute_node, critic_node, synthesis_node

ProgressCallback = Callable[[dict], None]


def _emit(progress: ProgressCallback | None, **payload) -> None:
    """Best-effort progress events for streaming clients."""
    if progress is None:
        return
    try:
        progress(payload)
    except Exception:
        return


_TOOLS: dict[types.ToolName, Callable] = {
    types.ToolName.RESOLVE_SESSION: tools.resolve_session,
    types.ToolName.RESOLVE_DRIVER: tools.resolve_driver,
    types.ToolName.FIND_PIT_STOPS: tools.find_pit_stops,
    types.ToolName.GET_LAP_TELEMETRY_ARTIFACTS: tools.get_lap_telemetry_artifacts,
    types.ToolName.COMPUTE_SPEED_WINDOW: tools.compute_speed_window,
    types.ToolName.INSPECT_LAP_EVENTS: tools.inspect_lap_events,
    types.ToolName.STINT_DEGRADATION_SCANNER: tools.stint_degradation_scanner,
    types.ToolName.TELEMETRY_INSPECTOR: tools.telemetry_inspector,
    types.ToolName.GAP_POSITION_SNAPSHOT: tools.gap_and_position_snapshot,
    types.ToolName.FETCH_RACE_CONTROL_WINDOW: tools.fetch_race_control_window,
    types.ToolName.FETCH_RADIO_MESSAGES: tools.fetch_radio_messages,
    types.ToolName.FETCH_WEATHER_WINDOW: tools.fetch_weather_window,
    types.ToolName.DRIVER_STYLE_COMPARE: tools.driver_style_compare,
    types.ToolName.LIST_AVAILABLE_SESSIONS: tools.list_available_sessions,
    types.ToolName.DESCRIBE_SESSION_COVERAGE: tools.describe_session_coverage,
    types.ToolName.SEARCH_SESSIONS: tools.search_sessions,
    types.ToolName.ESTIMATE_PIT_LOSS: tools.estimate_pit_loss,
    types.ToolName.COMPARE_STRATEGY_SCENARIOS: tools.compare_strategy_scenarios,
    types.ToolName.SEARCH_STRATEGY_SOURCES: tools.search_strategy_sources,
    types.ToolName.FETCH_TRACK_STATUS: tools.fetch_track_status,
    types.ToolName.FETCH_SESSION_RESULTS: tools.fetch_session_results,
    types.ToolName.VERIFY_EVIDENCE: tools.verify_evidence,
}
_MAX_WORKERS = 4
MAX_DAG_NODES = 8


_BINDERS: dict[types.ToolName, Callable[[dict, dict], Any]] = {}


def _bind(tool_name: types.ToolName, params: dict, env: dict) -> Any:
    return _BINDERS[tool_name](params, env)


def _register(tool_name: types.ToolName):
    def wrap(fn):
        _BINDERS[tool_name] = fn
        return fn

    return wrap


@_register(types.ToolName.RESOLVE_SESSION)
def _bind_session(params, env):
    return types.ResolveSessionInput(
        year=params["year"],
        gp_name=params["gp_name"],
        session_type=env["routed"].session_type or types.SessionType.RACE,
    )


@_register(types.ToolName.RESOLVE_DRIVER)
def _bind_driver(params, env):
    return types.ResolveDriverInput(
        name_or_abbreviation=params["name"],
        session_key=env["session"].session_key,
    )


@_register(types.ToolName.FIND_PIT_STOPS)
def _bind_pit_stops(params, env):
    return types.FindPitStopsInput(
        session_key=env["session"].session_key,
        driver_number=env["driver"].driver_number,
    )


@_register(types.ToolName.GET_LAP_TELEMETRY_ARTIFACTS)
def _bind_artifacts(params, env):
    laps = _pit_laps(env["pits"].pit_stops[0], env["routed"].laps_window)
    return types.GetLapTelemetryArtifactsInput(
        session_key=env["session"].session_key,
        driver_number=env["driver"].driver_number,
        lap_numbers=laps,
    )


@_register(types.ToolName.COMPUTE_SPEED_WINDOW)
def _bind_window(params, env):
    stop = env["pits"].pit_stops[0]
    laps = _pit_laps(stop, params["laps_window"])
    before = tuple(lap for lap in laps if lap < stop.pit_in_lap)
    after = tuple(lap for lap in laps if lap > stop.pit_out_lap)
    return types.ComputeSpeedWindowInput(
        session_key=env["session"].session_key,
        driver_number=env["driver"].driver_number,
        before_laps=before,
        after_laps=after,
        metric=types.SpeedMetric(params["metric"]),
    )


@_register(types.ToolName.VERIFY_EVIDENCE)
def _bind_verify(params, env):
    required_laps: tuple[int, ...] = ()
    routed = env["routed"]
    if (
        "pits" in env
        and env["pits"].pit_stops
        and routed.intent
        in (
            types.Intent.PIT_STOP_SPEED_DELTA,
            types.Intent.RACE_CONTROL_EVENTS,
        )
    ):
        required_laps = _pit_laps(env["pits"].pit_stops[0], routed.laps_window)
    return types.VerifyEvidenceInput(
        session_key=env["session"].session_key,
        driver_number=env["driver"].driver_number,
        required_laps=required_laps,
    )


@_register(types.ToolName.INSPECT_LAP_EVENTS)
def _bind_lap_events(params, env):
    return types.InspectLapEventsInput(
        session_key=env["session"].session_key,
        driver_number=env["driver"].driver_number,
        target_lap=params.get("target_lap"),
        window_laps=params.get("laps_window", 5),
    )


@_register(types.ToolName.STINT_DEGRADATION_SCANNER)
def _bind_stints(params, env):
    return types.StintDegradationInput(
        session_key=env["session"].session_key,
        driver_number=env["driver"].driver_number,
    )


@_register(types.ToolName.TELEMETRY_INSPECTOR)
def _bind_telemetry(params, env):
    return types.TelemetryInspectorInput(
        session_key=env["session"].session_key,
        driver_number=env["driver"].driver_number,
        lap_numbers=params.get("lap_numbers") or (),
        compare_driver_number=env["driver_cmp"].driver_number
        if "driver_cmp" in env
        else None,
        compare_lap_numbers=params.get("compare_lap_numbers") or (),
    )


@_register(types.ToolName.DRIVER_STYLE_COMPARE)
def _bind_driver_style(params, env):
    return types.DriverStyleCompareInput(
        driver_name=params.get("driver_name") or "",
        compare_driver_name=params.get("compare_driver_name"),
        year=int(params.get("year") or 0),
    )


@_register(types.ToolName.GAP_POSITION_SNAPSHOT)
def _bind_gap(params, env):
    target_lap = params.get("target_lap") or env["routed"].target_lap
    if target_lap is None and env.get("pits") and env["pits"].pit_stops:
        target_lap = env["pits"].pit_stops[0].pit_in_lap
    return types.GapPositionInput(
        session_key=env["session"].session_key,
        driver_number=env["driver"].driver_number,
        target_lap=target_lap,
    )


@_register(types.ToolName.FETCH_RACE_CONTROL_WINDOW)
def _bind_race_control(params, env):

    pits = env.get("pits")
    stop = pits.pit_stops[0] if pits and pits.pit_stops else None
    target = env["routed"].target_lap
    from_lap = params.get("from_lap") or (target or (stop.pit_in_lap if stop else None))
    to_lap = params.get("to_lap")
    if to_lap is None and stop:
        to_lap = stop.pit_out_lap

    return types.RaceControlWindowInput(
        session_key=env["session"].session_key,
        driver_number=env["driver"].driver_number,
        from_lap=from_lap,
        to_lap=to_lap,
    )


@_register(types.ToolName.FETCH_TRACK_STATUS)
def _bind_track_status(params, env):
    return types.TrackStatusInput(
        session_key=env["session"].session_key,
        from_lap=params.get("from_lap"),
        to_lap=params.get("to_lap"),
    )


@_register(types.ToolName.FETCH_SESSION_RESULTS)
def _bind_session_results(params, env):
    # An explicit driver_number in the node params wins; otherwise fall back to
    # a driver resolved earlier in the plan (same convention as the other binders).
    driver_number = params.get("driver_number")
    if driver_number is None:
        driver_number = getattr(env.get("driver"), "driver_number", None)
    return types.SessionResultsInput(
        session_key=env["session"].session_key,
        driver_number=driver_number,
    )


@_register(types.ToolName.FETCH_RADIO_MESSAGES)
def _bind_radio(params, env):
    pits = env.get("pits")
    stop = pits.pit_stops[0] if pits and pits.pit_stops else None
    target = env["routed"].target_lap
    from_lap = params.get("from_lap") or (target or (stop.pit_in_lap if stop else None))
    to_lap = params.get("to_lap")
    if to_lap is None and stop:
        to_lap = stop.pit_out_lap

    return types.RadioWindowInput(
        session_key=env["session"].session_key,
        driver_number=env["driver"].driver_number,
        from_lap=from_lap,
        to_lap=to_lap,
    )


@_register(types.ToolName.FETCH_WEATHER_WINDOW)
def _bind_weather(params, env):
    pits = env.get("pits")
    stop = pits.pit_stops[0] if pits and pits.pit_stops else None
    target = env["routed"].target_lap
    from_lap = params.get("from_lap") or (target or (stop.pit_in_lap if stop else None))
    to_lap = params.get("to_lap")
    if to_lap is None and stop:
        to_lap = stop.pit_out_lap

    return types.WeatherWindowInput(
        session_key=env["session"].session_key,
        from_lap=from_lap,
        to_lap=to_lap,
    )


def _session_type_param(value: Any, routed: types.RoutedQuestion | None) -> Any:
    if isinstance(value, types.SessionType):
        return value
    if isinstance(value, str):
        try:
            return types.SessionType(value)
        except ValueError:
            pass
    return routed.session_type if routed is not None else None


@_register(types.ToolName.LIST_AVAILABLE_SESSIONS)
def _bind_list_sessions(params, env):
    routed = env.get("routed")
    return types.ListAvailableSessionsInput(
        year=params.get("year", routed.year if routed else None),
        gp_name=params.get("gp_name", routed.gp_name if routed else None),
        country=params.get("country"),
        session_type=_session_type_param(params.get("session_type"), routed),
        limit=int(params.get("limit", 50)),
    )


@_register(types.ToolName.SEARCH_SESSIONS)
def _bind_search_sessions(params, env):
    routed = env.get("routed")
    query = params.get("query") or (routed.gp_name if routed else "") or ""
    return types.SearchSessionsInput(
        query=query,
        year=params.get("year", routed.year if routed else None),
        session_type=_session_type_param(params.get("session_type"), routed),
        limit=int(params.get("limit", 20)),
    )


@_register(types.ToolName.DESCRIBE_SESSION_COVERAGE)
def _bind_coverage(params, env):
    session_key = params.get("session_key")
    if session_key is None and "session" in env:
        session_key = env["session"].session_key
    if session_key is None:
        catalog = env.get("catalog")
        if catalog is not None and getattr(catalog, "sessions", ()):
            session_key = catalog.sessions[0].session_key
    if session_key is None:
        raise types.DataError("describe_session_coverage requires a resolved session")
    return types.DescribeSessionCoverageInput(session_key=int(session_key))


@_register(types.ToolName.ESTIMATE_PIT_LOSS)
def _bind_estimate_pit_loss(params, env):
    session_key = params.get("session_key")
    if session_key is None:
        session_key = env["session"].session_key
    driver_number = params.get("driver_number")
    if driver_number is None and "driver" in env:
        driver_number = env["driver"].driver_number
    return types.EstimatePitLossInput(
        session_key=int(session_key), driver_number=driver_number
    )


@_register(types.ToolName.COMPARE_STRATEGY_SCENARIOS)
def _bind_strategy(params, env):
    routed = env.get("routed")
    current_lap = params.get("current_lap")
    if current_lap is None and routed is not None:
        current_lap = routed.target_lap
    return types.CompareStrategyScenariosInput(
        session_key=params.get("session_key") or env["session"].session_key,
        driver_number=params.get("driver_number") or env["driver"].driver_number,
        current_lap=current_lap,
    )


@_register(types.ToolName.SEARCH_STRATEGY_SOURCES)
def _bind_search_strategy_sources(params, env):
    routed = env.get("routed")
    raw_types = params.get("source_types") or params.get("source_type") or ()
    if isinstance(raw_types, str):
        raw_types = (raw_types,)
    session_key = params.get("session_key")
    if session_key is None and "session" in env:
        session_key = env["session"].session_key
    driver_number = params.get("driver_number")
    if driver_number is None and "driver" in env:
        driver_number = env["driver"].driver_number
    year = params.get("year")
    if year is None and routed is not None:
        year = routed.year
    query = params.get("query") or (routed.question if routed is not None else "")
    return types.SearchStrategySourcesInput(
        query=query,
        source_types=tuple(str(s) for s in raw_types),
        year=year,
        session_key=session_key,
        driver_number=driver_number,
        limit=int(params.get("limit", 6)),
    )


def _pit_laps(stop: types.PitStop, laps_window: int) -> tuple[int, ...]:
    """Clean laps around a pitstop (pit in / pit out laps excluded)"""
    before = tuple(range(stop.pit_in_lap - laps_window, stop.pit_in_lap))
    after = tuple(range(stop.pit_out_lap + 1, stop.pit_out_lap + 1 + laps_window))
    return tuple(sorted(set(before) | set(after)))


def _session_node(routed: types.RoutedQuestion) -> types.DAGNode:
    return types.DAGNode(
        id="session",
        tool_name=types.ToolName.RESOLVE_SESSION,
        label="Resolve Session",
        description=f"Find the {routed.year} {routed.gp_name} race session",
        input_params={"year": routed.year, "gp_name": routed.gp_name},
    )


def _driver_node(routed: types.RoutedQuestion) -> types.DAGNode:
    return types.DAGNode(
        id="driver",
        tool_name=types.ToolName.RESOLVE_DRIVER,
        label="Resolve Driver",
        description=f"Resolve Driver {routed.driver_name}",
        depends_on=("session",),
        input_params={"name": routed.driver_name},
    )


def _verify_node(depends_on: tuple[str, ...]) -> types.DAGNode:
    return types.DAGNode(
        id="verify",
        tool_name=types.ToolName.VERIFY_EVIDENCE,
        label="Verify Evidence",
        description="Confirm the facts we are about to report exist",
        depends_on=depends_on,
    )


def _build_template_dag(routed: types.RoutedQuestion) -> types.ExecutionDAG:
    """Turn a routed question into a concrete execution graph"""

    if routed.intent is types.Intent.DRIVER_STYLE_COMPARISON:
        if not routed.driver_name:
            raise types.PlanValidationError(
                "driver_style_comparison requires a driver_name"
            )
        nodes = [
            types.DAGNode(
                id="style",
                tool_name=types.ToolName.DRIVER_STYLE_COMPARE,
                label="Compare Driving Styles",
                description="PCA/K-Means archetypes + trait percentiles vs the field",
                depends_on=(),
                input_params={
                    "driver_name": routed.driver_name,
                    "compare_driver_name": routed.compare_driver_name,
                    "year": routed.year or 0,
                },
            )
        ]
        return types.ExecutionDAG(nodes=tuple(nodes), edges=tuple())

    if routed.intent is types.Intent.DATA_AVAILABILITY:
        if routed.gp_name:
            catalog_node = types.DAGNode(
                id="catalog",
                tool_name=types.ToolName.SEARCH_SESSIONS,
                label="Search Sessions",
                description="Find stored sessions matching the requested race",
                depends_on=(),
                input_params={"query": routed.gp_name, "year": routed.year},
            )
        else:
            catalog_node = types.DAGNode(
                id="catalog",
                tool_name=types.ToolName.LIST_AVAILABLE_SESSIONS,
                label="List Available Sessions",
                description="List the sessions we actually hold in Postgres",
                depends_on=(),
                input_params={"year": routed.year},
            )
        nodes = [
            catalog_node,
            types.DAGNode(
                id="coverage",
                tool_name=types.ToolName.DESCRIBE_SESSION_COVERAGE,
                label="Describe Session Coverage",
                description="Report exactly which datasets exist for the matched session",
                depends_on=("catalog",),
            ),
        ]
        return types.ExecutionDAG(nodes=tuple(nodes), edges=tuple())

    if routed.intent is types.Intent.STRATEGY_SOURCES:
        source_node = types.DAGNode(
            id="sources",
            tool_name=types.ToolName.SEARCH_STRATEGY_SOURCES,
            label="Search Strategy Sources",
            description="Retrieve approved regulation/briefing/radio chunks",
            depends_on=("session",) if (routed.gp_name and routed.year) else (),
            input_params={"query": routed.question},
        )
        if routed.gp_name and routed.year:
            nodes = [_session_node(routed), source_node]
        else:
            nodes = [source_node]
        return types.ExecutionDAG(nodes=tuple(nodes), edges=tuple())

    nodes: list[types.DAGNode] = [_session_node(routed), _driver_node(routed)]

    if routed.intent is types.Intent.PIT_STOP_SPEED_DELTA:
        nodes.append(
            types.DAGNode(
                id="pits",
                tool_name=types.ToolName.FIND_PIT_STOPS,
                label="Find Pit stops",
                description="Locate the driver's Pitstop",
                depends_on=(
                    "session",
                    "driver",
                ),
            )
        )
        nodes.append(
            types.DAGNode(
                id="artifacts",
                tool_name=types.ToolName.GET_LAP_TELEMETRY_ARTIFACTS,
                label="Fetch lap telemetry",
                description="Check weather telemetry artifacts exist around the stop",
                depends_on=("pits",),
            )
        )
        nodes.append(
            types.DAGNode(
                id="window",
                tool_name=types.ToolName.COMPUTE_SPEED_WINDOW,
                label="Compute Speed Window",
                description="Average Speed before and after the pitstop",
                depends_on=("pits",),
                input_params={
                    "laps_window": routed.laps_window,
                    "metric": types.SpeedMetric.DISTANCE_WEIGHTED_TELEMETRY.value,
                },
            )
        )
        nodes.append(_verify_node(depends_on=("artifacts", "window")))

    elif routed.intent is types.Intent.LAP_EVENT_INVESTIGATION:
        nodes.append(
            types.DAGNode(
                id="laps",
                tool_name=types.ToolName.INSPECT_LAP_EVENTS,
                label="Inspect Lap Events",
                description="Flag off-pace laps with a reason",
                depends_on=(
                    "session",
                    "driver",
                ),
                input_params={
                    "target_lap": routed.target_lap,
                    "laps_window": routed.laps_window,
                },
            )
        )
        nodes.append(_verify_node(depends_on=("session", "driver")))

    elif routed.intent is types.Intent.TYRE_DEGRADATION_ANALYSIS:
        nodes.append(
            types.DAGNode(
                id="stints",
                tool_name=types.ToolName.STINT_DEGRADATION_SCANNER,
                label="Scan stint degradation",
                description="Fit degradation slopes per tyre stint",
                depends_on=("session", "driver"),
            )
        )
        nodes.append(_verify_node(depends_on=("session", "driver")))

    elif routed.intent is types.Intent.POSITION_GAP_TRACKING:
        nodes.append(
            types.DAGNode(
                id="pits",
                tool_name=types.ToolName.FIND_PIT_STOPS,
                label="Find Pit Stops",
                description="Locate the driver's pitstop laps",
                depends_on=("session", "driver"),
            )
        )
        nodes.append(
            types.DAGNode(
                id="gap",
                tool_name=types.ToolName.GAP_POSITION_SNAPSHOT,
                label="Gap and. Position Snapshot",
                description="Commulative-time ranking at one lap",
                depends_on=("pits",),
                input_params={"target_lap": routed.target_lap},
            )
        )
        nodes.append(_verify_node(depends_on=("pits", "gap")))

    elif routed.intent is types.Intent.RACE_CONTROL_EVENTS:
        nodes.append(
            types.DAGNode(
                id="pits",
                tool_name=types.ToolName.FIND_PIT_STOPS,
                label="Find Pit Stops",
                description="Locate the driver's pitstop laps to bound the race-control window",
                depends_on=("session", "driver"),
            )
        )
        nodes.append(
            types.DAGNode(
                id="rc",
                tool_name=types.ToolName.FETCH_RACE_CONTROL_WINDOW,
                label="Race Control Window",
                description="Scan flag/SC/VSC events around the pit window",
                depends_on=("pits",),
            )
        )
        nodes.append(_verify_node(depends_on=("pits", "rc")))

    elif routed.intent is types.Intent.TEAM_RADIO:
        nodes.append(
            types.DAGNode(
                id="pits",
                tool_name=types.ToolName.FIND_PIT_STOPS,
                label="Find Pit Stops",
                description="Locate the driver's pitstop laps to bound the radio window",
                depends_on=("session", "driver"),
            )
        )
        nodes.append(
            types.DAGNode(
                id="radio",
                tool_name=types.ToolName.FETCH_RADIO_MESSAGES,
                label="Team Radio Clips",
                description="Fetch team radio clips around the pit window",
                depends_on=("pits",),
            )
        )
        nodes.append(_verify_node(depends_on=("pits", "radio")))

    elif routed.intent is types.Intent.WEATHER_CORRELATION:
        nodes.append(
            types.DAGNode(
                id="pits",
                tool_name=types.ToolName.FIND_PIT_STOPS,
                label="Find Pit Stops",
                description="Locate the driver's pitstop laps to bound the weather window",
                depends_on=("session", "driver"),
            )
        )
        nodes.append(
            types.DAGNode(
                id="weather",
                tool_name=types.ToolName.FETCH_WEATHER_WINDOW,
                label="Weather Window",
                description="Fetch weather events around the pit window",
                depends_on=("pits",),
            )
        )
        nodes.append(_verify_node(depends_on=("pits", "weather")))

    elif routed.intent is types.Intent.QUALIFYING_LAP_ANALYSIS:
        nodes.append(
            types.DAGNode(
                id="qlaps",
                tool_name=types.ToolName.INSPECT_LAP_EVENTS,
                label="Qualifying Lap Events",
                description="Flag qualifying laps and sectors for the driver",
                depends_on=("session", "driver"),
                input_params={
                    "target_lap": routed.target_lap,
                    "laps_window": routed.laps_window,
                },
            )
        )
        nodes.append(
            types.DAGNode(
                id="telemetry",
                tool_name=types.ToolName.TELEMETRY_INSPECTOR,
                label="Inspect Telemetry",
                description="Lap trace for the driver's best qualifying lap",
                depends_on=("session", "driver"),
                input_params={
                    "lap_numbers": (routed.target_lap,) if routed.target_lap else (),
                },
            )
        )
        nodes.append(_verify_node(depends_on=("qlaps", "telemetry")))

    elif routed.intent is types.Intent.STRATEGY_ANALYSIS:
        nodes.append(
            types.DAGNode(
                id="strategy",
                tool_name=types.ToolName.COMPARE_STRATEGY_SCENARIOS,
                label="Compare Strategy Scenarios",
                description="Measured pit loss + degradation against stay-out baseline",
                depends_on=("session", "driver"),
                input_params={"current_lap": routed.target_lap},
            )
        )
        nodes.append(_verify_node(depends_on=("session", "driver")))

    else:  # The telemetry comparison
        nodes.append(
            types.DAGNode(
                id="driver_cmp",
                tool_name=types.ToolName.RESOLVE_DRIVER,
                label="Resolve Compare Driver",
                description=f"Resolve {routed.compare_driver_name}",
                depends_on=("session",),
                input_params={"name": routed.compare_driver_name},
            )
        )

        nodes.append(
            types.DAGNode(
                id="telemetry",
                tool_name=types.ToolName.TELEMETRY_INSPECTOR,
                label="Compare telemetry",
                description="Resampled lap traces for both drivers",
                depends_on=("session", "driver", "driver_cmp"),
                input_params={
                    "lap_numbers": (routed.target_lap,) if routed.target_lap else (),
                    "compare_lap_numbers": (routed.target_lap,)
                    if routed.target_lap
                    else (),
                },
            )
        )
        nodes.append(_verify_node(depends_on=("session", "driver", "driver_cmp")))

    if len(nodes) > MAX_DAG_NODES:
        raise types.DataError(
            f"plan exceeds MAX_DAG_NODES={MAX_DAG_NODES}: got {len(nodes)} nodes"
        )

    edges = tuple(
        types.DAGEdge(source=dep, target=node.id)
        for node in nodes
        for dep in node.depends_on
    )

    return types.ExecutionDAG(nodes=tuple(nodes), edges=edges)


def build_dag(routed: types.RoutedQuestion) -> types.ExecutionDAG:
    """Build the tool-plan DAG using the deterministic template planner.

    T1.2's agentic loop does NOT live here -- it owns execution and lives in
    run(), behind settings.agent_planner_mode == "llm". This function always
    returns the hardcoded template DAG, which is the T0.1 golden-eval baseline
    every future planner change is measured against.
    """
    return _build_template_dag(routed)


def topo_sort(dag: types.ExecutionDAG) -> tuple[str, ...]:
    """The node id's where the every node comes afterwards after its dependencies
    Kahn's algorithm: repeatedly emit the nodes whose dependencies are already emitted."""
    node_map = {n.id: n for n in dag.nodes}
    if len(node_map) != len(dag.nodes):
        raise types.DataError("duplicate node ids in the execution DAG")

    order: list[str] = []
    emitted: set[str] = set()
    while len(order) < len(dag.nodes):
        progressed = False
        for node in dag.nodes:
            if node.id in emitted:
                continue
            if all(dep in emitted for dep in node.depends_on):
                order.append(node.id)
                emitted.add(node.id)
                progressed = True
        if not progressed:
            raise types.DataError(
                "the execution DAG has a dependency cycle; every query graph must be acyclic"
            )

    return tuple(order)


_RETRYABLE_DELAYS_MS: tuple[int, int, int] = (200, 400, 800)


def _retry_transient(fn: Callable[[], Any]) -> Any:
    """Run fn, retrying ONLY on types.RetryableError with capped backoff.

    NotFoundError / DataError / everything else propagates immediately so
    the fail-closed semantics of run_node are unchanged. Hard-bounded at
    3 attempts -- the loop can never run away."""
    attempt = 0
    while True:
        try:
            return fn()
        except types.RetryableError:
            attempt += 1
            if attempt >= len(_RETRYABLE_DELAYS_MS):
                raise
            time.sleep(_RETRYABLE_DELAYS_MS[attempt - 1] / 1000)


def _execute_dag(
    dag: types.ExecutionDAG,
    routed: types.RoutedQuestion,
    progress: ProgressCallback | None = None,
) -> tuple[tuple[types.ToolCallRecord, ...], dict[str, Any], set[str]]:
    """Run any DAG. Independent branches run in parallel.
    Returns (trace, outputs, failed_ids). A node whose dependency failed is never executed"""

    node_map = {n.id: n for n in dag.nodes}
    order = topo_sort(dag)
    position = {nid: i for i, nid in enumerate(order)}

    env: dict[str, Any] = {"routed": routed}
    trace: list[types.ToolCallRecord] = []
    failed_ids: set[str] = set()

    def run_node(
        node: types.DAGNode,
    ) -> tuple[types.ToolCallRecord, Any | None, str | None]:
        _emit(
            progress,
            type="node_start",
            node_id=node.id,
            tool_name=node.tool_name.value,
            label=node.label,
        )
        start = time.perf_counter()
        try:
            inp = _bind(node.tool_name, node.input_params, env)
            result = _retry_transient(lambda: _TOOLS[node.tool_name](inp))
            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            call = types.ToolCallRecord(
                tool_name=node.tool_name,
                status="ok",
                input_summary=str(inp),
                output_summary=str(result)[:400],
                duration_ms=duration_ms,
                node_id=node.id,
            )
            _emit(
                progress,
                type="node_complete",
                node_id=node.id,
                status="ok",
                duration_ms=duration_ms,
                label=node.label,
                summary=str(result)[:200],
            )
            return call, result, None

        except Exception as exc:
            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            call = types.ToolCallRecord(
                tool_name=node.tool_name,
                status="error",
                input_summary=str(env.get("routed")),
                error=str(exc),
                duration_ms=duration_ms,
                node_id=node.id,
            )
            _emit(
                progress,
                type="node_error",
                node_id=node.id,
                status="error",
                duration_ms=duration_ms,
                label=node.label,
            )
            return call, None, str(exc)

    with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as pool:
        pending = set(node_map)
        in_flight: dict[str, tuple[Any, types.DAGNode]] = {}

        while pending or in_flight:
            # 1. submit every node whose dependencies are all done
            for nid in sorted(pending):
                node = node_map[nid]
                if all(dep in env for dep in node.depends_on):
                    pending.discard(nid)
                    in_flight[nid] = (pool.submit(run_node, node), node)

            # 2. if nothing can run, the rest are blocked by failed deps → fail-closed
            if not in_flight:
                for nid in sorted(pending):
                    node = node_map[nid]
                    blocked_by = [d for d in node.depends_on if d in failed_ids]
                    call = types.ToolCallRecord(
                        tool_name=node.tool_name,
                        status="error",
                        input_summary="",
                        error=f"dependency failed: {', '.join(blocked_by)}",
                        node_id=node.id,
                    )
                    trace.append(call)
                    failed_ids.add(nid)
                pending.clear()
                break

            # 3. wait for at least one future and harvest the completions
            futures = [f for f, _ in in_flight.values()]
            completed, _ = wait(futures, return_when=FIRST_COMPLETED)
            for nid, (fut, node) in list(in_flight.items()):
                if fut in completed:
                    del in_flight[nid]
                    call, result, error = fut.result()
                    trace.append(call)
                    if error is not None:
                        failed_ids.add(nid)
                    else:
                        env[nid] = result

    # 4. determinism: report the trace in graph order, not completion order
    trace.sort(key=lambda c: position[c.node_id])
    return tuple(trace), env, failed_ids


def _compose(
    question: str,
    routed: types.RoutedQuestion,
    outputs: dict[str, Any],
    failed_ids: set[str],
    trace: tuple[types.ToolCallRecord, ...],
    progress: ProgressCallback | None = None,
) -> types.AgentAnswer:
    """Build the final structured answer from the DAG's node outputs."""

    _emit(
        progress,
        type="stage",
        stage="compose",
        status="running",
        label="Composing evidence-backed answer",
    )
    refusals: list[str] = []
    if failed_ids:
        refusals.append("one or more evidence steps failed; the answer was not trusted")
    verify = outputs.get("verify")
    if verify is not None and not verify.passed and verify.refusal_reason:
        refusals.append(verify.refusal_reason)

    pit_stop = None
    if outputs.get("pits") and outputs["pits"].pit_stops:
        pit_stop = outputs["pits"].pit_stops[0]

    if refusals:
        answer = types.AgentAnswer(
            question=question,
            intent=routed.intent,
            answer=(
                "I could not fully answer that question. "
                + " ".join(refusals)
                + " No numbers were invented from missing data."
            ),
            refusals=tuple(refusals),
            session=outputs.get("session"),
            driver=outputs.get("driver"),
            pit_stop=pit_stop,
            speed_window=None,
            evidence=verify,
            sources=outputs.get("sources"),
            trace=trace,
        )
        _emit(
            progress,
            type="stage",
            stage="compose",
            status="ok",
            label="Prepared refusal with available evidence",
        )
        return answer

    session = outputs["session"]
    driver = outputs["driver"]

    fallback_lines: list[str] = []
    if routed.intent is types.Intent.PIT_STOP_SPEED_DELTA:
        stop = outputs["pits"].pit_stops[0]
        window = outputs["window"]
        fallback_lines.extend(
            [
                f"{driver.full_name} made a pit stop across lap {stop.pit_in_lap} "
                f"into lap {stop.pit_out_lap}.",
                "",
                f"Using telemetry sample average speed, the {routed.laps_window}-lap pre-stop "
                f"window averaged {window.before_avg_speed_kmh} km/h, while the "
                f"{routed.laps_window}-lap post-stop window averaged {window.after_avg_speed_kmh} km/h. "
                f"That is a {window.delta_kmh:+.1f} km/h change.",
            ]
        )
        if stop.compound_before and stop.compound_after:
            fallback_lines.append(
                f"He switched from {stop.compound_before} to {stop.compound_after} tyres."
            )

    elif routed.intent is types.Intent.LAP_EVENT_INVESTIGATION:
        laps = outputs["laps"]
        fallback_lines.append(
            f"{driver.full_name} had {laps.anomaly_count} off-pace lap(s) in that session; median clean pace was {laps.median_pace_ms} ms."
        )

    elif routed.intent is types.Intent.TYRE_DEGRADATION_ANALYSIS:
        stints = outputs["stints"]
        fallback_lines.append(
            f"Found {len(stints.stints)} stint(s); the worst degradation stint was stint {stints.worst_degradation_stint}."
        )

    elif routed.intent is types.Intent.POSITION_GAP_TRACKING:
        gap = outputs["gap"]
        pos = gap.position if gap.position is not None else "?"
        fallback_lines.append(
            f"At lap {gap.lap_number}, {driver.full_name} was P{pos}."
        )
        if gap.gap_to_leader_ms is not None:
            fallback_lines.append(
                f"On cumulative race time he was {gap.gap_to_leader_ms} ms behind the leader (#{gap.leader_number})."
            )
        if gap.car_ahead_number is not None:
            fallback_lines.append(
                f"The car ahead (#{gap.car_ahead_number}) was {gap.car_ahead_gap_ms} ms ahead; the car behind (#{gap.car_behind_number}) trailed by {gap.car_behind_gap_ms} ms."
            )

    elif routed.intent is types.Intent.RACE_CONTROL_EVENTS:
        rc = outputs["rc"]
        if rc.events:
            flags = ", ".join(
                sorted({f"{e.flag or e.category}@{e.lap_number}" for e in rc.events})
            )
            fallback_lines.append(
                f"Between laps {rc.from_lap} and {rc.to_lap}, race control reported: {flags}. Distinct safety-car/VSC periods: {rc.safety_car_periods} "
            )
        else:
            fallback_lines.append(
                f"No race control events found between laps {rc.from_lap} and {rc.to_lap}."
            )

    elif routed.intent is types.Intent.TEAM_RADIO:
        radio = outputs["radio"]
        if radio.messages:
            clips = len(radio.messages)
            first_date = radio.messages[0].date
            fallback_lines.append(
                f"Found {clips} team radio clip(s) for {driver.full_name} (first at {first_date})."
            )
            fallback_lines.append(
                f"The recordings are attached below — from_lap {radio.from_lap} to lap {radio.to_lap}."
            )
        else:
            fallback_lines.append(
                f"No team radio clips found for {driver.full_name} between laps {radio.from_lap} and {radio.to_lap}."
            )

    elif routed.intent is types.Intent.WEATHER_CORRELATION:
        weather = outputs["weather"]
        if weather.samples:
            fallback_lines.append(
                f"Across {weather.total_laps} lap(s) in the window, rain was present on {weather.rainfall_laps} "
                f"(~{weather.rain_share_pct}% of laps)."
            )
            if weather.track_temp_delta_c is not None:
                fallback_lines.append(
                    f"Track temperature swung {weather.track_temp_delta_c:+.1f}\u00b0C across the window."
                )
        else:
            fallback_lines.append(
                f"No weather events found between laps {weather.from_lap} and {weather.to_lap}."
            )

    elif routed.intent is types.Intent.QUALIFYING_LAP_ANALYSIS:
        laps = outputs["qlaps"]
        fallback_lines.append(
            f"{driver.full_name} had {laps.anomaly_count} off-pace qualifying lap(s); median clean pace was {laps.median_pace_ms} ms."
        )

    elif routed.intent is types.Intent.DRIVER_STYLE_COMPARISON:
        style = outputs["style"]
        fallback_lines.append(style.summary)

    elif routed.intent is types.Intent.STRATEGY_ANALYSIS:
        strat = outputs["strategy"]
        fallback_lines.append(
            f"Deterministic strategy comparison at lap {strat.current_lap} "
            f"({strat.remaining_laps if strat.remaining_laps is not None else '?'} laps remaining)."
        )
        for scenario in strat.scenarios:
            delta = (
                f"{scenario.projected_delta_ms:+d} ms"
                if scenario.projected_delta_ms is not None
                else "not costed"
            )
            fallback_lines.append(f"- {scenario.label}: {delta} vs staying out.")
        if strat.assumptions:
            fallback_lines.append("Assumptions: " + "; ".join(strat.assumptions))
        if strat.notes:
            fallback_lines.append("Notes: " + "; ".join(strat.notes))

    elif routed.intent is types.Intent.STRATEGY_SOURCES:
        sources = outputs.get("sources")
        if sources is not None and sources.hits:
            fallback_lines.append(
                f"I found {len(sources.hits)} approved source(s) for that question:"
            )
            for hit in sources.hits:
                citation = hit.title
                if hit.page_number is not None:
                    citation += f", p.{hit.page_number}"
                if hit.timestamp_from_ms is not None:
                    citation += f", t={hit.timestamp_from_ms}ms"
                fallback_lines.append(f"- {citation}: {hit.excerpt}")
        elif sources is not None and sources.degraded:
            fallback_lines.append(
                "I could not reach the document store, so no sources were retrieved."
            )
        else:
            fallback_lines.append(
                "I did not find an approved source covering that question."
            )

    else:
        telemetry = outputs["telemetry"]
        fallback_lines.append(
            f"Compared {len(telemetry.traces)} telemetry trace(s); full-throttle share was {telemetry.full_throttle_pct}%."
        )

    fallback_text = "\n".join(fallback_lines)

    evidence_payload = {
        nid: asdict(val)
        for nid, val in outputs.items()
        if hasattr(val, "__dataclass_fields__")
    }
    compose_cost = 0.0
    try:
        answer_text, compose_cost = llm.compose_answer(
            question,
            evidence_payload,
            intent=routed.intent,
            complexity=routed.complexity,
            requires_compute=routed.requires_compute,
            intent_category=routed.intent_category,
        )
    except types.LLMError:
        answer_text = fallback_text

    answer = types.AgentAnswer(
        question=question,
        intent=routed.intent,
        answer=answer_text,
        session=session,
        driver=driver,
        pit_stop=pit_stop,
        speed_window=outputs.get("window"),
        evidence=verify,
        telemetry_overlay=outputs.get("telemetry"),
        stint_degradation=outputs.get("stints"),
        gap_position=outputs.get("gap"),
        race_control=outputs.get("rc"),
        team_radio=outputs.get("radio"),
        weather=outputs.get("weather"),
        strategy=outputs.get("strategy"),
        sources=outputs.get("sources"),
        trace=trace,
        cost_usd=compose_cost,
    )
    _emit(progress, type="stage", stage="compose", status="ok", label="Answer composed")
    return answer


def _run_agentic(
    question: str,
    routed: types.RoutedQuestion,
    progress: ProgressCallback | None = None,
) -> dict[str, Any] | None:
    """Run the T1.2 agentic loop. Returns the evidence env, or None to
    fall back to the deterministic template DAG."""
    try:
        from backend.agent import agentic_loop, planner
    except ImportError:
        return None

    env = agentic_loop.run_agentic_dag(
        question=question,
        routed=routed,
        registry=planner.TOOL_REGISTRY,
    )
    tool_results = {
        k: v
        for k, v in env.items()
        if k != "routed"
        and not (isinstance(v, dict) and v == {"error": v.get("error")})
    }
    if not tool_results:
        return None
    return env


def _compose_agentic(
    question: str,
    routed: types.RoutedQuestion,
    env: dict[str, Any],
    progress: ProgressCallback | None = None,
) -> types.AgentAnswer:
    """Build an AgentAnswer from an agentic-loop evidence env."""
    from backend.agent import tools

    _emit(
        progress,
        type="stage",
        stage="compose",
        status="running",
        label="Verifying agent-collected evidence",
    )

    refusals: list[str] = []
    session = _first_result(env, "session_key", types.ResolvedSession)
    driver = _first_result(env, "driver_number", types.ResolvedDriver)
    if session is None or driver is None:
        refusals.append("no session/driver evidence gathered; answer not trusted")

    verify = None
    if session is not None and driver is not None:
        try:
            verify = tools.verify_evidence(
                types.VerifyEvidenceInput(
                    session_key=session.session_key,
                    driver_number=driver.driver_number,
                    required_laps=(),
                )
            )
            if not verify.passed and verify.refusal_reason:
                refusals.append(verify.refusal_reason)
        except Exception as exc:  # verify itself failed -> refuse, don't crash
            refusals.append(f"evidence verification failed: {exc}")

    _emit(
        progress,
        type="stage",
        stage="compose",
        status="ok",
        label="Agentic answer prepared",
    )

    if refusals:
        return types.AgentAnswer(
            question=question,
            intent=routed.intent,
            answer="I could not fully answer that question. "
            + " ".join(refusals)
            + " No numbers were invented from missing data.",
            refusals=tuple(refusals),
            evidence=verify,
        )

    evidence_payload = {
        nid: asdict(val)
        for nid, val in env.items()
        if nid != "routed" and hasattr(val, "__dataclass_fields__")
    }
    answer_text = ""
    cost = 0.0
    try:
        answer_text, cost = llm.compose_answer(
            question,
            evidence_payload,
            intent=routed.intent,
            complexity=routed.complexity,
        )
    except types.LLMError:
        answer_text = (
            "I have gathered evidence but could not compose a narrative answer."
        )

    return types.AgentAnswer(
        question=question,
        intent=routed.intent,
        answer=answer_text,
        session=session,
        driver=driver,
        evidence=verify,
        cost_usd=cost,
        sources=_first_result(env, "hits", types.SearchStrategySourcesResult),
    )


def _first_result(env: dict[str, Any], attr: str, cls: type) -> Any:
    """Return the first env value that is an instance of cls, else None."""
    for val in env.values():
        if isinstance(val, cls):
            return val
    return None


def _clarify(
    question: str, routed: types.RoutedQuestion, missing: str, text: str, refusal: str
) -> types.AgentAnswer:
    """A structured counter question, No DAG runs here, the pipeline halts to ask the user for one missing enitity.

    The reply carries:
        - clarification -> {missing, question} rendered by the UI
        - routing_context -> entities resolved so far plus the missing spot, the next agent turn merges it
    """
    return types.AgentAnswer(
        question=question,
        intent=routed.intent,
        answer=text,
        refusals=(refusal,),
        clarification={"missing": [missing], "question": text},
        routing_context=agent_context.routed_to_context(routed, missing=[missing]),
    )


def _run_data_availability(
    question: str,
    routed: types.RoutedQuestion,
    progress: ProgressCallback | None = None,
) -> types.AgentAnswer:
    """Answer 'what data do you have?' from the exact catalog.

    This path never touches the vector store: availability is a fact about
    Postgres, so we list/search sessions and report coverage deterministically.
    """
    _emit(
        progress,
        type="stage",
        stage="route",
        status="ok",
        label="Checking the exact data catalog",
    )
    try:
        dag = build_dag(routed)
    except types.DataError as exc:
        return types.AgentAnswer(
            question=question,
            intent=routed.intent,
            answer="I could not build a catalog lookup for that request.",
            refusals=(str(exc),),
            routing_context=agent_context.routed_to_context(routed),
        )

    _emit(
        progress,
        type="dag_init",
        status="ok",
        nodes=[asdict(n) for n in dag.nodes],
        edges=[asdict(e) for e in dag.edges],
        label="Catalog graph prepared",
    )
    trace, outputs, failed_ids = _execute_dag(dag, routed, progress)

    catalog = outputs.get("catalog")
    coverage_result = outputs.get("coverage")
    coverage = coverage_result.coverage if coverage_result is not None else None

    refusals: list[str] = []
    if failed_ids:
        refusals.append("one or more catalog steps failed")

    if catalog is None:
        answer_text = "I could not look up the data catalog right now."
    elif catalog.total == 0:
        where = f" '{routed.gp_name}'" if routed.gp_name else ""
        answer_text = (
            f"I do not hold any stored session{where}"
            + (f" for {routed.year}" if routed.year else "")
            + ". I will not guess; try a different race or year."
        )
    else:
        lines = [f"I hold {catalog.total} matching session(s):"]
        for entry in catalog.sessions[:20]:
            lines.append(
                f"- {entry.year} {entry.gp_name} ({entry.session_type}) "
                f"[session {entry.session_key}]"
            )
        if coverage is not None:
            datasets = (
                ("laps", coverage.has_laps),
                ("telemetry", coverage.has_telemetry),
                ("weather", coverage.has_weather),
                ("race control", coverage.has_race_control),
                ("team radio", coverage.has_radio),
                ("indexed documents", coverage.has_indexed_documents),
            )
            present = [name for name, flag in datasets if flag]
            missing = [name for name, flag in datasets if not flag]
            lines.append(
                f"For session {coverage.session_key}: available data = "
                + (", ".join(present) if present else "none")
                + (f"; not available = {', '.join(missing)}" if missing else "")
                + "."
            )
        answer_text = "\n".join(lines)

    _emit(
        progress,
        type="stage",
        stage="compose",
        status="ok",
        label="Catalog answer ready",
    )
    return types.AgentAnswer(
        question=question,
        intent=routed.intent,
        answer=answer_text,
        catalog=catalog,
        coverage=coverage,
        refusals=tuple(refusals),
        trace=trace,
        routing_context=agent_context.routed_to_context(routed),
    )


def _run_strategy_sources(
    question: str,
    routed: types.RoutedQuestion,
    progress: ProgressCallback | None = None,
) -> types.AgentAnswer:
    """Answer a qualitative question from approved strategy sources.

    Retrieval here is optional: if the vector store is unavailable we degrade
    gracefully instead of failing the request.
    """
    _emit(
        progress,
        type="stage",
        stage="route",
        status="ok",
        label="Searching approved strategy sources",
    )
    try:
        dag = build_dag(routed)
    except types.DataError as exc:
        return types.AgentAnswer(
            question=question,
            intent=routed.intent,
            answer="I could not build a source lookup for that request.",
            refusals=(str(exc),),
            routing_context=agent_context.routed_to_context(routed),
        )

    _emit(
        progress,
        type="dag_init",
        status="ok",
        nodes=[asdict(n) for n in dag.nodes],
        edges=[asdict(e) for e in dag.edges],
        label="Source retrieval graph prepared",
    )
    trace, outputs, failed_ids = _execute_dag(dag, routed, progress)

    sources = outputs.get("sources")
    refusals: list[str] = []
    if failed_ids:
        refusals.append("one or more source retrieval steps failed")

    lines: list[str] = []
    if sources is not None and sources.hits:
        lines.append(
            f"I found {len(sources.hits)} approved source(s) for that question:"
        )
        for hit in sources.hits:
            citation = hit.title
            if hit.page_number is not None:
                citation += f", p.{hit.page_number}"
            if hit.timestamp_from_ms is not None:
                citation += f", t={hit.timestamp_from_ms}ms"
            lines.append(f"- {citation}: {hit.excerpt}")
    elif sources is not None and sources.degraded:
        lines.append(
            "I could not reach the document store right now, so I retrieved no sources."
        )
    else:
        lines.append("I did not find an approved source covering that question.")

    answer_text = "\n".join(lines)
    compose_cost = 0.0
    if sources is not None and sources.hits:
        try:
            composed, compose_cost = llm.compose_answer(
                question,
                {str(hit.chunk_id): asdict(hit) for hit in sources.hits},
                intent=routed.intent,
                complexity=routed.complexity,
            )
            if composed:
                answer_text = composed
        except types.LLMError:
            compose_cost = 0.0

    _emit(
        progress,
        type="stage",
        stage="compose",
        status="ok",
        label="Source answer ready",
    )
    return types.AgentAnswer(
        question=question,
        intent=routed.intent,
        answer=answer_text,
        refusals=tuple(refusals),
        session=outputs.get("session"),
        sources=sources,
        trace=trace,
        cost_usd=compose_cost,
        routing_context=agent_context.routed_to_context(routed),
    )


def run(
    question: str,
    progress: ProgressCallback | None = None,
    context: dict[str, Any] | None = None,
) -> types.AgentAnswer:
    """Public entry point: one question in, one structured answer out"""
    if circuit_breaker.breaker.is_open():
        _emit(
            progress,
            type="stage",
            stage="route",
            status="error",
            label="LLM provider unavailable (circuit open)",
        )
        return types.AgentAnswer(
            question=question,
            intent=types.Intent.UNSUPPORTED,
            answer="The AI service is temporarily unavailable. Try again in a few minutes.",
            refusals=("llm_provider_unavailable",),
        )

    try:
        routed, routing_cost = llm.route_question(question)
    except types.LLMError as exc:
        _emit(
            progress,
            type="stage",
            stage="route",
            status="error",
            label="Question router unavailable",
        )
        return types.AgentAnswer(
            question=question,
            intent=types.Intent.UNSUPPORTED,
            answer=(
                f"I could not process that question because the question router is unavailable {exc}"
            ),
            refusals=("llm_router_unavailable",),
        )
    _emit(progress, type="stage", stage="route", status="ok", label="Question routed")

    if context is not None:
        routed = agent_context.merge_context(context, routed)

    if routed.intent is types.Intent.UNSUPPORTED:
        return types.AgentAnswer(
            question=question,
            intent=routed.intent,
            answer="I cannot answer that yet. v1 supports pit-stop, lap event, tyre degradation, telemetry comparison, position/gap, race control, qualifying, team radio, and weather questions.",
            refusals=("unsupported question",),
            routing_context=agent_context.routed_to_context(routed),
        )

    if routed.intent is types.Intent.DATA_AVAILABILITY:
        return _run_data_availability(question, routed, progress)

    if routed.intent is types.Intent.STRATEGY_SOURCES:
        return _run_strategy_sources(question, routed, progress)

    if not routed.driver_name:
        return _clarify(
            question,
            routed,
            missing="driver",
            text="Which driver should I look at? Name one, e.g. 'Sainz'.",
            refusal="missing_driver",
        )

    if not routed.gp_name or routed.year is None:
        return _clarify(
            question,
            routed,
            missing="race",
            text="Which race should I use? Name the year and Grand Prix, e.g. '2026 Monaco GP'.",
            refusal="missing_race",
        )

    if routed.intent is types.Intent.TELEMETRY_COMPARISON:
        if not routed.target_lap:
            return _clarify(
                question,
                routed,
                missing="target_lap",
                text="Which lap should I compare? Name a lap number, e.g. 'lap 34'.",
                refusal="missing_lap",
            )
        if not routed.compare_driver_name:
            return _clarify(
                question,
                routed,
                missing="compare_driver",
                text="Which second driver should I compare against?",
                refusal="missing_compare_driver",
            )

    env: dict | None = None
    if settings.agent_planner_mode == "llm":
        env = _run_agentic(question, routed, progress)
        if env is not None:
            return _compose_agentic(question, routed, env, progress)

    try:
        dag = build_dag(routed)
    except types.DataError:
        return _clarify(
            question,
            routed,
            missing="race",
            text="That question needs too many steps. Ask me something more focused.",
            refusal="plan_too_large",
        )

    from backend.agent.planner import prune_dag

    dag = prune_dag(dag, routed)

    _emit(
        progress,
        type="dag_init",
        status="ok",
        nodes=[asdict(n) for n in dag.nodes],
        edges=[asdict(e) for e in dag.edges],
        label="Execution graph prepared",
    )

    trace, outputs, failed_ids = _execute_dag(dag, routed, progress)

    if env is None:
        env = outputs

    answer = _compose(question, routed, outputs, failed_ids, trace, progress)

    MAX_RETRIES = 3
    compute_result: str | None = None

    if routed.requires_compute:
        _emit(progress, type="node_start", tool_name="compute_node")
        data_csv = _serialise_evidence_as_csv(env)
        compute_inp = compute_node.ComputeInput(query=question, data_csv=data_csv)

        for attempt in range(MAX_RETRIES):
            out = compute_node.run(compute_inp)
            if not out.success:
                break

            _emit(progress, type="node_start", tool_name="critic_node")
            eval_result = critic_node.run(
                critic_node.CriticInput(user_query=question, compute_result=out.result)
            )

            if eval_result.is_logically_sound:
                compute_result = out.result
                _emit(progress, type="node_done", tool_name="critic_node")
                break

            _emit(
                progress,
                type="self_correcting",
                tool_name="compute_node",
                attempt=attempt + 1,
            )
            compute_inp = compute_node.ComputeInput(
                query=question,
                data_csv=data_csv,
                error_feedback=eval_result.error_feedback or "",
            )

        _emit(progress, type="node_done", tool_name="compute_node")

        _emit(progress, type="node_start", tool_name="synthesizer")
        try:
            synth_inp = synthesis_node.SynthesisInput(
                user_query=question,
                tool_evidence=_serialise_evidence_as_text(env),
                compute_result=compute_result,
            )
            synthesis_chunks: list[str] = []
            for chunk in synthesis_node.stream(synth_inp):
                _emit(progress, type="synthesis_chunk", chunk=chunk)
                synthesis_chunks.append(chunk)
            final_synthesis = "".join(synthesis_chunks).strip()
            if final_synthesis:
                answer = replace(answer, answer=final_synthesis)
        except types.LLMError:
            pass
        except Exception:
            pass
        finally:
            _emit(progress, type="node_done", tool_name="synthesizer")

    return replace(
        answer,
        cost_usd=round(routing_cost + answer.cost_usd, 6),
        routing_context=agent_context.routed_to_context(routed),
    )


def _serialise_evidence_as_csv(env: dict) -> str:
    """Convert numeric telemetry in env into a CSV string for ComputeNode."""
    import csv
    import io

    rows: list[dict] = []
    telemetry = env.get("telemetry")
    if telemetry is not None:
        for trace in getattr(telemetry, "traces", ()):
            samples = trace.samples
            avg_speed = (
                round(sum(s.speed_kmh for s in samples) / len(samples), 1)
                if samples
                else ""
            )
            rows.append(
                {
                    "lap": trace.lap_number,
                    "driver": trace.driver_abbreviation,
                    "avg_speed_kmh": avg_speed,
                }
            )
    laps = env.get("laps")
    if laps is not None:
        for ev in getattr(laps, "events", ()):
            rows.append(
                {
                    "lap": ev.lap_number,
                    "time_ms": ev.lap_time_ms,
                    "compound": ev.compound,
                }
            )
    stints = env.get("stints")
    if stints is not None:
        for stint in getattr(stints, "stints", ()):
            for point in getattr(stint, "laps", ()):
                rows.append(
                    {
                        "lap": point.lap_number,
                        "time_ms": point.lap_time_ms,
                        "tyre_age": point.tyre_age,
                    }
                )
    if not rows:
        return ""
    buf = io.StringIO()
    fieldnames = list(dict.fromkeys(k for row in rows for k in row.keys()))
    writer = csv.DictWriter(buf, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue()


def _serialise_evidence_as_text(env: dict) -> str:
    """Produce a plain-text summary of all tool outputs for SynthesisNode."""
    lines = []
    for key, val in env.items():
        if key in ("routed", "session", "driver") or val is None:
            continue
        if hasattr(val, "__dataclass_fields__"):
            text = str(asdict(val))
        else:
            text = str(val)
        lines.append(f"[{key}]: {text[:800]}")
    return "\n".join(lines)
