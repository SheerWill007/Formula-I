from __future__ import annotations
import dataclasses
import json
import typing as t

from backend.agent import llm, types

MAX_DAG_NODES = 8
MIN_NODE_BUDGET = 3


@dataclasses.dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_fields: dict[str, str]
    required_fields: frozenset[str]
    output_summary: str

    @staticmethod
    def from_dataclass(
        name: str, description: str, input_cls: type, output_summary: str
    ) -> ToolSpec:
        """We use dataclasses.fields() + get_type_hints() to introspect the dataclass.
        This is the "reflection" pattern, instead of manually writing out each tool's schema,
        we derive it from the code."""

        hints = t.get_type_hints(input_cls)
        fields: dict[str, str] = {}
        for f in dataclasses.fields(input_cls):
            hint = hints.get(f.name, f.type)
            fields[f.name] = _type_to_str(hint)

        required = frozenset(
            f.name
            for f in dataclasses.fields(input_cls)
            if f.default is dataclasses.MISSING
            and f.default_factory is dataclasses.MISSING
        )
        return ToolSpec(
            name=name,
            description=description,
            input_fields=fields,
            required_fields=required,
            output_summary=output_summary,
        )


def _type_to_str(ty: t.Any) -> str:
    """Convert a type annotation to a human-readable string for the LLM prompt.

    LESSON: get_type_hints() gives us raw Python type objects. We need strings
    because this goes into a prompt. tuple[int, ...] -> "tuple[int]",
    str | None -> "str | None", etc.
    """
    if ty is type(None):
        return "None"

    if isinstance(ty, str):
        return ty

    origin = getattr(ty, "__origin__", None)

    if origin is t.Union:
        args = [a for a in ty.__args__ if a is not type(None)]
        if len(args) < len(ty.__args__):
            return f"{_type_to_str(args[0])} | None"
        return " | ".join(_type_to_str(a) for a in ty.__args__)

    if origin is not None:
        args_str = ", ".join(_type_to_str(a) for a in ty.__args__)
        name = getattr(ty, "__name__", None) or origin.__name__
        return f"{name}[{args_str}]"

    name = getattr(ty, "__name__", None)
    if name:
        return name
    return str(ty)


