"""
Driver style clustering (Phase 1 of the ML feature plan).

Job: turn raw season data into:
  1. driver_features rows   (one per driver/season -- raw feature store)
  2. driver_embeddings rows (PCA 5-dim projection + K-Means archetype)

"""

from __future__ import annotations
import argparse
import json

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler
from sqlalchemy import create_engine, text

from ml.config import settings

K = 4  # number of style clusters

_ARCHETYPE_BY_FEATURE: dict[str, tuple[str, str]] = {  # req update
    "braking_aggression": ("Late Braker", "Smooth Operator"),
    "drs_usage_pct": ("Top-Speed Merchant", "Downforce Runner"),
    "max_speed_capability": ("Top-Speed Specialist", "Corner Specialist"),
    "avg_speed_trap": ("High Trap Speed", "Low Trap Speed"),
    "avg_positions_gained": ("Race Overtaker", "Front-Row Holder"),
    "podium_rate": ("Front-Runner", "Long-Haul Scrapper"),
    "dnf_rate": ("Gambler", "Survivor"),
}

_NEGATIVE_BETTER = frozenset({"avg_finish_position", "lap_time_consistency"})

_FEATURE_LABELS = {
    "braking_aggression": "Brake aggression",
    "drs_usage_pct": "DRS usage",
    "max_speed_capability": "Top speed",
    "avg_speed_trap": "Trap speed",
    "lap_time_consistency": "Lap consistency",
    "avg_positions_gained": "Positions gained",
    "dnf_rate": "DNF rate",
}

CLUSTER_COLS = [
    "braking_aggression",
    "drs_usage_pct",
    "max_speed_capability",
    "avg_speed_trap",
    "lap_time_consistency",
    "avg_positions_gained",
    "podium_rate",
    "dnf_rate",
]

FEATURES_QUERY = text("""
    WITH year_drivers AS (
        SELECT DISTINCT d.driver_number, d.full_name, d.abbreviation, d.team_name
        FROM drivers d
        JOIN sessions s USING (session_key)
        WHERE s.year = :year
    ),
    race_results_agg AS (
        SELECT
            r.driver_number,
            AVG(r.position)::float AS avg_finish_position,
            COALESCE(STDDEV_SAMP(r.position)::float, 0.0) AS finish_position_stddev,
            AVG((r.position <= 3)::int)::float AS podium_rate,
            AVG((r.position = 1)::int)::float AS win_rate,
            AVG(r.grid_position - r.position)::float AS avg_positions_gained,
            AVG(CASE WHEN r.status IN ('DNF', 'DSQ') THEN 1 ELSE 0 END)::float AS dnf_rate
        FROM race_results r
        JOIN sessions s USING (session_key)
        WHERE s.year = :year
        AND s.session_type = 'R'
        AND r.grid_position IS NOT NULL
        GROUP BY r.driver_number
    ),
    lap_agg AS (
        SELECT
            l.driver_number,
            (STDDEV_SAMP(l.lap_time_ms) / NULLIF(AVG(l.lap_time_ms), 0))::float AS lap_time_consistency,
            AVG(COALESCE(l.speed_st, l.speed_i1))::float AS avg_speed_trap
        FROM lap_times l
        JOIN sessions s USING (session_key)
        WHERE s.year = :year
        AND s.session_type = 'R'
        AND l.deleted = FALSE
        AND l.lap_time_ms IS NOT NULL
        GROUP BY l.driver_number
    ),
    telemetry_agg AS (
        SELECT
            t.driver_number,
            MAX(t.speed_kmh)::float AS max_speed_capability,
            (AVG((t.drs > 0)::int) * 100.0)::float AS drs_usage_pct,
            (AVG(t.brake::int) * 100.0)::float AS braking_aggression
        FROM telemetry t
        JOIN sessions s USING (session_key)
        WHERE s.year = :year
        AND s.session_type = 'Q'
        GROUP BY t.driver_number
    )
    SELECT
        yd.driver_number, yd.full_name, yd.abbreviation, yd.team_name,
        r.avg_finish_position, r.finish_position_stddev, r.podium_rate, r.win_rate,
        r.avg_positions_gained, r.dnf_rate,
        l.lap_time_consistency, l.avg_speed_trap,
        t.max_speed_capability, t.drs_usage_pct, t.braking_aggression
    FROM year_drivers yd
    LEFT JOIN race_results_agg r USING (driver_number)
    LEFT JOIN lap_agg l USING (driver_number)
    LEFT JOIN telemetry_agg t USING (driver_number)
    ORDER BY yd.driver_number
""")


