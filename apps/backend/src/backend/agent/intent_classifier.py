"""
Local intent classifier for compute and prediction needs.

Runs BEFORE the LLM router, on EVERY question -- including semantic-cache
hits. Keyword matching + heuristics make it deterministic and free:
no extra LLM round-trip, no hallucination.
"""

from __future__ import annotations
import re
from dataclasses import dataclass, field
from typing import Literal
import structlog

log = structlog.get_logger()

IntentCategory = Literal["descriptive", "comparative", "predictive", "chitchat"]

_COMPUTE_KEYWORDS = frozenset(
    {
        "average",
        "avg",
        "mean",
        "median",
        "difference",
        "diff",
        "delta",
        "gap",
        "compare",
        "comparison",
        "vs",
        "versus",
        "faster",
        "slower",
        "quicker",
        "total",
        "sum",
        "count",
        "percentage",
        "percent",
        "%",
        "degradation",
        "wear rate",
        "dropoff",
        "how much",
        "how many",
        "improve",
        "worse",
        "better",
        "fastest",
        "slowest",
        "sector time",
        "sector speed",
        "lap time",
        "lap pace",
        "speed delta",
        "time delta",
    }
)

_DIAGNOSTIC_PATTERNS = (
    r"\bwhy\b",
    r"\bwhat caused\b",
    r"\bhow did\b",
    r"\bwhat happened\b",
    r"\bexplain\b",
)

_COMPARATIVE_KEYWORDS = frozenset(
    {
        "compare",
        "comparison",
        "versus",
        "vs",
        "vs.",
        "head-to-head",
        "head to head",
        "differ",
        "difference between",
    }
)

_PREDICTION_KEYWORDS = frozenset(
    {
        "predict",
        "prediction",
        "forecast",
        "will",
        "going to",
        "likely",
        "strategy",
        "undercut",
        "overcut",
        "pit stop",
        "when should",
        "optimal",
        "best strategy",
        "next lap",
        "remaining laps",
    }
)

_CHITCHAT_PATTERN = re.compile(r"^(hi|hello|hey|yo)\b", re.IGNORECASE)

_SUGGESTED_TOOLS: dict[IntentCategory, tuple[str, ...]] = {
    "descriptive": ("resolve_session", "resolve_driver"),
    "comparative": (
        "telemetry_inspector",
        "gap_position_snapshot",
        "stint_degradation_scanner",
    ),
    "predictive": ("stint_degradation_scanner", "inspect_lap_events"),
    "chitchat": (),
}


@dataclass(frozen=True)
class IntentClassification:
    """Structured output of the local classifier (v3 doc 5.2)."""

    requires_compute: bool
    requires_prediction: bool
    intent_category: IntentCategory
    suggested_tools: tuple[str, ...] = field(default_factory=tuple)


def classify_intent(question: str) -> IntentClassification:
    """Classify compute/prediction needs and a category for the question"""
    lowered = question.lower()

    requires_compute = any(kw in lowered for kw in _COMPUTE_KEYWORDS)
    if not requires_compute:
        requires_compute = any(re.search(pat, lowered) for pat in _DIAGNOSTIC_PATTERNS)

    requires_prediction = any(kw in lowered for kw in _PREDICTION_KEYWORDS)
    is_comparative = any(kw in lowered for kw in _COMPARATIVE_KEYWORDS)

    if (
        not requires_compute
        and not requires_prediction
        and _CHITCHAT_PATTERN.match(lowered)
    ):
        category: IntentCategory = "chitchat"
    elif requires_prediction:
        category = "predictive"
    elif is_comparative:
        category = "comparative"
    else:
        category = "descriptive"

    result = IntentClassification(
        requires_compute=requires_compute,
        requires_prediction=requires_prediction,
        intent_category=category,
        suggested_tools=_SUGGESTED_TOOLS[category],
    )
    log.info(
        "intent_classifier.result",
        compute=result.requires_compute,
        prediction=result.requires_prediction,
        category=result.intent_category,
        question=question[:60],
    )

    return result
