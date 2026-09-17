"""
Feature engineering for race prediction.

═══════════════════════════════════════════════════════════════════════════════
ARCHITECTURE NOTE — read this before changing anything
═══════════════════════════════════════════════════════════════════════════════

The single most important rule in feature engineering: NO DATA LEAKAGE.

Data leakage means your model accidentally sees information from the future
during training. It produces models that look great in cross-validation but
fail completely in production — because in production, the future doesn't exist.

How we prevent it:
  1. We load ALL race history once, sorted by date.
  2. For each race we're computing features for, we filter history to
     rows with date STRICTLY BEFORE the current race's date.
  3. Rolling features (team form, driver history) are computed from
     that filtered slice only.

This is called a "point-in-time" feature computation. An analyst sitting
in the paddock on qualifying day would only have access to past races —
never future ones. Our features must respect the same constraint.

═══════════════════════════════════════════════════════════════════════════════
FEATURE PHILOSOPHY
═══════════════════════════════════════════════════════════════════════════════

A useful feature answers: "Would a knowledgeable human use this to make
a better prediction?" If yes, it's probably worth including.

Our features fall into three categories:

1. QUALIFYING PERFORMANCE — what happened on Saturday
   grid_position, quali_gap_ms, sector gaps/ranks, compound used

2. HISTORICAL CONTEXT — what's been happening over the season
   team_form_3race, driver_circuit_avg, quali_to_race_conversion

3. CIRCUIT CONTEXT — what kind of track is this
   is_street_circuit, is_power_circuit, is_high_df_circuit

═══════════════════════════════════════════════════════════════════════════════
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sqlalchemy import create_engine, text

from ml.config import settings
import structlog

log = structlog.get_logger()

# ── Feature column lists ──────────────────────────────────────────────────────
# Separating original vs new features makes ablation studies easy:
# you can test "does adding team form actually help?" by swapping feature lists.

ORIGINAL_FEATURES = [
    "grid_position",
    "quali_gap_ms",
    "s1_gap_ms",
    "s2_gap_ms",
    "s3_gap_ms",
    "s1_rank",
    "s2_rank",
    "s3_rank",
    "quali_compound_soft",
    "quali_compound_inter",
    "is_street_circuit",
    "is_power_circuit",
    "is_high_df_circuit",
]

NEW_FEATURES = [
    # Rolling team performance — captures car development momentum
    "team_form_3race",  # team's avg finish position, last 3 races
    "team_form_trend",  # is team improving or declining? (negative = improving)
    # Driver-circuit historical performance
    "driver_circuit_avg",  # driver's avg finish here across all prior years
    "driver_circuit_best",  # driver's best finish here (ceiling of performance)
    # FP2 race simulation signal — compound strategy intention
    "fp2_hard_laps_pct",  # % of team's FP2 laps on HARD (high = planning 1-stop)
    "fp2_medium_laps_pct",  # % of team's FP2 laps on MEDIUM
    # Miami v1.5 weekend signals
    "speed_st_rank",  # speed trap rank on best qualifying lap
    "speed_st_delta_kmh",  # straight-line speed gap to fastest speed trap
    "fp1_deg_rate_ms_lap",  # FP1 long-run degradation slope
    "fp1_long_run_pace_ms",  # FP1 long-run average pace
    "sprint_finish_position",  # sprint result where available, neutral otherwise
    "sprint_position_delta",  # sprint gain/loss vs start proxy
    "sc_probability",  # circuit safety-car prior
    "overtake_difficulty",  # 0-1 circuit passing difficulty prior
    "dnf_rate_circuit",  # circuit reliability/DNF prior
    # Derived qualifying quality signals
    "sector_weakness_score",  # max sector rank - min sector rank (consistency measure)
    "pole_gap_pct",  # quali gap as % of pole time (circuit-normalised)
]

FEATURE_COLS = ORIGINAL_FEATURES + NEW_FEATURES
TARGET_COL = "finish_position"

# Circuit classification
# WHY we encode this: tree-based models can't infer "Monaco is tight" from
# lap times alone. Explicit flags let the model learn "street circuits favour
# grid position more than power circuits do."
STREET_CIRCUITS = {"Monaco Grand Prix", "Azerbaijan Grand Prix", "Singapore Grand Prix"}
POWER_CIRCUITS = {"Italian Grand Prix", "Belgian Grand Prix", "Azerbaijan Grand Prix"}
HIGH_DF_CIRCUITS = {"Monaco Grand Prix", "Hungarian Grand Prix"}

FEATURE_STREAMS = {
    "car_pace": [
        "grid_position",
        "quali_gap_ms",
        "s1_gap_ms",
        "s2_gap_ms",
        "s3_gap_ms",
        "s1_rank",
        "s2_rank",
        "s3_rank",
        "speed_st_rank",
        "speed_st_delta_kmh",
        "sector_weakness_score",
        "pole_gap_pct",
    ],
    "tyre_strategy": [
        "quali_compound_soft",
        "quali_compound_inter",
        "fp2_hard_laps_pct",
        "fp2_medium_laps_pct",
        "fp1_deg_rate_ms_lap",
        "fp1_long_run_pace_ms",
    ],
    "driver_team_form": [
        "team_form_3race",
        "team_form_trend",
        "driver_circuit_avg",
        "driver_circuit_best",
        "sprint_finish_position",
        "sprint_position_delta",
    ],
    "circuit_context": [
        "is_street_circuit",
        "is_power_circuit",
        "is_high_df_circuit",
        "sc_probability",
        "overtake_difficulty",
        "dnf_rate_circuit",
    ],
}

CIRCUIT_PRIORS = {
    "Miami Grand Prix": {
        "sc_probability": 0.72,
        "overtake_difficulty": 0.64,
        "dnf_rate_circuit": 0.12,
    },
    "Monaco Grand Prix": {
        "sc_probability": 0.80,
        "overtake_difficulty": 0.95,
        "dnf_rate_circuit": 0.18,
    },
    "Singapore Grand Prix": {
        "sc_probability": 0.90,
        "overtake_difficulty": 0.78,
        "dnf_rate_circuit": 0.16,
    },
    "Azerbaijan Grand Prix": {
        "sc_probability": 0.78,
        "overtake_difficulty": 0.42,
        "dnf_rate_circuit": 0.20,
    },
    "Australian Grand Prix": {
        "sc_probability": 0.55,
        "overtake_difficulty": 0.50,
        "dnf_rate_circuit": 0.14,
    },
    "Italian Grand Prix": {
        "sc_probability": 0.35,
        "overtake_difficulty": 0.32,
        "dnf_rate_circuit": 0.10,
    },
    "Belgian Grand Prix": {
        "sc_probability": 0.45,
        "overtake_difficulty": 0.36,
        "dnf_rate_circuit": 0.12,
    },
    "Hungarian Grand Prix": {
        "sc_probability": 0.50,
        "overtake_difficulty": 0.76,
        "dnf_rate_circuit": 0.11,
    },
}

DEFAULT_CIRCUIT_PRIORS = {
    "sc_probability": 0.45,
    "overtake_difficulty": 0.50,
    "dnf_rate_circuit": 0.12,
}


def get_engine():
    return create_engine(settings.db_url)


# ══════════════════════════════════════════════════════════════════════════════
# STEP 1: Load shared historical context
# ══════════════════════════════════════════════════════════════════════════════


def load_race_history(engine) -> pd.DataFrame:
    """
    Load ALL historical race results ordered by date.

    WHY we do this once at the top level rather than per-race:
    - Efficiency: one DB query instead of 26
    - Correctness: we can filter by date with a simple comparison
    - Clarity: the "timeline" of past results is explicit

    Returns a DataFrame with one row per driver per race, sorted by date.
    The 'finish_position' here is derived using the same fallback logic
    as training — total laps + cumulative time when live position unavailable.
    """
    with engine.connect() as conn:
        rows = (
            conn.execute(
                text("""
            WITH final_lap AS (
                SELECT DISTINCT ON (l.driver_number, l.session_key)
                    l.session_key,
                    l.driver_number,
                    l.lap_number  AS total_laps,
                    l.position    AS live_pos
                FROM lap_times l
                ORDER BY l.driver_number, l.session_key, l.lap_number DESC
            ),
            race_time AS (
                SELECT session_key, driver_number,
                       SUM(lap_time_ms) AS total_ms
                FROM lap_times
                WHERE lap_time_ms IS NOT NULL AND deleted = FALSE
                GROUP BY session_key, driver_number
            ),
            tie_breaker AS (
                SELECT
                    fl.session_key,
                    fl.driver_number,
                    fl.live_pos,
                    ROW_NUMBER() OVER (
                        PARTITION BY fl.session_key
                        ORDER BY fl.total_laps DESC, rt.total_ms ASC NULLS LAST
                    ) AS calc_pos
                FROM final_lap fl
                LEFT JOIN race_time rt
                    ON rt.session_key   = fl.session_key
                    AND rt.driver_number = fl.driver_number
            )
            SELECT
                s.session_key,
                s.year,
                s.gp_name,
                s.date_start,
                tb.driver_number,
                d.abbreviation,
                d.team_name,
                COALESCE(tb.live_pos, tb.calc_pos) AS finish_position
            FROM tie_breaker tb
            JOIN sessions s ON s.session_key = tb.session_key
            JOIN drivers d
                ON d.driver_number = tb.driver_number
                AND d.session_key  = tb.session_key
            WHERE s.session_type = 'R'
            ORDER BY s.date_start ASC
        """)
            )
            .mappings()
            .all()
        )

    df = pd.DataFrame([dict(r) for r in rows])
    log.info(
        "history.loaded",
        rows=len(df),
        years=sorted(df["year"].unique().tolist()) if len(df) else [],
    )
    return df


def load_fp2_compound_usage(engine) -> pd.DataFrame:
    """
    Load FP2 compound usage per team per session.

    WHY FP2 specifically (not FP1 or FP3):
    - FP1: installation laps, aero mapping — not representative of race plans
    - FP2: teams run race simulations on Friday evening — this is the session
      where engineers decide their Sunday tyre strategy
    - FP3: qualifying preparation on low fuel — not representative of race pace

    Returns: one row per (gp_name, year, team_name, compound) with lap counts.
    """
    expected_columns = ["gp_name", "year", "team_name", "compound", "laps"]

    with engine.connect() as conn:
        rows = (
            conn.execute(
                text("""
            SELECT
                s.gp_name,
                s.year,
                d.team_name,
                l.compound,
                COUNT(*) AS laps
            FROM lap_times l
            JOIN sessions s ON s.session_key = l.session_key
            JOIN drivers d
                ON d.driver_number = l.driver_number
                AND d.session_key  = l.session_key
            WHERE s.session_type = 'FP2'
              AND l.compound     IS NOT NULL
              AND l.lap_time_ms  IS NOT NULL
              AND l.deleted      = FALSE
            GROUP BY s.gp_name, s.year, d.team_name, l.compound
        """)
            )
            .mappings()
            .all()
        )

    if not rows:
        return pd.DataFrame(columns=expected_columns)

    return pd.DataFrame([dict(r) for r in rows], columns=expected_columns)


# ══════════════════════════════════════════════════════════════════════════════
# STEP 2: Feature computation functions
# ══════════════════════════════════════════════════════════════════════════════


def compute_team_form(
    history: pd.DataFrame,
    team_name: str,
    before_date: pd.Timestamp,
    window: int = 3,
) -> dict:
    """
    Compute rolling team performance before a specific date.

    WHY window=3:
    F1 car development cycles are roughly 3-4 races. A team solving an
    aero problem will show improvement over ~3 races. Shorter windows
    are too noisy (one DNF destroys the signal). Longer windows miss
    recent changes (e.g. a car upgrade at race 10 is diluted by bad
    results from races 1-9).

    This is a hyperparameter we could tune — in production you'd test
    window=2, 3, 4, 5 and pick the one that minimises CV MAE.

    WHY we use TEAM results not DRIVER results:
    A driver's individual result has too much noise (crashes, strategy,
    luck). The team's aggregate over 2 drivers better represents the
    underlying car performance, which is what we want to capture.

    Returns:
        team_form_3race: average team finish position (lower = better)
        team_form_trend: slope of finish positions over window
                        (negative = improving, positive = declining)
    """
    # Filter to this team, strictly before the race date
    # The date filter is critical — no data leakage
    mask = (history["team_name"] == team_name) & (history["date_start"] < before_date)
    team_hist = history[mask].sort_values("date_start")

    # Take last N races
    recent = team_hist.tail(window * 2)  # *2 because 2 drivers per team

    if len(recent) < 2:
        # Not enough history — use a neutral value
        # WHY 10 (not NaN): tree models handle missing values differently.
        # A neutral midfield value (P10 of 20) is more informative than
        # imputing with mean, which leaks global statistics.
        return {"team_form_3race": 10.0, "team_form_trend": 0.0}

    avg_finish = float(recent["finish_position"].mean())

    # Trend: fit a line through recent results
    # If the line slopes down (negative), team is improving
    # If the line slopes up (positive), team is declining
    if len(recent) >= 3:
        x = np.arange(len(recent))
        trend = float(np.polyfit(x, recent["finish_position"].values, deg=1)[0])
    else:
        trend = 0.0

    return {
        "team_form_3race": round(avg_finish, 2),
        "team_form_trend": round(trend, 3),
    }


def compute_driver_circuit_history(
    history: pd.DataFrame,
    driver_number: int,
    gp_name: str,
    before_date: pd.Timestamp,
) -> dict:
    """
    How does this driver historically perform at this specific circuit?

    WHY this matters:
    Some drivers have strong affinity with specific circuits — Hamilton
    at Silverstone, Verstappen at Spa, Alonso at Monaco. This isn't
    random: track characteristics (rhythm, specific corners, elevation)
    suit different driving styles. A driver who consistently gains places
    at Monaco regardless of car pace is worth rewarding in predictions.

    WHY we need at least 2 years of data:
    One result is just a single data point — it could be a DNF or a
    particularly strong/weak car year. Two or more results start showing
    a pattern. We use neutral fallbacks when we don't have enough data.

    Returns:
        driver_circuit_avg: average finish here (lower = better)
        driver_circuit_best: best finish here (the driver's ceiling)
    """
    mask = (
        (history["driver_number"] == driver_number)
        & (history["gp_name"] == gp_name)
        & (history["date_start"] < before_date)
    )
    circuit_hist = history[mask]

    if len(circuit_hist) == 0:
        return {"driver_circuit_avg": 10.0, "driver_circuit_best": 10}

    return {
        "driver_circuit_avg": round(float(circuit_hist["finish_position"].mean()), 2),
        "driver_circuit_best": int(circuit_hist["finish_position"].min()),
    }


# compute_quali_momentum removed (drop-dead feature)


def compute_quali_momentum(
    quali_key: int,
    driver_number: int,
    engine,
) -> dict:
    """
    Did the driver improve from Q2 to Q3, or did they peak in Q2?

    WHY this matters:
    A driver who sets their fastest Q2 time and then fails to improve
    in Q3 was at their limit — there's little margin left for Sunday.
    A driver who improves Q2→Q3 was still finding time — they have
    headroom and likely managed tyres better.

    This is especially revealing for drivers who qualify unexpectedly
    high or low: was it a fluke hot lap or consistent improvement?

    WHY we look at the fastest lap in each Q session rather than just
    the overall fastest: drivers sometimes abort Q3 laps for strategy
    (e.g. starting on a tyre of their choice). We want the actual
    best attempt in each phase.

    Returns:
        quali_improvement_q2_q3: Q3_best - Q2_best in ms
                                 Negative = got faster (good)
                                 Positive = got slower (bad, or Q3 abort)
                                 0 = no Q3 data (eliminated in Q2)
    """
    with engine.connect() as conn:
        rows = (
            conn.execute(
                text("""
            SELECT
                -- Get the fastest lap in each 'deleted' = FALSE group
                -- FastF1 marks Q1/Q2/Q3 phases via tyre_life_laps and stint
                -- We use stint as a proxy for Q phase (stint 1=Q1, 2=Q2, 3=Q3)
                COALESCE(stint, 1) AS q_phase,
                MIN(lap_time_ms)   AS best_ms
            FROM lap_times
            WHERE session_key  = :qk
              AND driver_number = :dn
              AND lap_time_ms   IS NOT NULL
              AND deleted       = FALSE
            GROUP BY COALESCE(stint, 1)
            ORDER BY COALESCE(stint, 1)
        """),
                {"qk": quali_key, "dn": driver_number},
            )
            .mappings()
            .all()
        )

    phase_times = {r["q_phase"]: r["best_ms"] for r in rows}

    q2_best = phase_times.get(2)
    q3_best = phase_times.get(3)

    if q2_best is None or q3_best is None:
        # Driver eliminated before Q3, or stint data unavailable
        return {"quali_improvement_q2_q3": 0.0}

    improvement = float(q3_best - q2_best)  # negative = improved
    return {"quali_improvement_q2_q3": round(improvement, 1)}


def compute_fp2_strategy(
    fp2_data: pd.DataFrame,
    team_name: str,
    gp_name: str,
    year: int,
) -> dict:
    """
    What tyre strategy is this team planning based on FP2 compound usage?

    WHY FP2 compound usage predicts race strategy:
    Teams use FP2 to run race simulations on the compounds they plan to
    use on Sunday. If Ferrari runs 30 HARD laps in FP2, they're likely
    planning a 1-stop on HARD. If they run mostly MEDIUM, they might
    go 2-stop. Teams don't run compounds they don't intend to use —
    tyre allocation is limited across the weekend.

    This gives us a Friday afternoon view of Sunday's strategy intentions
    before the teams announce anything.

    WHY percentages rather than raw counts:
    Some teams run more FP2 laps than others (different programmes).
    Normalising to percentages makes the feature circuit/team agnostic.

    Returns:
        fp2_hard_laps_pct: % of FP2 laps on HARD (0-1)
        fp2_medium_laps_pct: % of FP2 laps on MEDIUM (0-1)
    """
    required_columns = {"team_name", "gp_name", "year", "compound", "laps"}
    if fp2_data.empty or not required_columns.issubset(fp2_data.columns):
        return {"fp2_hard_laps_pct": 0.0, "fp2_medium_laps_pct": 0.0}

    mask = (
        (fp2_data["team_name"] == team_name)
        & (fp2_data["gp_name"] == gp_name)
        & (fp2_data["year"] == year)
    )
    team_fp2 = fp2_data[mask]

    if len(team_fp2) == 0:
        # No FP2 data — neutral 0 (not informative but not misleading)
        return {"fp2_hard_laps_pct": 0.0, "fp2_medium_laps_pct": 0.0}

    total_laps = team_fp2["laps"].sum()
    if total_laps == 0:
        return {"fp2_hard_laps_pct": 0.0, "fp2_medium_laps_pct": 0.0}

    hard_laps = team_fp2.loc[team_fp2["compound"] == "HARD", "laps"].sum()
    medium_laps = team_fp2.loc[team_fp2["compound"] == "MEDIUM", "laps"].sum()

    return {
        "fp2_hard_laps_pct": round(float(hard_laps / total_laps), 3),
        "fp2_medium_laps_pct": round(float(medium_laps / total_laps), 3),
    }


def compute_fp1_long_run_signal(
    engine,
    team_name: str,
    gp_name: str,
    year: int,
) -> dict:
    """
    FP1 race-sim proxy for sprint weekends.

    Miami 2026 has only FP1 before sprint qualifying, so this is deliberately
    conservative: use medium/hard stints of 5+ usable laps and return neutral
    values if the session has no credible long-run work.
    """
    with engine.connect() as conn:
        rows = conn.execute(
            text("""
            WITH fp1 AS (
                SELECT session_key
                FROM sessions
                WHERE gp_name = :gp_name
                  AND year = :year
                  AND session_type = 'FP1'
                ORDER BY date_start DESC NULLS LAST
                LIMIT 1
            ),
            clean_laps AS (
                SELECT
                    l.driver_number,
                    l.lap_number,
                    l.lap_time_ms,
                    l.compound,
                    COALESCE(l.stint, 1) AS stint
                FROM lap_times l
                JOIN fp1 ON fp1.session_key = l.session_key
                JOIN drivers d
                    ON d.session_key = l.session_key
                    AND d.driver_number = l.driver_number
                WHERE d.team_name = :team_name
                  AND l.lap_time_ms IS NOT NULL
                  AND l.deleted = FALSE
                  AND l.compound IN ('MEDIUM', 'HARD')
            ),
            stints AS (
                SELECT
                    driver_number,
                    compound,
                    stint,
                    COUNT(*) AS laps,
                    AVG(lap_time_ms) AS avg_ms,
                    REGR_SLOPE(lap_time_ms, lap_number) AS deg_ms_lap
                FROM clean_laps
                GROUP BY driver_number, compound, stint
                HAVING COUNT(*) >= 5
            )
            SELECT
                AVG(avg_ms) AS long_run_pace_ms,
                AVG(deg_ms_lap) AS deg_rate_ms_lap
            FROM stints
        """),
            {"team_name": team_name, "gp_name": gp_name, "year": year},
        ).mappings().first()

    if not rows or rows["long_run_pace_ms"] is None:
        return {"fp1_deg_rate_ms_lap": 0.0, "fp1_long_run_pace_ms": 0.0}

    return {
        "fp1_deg_rate_ms_lap": round(float(rows["deg_rate_ms_lap"] or 0.0), 2),
        "fp1_long_run_pace_ms": round(float(rows["long_run_pace_ms"] or 0.0), 1),
    }


def compute_sprint_signal(
    engine,
    driver_number: int,
    gp_name: str,
    year: int,
) -> dict:
    """Sprint result signal where available; neutral when the weekend has no sprint."""
    with engine.connect() as conn:
        row = conn.execute(
            text("""
            WITH sprint_session AS (
                SELECT session_key
                FROM sessions
                WHERE gp_name = :gp_name
                  AND year = :year
                  AND session_type IN ('S', 'SS')
                ORDER BY date_start DESC NULLS LAST
                LIMIT 1
            ),
            final_lap AS (
                SELECT DISTINCT ON (l.driver_number)
                    l.driver_number,
                    l.lap_number AS total_laps,
                    l.position AS live_pos
                FROM lap_times l
                JOIN sprint_session ss ON ss.session_key = l.session_key
                ORDER BY l.driver_number, l.lap_number DESC
            ),
            sprint_time AS (
                SELECT l.driver_number, SUM(l.lap_time_ms) AS total_ms
                FROM lap_times l
                JOIN sprint_session ss ON ss.session_key = l.session_key
                WHERE l.lap_time_ms IS NOT NULL AND l.deleted = FALSE
                GROUP BY l.driver_number
            ),
            classified AS (
                SELECT
                    fl.driver_number,
                    ROW_NUMBER() OVER (
                        ORDER BY fl.total_laps DESC, st.total_ms ASC NULLS LAST
                    ) AS calc_pos,
                    fl.live_pos
                FROM final_lap fl
                LEFT JOIN sprint_time st ON st.driver_number = fl.driver_number
            )
            SELECT COALESCE(live_pos, calc_pos) AS sprint_finish_position
            FROM classified
            WHERE driver_number = :driver_number
        """),
            {"driver_number": driver_number, "gp_name": gp_name, "year": year},
        ).mappings().first()

    if not row or row["sprint_finish_position"] is None:
        return {"sprint_finish_position": 10.0, "sprint_position_delta": 0.0}

    sprint_pos = float(row["sprint_finish_position"])
    return {
        "sprint_finish_position": sprint_pos,
        "sprint_position_delta": round(10.0 - sprint_pos, 2),
    }


def compute_circuit_priors(gp_name: str) -> dict:
    priors = {**DEFAULT_CIRCUIT_PRIORS, **CIRCUIT_PRIORS.get(gp_name, {})}
    return {k: float(v) for k, v in priors.items()}


def compute_weekend_inputs_used(engine, gp_name: str, year: int) -> dict:
    """Report available weekend streams so the UI can be honest about gaps."""
    expected = {
        "FP1": "practice_long_run",
        "SQ": "sprint_qualifying",
        "S": "sprint_race",
        "SS": "sprint_race",
        "Q": "qualifying",
    }
    with engine.connect() as conn:
        rows = conn.execute(
            text("""
            SELECT
                s.session_type,
                s.session_key,
                COUNT(l.lap_number) AS lap_count,
                MAX(s.date_start) AS date_start
            FROM sessions s
            LEFT JOIN lap_times l ON l.session_key = s.session_key
            WHERE s.gp_name = :gp_name
              AND s.year = :year
              AND s.session_type IN ('FP1', 'SQ', 'S', 'SS', 'Q')
            GROUP BY s.session_type, s.session_key
            ORDER BY MAX(s.date_start) ASC NULLS LAST
        """),
            {"gp_name": gp_name, "year": year},
        ).mappings().all()

    status = {
        "practice_long_run": {"available": False, "session_type": "FP1", "lap_count": 0},
        "sprint_qualifying": {"available": False, "session_type": "SQ", "lap_count": 0},
        "sprint_race": {"available": False, "session_type": "S", "lap_count": 0},
        "qualifying": {"available": False, "session_type": "Q", "lap_count": 0},
    }
    for row in rows:
        key = expected.get(row["session_type"])
        if not key:
            continue
        lap_count = int(row["lap_count"] or 0)
        status[key] = {
            "available": lap_count > 0,
            "session_type": row["session_type"],
            "session_key": row["session_key"],
            "lap_count": lap_count,
        }

    return status


# ══════════════════════════════════════════════════════════════════════════════
# STEP 3: Main feature matrix builder
# ══════════════════════════════════════════════════════════════════════════════


def build_feature_matrix() -> pd.DataFrame:
    """
    Build the complete feature matrix for model training.

    Architecture:
    1. Load shared context once (race history + FP2 data)
    2. Get all Q+R session pairs
    3. For each pair, compute features using shared context
    4. Return as a single DataFrame

    The shared context pattern (steps 1-2) is the most important
    architectural decision here — see module docstring for why.
    """
    engine = get_engine()

    # Load shared historical context once
    # These are expensive operations — we do them once, not per race
    log.info("feature.loading_history")
    race_history = load_race_history(engine)
    fp2_data = load_fp2_compound_usage(engine)

    # Get all qualifying + race pairs
    with engine.connect() as conn:
        pairs = (
            conn.execute(
                text("""
            SELECT
                year,
                gp_name,
                MIN(date_start) AS date_start,
                MAX(CASE WHEN session_type = 'Q'  THEN session_key END) AS quali_key,
                MAX(CASE WHEN session_type = 'R'  THEN session_key END) AS race_key
            FROM sessions
            GROUP BY year, gp_name
            HAVING
                MAX(CASE WHEN session_type = 'Q' THEN session_key END) IS NOT NULL AND
                MAX(CASE WHEN session_type = 'R' THEN session_key END) IS NOT NULL
            ORDER BY date_start ASC
        """)
            )
            .mappings()
            .all()
        )

    log.info("feature.pairs", count=len(pairs))

    all_rows = []
    for pair in pairs:
        rows = _build_weekend_features(
            year=pair["year"],
            gp_name=pair["gp_name"],
            date_start=pd.Timestamp(pair["date_start"]),
            quali_key=pair["quali_key"],
            race_key=pair["race_key"],
            race_history=race_history,
            fp2_data=fp2_data,
            engine=engine,
        )
        all_rows.extend(rows)
        log.info(
            "feature.weekend_done",
            year=pair["year"],
            gp=pair["gp_name"],
            rows=len(rows),
        )

    df = pd.DataFrame(all_rows)
    if df.empty:
        df = pd.DataFrame(columns=FEATURE_COLS + [TARGET_COL, "abbreviation", "year", "driver_number"])
    log.info("feature.matrix_built", shape=df.shape, features=FEATURE_COLS)
    return df


def _build_weekend_features(
    year: int,
    gp_name: str,
    date_start: pd.Timestamp,
    quali_key: int,
    race_key: int,
    race_history: pd.DataFrame,
    fp2_data: pd.DataFrame,
    engine,
) -> list[dict]:
    """Build features for a single race weekend."""

    # ── Qualifying data ───────────────────────────────────────────────────────
    with engine.connect() as conn:
        quali_laps = (
            conn.execute(
                text("""
            SELECT DISTINCT ON (l.driver_number)
                l.driver_number,
                d.abbreviation,
                d.team_name,
                l.lap_time_ms,
                l.s1_ms, l.s2_ms, l.s3_ms,
                l.speed_st,
                l.compound AS quali_compound
            FROM lap_times l
            JOIN drivers d
                ON d.driver_number = l.driver_number
                AND d.session_key  = l.session_key
            WHERE l.session_key  = :qk
              AND l.lap_time_ms  IS NOT NULL
            ORDER BY l.driver_number, l.lap_time_ms ASC
        """),
                {"qk": quali_key},
            )
            .mappings()
            .all()
        )

        race_results = (
            conn.execute(
                text("""
            WITH final_lap AS (
                SELECT DISTINCT ON (l.driver_number)
                    l.driver_number,
                    l.lap_number AS total_laps,
                    l.position   AS live_pos
                FROM lap_times l
                WHERE l.session_key = :rk
                ORDER BY l.driver_number, l.lap_number DESC
            ),
            race_time AS (
                SELECT driver_number, SUM(lap_time_ms) AS total_ms
                FROM lap_times
                WHERE session_key = :rk
                  AND lap_time_ms IS NOT NULL AND deleted = FALSE
                GROUP BY driver_number
            ),
            tie_breaker AS (
                SELECT fl.driver_number, fl.live_pos,
                    ROW_NUMBER() OVER (
                        ORDER BY fl.total_laps DESC, rt.total_ms ASC NULLS LAST
                    ) AS calc_pos
                FROM final_lap fl
                LEFT JOIN race_time rt ON rt.driver_number = fl.driver_number
            )
            SELECT driver_number,
                ROW_NUMBER() OVER (
                    ORDER BY COALESCE(live_pos, calc_pos) ASC
                ) AS finish_position
            FROM tie_breaker
        """),
                {"rk": race_key},
            )
            .mappings()
            .all()
        )

    if not quali_laps or not race_results:
        log.warning(
            "feature.missing_data",
            year=year,
            gp=gp_name,
            quali=len(quali_laps or []),
            race=len(race_results or []),
        )
        return []

    finish_map = {r["driver_number"]: r["finish_position"] for r in race_results}

    # ── Qualifying feature computation ────────────────────────────────────────
    q = pd.DataFrame([dict(r) for r in quali_laps])
    q["grid_position"] = q["lap_time_ms"].rank(method="min").astype(int)
    q["quali_gap_to_pole_ms"] = q["lap_time_ms"] - q["lap_time_ms"].min()
    pole_time = float(q["lap_time_ms"].min())

    for sec in ["s1_ms", "s2_ms", "s3_ms"]:
        q[f"{sec}_rank"] = q[sec].rank(method="min", na_option="bottom").astype(int)
        q[f"{sec}_gap"] = (q[sec] - q[sec].min()).fillna(9999)
    q["speed_st_rank"] = q["speed_st"].rank(method="min", ascending=False, na_option="bottom").astype(int)
    fastest_speed_st = float(q["speed_st"].max()) if q["speed_st"].notna().any() else 0.0

    # Circuit type flags
    is_street = int(gp_name in STREET_CIRCUITS)
    is_power = int(gp_name in POWER_CIRCUITS)
    is_high_df = int(gp_name in HIGH_DF_CIRCUITS)

    rows = []
    for _, r in q.iterrows():
        driver_number = int(r["driver_number"])
        finish = finish_map.get(driver_number)
        if finish is None:
            continue

        team_name = r["team_name"] or "Unknown"

        # ── New features — computed per driver using shared context ───────────

        # Feature: team form
        # Uses race_history filtered to before this race's date
        team_form = compute_team_form(race_history, team_name, date_start)

        # driver_circuit_avg, driver_circuit_best
        driver_circuit = compute_driver_circuit_history(
            race_history, driver_number, gp_name, date_start
        )

        # Feature: FP2 strategy signal
        fp2_strategy = compute_fp2_strategy(fp2_data, team_name, gp_name, year)

        fp1_signal = compute_fp1_long_run_signal(engine, team_name, gp_name, year)
        sprint_signal = compute_sprint_signal(engine, driver_number, gp_name, year)
        circuit_priors = compute_circuit_priors(gp_name)

        # Feature: sector consistency (derived from existing sector features)
        # WHY: A driver P3 who is P1 in S1, P6 in S3 has a clear weakness.
        # A driver P3 who is P3 in all sectors is consistently P3.
        # The first driver will lose more in races than the second.
        sector_ranks = [
            int(r["s1_ms_rank"]),
            int(r["s2_ms_rank"]),
            int(r["s3_ms_rank"]),
        ]
        weakness_score = max(sector_ranks) - min(sector_ranks)

        # Feature: pole gap as percentage
        # WHY: 0.5s gap at Monaco ≈ 0.2s gap at Monza (different lap lengths).
        # Percentage normalises across circuits so the model can compare.
        gap_ms = float(r["quali_gap_to_pole_ms"] or 0)
        pole_gap_pct = round(gap_ms / max(pole_time, 1) * 100, 4)
        speed_st = float(r["speed_st"]) if pd.notna(r["speed_st"]) else fastest_speed_st

        rows.append(
            {
                # Identifiers (not features — never passed to model)
                "year": year,
                "gp_name": gp_name,
                "driver_number": driver_number,
                "abbreviation": r["abbreviation"],
                "team_name": team_name,
                # Original features
                "grid_position": int(r["grid_position"]),
                "quali_gap_ms": float(r["quali_gap_to_pole_ms"] or 0),
                "s1_gap_ms": float(r["s1_ms_gap"]),
                "s2_gap_ms": float(r["s2_ms_gap"]),
                "s3_gap_ms": float(r["s3_ms_gap"]),
                "s1_rank": int(r["s1_ms_rank"]),
                "s2_rank": int(r["s2_ms_rank"]),
                "s3_rank": int(r["s3_ms_rank"]),
                "quali_compound_soft": int(r["quali_compound"] == "SOFT"),
                "quali_compound_inter": int(r["quali_compound"] == "INTERMEDIATE"),
                "is_street_circuit": is_street,
                "is_power_circuit": is_power,
                "is_high_df_circuit": is_high_df,
                # New features
                **team_form,
                **driver_circuit,
                **fp2_strategy,
                "speed_st_rank": int(r["speed_st_rank"]),
                "speed_st_delta_kmh": round(float(speed_st - fastest_speed_st), 2),
                **fp1_signal,
                **sprint_signal,
                **circuit_priors,
                "sector_weakness_score": weakness_score,
                "pole_gap_pct": pole_gap_pct,
                # Target
                "finish_position": int(finish),
            }
        )

    return rows


# ══════════════════════════════════════════════════════════════════════════════
# STEP 4: Inference feature builder (no target)
# ══════════════════════════════════════════════════════════════════════════════


def build_inference_features(quali_session_key: int) -> pd.DataFrame:
    """
    Build features for an unseen qualifying session — used for live predictions.

    WHY this is separate from build_feature_matrix:
    At training time, we have past AND future data available (but carefully
    filter to prevent leakage). At inference time, we ONLY have data up to
    "right now" — so the filtering is automatic, not deliberate.

    The key difference: we load race history up to today, not up to a
    specific past date.
    """
    engine = get_engine()

    # Load context — all history up to now (inference = "current moment")
    race_history = load_race_history(engine)
    fp2_data = load_fp2_compound_usage(engine)

    with engine.connect() as conn:
        session_row = conn.execute(
            text("""
            SELECT gp_name, year, date_start FROM sessions WHERE session_key = :sk
        """),
            {"sk": quali_session_key},
        ).first()

        if not session_row:
            raise ValueError(f"Session {quali_session_key} not found")

        gp_name = session_row[0]
        year = session_row[1]
        date_start = pd.Timestamp(session_row[2])

        quali_laps = (
            conn.execute(
                text("""
            SELECT DISTINCT ON (l.driver_number)
                l.driver_number,
                d.abbreviation,
                d.team_name,
                l.lap_time_ms,
                l.s1_ms, l.s2_ms, l.s3_ms,
                l.speed_st,
                l.compound AS quali_compound
            FROM lap_times l
            JOIN drivers d
                ON d.driver_number = l.driver_number
                AND d.session_key  = l.session_key
            WHERE l.session_key = :qk
              AND l.lap_time_ms IS NOT NULL
            ORDER BY l.driver_number, l.lap_time_ms ASC
        """),
                {"qk": quali_session_key},
            )
            .mappings()
            .all()
        )

    if not quali_laps:
        raise ValueError(f"No qualifying data for session {quali_session_key}")

    q = pd.DataFrame([dict(r) for r in quali_laps])
    q["grid_position"] = q["lap_time_ms"].rank(method="min").astype(int)
    q["quali_gap_to_pole_ms"] = q["lap_time_ms"] - q["lap_time_ms"].min()
    pole_time = float(q["lap_time_ms"].min())

    for sec in ["s1_ms", "s2_ms", "s3_ms"]:
        q[f"{sec}_rank"] = q[sec].rank(method="min", na_option="bottom").astype(int)
        q[f"{sec}_gap"] = (q[sec] - q[sec].min()).fillna(9999)
    q["speed_st_rank"] = q["speed_st"].rank(method="min", ascending=False, na_option="bottom").astype(int)
    fastest_speed_st = float(q["speed_st"].max()) if q["speed_st"].notna().any() else 0.0

    is_street = int(gp_name in STREET_CIRCUITS)
    is_power = int(gp_name in POWER_CIRCUITS)
    is_high_df = int(gp_name in HIGH_DF_CIRCUITS)

    rows = []
    for _, r in q.iterrows():
        driver_number = int(r["driver_number"])
        team_name = r["team_name"] or "Unknown"

        team_form = compute_team_form(race_history, team_name, date_start)
        driver_circuit = compute_driver_circuit_history(
            race_history, driver_number, gp_name, date_start
        )
        fp2_strategy = compute_fp2_strategy(fp2_data, team_name, gp_name, year)
        fp1_signal = compute_fp1_long_run_signal(engine, team_name, gp_name, year)
        sprint_signal = compute_sprint_signal(engine, driver_number, gp_name, year)
        circuit_priors = compute_circuit_priors(gp_name)

        sector_ranks = [
            int(r["s1_ms_rank"]),
            int(r["s2_ms_rank"]),
            int(r["s3_ms_rank"]),
        ]
        weakness_score = max(sector_ranks) - min(sector_ranks)
        gap_ms = float(r["quali_gap_to_pole_ms"] or 0)
        pole_gap_pct = round(gap_ms / max(pole_time, 1) * 100, 4)
        speed_st = float(r["speed_st"]) if pd.notna(r["speed_st"]) else fastest_speed_st

        rows.append(
            {
                "gp_name": gp_name,
                "driver_number": driver_number,
                "abbreviation": r["abbreviation"],
                "team_name": team_name,
                "grid_position": int(r["grid_position"]),
                "quali_gap_ms": float(r["quali_gap_to_pole_ms"] or 0),
                "s1_gap_ms": float(r["s1_ms_gap"]),
                "s2_gap_ms": float(r["s2_ms_gap"]),
                "s3_gap_ms": float(r["s3_ms_gap"]),
                "s1_rank": int(r["s1_ms_rank"]),
                "s2_rank": int(r["s2_ms_rank"]),
                "s3_rank": int(r["s3_ms_rank"]),
                "quali_compound_soft": int(r["quali_compound"] == "SOFT"),
                "quali_compound_inter": int(r["quali_compound"] == "INTERMEDIATE"),
                "is_street_circuit": is_street,
                "is_power_circuit": is_power,
                "is_high_df_circuit": is_high_df,
                **team_form,
                **driver_circuit,
                **fp2_strategy,
                "speed_st_rank": int(r["speed_st_rank"]),
                "speed_st_delta_kmh": round(float(speed_st - fastest_speed_st), 2),
                **fp1_signal,
                **sprint_signal,
                **circuit_priors,
                "sector_weakness_score": weakness_score,
                "pole_gap_pct": pole_gap_pct,
            }
        )

    return pd.DataFrame(rows)
