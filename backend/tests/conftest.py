"""
pytest configuration and shared fixtures.

conftest.py is a special pytest file — fixtures defined here are
automatically available to all test files without importing them.

The test suite creates its own tables in the connected database,
seeds minimal data, and tears everything down afterwards.
"""
import pytest
from sqlalchemy import create_engine, text

from backend import create_app
from backend.config import settings


# ── SQL to create all tables needed by tests ──────────────────────────────────
# Mirrors the schema from migrations 0001 through 0009, but skips
# TimescaleDB extensions / hypertable calls which aren't available in CI.

_CREATE_TABLES = """
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
    track_temp_c    DOUBLE PRECISION,
    air_temp_c      DOUBLE PRECISION,
    humidity_pct    DOUBLE PRECISION,
    rainfall        BOOLEAN,
    wind_speed_ms   DOUBLE PRECISION,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

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
    stint               INTEGER,
    position            INTEGER,
    fresh_tyre          BOOLEAN,
    deleted_reason      TEXT,
    is_accurate         BOOLEAN,
    speed_i1            DOUBLE PRECISION,
    speed_i2            DOUBLE PRECISION,
    speed_fl            DOUBLE PRECISION,
    speed_st            DOUBLE PRECISION,
    quali_segment       INTEGER,
    PRIMARY KEY (id)
);

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

CREATE INDEX IF NOT EXISTS idx_lap_times_session_driver
    ON lap_times (session_key, driver_number);
CREATE INDEX IF NOT EXISTS idx_lap_times_driver_lap
    ON lap_times (driver_number, lap_number);
CREATE INDEX IF NOT EXISTS idx_telemetry_session_driver
    ON telemetry (session_key, driver_number);
"""


@pytest.fixture(scope="session")
def app():
    """
    Create a Flask app configured for testing.
    scope="session" means this runs once for the entire test suite.
    """
    test_app = create_app()
    test_app.config["TESTING"] = True
    return test_app


@pytest.fixture(scope="session")
def client(app):
    """
    Flask test client — makes HTTP requests without running a real server.
    Use this in tests: client.get("/health")
    """
    return app.test_client()


@pytest.fixture(scope="session")
def db_engine():
    """Real database engine for seeding test data."""
    return create_engine(settings.database_url)


@pytest.fixture(scope="session", autouse=True)
def _create_tables(db_engine):
    """Create all tables before anything else runs, drop after all tests."""
    with db_engine.begin() as conn:
        conn.execute(text(_CREATE_TABLES))
    yield
    # Tear down tables after the full test suite finishes.
    # Drop in reverse dependency order.
    with db_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS race_results CASCADE;"))
        conn.execute(text("DROP TABLE IF EXISTS telemetry CASCADE;"))
        conn.execute(text("DROP TABLE IF EXISTS lap_times CASCADE;"))
        conn.execute(text("DROP TABLE IF EXISTS drivers CASCADE;"))
        conn.execute(text("DROP TABLE IF EXISTS sessions CASCADE;"))


@pytest.fixture(scope="session")
def seed_session(db_engine, _create_tables):
    """
    Insert one minimal session into the DB for tests to use.
    scope="session" = runs once, shared across all tests.
    The session_key 99999 is obviously fake — easy to identify in the DB.
    """
    with db_engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO sessions (
                session_key, year, gp_name, country,
                session_type, session_name
            ) VALUES (
                99999, 2024, 'Test Grand Prix', 'Testland',
                'Q', 'Qualifying'
            )
            ON CONFLICT (session_key) DO NOTHING
        """))

        conn.execute(text("""
            INSERT INTO drivers (
                driver_number, session_key, full_name, abbreviation, team_name, team_colour
            ) VALUES
                (44, 99999, 'Lewis Hamilton', 'HAM', 'Mercedes', '27F4D2'),
                (63, 99999, 'George Russell',  'RUS', 'Mercedes', '27F4D2')
            ON CONFLICT DO NOTHING
        """))

        conn.execute(text("""
            INSERT INTO lap_times (
                session_key, driver_number, lap_number,
                lap_time_ms, s1_ms, s2_ms, s3_ms,
                compound, is_personal_best, deleted, recorded_at
            ) VALUES
                (99999, 44, 1, 90000, 28000, 36000, 26000, 'SOFT', false, false, NOW()),
                (99999, 44, 2, 88000, 27500, 35000, 25500, 'SOFT', true,  false, NOW()),
                (99999, 63, 1, 91000, 28500, 36500, 26000, 'SOFT', false, false, NOW()),
                (99999, 63, 2, 87000, 27000, 34500, 25500, 'SOFT', true,  false, NOW())
            ON CONFLICT DO NOTHING
        """))

    yield 99999   # yield the session_key to tests that need it

    # Cleanup after ALL tests finish
    with db_engine.begin() as conn:
        conn.execute(text("DELETE FROM lap_times   WHERE session_key = 99999"))
        conn.execute(text("DELETE FROM drivers      WHERE session_key = 99999"))
        conn.execute(text("DELETE FROM sessions     WHERE session_key = 99999"))
