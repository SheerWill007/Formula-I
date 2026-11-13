"""Lateral and longitudinal g from telemetry samples. Pure functions.

Samples are dicts shaped like the telemetry artifact rows:
distance_m, speed_kmh, x_pos, y_pos. There is no time channel, so
longitudinal acceleration uses a = v * dv/ds.

Everything here is an ESTIMATE: X/Y position is noisy, and the smoothing
needed to tame that biases tight corners slightly. Report ranges, not points.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

G = 9.80665

# (smoothing window, point offset) settings tried for a peak estimate
_PEAK_CONFIGS = ((7, 2), (9, 3), (11, 3), (15, 3))


def moving_average(values: list[float], window: int) -> list[float]:
    """Centered moving average; the window shrinks at the edges."""
    if window <= 1:
        return list(values)
    half = window // 2
    out = []
    for i in range(len(values)):
        chunk = values[max(0, i - half) : i + half + 1]
        out.append(sum(chunk) / len(chunk))
    return out


def xy_scale_m_per_unit(samples: list[dict]) -> float | None:
    """Metres per X/Y unit, from XY path length vs the distance channel.

    FastF1 positions are in 1/10 m, so this is ~0.1. A value within 5% of 0.1
    is snapped to exactly 0.1 (the distance channel is itself integrated).
    Returns None when it cannot be determined.
    """
    if len(samples) < 2:
        return None
    path = sum(
        math.hypot(b["x_pos"] - a["x_pos"], b["y_pos"] - a["y_pos"])
        for a, b in zip(samples, samples[1:])
    )
    dist = samples[-1]["distance_m"] - samples[0]["distance_m"]
    if path <= 0 or dist <= 0:
        return None
    scale = dist / path
    return 0.1 if 0.095 <= scale <= 0.105 else scale


def lateral_g(
    samples: list[dict],
    *,
    window: int = 9,
    step: int = 3,
    xy_scale: float | None = None,
) -> list[float | None]:
    """Lateral acceleration in g per sample: a = v^2 * curvature / g.

    Curvature is the Menger curvature of three smoothed XY points `step`
    samples apart. The first and last `step` samples are None.
    """
    n = len(samples)
    out: list[float | None] = [None] * n
    if n < 2 * step + 1:
        return out
    scale = xy_scale or xy_scale_m_per_unit(samples)
    if not scale:
        raise ValueError(
            "cannot determine the XY scale (need distance_m and x_pos/y_pos)"
        )

    xs = moving_average([s["x_pos"] for s in samples], window)
    ys = moving_average([s["y_pos"] for s in samples], window)
    for i in range(step, n - step):
        ax, ay, bx, by, cx, cy = (
            xs[i - step],
            ys[i - step],
            xs[i],
            ys[i],
            xs[i + step],
            ys[i + step],
        )
        a = math.hypot(bx - ax, by - ay)
        b = math.hypot(cx - bx, cy - by)
        c = math.hypot(cx - ax, cy - ay)
        if a * b * c == 0:
            out[i] = 0.0
            continue
        cross = abs((bx - ax) * (cy - ay) - (by - ay) * (cx - ax))
        curvature_per_m = (2 * cross / (a * b * c)) / scale
        v = samples[i]["speed_kmh"] / 3.6
        out[i] = v * v * curvature_per_m / G
    return out


def longitudinal_g(
    samples: list[dict], *, window: int = 5, step: int = 2
) -> list[float | None]:
    """Longitudinal acceleration in g per sample (negative = braking).

    step=2 (not 1): on real laps a one-sample central difference reads
    -7 to -9 g under braking, which is noise; two samples gives ~-4 g.
    The first and last `step` samples are None.
    """
    n = len(samples)
    out: list[float | None] = [None] * n
    v = moving_average([s["speed_kmh"] / 3.6 for s in samples], window)
    for i in range(step, n - step):
        ds = samples[i + step]["distance_m"] - samples[i - step]["distance_m"]
        if ds <= 0:
            continue
        out[i] = v[i] * (v[i + step] - v[i - step]) / ds / G
    return out


@dataclass(frozen=True)
class PeakG:
    value_g: float  # estimate (middle smoothing setting)
    low_g: float  # lowest peak across smoothing settings
    high_g: float  # highest peak across smoothing settings
    distance_m: float  # where on the lap the estimate happened


def lateral_peak(samples: list[dict]) -> PeakG | None:
    """Peak lateral g with an uncertainty range across smoothing settings."""
    peaks: list[tuple[float, float]] = []
    for window, step in _PEAK_CONFIGS:
        values = lateral_g(samples, window=window, step=step)
        found = [
            (g, samples[i]["distance_m"]) for i, g in enumerate(values) if g is not None
        ]
        if found:
            peaks.append(max(found))
    if not peaks:
        return None
    mid = sorted(peaks)[len(peaks) // 2]
    values_only = [p[0] for p in peaks]
    return PeakG(mid[0], min(values_only), max(values_only), mid[1])