TOOL_REGISTRY: dict[str, ToolSpec] = {
    "resolve_session": ToolSpec.from_dataclass(
        "resolve_session",
        "Find a session by year, GP name, and session type.",
        types.ResolveSessionInput,
        "Returns session_key, year, gp_name, session_type.",
    ),
    "resolve_driver": ToolSpec.from_dataclass(
        "resolve_driver",
        "Resolve a driver name/abbreviation/number to session-specific driver info.",
        types.ResolveDriverInput,
        "Returns driver_number, abbreviation, full_name, team_name.",
    ),
    "find_pit_stops": ToolSpec.from_dataclass(
        "find_pit_stops",
        "Detect pit stops for a driver in a session.",
        types.FindPitStopsInput,
        "Returns list of pit stops with lap numbers and tyre compounds.",
    ),
    "get_lap_telemetry_artifacts": ToolSpec.from_dataclass(
        "get_lap_telemetry_artifacts",
        "Check if telemetry artifacts exist for specific laps.",
        types.GetLapTelemetryArtifactsInput,
        "Returns artifact metadata (storage keys, sample counts).",
    ),
    "compute_speed_window": ToolSpec.from_dataclass(
        "compute_speed_window",
        "Compare average speed before and after a pit stop across a lap window.",
        types.ComputeSpeedWindowInput,
        "Returns before/after avg speed and delta in km/h.",
    ),
    "inspect_lap_events": ToolSpec.from_dataclass(
        "inspect_lap_events",
        "Flag off-pace laps with sector times, compounds, and anomaly reasons.",
        types.InspectLapEventsInput,
        "Returns every lap with anomaly flags and median pace.",
    ),
    "stint_degradation_scanner": ToolSpec.from_dataclass(
        "stint_degradation_scanner",
        "Fit degradation slopes per tyre stint, detect cliff laps.",
        types.StintDegradationInput,
        "Returns per-stint degradation metrics and worst stint index.",
    ),
    "telemetry_inspector": ToolSpec.from_dataclass(
        "telemetry_inspector",
        "Full resampled telemetry traces for laps, optionally comparing two drivers.",
        types.TelemetryInspectorInput,
        "Returns speed/throttle/brake traces, speed delta, full-throttle %.",
    ),
    "gap_position_snapshot": ToolSpec.from_dataclass(
        "gap_position_snapshot",
        "Position and cumulative-time gaps at a specific lap.",
        types.GapPositionInput,
        "Returns position, gap to leader, gaps to car ahead/behind.",
    ),
    "fetch_race_control_window": ToolSpec.from_dataclass(
        "fetch_race_control_window",
        "Flag/SC/VSC/yellow/red flag events in a lap window.",
        types.RaceControlWindowInput,
        "Returns race control events and safety car period count.",
    ),
    "fetch_track_status": ToolSpec.from_dataclass(
        "fetch_track_status",
        "Safety car / VSC / red flag / yellow periods with start and end laps, from timing data.",
        types.TrackStatusInput,
        "Returns track-status periods and counts of SC, VSC, red-flag and yellow periods (yellow_periods is null when yellow flags are not tracked for the session).",
    ),
    "fetch_session_results": ToolSpec.from_dataclass(
        "fetch_session_results",
        "Official classification: grid, finishing position, status (DNF reason), points, Q1/Q2/Q3 times.",
        types.SessionResultsInput,
        "Returns per-driver results with positions gained.",
    ),
    "fetch_radio_messages": ToolSpec.from_dataclass(
        "fetch_radio_messages",
        "Team radio clips and transcripts for a driver in a lap window.",
        types.RadioWindowInput,
        "Returns radio clips with dates and transcripts.",
    ),
    "fetch_weather_window": ToolSpec.from_dataclass(
        "fetch_weather_window",
        "Weather events (temp, rain, wind) in a lap window.",
        types.WeatherWindowInput,
        "Returns weather samples with rain stats and temp deltas.",
    ),
    "driver_style_compare": ToolSpec.from_dataclass(
        "driver_style_compare",
        "Compare two drivers' PCA/K-Means driving-style archetypes and trait percentiles for a season.",
        types.DriverStyleCompareInput,
        "Returns archetypes and field-size percentile traits for the primary and secondary driver.",
    ),
    "list_available_sessions": ToolSpec.from_dataclass(
        "list_available_sessions",
        "List stored sessions, optionally filtered by year/GP/country/session type. Use for 'what data do you have' questions.",
        types.ListAvailableSessionsInput,
        "Returns a list of sessions with session_key, year, gp_name, session_type.",
    ),
    "search_sessions": ToolSpec.from_dataclass(
        "search_sessions",
        "Free-text lookup of stored sessions by partial GP/country/session name (SQL match, not semantic).",
        types.SearchSessionsInput,
        "Returns a list of matching sessions with session_key, year, gp_name, session_type.",
    ),
    "describe_session_coverage": ToolSpec.from_dataclass(
        "describe_session_coverage",
        "Report exactly which datasets (laps, telemetry, weather, race control, radio, documents) exist for a session.",
        types.DescribeSessionCoverageInput,
        "Returns per-dataset presence booleans and counts for one session.",
    ),
    "estimate_pit_loss": ToolSpec.from_dataclass(
        "estimate_pit_loss",
        "Measure observed pit loss (in+out lap vs clean laps) grouped by track condition for a session.",
        types.EstimatePitLossInput,
        "Returns per-condition pit-loss estimates (samples, mean/min/max ms).",
    ),
    "compare_strategy_scenarios": ToolSpec.from_dataclass(
        "compare_strategy_scenarios",
        "Compare stay-out vs pit-now scenario costs from measured pit loss and degradation. Deterministic, no probabilities.",
        types.CompareStrategyScenariosInput,
        "Returns named scenarios with projected deltas, assumptions, and risks.",
    ),
    "search_strategy_sources": ToolSpec.from_dataclass(
        "search_strategy_sources",
        "Semantic search over APPROVED strategy documents (regulations, briefings, radio transcripts). Qualitative sources only; never data availability or numeric telemetry.",
        types.SearchStrategySourcesInput,
        "Returns cited source chunks with title, excerpt, page/timestamp and score.",
    ),
    "verify_evidence": ToolSpec.from_dataclass(
        "verify_evidence",
        "Terminal node: verify all required evidence exists before answering.",
        types.VerifyEvidenceInput,
        "Returns passed (bool), checks list, and optional refusal reason.",
    ),
}


