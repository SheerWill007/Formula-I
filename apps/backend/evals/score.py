"""Deterministic scoring for the agent answer-quality eval.

Pure functions only: no DB, no LLM. The run record is the plain dict that
run_eval.py writes (an AgentAnswer asdict() plus latency).
"""

from __future__ import annotations

import json
import re
import statistics
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

QUESTIONS_PATH = Path(__file__).parent / "questions.json"
TIERS = ("simple", "supported", "analytical", "trap")
_REQUIRED_KEYS = {
    "id",
    "tier",
    "question",
    "must_mention",
    "numeric_checks",
    "needs_chart",
    "expect_refusal",
    "rubric",
}
_VISUAL_FIELDS = (
    "telemetry_overlay",
    "stint_degradation",
    "gap_position",
    "weather",
    "charts",
)


def load_questions(path: Path = QUESTIONS_PATH) -> list[dict]:
    """Load and validate the question set. Raises ValueError on a bad entry."""
    questions = json.loads(path.read_text())["questions"]
    seen: set[str] = set()
    for q in questions:
        missing = _REQUIRED_KEYS - q.keys()
        if missing:
            raise ValueError(f"{q.get('id', '?')}: missing keys {sorted(missing)}")
        if q["id"] in seen:
            raise ValueError(f"duplicate id {q['id']}")
        seen.add(q["id"])
        if q["tier"] not in TIERS:
            raise ValueError(f"{q['id']}: unknown tier {q['tier']!r}")
        if (q["tier"] == "trap") != q["expect_refusal"]:
            raise ValueError(
                f"{q['id']}: trap tier must be exactly the expect_refusal ones"
            )
        for check in q["numeric_checks"]:
            if not {"name", "unit", "min", "max"} <= check.keys():
                raise ValueError(f"{q['id']}: bad numeric_check {check}")
    return questions


@dataclass
class QuestionScore:
    id: str
    tier: str
    passed: bool
    refused: bool
    checks: dict[str, Any] = field(default_factory=dict)
    failures: list[str] = field(default_factory=list)
    cost_usd: float = 0.0
    latency_s: float = 0.0
    tool_calls: int = 0
    has_visual: bool = False


# Spellings an LLM may use for a canonical unit, with the factor that converts
# the written value into the canonical unit (e.g. 126 ms per lap -> 0.126 s/lap).
UNIT_ALIASES: dict[str, tuple[tuple[str, float], ...]] = {
    "s/lap": (
        ("s/lap", 1.0),
        ("s per lap", 1.0),
        ("sec/lap", 1.0),
        ("seconds per lap", 1.0),
        ("ms/lap", 0.001),
        ("ms per lap", 0.001),
        ("milliseconds per lap", 0.001),
    ),
    "km/h": (("km/h", 1.0), ("kph", 1.0), ("kmh", 1.0), ("km/hr", 1.0)),
    "s": (
        ("s", 1.0),
        ("sec", 1.0),
        ("seconds", 1.0),
        ("ms", 0.001),
        ("milliseconds", 0.001),
    ),
}

# Phrases that mean the agent had no evidence for part of the answer. A good
# answer never contains them (the honest alternative is to refuse).
DEFAULT_FORBIDDEN = (
    "not provided",
    "no evidence",
    "could not compose",
    "not available in the evidence",
    "unable to",
    "could not determine",
    "cannot confirm",
    "cannot provide",
    "could not establish",
    "analysis incomplete",
    "insufficient data",
    "cannot conclude",
)

_MINUS = "−"  # LLMs sometimes write a unicode minus


_LAP_TIME = re.compile(r"(?<![\w.:])(\d{1,2}):(\d{2}(?:\.\d+)?)(?![\d:])")


def extract_numbers(text: str, unit: str) -> list[float]:
    """Numbers written directly before `unit` (or an alias), normalised to `unit`.

    '0.08 s/lap' -> 0.08 ; '126 ms per lap' with unit 's/lap' -> 0.126.
    """
    text = text.replace(_MINUS, "-")
    values: list[float] = []
    if unit == "s":  # a lap time written as 1:37.221 is 97.221 s
        values.extend(int(m) * 60 + float(sec) for m, sec in _LAP_TIME.findall(text))
    for spelling, factor in UNIT_ALIASES.get(unit, ((unit, 1.0),)):
        # (?![\w/]) stops 's' matching inside 's/lap' or 'seconds'
        pattern = r"(-?\d+(?:[.,]\d+)?)\s*" + re.escape(spelling) + r"(?![\w/])"
        values += [
            float(m.replace(",", ".")) * factor
            for m in re.findall(pattern, text, re.IGNORECASE)
        ]
    return values