def get_engine():
    return create_engine(settings.db_url)


def load_features(year: int, engine) -> pd.DataFrame:
    return pd.read_sql(FEATURES_QUERY, engine, params={"year": year})


def _label_archetypes(centers: np.ndarray, cols: list[str]) -> list[str]:
    """Name each cluster from the feature that dominates its centroid.

    K-Means centroids live in STANDARDIZED space (Mean 0, Std 1 per
    feature), so feature magnitudes are comparable across units.
    For negative-better features, a negative centroid value means
    "better" and therefore the high-skill label.
    """
    names: list[str] = []
    for center in centers:
        i = int(np.argmax(np.abs(center)))
        feature = cols[i]
        value = float(center[i])
        high, low = _ARCHETYPE_BY_FEATURE.get(
            feature, ("Balanced All-Rounder", "Balanced All-Rounder")
        )
        is_negative_better = feature in _NEGATIVE_BETTER
        names.append(high if (value < 0) == is_negative_better else low)
    return names


def _axis_labels(pca: PCA, cols: list[str]) -> dict[str, str]:
    """Human name for each principal component: its strongest-loading feature."""
    out: dict[str, str] = {}
    for i, loadings in enumerate(pca.components_):
        feature = cols[int(np.argmax(np.abs(loadings)))]
        out[f"PC{i + 1}"] = _FEATURE_LABELS.get(feature, feature)
    return out


def _feature_row(row: pd.Series, season: int) -> dict:
    return {
        "driver_number": int(row["driver_number"]),
        "season": season,
        "full_name": row["full_name"],
        "abbreviation": row["abbreviation"],
        "team_name": row.get("team_name"),
        "avg_finish_position": _f(row.get("avg_finish_position")),
        "finish_position_stddev": _f(row.get("finish_position_stddev")),
        "podium_rate": _f(row.get("podium_rate")),
        "win_rate": _f(row.get("win_rate")),
        "avg_positions_gained": _f(row.get("avg_positions_gained")),
        "dnf_rate": _f(row.get("dnf_rate")),
        "lap_time_consistency": _f(row.get("lap_time_consistency")),
        "avg_speed_trap": _f(row.get("avg_speed_trap")),
        "max_speed_capability": _f(row.get("max_speed_capability")),
        "braking_aggression": _f(row.get("braking_aggression")),
        "drs_usage_pct": _f(row.get("drs_usage_pct")),
        "qual_to_race_delta": _f(row.get("avg_positions_gained")),
        "wet_pace_delta": None,
        "throttle_instability": None,
        "kerb_confidence": None,
        "track_limits_rate": None,
    }


def _f(value) -> float | None:
    """Coerce a sqlalchemy/pandas scalar to float or None (numpy NaN-safe)."""
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return None if pd.isna(f) else f