@dataclasses.dataclass(frozen=True)
class PlannerDAGNode:
    node_id: str
    tool: str
    params: dict
    depends_on: list[str]
    round: int = 0
    input_param_refs: dict = dataclasses.field(default_factory=dict)


@dataclasses.dataclass(frozen=True)
class PlannerExecutionDAG:
    nodes: list[PlannerDAGNode]

    def edges(self) -> list[tuple[str, str]]:
        return [(dep, n.node_id) for n in self.nodes for dep in n.depends_on]


class PlanValidationError(Exception):
    """Raised whenever a plan fails validation. Caller MUST catch and fall
    back to the template DAG."""

    pass


def topo_sort(dag: PlannerExecutionDAG) -> list[str] | None:
    """Kahn's algorithm. Returns execution order, or None if a cycle exists."""
    indegree: dict[str, int] = {n.node_id: 0 for n in dag.nodes}
    adj: dict[str, list[str]] = {n.node_id: [] for n in dag.nodes}
    for n in dag.nodes:
        for dep in n.depends_on:
            if dep not in indegree:
                continue
            adj[dep].append(n.node_id)
            indegree[n.node_id] += 1
    queue = [nid for nid, d in indegree.items() if d == 0]
    order: list[str] = []
    while queue:
        nid = queue.pop(0)
        order.append(nid)
        for nxt in adj[nid]:
            indegree[nxt] -= 1
            if indegree[nxt] == 0:
                queue.append(nxt)
    return order if len(order) == len(dag.nodes) else None


def validate_plan(
    raw: dict, registry: dict[str, ToolSpec], known_node_ids: t.Iterable[str] = ()
) -> PlannerExecutionDAG:
    """Validate a raw parsed-JSON plan from the LLM.

    Checks: unknown tool, missing required params, dangling dependency,
    cycle, exceeding MAX_DAG_NODES."""

    if "nodes" not in raw or not isinstance(raw["nodes"], list):
        raise PlanValidationError("plan JSON missing 'nodes' list")

    if len(raw["nodes"]) > MAX_DAG_NODES:
        raise PlanValidationError(
            f"plan has {len(raw['nodes'])} nodes, cap is {MAX_DAG_NODES}"
        )

    known_ids = set(known_node_ids)
    nodes: list[PlannerDAGNode] = []

    for raw_node in raw["nodes"]:
        for required_key in ("id", "tool", "params", "depends_on"):
            if required_key not in raw_node:
                raise PlanValidationError(
                    f"node missing required key '{required_key}': {raw_node}"
                )

        tool_name = raw_node["tool"]
        if tool_name not in registry:
            raise PlanValidationError(
                f"unknown tool '{tool_name}' -- not in TOOL_REGISTRY"
            )

        spec = registry[tool_name]
        params = raw_node["params"]
        if not isinstance(params, dict):
            raise PlanValidationError(
                f"node '{raw_node['id']}' params must be an object"
            )

        refs = raw_node.get("input_param_refs", {})
        missing = spec.required_fields - set(params.keys())
        still_missing = missing - set(refs.keys())
        if still_missing:
            raise PlanValidationError(
                f"node '{raw_node['id']}' missing required params for '{tool_name}': {still_missing}"
            )

        unknown_params = set(params.keys()) - set(spec.input_fields.keys())
        if unknown_params:
            raise PlanValidationError(
                f"node '{raw_node['id']}' has params not in '{tool_name}' schema: {unknown_params}"
            )

        depends_on = raw_node["depends_on"]
        if not isinstance(depends_on, list):
            raise PlanValidationError(
                f"node '{raw_node['id']}' depends_on must be a list"
            )

        nodes.append(
            PlannerDAGNode(
                node_id=raw_node["id"],
                tool=tool_name,
                params=params,
                depends_on=depends_on,
                round=raw_node.get("round", 0),
                input_param_refs=refs,
            )
        )

    node_ids = {n.node_id for n in nodes}
    for n in nodes:
        for dep in n.depends_on:
            if dep not in node_ids and dep not in known_ids:
                raise PlanValidationError(
                    f"node '{n.node_id}' depends on '{dep}' which doesn't exist in this plan or in prior-round evidence"
                )

    dag = PlannerExecutionDAG(nodes=nodes)
    if topo_sort(dag) is None:
        raise PlanValidationError("plan contains a dependency cycle")

    return dag


