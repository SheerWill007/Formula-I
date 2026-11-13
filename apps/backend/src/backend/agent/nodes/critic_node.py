from __future__ import annotations
from dataclasses import dataclass
from typing import Optional

from pydantic import BaseModel, Field
from backend.agent import llm as llm_client

SYSTEM_PROMPT = (
    "You are an expert F1 Data Steward. Evaluate the provided script output against "
    "the user's query. Check for F1 logic violations such as: lap times under 50 "
    "seconds, top speeds over 370 km/h, tyre degradation that improves over time, or "
    "impossible gap deltas. If the output is physically impossible or fails to answer "
    "the question, set is_logically_sound to False and populate error_feedback with "
    "clear instructions on how to fix the script. Respond only in valid JSON."
)


class CriticEvaluation(BaseModel):
    is_logically_sound: bool = Field(
        description="True if the result is physically plausible in F1."
    )
    reasoning: str
    error_feedback: Optional[str] = Field(
        default=None,
        description="Must be set if is_logically_sound is False. Tells ComputeNode how to fix the script.",
    )


@dataclass
class CriticInput:
    user_query: str
    compute_result: str


def run(inp: CriticInput) -> CriticEvaluation:
    """Ask the LLM to validate the compute result against F1 domain rules."""
    prompt = (
        f"User query: {inp.user_query}\n\n"
        f"Compute output:\n{inp.compute_result}\n\n"
        "Evaluate the output and respond with valid JSON matching the schema."
    )
    raw = llm_client.complete(prompt, system=SYSTEM_PROMPT, response_format="json")
    return CriticEvaluation.model_validate_json(raw)