def cluster_for_year(year: int, engine=None) -> int:
    """Compute driver_features + driver_embeddings for one season.

    Returns the number of drivers embedded (0 when nothing usable exists).
    """
    engine = engine or get_engine()
    df = load_features(year, engine)
    if df.empty:
        print(f"[driver_clustering] no drivers found for {year}")
        return 0

    cols = [c for c in CLUSTER_COLS if df[c].notna().sum() >= 2]
    if not cols:
        print(f"[driver_clustering] no usable features for {year}")
        return 0

    fit_df = df.dropna(subset=cols).reset_index(drop=True)
    n = len(fit_df)
    if n < K:
        print(f"[driver_clustering] only {n} drivers fit; need at least {K}")
        return 0

    scaled = StandardScaler().fit_transform(fit_df[cols])

    n_components = min(5, len(cols), n - 1)
    pca = PCA(n_components=n_components).fit(scaled)
    pcs = pca.transform(scaled)

    kmeans = KMeans(n_clusters=min(K, n), n_init=10, random_state=42).fit(scaled)
    labels = kmeans.predict(scaled)
    archetypes = _label_archetypes(kmeans.cluster_centers_, cols)
    axis_labels = _axis_labels(pca, cols)

    features_rows = [_feature_row(row, year) for _, row in fit_df.iterrows()]

    embedding_rows = []
    for i, (_, row) in enumerate(fit_df.iterrows()):
        cluster_idx = int(labels[i])
        embedding_rows.append(
            {
                "driver_number": int(row["driver_number"]),
                "season": year,
                "abbreviation": row["abbreviation"],
                "team_name": row.get("team_name"),
                "embedding": [float(x) for x in pcs[i]],
                "pca_explained_variance": [
                    float(x) for x in pca.explained_variance_ratio_
                ],
                "pca_loadings": json.dumps(
                    {
                        f"D{d + 1}": {
                            "top_feature": f,
                            "label": _FEATURE_LABELS.get(f, f),
                        }
                        for d, f in enumerate(_axis_labels(pca, cols))
                    }
                ),
                "axis_labels": json.dumps(axis_labels),
                "archetype": archetypes[cluster_idx],
            }
        )

    with engine.begin() as conn:
        conn.execute(
            text("""
            INSERT INTO driver_features (
                driver_number, season, full_name, abbreviation, team_name,
                avg_finish_position, finish_position_stddev, podium_rate, win_rate,
                avg_positions_gained, quali_to_race_delta, dnf_rate,
                lap_time_consistency, avg_speed_trap, max_speed_capability,
                braking_aggression, drs_usage_pct, wet_pace_delta,
                throttle_instability, kerb_confidence, track_limits_rate, computed_at
            ) VALUES (
                :driver_number, :season, :full_name, :abbreviation, :team_name,
                :avg_finish_position, :finish_position_stddev, :podium_rate, :win_rate,
                :avg_positions_gained, :qual_to_race_delta, :dnf_rate,
                :lap_time_consistency, :avg_speed_trap, :max_speed_capability,
                :braking_aggression, :drs_usage_pct, :wet_pace_delta,
                :throttle_instability, :kerb_confidence, :track_limits_rate, NOW()
            )
            ON CONFLICT (driver_number, season) DO UPDATE SET
                full_name = EXCLUDED.full_name,
                abbreviation = EXCLUDED.abbreviation,
                team_name = EXCLUDED.team_name,
                avg_finish_position = EXCLUDED.avg_finish_position,
                finish_position_stddev = EXCLUDED.finish_position_stddev,
                podium_rate = EXCLUDED.podium_rate,
                win_rate = EXCLUDED.win_rate,
                avg_positions_gained = EXCLUDED.avg_positions_gained,
                dnf_rate = EXCLUDED.dnf_rate,
                lap_time_consistency = EXCLUDED.lap_time_consistency,
                avg_speed_trap = EXCLUDED.avg_speed_trap,
                max_speed_capability = EXCLUDED.max_speed_capability,
                braking_aggression = EXCLUDED.braking_aggression,
                drs_usage_pct = EXCLUDED.drs_usage_pct,
                computed_at = NOW()
        """),
            features_rows,
        )

        conn.execute(
            text("""
            INSERT INTO driver_embeddings (
                driver_number, season, abbreviation, team_name, embedding,
                pca_explained_variance, pca_loadings, axis_labels, archetype, computed_at
            ) VALUES (
                :driver_number, :season, :abbreviation, :team_name, :embedding::float[],
                :pca_explained_variance::float[], CAST(:pca_loadings AS JSONB),
                CAST(:axis_labels AS JSONB), :archetype, NOW()
            )
            ON CONFLICT (driver_number, season) DO UPDATE SET
                abbreviation = EXCLUDED.abbreviation,
                team_name = EXCLUDED.team_name,
                embedding = EXCLUDED.embedding,
                pca_explained_variance = EXCLUDED.pca_explained_variance,
                pca_loadings = EXCLUDED.pca_loadings,
                axis_labels = EXCLUDED.axis_labels,
                archetype = EXCLUDED.archetype,
                computed_at = NOW()
        """),
            embedding_rows,
        )

    print(
        f"[driver_clustering] {year}: embedded {len(embedding_rows)} drivers into {len(set(labels))} archetypes"
    )
    return len(embedding_rows)


def main() -> int:
    parser = argparse.ArgumentParser(description="Driver style clustering")
    parser.add_argument("--year", type=int, required=True)
    args = parser.parse_args()
    cluster_for_year(args.year)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