def _to_execution_dag(dag: PlannerExecutionDAG) -> types.ExecutionDAG:
    """Convert a validated planner DAG into the real types.ExecutionDAG that the orchestrator's executor knows how to run."""

    tool_name_map = {tn.value: tn for tn in types.ToolName}

    nodes: list[types.DAGNode] = []
    for n in dag.nodes:
        tool_enum = tool_name_map.get(n.tool)
        if tool_enum is None:
            raise PlanValidationError(
                f"tool '{n.tool}' has no corresponding ToolName enum value"
            )

        spec = TOOL_REGISTRY.get(n.tool)
        label = spec.name.replace("_", " ").title() if spec else n.tool

        nodes.append(
            types.DAGNode(
                id=n.node_id,
                tool_name=tool_enum,
                label=label,
                description=spec.description if spec else "",
                depends_on=tuple(n.depends_on),
                input_params=dict(n.params),
            )
        )

    edges = tuple(
        types.DAGEdge(source=dep, target=node.id)
        for node in nodes
        for dep in node.depends_on
    )

    return types.ExecutionDAG(nodes=tuple(nodes), edges=edges)


_HEAVY_TELEMETRY_TOOLS = frozenset(
    {
        types.ToolName.TELEMETRY_INSPECTOR,
        types.ToolName.STINT_DEGRADATION_SCANNER,
        types.ToolName.GET_LAP_TELEMETRY_ARTIFACTS,
    }
)

# Heavy tools whose output _compose consumes directly for a given intent. A leaf
# check alone is not enough -- these nodes may have no DAG consumer (the verify
# node is deliberately decoupled from them) yet still be the answer's core
# evidence, so pruning them crashes compose with a missing key.
_COMPOSE_REQUIRED_TOOLS: dict[types.ToolName, frozenset[types.Intent]] = {
    types.ToolName.TELEMETRY_INSPECTOR: frozenset({types.Intent.TELEMETRY_COMPARISON}),
    types.ToolName.STINT_DEGRADATION_SCANNER: frozenset(
        {types.Intent.TYRE_DEGRADATION_ANALYSIS}
    ),
}


def prune_dag(
    dag: types.ExecutionDAG, routed: types.RoutedQuestion
) -> types.ExecutionDAG:
    """orchestrator post-step. For SIMPLE questions (complexity <= 2) drop heavy-telemetry nodes that are pure leaves: nothing downstream
    consumes them, so the evidence gate never needs them.

    Exception: never drop a heavy leaf whose output _compose() requires for this
    intent (e.g. telemetry_inspector on a telemetry-comparison question) -- the
    leaf check is about DAG edges, but compose is a consumer too."""
    if routed.complexity > 2:
        return dag

    consumers: dict[str, set[str]] = {}
    for node in dag.nodes:
        for dep in node.depends_on:
            consumers.setdefault(dep, set()).add(node.id)

    kept: list[types.DAGNode] = []
    for node in dag.nodes:
        required_intents = _COMPOSE_REQUIRED_TOOLS.get(node.tool_name, frozenset())
        is_heavy_leaf = (
            node.tool_name in _HEAVY_TELEMETRY_TOOLS
            and not consumers.get(node.id)
            and routed.intent not in required_intents
        )
        if is_heavy_leaf:
            continue
        kept.append(node)

    if len(kept) == len(dag.nodes):
        return dag

    kept_ids = {n.id for n in kept}
    edges = tuple(
        types.DAGEdge(source=e.source, target=e.target)
        for e in dag.edges
        if e.source in kept_ids and e.target in kept_ids
    )
    return types.ExecutionDAG(nodes=tuple(kept), edges=edges)


