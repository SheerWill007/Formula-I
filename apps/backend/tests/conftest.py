"""
pytest configuration and shared fixtures.

conftest.py is a special pytest file — fixtures defined here are
automatically available to all test files without importing them.

The test suite creates its own tables in the connected database,
seeds minimal data, and tears everything down afterwards.
"""

import os

import pytest
from sqlalchemy import create_engine, text

# Keep local tests isolated from the developer database. CI supplies its own
# disposable PostgreSQL service and DATABASE_URL (port 5432), which must not
# be replaced with the local-only test database port.
if os.environ.get("CI", "").lower() != "true":
    os.environ["DATABASE_URL"] = (
        "postgresql+psycopg://pitwall:pitwall@localhost:5433/pitwall"
    )

from backend import create_app  # noqa: E402
from backend.config import settings  # noqa: E402
from backend import auth as backend_auth  # noqa: E402

# Product APIs (agent, sessions, telemetry, predictions) are Clerk-protected.
# The suite stubs the verifier so any non-empty bearer token is accepted; the
# dedicated 401 tests override this per-test. The shared `client` fixture sends
# a bearer token by default so feature tests do not need to attach one.
backend_auth.verify_session_token = lambda token: "test-clerk-user"  # type: ignore[assignment]


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
    sample_order    INTEGER,
    recorded_at     TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS telemetry_artifacts (
    id              SERIAL PRIMARY KEY,
    session_key     INTEGER NOT NULL REFERENCES sessions(session_key),
    driver_number   INTEGER NOT NULL,
    lap_number      INTEGER NOT NULL,
    storage_key     TEXT NOT NULL,
    storage_backend TEXT NOT NULL DEFAULT 'local',
    format          TEXT NOT NULL DEFAULT 'json.gz',
    sample_count    INTEGER NOT NULL,
    size_bytes      INTEGER NOT NULL,
    checksum_sha256 TEXT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_telemetry_artifact_lap
        UNIQUE (session_key, driver_number, lap_number)
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

CREATE TABLE IF NOT EXISTS race_intelligence_events (
    id              SERIAL PRIMARY KEY,
    session_key     INTEGER NOT NULL REFERENCES sessions(session_key),
    event_type      TEXT NOT NULL,
    event_key       TEXT NOT NULL,
    driver_number   INTEGER,
    lap_number      INTEGER,
    payload         JSONB NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_race_intelligence_event
        UNIQUE (session_key, event_type, event_key)
);

CREATE TABLE IF NOT EXISTS users (
    id              SERIAL PRIMARY KEY,
    clerk_user_id   TEXT NOT NULL,
    email           TEXT,
    name            TEXT,
    avatar_url      TEXT,
    plan            TEXT,
    role            TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen_at    TIMESTAMPTZ
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_users_clerk_user_id ON users (clerk_user_id);

CREATE TABLE IF NOT EXISTS agent_conversations (
    id          SERIAL PRIMARY KEY,
    user_id     INTEGER NOT NULL REFERENCES users(id),
    title       TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at  TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS agent_messages (
    id              SERIAL PRIMARY KEY,
    conversation_id INTEGER NOT NULL REFERENCES agent_conversations(id),
    role            TEXT NOT NULL,
    content         TEXT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS analyst_runs (
    id              SERIAL PRIMARY KEY,
    user_id         INTEGER NOT NULL REFERENCES users(id),
    conversation_id INTEGER REFERENCES agent_conversations(id),
    question        TEXT NOT NULL,
    answer          TEXT NOT NULL,
    cost_usd        DOUBLE PRECISION NOT NULL DEFAULT 0,
    steps           INTEGER NOT NULL DEFAULT 0,
    error           TEXT,
    events          JSONB NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS agent_runs (
    id                  SERIAL PRIMARY KEY,
    conversation_id     INTEGER REFERENCES agent_conversations(id),
    user_id             INTEGER NOT NULL REFERENCES users(id),
    status              TEXT NOT NULL,
    model               TEXT,
    started_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at        TIMESTAMPTZ,
    cost_estimate_usd   NUMERIC,
    error               TEXT,
    context_json        JSONB
);

CREATE TABLE IF NOT EXISTS agent_tool_calls (
    id                    SERIAL PRIMARY KEY,
    run_id                INTEGER NOT NULL REFERENCES agent_runs(id),
    tool_name             TEXT NOT NULL,
    input_json            JSONB,
    output_summary_json   JSONB,
    status                TEXT NOT NULL,
    duration_ms           INTEGER,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS agent_run_feedback (
    id              SERIAL PRIMARY KEY,
    run_id          INTEGER NOT NULL REFERENCES agent_runs(id) ON DELETE CASCADE,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    rating          SMALLINT NOT NULL CHECK (rating IN (-1, 1)),
    comment         TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (run_id, user_id)
);
CREATE INDEX IF NOT EXISTS idx_agent_run_feedback_run_id
    ON agent_run_feedback (run_id);

CREATE INDEX IF NOT EXISTS idx_lap_times_session_driver
    ON lap_times (session_key, driver_number);
CREATE INDEX IF NOT EXISTS idx_lap_times_driver_lap
    ON lap_times (driver_number, lap_number);
CREATE INDEX IF NOT EXISTS idx_telemetry_session_driver
    ON telemetry (session_key, driver_number);
CREATE INDEX IF NOT EXISTS idx_telemetry_artifacts_session_driver
    ON telemetry_artifacts (session_key, driver_number);
CREATE INDEX IF NOT EXISTS idx_race_intelligence_events_session_type
    ON race_intelligence_events (session_key, event_type);
CREATE INDEX IF NOT EXISTS idx_race_intelligence_events_driver
    ON race_intelligence_events (session_key, driver_number);

CREATE TABLE IF NOT EXISTS team_radio (
    id              SERIAL PRIMARY KEY,
    session_key     INTEGER NOT NULL REFERENCES sessions(session_key),
    driver_number   INTEGER NOT NULL,
    lap_number      INTEGER,
    date            TIMESTAMPTZ,
    recording_url   TEXT NOT NULL,
    transcript      TEXT
);

CREATE TABLE IF NOT EXISTS weather_events (
    id              SERIAL PRIMARY KEY,
    session_key     INTEGER NOT NULL REFERENCES sessions(session_key),
    timestamp       TIMESTAMPTZ NOT NULL,
    lap_number      INTEGER,
    track_temp_c    DOUBLE PRECISION,
    air_temp_c      DOUBLE PRECISION,
    humidity_pct    DOUBLE PRECISION,
    rainfall        BOOLEAN,
    wind_speed_ms   DOUBLE PRECISION
);

CREATE INDEX IF NOT EXISTS idx_team_radio_session_driver
    ON team_radio (session_key, driver_number);
CREATE INDEX IF NOT EXISTS idx_weather_events_session_lap
    ON weather_events (session_key, lap_number);

CREATE TABLE IF NOT EXISTS race_control_events (
    id              SERIAL PRIMARY KEY,
    session_key     INTEGER NOT NULL REFERENCES sessions(session_key),
    category        TEXT,
    flag            TEXT,
    scope           TEXT,
    driver_number   INTEGER,
    sector          INTEGER,
    lap_number      INTEGER,
    message         TEXT,
    recorded_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_race_control_session_lap
    ON race_control_events (session_key, lap_number);
CREATE INDEX IF NOT EXISTS idx_race_control_session_driver
    ON race_control_events (session_key, driver_number);

CREATE TABLE IF NOT EXISTS strategy_documents (
    id                  SERIAL PRIMARY KEY,
    source_type         TEXT NOT NULL,
    title               TEXT NOT NULL,
    r2_key              TEXT,
    source_url          TEXT,
    sha256              TEXT NOT NULL,
    mime_type           TEXT,
    season              INTEGER,
    session_key         INTEGER REFERENCES sessions(session_key),
    driver_number       INTEGER,
    team_name           TEXT,
    published_at        TIMESTAMPTZ,
    permission_status   TEXT NOT NULL DEFAULT 'pending',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_strategy_documents_sha256 UNIQUE (sha256)
);

CREATE TABLE IF NOT EXISTS strategy_document_chunks (
    id                  SERIAL PRIMARY KEY,
    document_id         INTEGER NOT NULL REFERENCES strategy_documents(id) ON DELETE CASCADE,
    chunk_index         INTEGER NOT NULL,
    text                TEXT NOT NULL,
    page_number         INTEGER,
    lap_from            INTEGER,
    lap_to              INTEGER,
    timestamp_from_ms   BIGINT,
    timestamp_to_ms     BIGINT,
    token_count         INTEGER,
    vector_id           TEXT,
    index_status        TEXT NOT NULL DEFAULT 'pending',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_strategy_chunk_document_index UNIQUE (document_id, chunk_index)
);

CREATE INDEX IF NOT EXISTS idx_strategy_documents_session
    ON strategy_documents (session_key);
CREATE INDEX IF NOT EXISTS idx_strategy_documents_season
    ON strategy_documents (season);
CREATE INDEX IF NOT EXISTS idx_strategy_documents_source_type
    ON strategy_documents (source_type);
CREATE INDEX IF NOT EXISTS idx_strategy_documents_permission
    ON strategy_documents (permission_status);
CREATE INDEX IF NOT EXISTS idx_strategy_chunks_document
    ON strategy_document_chunks (document_id);
CREATE INDEX IF NOT EXISTS idx_strategy_chunks_index_status
    ON strategy_document_chunks (index_status);
"""


@pytest.fixture(scope="session")
def app():
    """
    Create a Flask app configured for testing.
    scope="session" means this runs once for the entire test suite.

    settings.testing is set before app creation so testing configuration is
    applied to the backend.
    """
    settings.testing = True
    test_app = create_app()
    test_app.config["TESTING"] = True
    return test_app


@pytest.fixture(scope="session")
def client(app):
    """
    Flask test client — makes HTTP requests without running a real server.
    Use this in tests: client.get("/health")
    The client carries a stub bearer token so Clerk-protected product APIs
    are reachable; `app.test_client()` gives an unauthenticated client.
    """
    test_client = app.test_client()
    test_client.environ_base["HTTP_AUTHORIZATION"] = "Bearer test-token"
    return test_client


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
        conn.execute(text("DROP TABLE IF EXISTS analyst_runs CASCADE;"))
        conn.execute(text("DROP TABLE IF EXISTS strategy_document_chunks CASCADE;"))
        conn.execute(text("DROP TABLE IF EXISTS strategy_documents CASCADE;"))
        conn.execute(text("DROP TABLE IF EXISTS agent_tool_calls CASCADE;"))
        conn.execute(text("DROP TABLE IF EXISTS agent_runs CASCADE;"))
        conn.execute(text("DROP TABLE IF EXISTS agent_messages CASCADE;"))
        conn.execute(text("DROP TABLE IF EXISTS agent_conversations CASCADE;"))
        conn.execute(text("DROP TABLE IF EXISTS users CASCADE;"))
        conn.execute(text("DROP TABLE IF EXISTS race_intelligence_events CASCADE;"))
        conn.execute(text("DROP TABLE IF EXISTS race_results CASCADE;"))
        conn.execute(text("DROP TABLE IF EXISTS telemetry_artifacts CASCADE;"))
        conn.execute(text("DROP TABLE IF EXISTS telemetry CASCADE;"))
        conn.execute(text("DROP TABLE IF EXISTS weather_events CASCADE;"))
        conn.execute(text("DROP TABLE IF EXISTS race_control_events CASCADE;"))
        conn.execute(text("DROP TABLE IF EXISTS team_radio CASCADE;"))
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
        conn.execute(
            text("""
            INSERT INTO sessions (
                session_key, year, gp_name, country,
                session_type, session_name
            ) VALUES (
                99999, 2024, 'Test Grand Prix', 'Testland',
                'Q', 'Qualifying'
            )
            ON CONFLICT (session_key) DO NOTHING
        """)
        )

        conn.execute(
            text("""
            INSERT INTO drivers (
                driver_number, session_key, full_name, abbreviation, team_name, team_colour
            ) VALUES
                (44, 99999, 'Lewis Hamilton', 'HAM', 'Mercedes', '27F4D2'),
                (63, 99999, 'George Russell',  'RUS', 'Mercedes', '27F4D2')
            ON CONFLICT DO NOTHING
        """)
        )

        conn.execute(
            text("""
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
        """)
        )

    yield 99999  # yield the session_key to tests that need it

    # Cleanup after ALL tests finish
    with db_engine.begin() as conn:
        conn.execute(text("DELETE FROM lap_times   WHERE session_key = 99999"))
        conn.execute(text("DELETE FROM drivers      WHERE session_key = 99999"))
        conn.execute(text("DELETE FROM sessions     WHERE session_key = 99999"))
