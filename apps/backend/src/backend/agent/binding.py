"""Parameter binding for agentic loops

Resolves the final kwargs for a tool call by applying, in priority order:
  1. an input_param_ref resolved from a prior node's output
  2. an explicit value the planner put directly in node.params
"""

from __future__ import annotations
import typing as t
from backend.agent import types


class BindError(Exception):
    """Raised when a required ref cannot be resolved. Fails this one node and its dependents"""


def resolve_ref(ref: str, env: dict[str, t.Any]) -> t.Any:
    """Resolve 'node_id.field' or 'node_id.field.nested' from the env"""

    parts = ref.split(".")
    node_id = parts[0]

    if node_id not in env:
        raise BindError(f"referenced node '{node_id}' has not executed yet")

    value = env[node_id]
    for part in parts[1:]:
        if isinstance(value, dict):
            if part not in value:
                raise BindError(f"field '{part}' not found in output of '{node_id}'")
            value = value[part]

        else:
            if not hasattr(value, part):
                raise BindError(f"field '{part}' not found in output of '{node_id}'")
            value = getattr(value, part)

    return value


def bind_params(node: t.Any, env: dict[str, t.Any], tool_name: types.ToolName) -> t.Any:
    """Resolve the final kwargs for a tool call, then type-hint them through the
    real orchestrator _bind."""

    from backend.agent.orchestrator import _bind

    merged: dict = dict(node.params)
    for param_name, ref in node.input_param_refs.items():
        merged[param_name] = resolve_ref(ref, env)
    return _bind(tool_name, merged, env)
