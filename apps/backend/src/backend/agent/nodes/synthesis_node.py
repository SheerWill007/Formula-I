from __future__ import annotations
from dataclasses import dataclass
from typing import Generator, Optional

from backend.agent import llm as llm_client

SYSTEM_PROMPT = (
    "You are Pitwall, an expert F1 analyst. Using the telemetry evidence and any "
    "computed results provided, write a clear, concise Markdown answer to the user's "
    "question. Be factual. Cite specific lap numbers, times, or speeds when available. "
    "Do not speculate beyond the data. Use bullet points for comparisons."
)


@dataclass
class SynthesisInput:
    user_query: str
    tool_evidence: str
    compute_result: Optional[str] = None


def stream(inp: SynthesisInput) -> Generator[str, None, None]:
    """Yield Markdown string chunks suitable for SSE streaming."""
    prompt = _build_prompt(inp)
    yield from llm_client.stream(prompt, system=SYSTEM_PROMPT)


def _build_prompt(inp: SynthesisInput) -> str:
    parts = [f"User question: {inp.user_query}", "", "Evidence gathered:"]
    if inp.tool_evidence:
        parts.append(inp.tool_evidence)
    if inp.compute_result:
        parts += ["", "Computed statistical result:", inp.compute_result]
    parts += ["", "Write the final Markdown answer now."]
    return "\n".join(parts)
