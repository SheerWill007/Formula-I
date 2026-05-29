"""initial_schema

Revision ID: 0001
Revises:
Create Date: 2026-03-01
"""
from alembic import op

revision = '0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:

    # ── Extensions ────────────────────────────────────────────────────────────
    op.execute("CREATE EXTENSION IF NOT EXISTS timescaledb;")
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp";')

    # ── sessions ──────────────────────────────────────────────────────────────
    # One row per F1 session (race, qualifying, practice).
    # session_key is FastF1's unique identifier — used as FK everywhere.
    op.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            session_key     INTEGER PRIMARY KEY,
            year            INTEGER NOT NULL,
            gp_name         TEXT NOT NULL,
            country         TEXT,
            circuit_key     INTEGER,
            session_type    TEXT NOT NULL,
            session_name    TEXT NOT NULL,
            date_start      TIMESTAMPTZ,
            date_end        TIMESTAMPTZ,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

            CONSTRAINT sessions_session_type_check
                CHECK (session_type IN ('R', 'Q', 'FP1', 'FP2', 'FP3', 'SS', 'SQ'))
        );
    """)

    # ── drivers ───────────────────────────────────────────────────────────────
    # Driver reference per session — same driver has different rows per session.
    op.execute("""
        CREATE TABLE IF NOT EXISTS drivers (
            driver_number   INTEGER NOT NULL,
            session_key     INTEGER NOT NULL REFERENCES sessions(session_key),
            full_name       TEXT NOT NULL,
            abbreviation    TEXT NOT NULL,
            team_name       TEXT,
            team_colour     TEXT,
            headshot_url    TEXT,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

            PRIMARY KEY (driver_number, session_key)
        );
    """)

    # ── lap_times ─────────────────────────────────────────────────────────────
    # One row per lap per driver. Becomes a TimescaleDB hypertable.
    # Hypertable = PostgreSQL table + automatic time-based partitioning.
    # Without partitioning, querying millions of laps across a full season
    # would do a full table scan. With partitioning, it only touches the
    # relevant time chunks — 10-100x faster.
    op.execute("""
        CREATE TABLE IF NOT EXISTS lap_times (
            id                  BIGSERIAL,
            session_key         INTEGER NOT NULL REFERENCES sessions(session_key),
            driver_number       INTEGER NOT NULL,
            lap_number          INTEGER NOT NULL,
            lap_time_ms         DOUBLE PRECISION,
            s1_ms               DOUBLE PRECISION,
            s2_ms               DOUBLE PRECISION,
            s3_ms               DOUBLE PRECISION,
            compound            TEXT,
            tyre_life_laps      INTEGER,
            is_personal_best    BOOLEAN DEFAULT FALSE,
            pit_in_time_ms      DOUBLE PRECISION,
            pit_out_time_ms     DOUBLE PRECISION,
            track_status        TEXT,
            deleted             BOOLEAN DEFAULT FALSE,
            recorded_at         TIMESTAMPTZ NOT NULL,

            PRIMARY KEY (id, recorded_at),

            CONSTRAINT lap_times_compound_check
                CHECK (
                    compound IN ('SOFT','MEDIUM','HARD','INTER','WET','TEST')
                    OR compound IS NULL
                )
        );
    """)

    # Convert to hypertable — this is the TimescaleDB magic line.
    # chunk_time_interval = 7 days means one partition per week.
    op.execute("""
        SELECT create_hypertable(
            'lap_times',
            'recorded_at',
            chunk_time_interval => INTERVAL '7 days',
            if_not_exists => TRUE
        );
    """)

    # ── telemetry ─────────────────────────────────────────────────────────────
    # High-frequency per-car data: speed, throttle, brake, gear every ~100ms.
    # One race = ~500,000 rows. A season = ~10 million rows.
    # MUST be a hypertable or queries become unusably slow.
    op.execute("""
        CREATE TABLE IF NOT EXISTS telemetry (
            session_key     INTEGER NOT NULL REFERENCES sessions(session_key),
            driver_number   INTEGER NOT NULL,
            lap_number      INTEGER,
            distance_m      DOUBLE PRECISION,
            speed_kmh       DOUBLE PRECISION,
            throttle_pct    DOUBLE PRECISION,
            brake           BOOLEAN,
            gear            INTEGER,
            rpm             DOUBLE PRECISION,
            drs             INTEGER,
            x_pos           DOUBLE PRECISION,
            y_pos           DOUBLE PRECISION,
            recorded_at     TIMESTAMPTZ NOT NULL
        );
    """)

    op.execute("""
        SELECT create_hypertable(
            'telemetry',
            'recorded_at',
            chunk_time_interval => INTERVAL '1 day',
            if_not_exists => TRUE
        );
    """)

    # ── race_results ──────────────────────────────────────────────────────────
    # Final race classification. One row per driver per race session.
    op.execute("""
        CREATE TABLE IF NOT EXISTS race_results (
            session_key     INTEGER NOT NULL REFERENCES sessions(session_key),
            driver_number   INTEGER NOT NULL,
            position        INTEGER,
            grid_position   INTEGER,
            points          DOUBLE PRECISION,
            status          TEXT,
            fastest_lap     BOOLEAN DEFAULT FALSE,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

            PRIMARY KEY (session_key, driver_number)
        );
    """)

    # ── ml_predictions ────────────────────────────────────────────────────────
    # Every prediction the ML pipeline makes, stored permanently.
    # After the race we compare predicted vs actual — this is how we
    # measure and improve model accuracy over time.
    op.execute("""
        CREATE TABLE IF NOT EXISTS ml_predictions (
            id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            session_key     INTEGER NOT NULL REFERENCES sessions(session_key),
            prediction_type TEXT NOT NULL,
            driver_number   INTEGER,
            predicted_value TEXT NOT NULL,
            confidence      DOUBLE PRECISION NOT NULL,
            model_version   TEXT NOT NULL,
            features_json   JSONB,
            shap_json       JSONB,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
    """)

    # ── indexes ───────────────────────────────────────────────────────────────
    # Add indexes on columns we filter by most often.
    # Rule of thumb: if you WHERE or ORDER BY a column regularly, index it.
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_lap_times_session_driver
        ON lap_times (session_key, driver_number);
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_lap_times_driver_lap
        ON lap_times (driver_number, lap_number);
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_telemetry_session_driver
        ON telemetry (session_key, driver_number);
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_ml_predictions_session
        ON ml_predictions (session_key, prediction_type);
    """)


def downgrade() -> None:
    # Reverses upgrade() in reverse order.
    # Foreign key constraints mean we must drop child tables before parents.
    op.execute("DROP TABLE IF EXISTS ml_predictions;")
    op.execute("DROP TABLE IF EXISTS race_results;")
    op.execute("DROP TABLE IF EXISTS telemetry;")
    op.execute("DROP TABLE IF EXISTS lap_times;")
    op.execute("DROP TABLE IF EXISTS drivers;")
    op.execute("DROP TABLE IF EXISTS sessions;")
