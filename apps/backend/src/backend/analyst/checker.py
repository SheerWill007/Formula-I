"""Deterministic check that the numbers in an answer come from computed output.

No model involved. It catches numbers that were invented or copied from the
wrong place; it cannot tell whether the computation itself was the right one.

Claims are numbers with a decimal point or a unit. Bare integers (lap numbers,
stint numbers, years, list markers) are skipped because they would mostly be noise.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Method constants from the system prompt, which the model may quote without computing:
# the fuel effect (f1lab.pace.FUEL_EFFECT_S_PER_LAP) and the low-r2 threshold.
KNOWN_ASSUMPTIONS = (0.05, 0.3)

_UNITS = (
    r"s/lap|ms/lap|s per lap|ms per lap|seconds per lap|km/h|kph|m/s|°C|%|"
    r"seconds|second|secs|sec|ms|s|g|m"
)
_LAP_TIME = re.compile(r"(?<![\w.:])(\d{1,2}):(\d{2}\.\d+)")
_NUMBER = re.compile(
    r"(?<![\w.:/])[-+−]?(\d{1,3}(?:,\d{3})+|\d+)(\.\d+)?"
    rf"(?:\s?({_UNITS})(?![\w/]))?"
)
_ANY_NUMBER = re.compile(r"(?<![\w.])\d+(?:\.\d+)?(?:[eE][-+]?\d+)?")
_FENCED_CODE = re.compile(r"```.*?```", re.S)
# Not evidence: a sample row says nothing about the data, and a run's duration is not a result.
_SAMPLE_ROW = re.compile(r"First row: .*")
_RUN_STATUS = re.compile(r"^OK \([\d.]+s\)")


@dataclass(frozen=True)
class Claim:
    raw: str
    value: float
    decimals: int
    unit: str | None


def extract_claims(answer: str) -> list[Claim]:
    text = _FENCED_CODE.sub(" ", answer)
    claims: list[Claim] = []

    def lap_time(match: re.Match) -> str:
        seconds = int(match[1]) * 60 + float(match[2])
        claims.append(Claim(match[0], seconds, len(match[2].split(".")[1]), "s"))
        return " "

    text = _LAP_TIME.sub(lap_time, text)
    for match in _NUMBER.finditer(text):
        whole, fraction, unit = match[1], match[2], match[3]
        if not fraction and not unit:
            continue
        value = float(whole.replace(",", "") + (fraction or ""))
        claims.append(Claim(match[0].strip(), value, len(fraction or ".") - 1, unit))
    return claims


def evidence_values(messages: list[dict]) -> list[float]:
    """Numbers from successful tool output, plus any the user's question states."""
    values = list(KNOWN_ASSUMPTIONS)
    for message in messages:
        content = message.get("content") or ""
        if message.get("role") == "tool":
            if content.startswith("ERROR"):
                continue
            content = _RUN_STATUS.sub("", _SAMPLE_ROW.sub("", content))
        elif message.get("role") != "user" or content.startswith("Review feedback"):
            continue
        values += [float(n) for n in _ANY_NUMBER.findall(content)]
    return values


def _matches(claim: Claim, values: list[float]) -> bool:
    # same value, or a ms/s conversion, at the precision the answer wrote it
    factors = (1.0, 0.001, 1000.0) + ((100.0,) if claim.unit == "%" else ())
    tolerance = 0.5 * 10**-claim.decimals + 1e-9
    return any(abs(v * f - claim.value) <= tolerance for v in values for f in factors)


def find_unverified(answer: str, messages: list[dict]) -> list[str]:
    """Numbers in the answer that no computed output supports (deduplicated)."""
    values = evidence_values(messages)
    missing = [c.raw for c in extract_claims(answer) if not _matches(c, values)]
    return list(dict.fromkeys(missing))


def feedback(unverified: list[str]) -> str:
    return (
        f"These numbers appear in no computed output: {', '.join(unverified)}. "
        "Compute and print them with run_python, or remove them. A 'First row' sample "
        "is not a statistic. Then send the corrected final_answer."
    )


def annotate(answer: str, unverified: list[str]) -> str:
    return (
        f"{answer}\n\n> **Unverified:** these numbers could not be traced to computed "
        f"output, so treat them with care: {', '.join(unverified)}."
    )
