"""Iterative reasoning loop
It uses the LLM to plan a sequesnce of tools to call and then executes them in order"""

from __future__ import annotations
import logging
import typing as t

from backend.agent import llm, planner, types
from backend.agent.planner import prune_dag, plan_dag

if t.TYPE_CHECKING:
    from backend.agent.planner import PlannerDAGNode

logger = logging.getLogger(__name__)

MAX_ROUNDS = 3


def _summarize(result: t.Any) -> str:
    """Truncate the node's output so the assess-evidence prompt says small"""
    s = str(result)
    return s[:500] + ("..." if len(s) > 500 else "")


def _build_assess_prompt(
    question: str, evidence: dict[str, t.Any], tool_names: list[str], round_num: int
) -> str:
    """Build the prompt that asks the LLM whether the gathered evidence is sufficient to answer the question or not"""

    evidence_summary = {
        node_id: _summarize(result) for node_id, result in evidence.items()
    }
    tools_block = ", ".join(sorted(tool_names))
    return f"""You already gathered this evidence for the question below (round {round_num} of {MAX_ROUNDS}): 

        Question: {question}
        Evidence so far: {evidence_summary}

        Available tools: {tools_block}

        Is this evidence sufficient to answer the question completely and accurately?

        Return ONLY JSON:
        - If sufficient: {{"satisfied": true}}
        - If not, and more tool calls are needed: {{"satisfied": false, "nodes": [ ... same shape as a plan ... ]}}
        New nodes may depend on node ids already listed in "Evidence so far" above -- those
        have already run.

        Do not repeat a tool call that already produced evidence you already have.
        """


def assess_evidence(
    question: str,
    evidence: dict[str, t.Any],
    registry: dict,
    round_num: int,
    model: str | None = None,
) -> t.Optional[planner.PlannerExecutionDAG]:
    """Ask the LLM whether the gathered evidence is sufficient to answer the question or not"""
    tool_names = list(registry.keys())
    prompt = _build_assess_prompt(question, evidence, tool_names, round_num)
    raw = planner.call_llm_json(prompt, model=model)

    if raw.get("satisfied") is True:
        return None
    return planner.validate_plan(raw, registry, known_node_ids=evidence.keys())


def execute_node(
    node: PlannerDAGNode, env: dict[str, t.Any], routed: types.RoutedQuestion
) -> t.Any:
    """Execute a single tool node"""
    from backend.agent.binding import bind_params
    from backend.agent.orchestrator import _TOOLS

    tool_name_enum = types.ToolName(node.tool)
    typed_input = bind_params(node, env, tool_name_enum)
    tool_fn = _TOOLS[tool_name_enum]

    return tool_fn(typed_input)


def run_agentic_dag(
    question: str,
    routed: types.RoutedQuestion,
    registry: dict,
) -> dict[str, t.Any]:
    """Plan round 0, execute, assess and repeat upto MAX_ROUNDS

    Returns the accumulated evidence env, pass this to the existing verify_evidence tool exactly as if it were a single tool call.
    """

    env: dict[str, t.Any] = {"routed": routed}
    model = llm.select_model(routed.intent, routed.complexity)

    try:
        dag = prune_dag(
            plan_dag(question, routed, registry),
            routed,
        )

    except planner.PlanValidationError:
        logger.warning("Round_0 plan validation failed", exc_info=True)
        return env

    round_num = 0
    while True:
        order = planner.topo_sort(dag)

        if order is None:
            logger.warning("DAG has cycles, cannot execute")
            return env

        for node_id in order:
            if node_id in env:
                continue
            node = next(n for n in dag.nodes if n.node_id == node_id)
            try:
                env[node_id] = execute_node(node, env, routed)
            except Exception as exc:
                logger.warning(f"Node {node_id} execution failed", exc_info=True)
                env[node_id] = {"error": str(exc)}

        round_num += 1
        if round_num >= MAX_ROUNDS:
            logger.info("Max rounds reached, stopping")
            return env

        try:
            next_dag = assess_evidence(question, env, registry, round_num, model=model)
        except planner.PlanValidationError:
            logger.warning("Round_%d plan validation failed", round_num, exc_info=True)
            return env

        if next_dag is None or not next_dag.nodes:
            break

        dag = next_dag

    return env
