"""Physics sanity checks. Pure functions returning Issues, never raising.

These are the checks the agent's reviewer will run before any number is
allowed into an answer. An 'error' means the value must not be reported.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from backend.f1lab import kinematics

MAX_SPEED_KMH = 380.0
MIN_LAP_TIME_MS = 50_000
MAX_LATERAL_G = 7.0
MAX_BRAKING_G = 7.0
GREEN_PIT_LOSS_S = (10.0, 40.0)
MAX_DEG_S_PER_LAP = 1.0
# fuel-corrected tyres should not get faster by more than measurement noise
MIN_CORRECTED_DEG_S_PER_LAP = -0.05

Severity = Literal["error", "warning"]


@dataclass(frozen=True)
class Issue:
    severity: Severity
    code: str
    message: str


def check_lap_time(lap_time_ms: float) -> list[Issue]:
    if lap_time_ms < MIN_LAP_TIME_MS:
        return [
            Issue(
                "error",
                "lap_time_too_short",
                f"{lap_time_ms / 1000:.1f} s is under 50 s",
            )
        ]
    return []


def check_degradation(slope_s_per_lap: float, *, fuel_corrected: bool) -> list[Issue]:
    if slope_s_per_lap > MAX_DEG_S_PER_LAP:
        return [
            Issue(
                "error",
                "deg_too_high",
                f"{slope_s_per_lap:+.2f} s/lap is implausibly large",
            )
        ]
    if slope_s_per_lap < 0 and not fuel_corrected:
        return [
            Issue(
                "warning",
                "deg_negative_uncorrected",
                "negative raw slope is expected from fuel burn; apply fuel correction",
            )
        ]
    if fuel_corrected and slope_s_per_lap < MIN_CORRECTED_DEG_S_PER_LAP:
        return [
            Issue(
                "error",
                "deg_negative_corrected",
                f"{slope_s_per_lap:+.3f} s/lap after fuel correction: tyres cannot improve",
            )
        ]
    return []


def check_pit_loss(loss_s: float | None, condition: str) -> list[Issue]:
    if loss_s is None:
        return []
    low, high = GREEN_PIT_LOSS_S
    if condition == "green" and not low <= loss_s <= high:
        return [
            Issue(
                "error",
                "pit_loss_range",
                f"{loss_s:.1f} s green pit loss outside {low}-{high} s",
            )
        ]
    return []


def check_telemetry(samples: list[dict]) -> list[Issue]:
    """Checks for one lap of telemetry samples (artifact-row dicts)."""
    if not samples:
        return [Issue("error", "no_samples", "telemetry lap has no samples")]

    issues: list[Issue] = []
    speeds = [s["speed_kmh"] for s in samples if s.get("speed_kmh") is not None]
    if speeds and (min(speeds) < 0 or max(speeds) > MAX_SPEED_KMH):
        issues.append(
            Issue(
                "error",
                "speed_range",
                f"speed {min(speeds):.0f}-{max(speeds):.0f} km/h outside 0-{MAX_SPEED_KMH:.0f}",
            )
        )

    distances = [s["distance_m"] for s in samples if s.get("distance_m") is not None]
    if any(b < a for a, b in zip(distances, distances[1:])):
        issues.append(
            Issue("error", "distance_not_monotonic", "distance goes backwards")
        )

    throttle_keys = [
        k for k in ("throttle", "throttle_pct") if any(k in s for s in samples)
    ]
    if not throttle_keys:
        issues.append(
            Issue(
                "warning",
                "throttle_missing",
                "no throttle channel in this data; do not report throttle values",
            )
        )
    else:
        values = [s.get(throttle_keys[0]) or 0.0 for s in samples]
        if speeds and sum(speeds) / len(speeds) > 150 and max(values) == 0:
            issues.append(
                Issue(
                    "error",
                    "throttle_all_zero",
                    "throttle is 0 for the whole lap at racing speed: channel is bad",
                )
            )

    if all(
        s.get(k) is not None
        for s in samples[:5]
        for k in ("x_pos", "y_pos", "distance_m")
    ):
        try:
            peak = kinematics.lateral_peak(samples)
        except ValueError:
            peak = None
        if peak is not None and peak.low_g > MAX_LATERAL_G:
            issues.append(
                Issue(
                    "error",
                    "lateral_g_implausible",
                    f"lateral g {peak.low_g:.1f}-{peak.high_g:.1f} is above {MAX_LATERAL_G}: position noise",
                )
            )
    longitudinal = [g for g in kinematics.longitudinal_g(samples) if g is not None]
    if longitudinal and min(longitudinal) < -MAX_BRAKING_G:
        issues.append(
            Issue(
                "error",
                "braking_g_implausible",
                f"braking {min(longitudinal):.1f} g is beyond {MAX_BRAKING_G} g",
            )
        )
    return issues