def _node_budget(complexity: int) -> int:
    return max(MIN_NODE_BUDGET, min(MAX_DAG_NODES, 1 + complexity * 2))


def _build_planner_prompt(
    question: str,
    routed: types.RoutedQuestion,
    registry: dict[str, ToolSpec],
) -> str:
    """Build the system prompt that tells the LLM which tools are available and asks it to produce a plan as JSON."""
    tool_lines: list[str] = []
    for spec in registry.values():
        req = ", ".join(sorted(spec.required_fields)) or "none"
        opt = ", ".join(sorted(set(spec.input_fields) - spec.required_fields)) or "none"
        tool_lines.append(
            f"- {spec.name}: {spec.description}\n"
            f"    required params: {req} | optional params: {opt}\n"
            f"    returns: {spec.output_summary}"
        )
    tools_block = "\n".join(tool_lines)

    entities = {
        k: v
        for k, v in {
            "intent": routed.intent.value if routed.intent else None,
            "driver_name": routed.driver_name,
            "gp_name": routed.gp_name,
            "year": routed.year,
            "target_lap": routed.target_lap,
            "session_type": routed.session_type.value if routed.session_type else None,
            "compare_driver_name": routed.compare_driver_name,
            "laps_window": routed.laps_window,
        }.items()
        if v is not None
    }

    return f"""You are planning which read-only data tools to call to answer an F1 race question.

            Question: {question}
            Extracted entities so far: {json.dumps(entities)}

            Injected complexity hint (1=simple, 5=complex compound analysis):
            {routed.complexity}
            Use at most {_node_budget(routed.complexity)} nodes. Prefer the
            FEWEST nodes that still fully answer the question -- do not pad
            the plan with speculative telemetry branches.

            Available tools:
            {tools_block}

            Return ONLY a JSON object, no prose, matching exactly this shape:
            {{
                "nodes": [
                    {{"id": "n1", "tool": "<tool name from the list above>", "params": {{...}}, "depends_on": []}}
                ]
            }}

            Rules:
            - Use ONLY tool names from the list above. Never invent a tool.
            - Every param key must be one listed for that tool.
            - "depends_on" lists node ids (from this same plan) that must run first.
            - Do not exceed {_node_budget(routed.complexity)} nodes
            - If a required param's value depends on another node's output (not known yet), omit it
            from "params" and add it instead to a sibling key "input_param_refs":
            {{"param_name": "node_id.field"}}.
            - If the question cannot be answered with these tools, return {{"nodes": []}}.
            - Always include a "verify_evidence" node as the last step, depending on all other nodes.
"""


def call_llm_json(prompt: str, model: str | None = None) -> dict:
    """Call the LLM and parse its response as JSON.

    We are setting the temperature to 0.0 for the planner beacuse we want a deterministic and reproducible plan.
    """
    text, _usage = llm._chat(
        [{"role": "user", "content": prompt}], temperature=0.0, model=model
    )

    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        lines = [li for li in lines[1:] if not li.strip().startswith("```")]
        cleaned = "\n".join(lines)

    return json.loads(cleaned)


def plan_dag(
    question: str,
    routed: types.RoutedQuestion,
    registry: dict[str, ToolSpec] | None = None,
) -> types.ExecutionDAG:
    """Ask the LLM to produce a plan for answering the question, then validate it and convert to ExecutionDAG."""
    if registry is None:
        registry = TOOL_REGISTRY

    prompt = _build_planner_prompt(question, routed, registry)
    model = llm.select_model(routed.intent, routed.complexity)
    raw_plan = call_llm_json(prompt, model=model)
    validated_dag = validate_plan(raw_plan, registry)
    execution_dag = _to_execution_dag(validated_dag)
    return prune_dag(execution_dag, routed)