def check_facts(facts: dict, answer: str) -> list[str]:
    """Failures against ground truth pulled from the database by hand."""
    lowered = answer.lower()
    failures = []
    for check in facts.get("numbers", []):
        values = extract_numbers(answer, check["unit"])
        if not any(abs(abs(v) - check["value"]) <= check["tol"] for v in values):
            failures.append(
                f"fact {check['name']}: expected {check['value']} {check['unit']}, found {values}"
            )
    for options in facts.get("any_of", []):
        if not any(o in lowered for o in options):
            failures.append(f"fact missing, expected one of {options}")
    for first, second in facts.get("in_order", []):
        a, b = lowered.find(first), lowered.find(second)
        if a == -1 or b == -1 or a > b:
            failures.append(f"expected {first!r} before {second!r}")
    for phrase in facts.get("forbidden", []):
        if phrase in lowered:
            failures.append(f"contradicts the data: {phrase!r}")
    return failures


def score_run(question: dict, run: dict) -> QuestionScore:
    """Score one saved run against its question entry."""
    answer: str = run.get("answer") or ""
    lowered = answer.lower()
    refused = bool(run.get("refusals")) or bool(run.get("clarification"))
    trace = run.get("trace") or []
    tool_errors = [c for c in trace if c.get("status") == "error"]

    score = QuestionScore(
        id=question["id"],
        tier=question["tier"],
        passed=False,
        refused=refused,
        cost_usd=float(run.get("cost_usd") or 0.0),
        latency_s=float(run.get("latency_s") or 0.0),
        tool_calls=len(trace),
        has_visual=any(run.get(f) for f in _VISUAL_FIELDS),
    )

    if question["expect_refusal"]:
        score.checks["refused"] = refused
        if not refused:
            score.failures.append("should have refused but answered")
        score.passed = refused
        return score

    if refused:
        score.failures.append(
            "refused: " + "; ".join(run.get("refusals") or ["clarification"])
        )

    missing_terms = [t for t in question["must_mention"] if t.lower() not in lowered]
    score.checks["must_mention"] = not missing_terms
    if missing_terms:
        score.failures.append(f"missing terms: {missing_terms}")

    forbidden = [
        p for p in (*DEFAULT_FORBIDDEN, *question.get("forbidden", [])) if p in lowered
    ]
    score.checks["no_evidence_gaps"] = not forbidden
    if forbidden:
        score.failures.append(f"admits missing evidence: {forbidden}")

    facts = question.get("facts")
    if facts:
        fact_failures = check_facts(facts, answer)
        score.checks["facts"] = not fact_failures
        score.failures += fact_failures

    for check in [] if facts else question["numeric_checks"]:
        values = extract_numbers(answer, check["unit"])
        ok = bool(values) and all(check["min"] <= v <= check["max"] for v in values)
        score.checks[f"num:{check['name']}"] = ok
        if not values:
            score.failures.append(
                f"{check['name']}: no value with unit {check['unit']!r}"
            )
        elif not ok:
            score.failures.append(
                f"{check['name']}: {values} outside [{check['min']}, {check['max']}]"
            )

    if run.get("unverified"):
        score.failures.append(f"untraceable numbers: {run['unverified']}")

    # Models legitimately hit and fix errors; what matters is that the last call worked.
    # The count is kept in checks so wasted steps stay visible.
    score.checks["tool_error_count"] = len(tool_errors)
    last_failed = bool(trace) and trace[-1].get("status") == "error"
    score.checks["tool_errors"] = not last_failed
    if last_failed and not facts:
        score.failures.append(
            f"final tool call errored ({len(tool_errors)} errors in total)"
        )

    # needs_chart is recorded, not enforced: the LLM judge will own it later.
    score.checks["chart_expected"] = question["needs_chart"]
    score.passed = not score.failures
    return score


def summarize(scores: list[QuestionScore]) -> dict[str, Any]:
    """Pass rate, cost and latency overall and per tier."""

    def block(items: list[QuestionScore]) -> dict[str, Any]:
        if not items:
            return {"n": 0}
        latencies = [s.latency_s for s in items]
        return {
            "n": len(items),
            "passed": sum(s.passed for s in items),
            "pass_rate": round(sum(s.passed for s in items) / len(items), 3),
            "mean_cost_usd": round(statistics.fmean(s.cost_usd for s in items), 5),
            "p50_latency_s": round(statistics.median(latencies), 2),
            "max_latency_s": round(max(latencies), 2),
        }

    return {
        "overall": block(scores),
        **{tier: block([s for s in scores if s.tier == tier]) for tier in TIERS},
    }
