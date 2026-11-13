"""Task 5 -- Exact Data Catalog.

Availability answers must come from PostgreSQL (exact catalog queries), never
from the vector store. These tests cover list/search filters, partial names,
empty results, coverage presence/absence, and the deterministic run() path.
"""

import pytest
from sqlalchemy import text

from backend.agent import orchestrator, types

YEAR = 2099
SESSIONS = [
    (88001, "Monaco Grand Prix", "Monaco", "R", "Race"),
    (88002, "Monaco Grand Prix", "Monaco", "Q", "Qualifying"),
    (88003, "Silverstone Grand Prix", "Great Britain", "R", "Race"),
]


@pytest.fixture
def catalog_sessions(app, db_engine):
    with db_engine.begin() as conn:
        for sk, gp, country, stype, name in SESSIONS:
            conn.execute(
                text(
                    """
                    INSERT INTO sessions (
                        session_key, year, gp_name, country, session_type, session_name
                    ) VALUES (:sk, :year, :gp, :country, :stype, :name)
                    ON CONFLICT (session_key) DO NOTHING
                    """
                ),
                {
                    "sk": sk,
                    "year": YEAR,
                    "gp": gp,
                    "country": country,
                    "stype": stype,
                    "name": name,
                },
            )
    yield
    with db_engine.begin() as conn:
        conn.execute(
            text("DELETE FROM sessions WHERE session_key = ANY(:keys)"),
            {"keys": [s[0] for s in SESSIONS]},
        )


def _tool_sequence(dag):
    order = orchestrator.topo_sort(dag)
    node_map = {n.id: n for n in dag.nodes}
    return [node_map[nid].tool_name.value for nid in order]


class TestCatalogBuildDag:
    def test_availability_with_gp_name_searches_then_covers(self):
        routed = types.RoutedQuestion(
            intent=types.Intent.DATA_AVAILABILITY,
            gp_name="Monaco",
            year=YEAR,
        )
        assert _tool_sequence(orchestrator.build_dag(routed)) == [
            "search_sessions",
            "describe_session_coverage",
        ]

    def test_availability_without_gp_name_lists_then_covers(self):
        routed = types.RoutedQuestion(
            intent=types.Intent.DATA_AVAILABILITY,
            gp_name=None,
            year=YEAR,
        )
        assert _tool_sequence(orchestrator.build_dag(routed)) == [
            "list_available_sessions",
            "describe_session_coverage",
        ]


class TestListAndSearch:
    def test_list_filters_by_year_and_type(self, db_engine, catalog_sessions):
        result = tools_list(
            types.ListAvailableSessionsInput(
                year=YEAR, session_type=types.SessionType.RACE
            )
        )
        keys = {e.session_key for e in result.sessions}
        assert keys == {88001, 88003}
        assert all(e.session_type == "R" for e in result.sessions)

    def test_list_filters_by_gp_partial(self, db_engine, catalog_sessions):
        result = tools_list(
            types.ListAvailableSessionsInput(gp_name="Monaco", year=YEAR)
        )
        keys = {e.session_key for e in result.sessions}
        assert keys == {88001, 88002}

    def test_search_partial_case_insensitive(self, db_engine, catalog_sessions):
        result = tools_search(types.SearchSessionsInput(query="silver", year=YEAR))
        assert [e.session_key for e in result.sessions] == [88003]

    def test_search_by_country(self, db_engine, catalog_sessions):
        result = tools_search(
            types.SearchSessionsInput(query="Great Britain", year=YEAR)
        )
        assert [e.session_key for e in result.sessions] == [88003]

    def test_search_no_results_is_empty_not_error(self, db_engine, catalog_sessions):
        result = tools_search(
            types.SearchSessionsInput(query="Nonexistent GP", year=YEAR)
        )
        assert result.sessions == ()
        assert result.total == 0

    def test_list_respects_limit(self, db_engine, catalog_sessions):
        result = tools_list(types.ListAvailableSessionsInput(year=YEAR, limit=1))
        assert result.total == 1


class TestCoverage:
    def test_coverage_absent_data_all_false(self, db_engine, catalog_sessions):
        cov = tools_coverage(
            types.DescribeSessionCoverageInput(session_key=88001)
        ).coverage
        assert cov.has_laps is False
        assert cov.has_telemetry is False
        assert cov.has_weather is False
        assert cov.has_race_control is False
        assert cov.has_radio is False
        assert cov.has_indexed_documents is False

    def test_coverage_presence_counts(self, db_engine, catalog_sessions):
        with db_engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO lap_times (
                        session_key, driver_number, lap_number, lap_time_ms,
                        compound, deleted, recorded_at
                    ) VALUES
                        (88001, 44, 1, 90000, 'SOFT', false, NOW()),
                        (88001, 44, 2, 91000, 'SOFT', false, NOW()),
                        (88001, 63, 1, 92000, 'MEDIUM', false, NOW())
                    """
                )
            )
            conn.execute(
                text(
                    """
                    INSERT INTO weather_events (session_key, timestamp, lap_number, rainfall)
                    VALUES (88001, NOW(), 1, true)
                    """
                )
            )
            conn.execute(
                text(
                    """
                    INSERT INTO race_control_events (session_key, category, flag, lap_number)
                    VALUES (88001, 'Flag', 'SC', 2)
                    """
                )
            )
            conn.execute(
                text(
                    """
                    INSERT INTO team_radio (session_key, driver_number, recording_url)
                    VALUES (88001, 44, 'http://example.test/clip.mp3')
                    """
                )
            )
        try:
            cov = tools_coverage(
                types.DescribeSessionCoverageInput(session_key=88001)
            ).coverage
            assert cov.has_laps is True
            assert cov.lap_count == 3
            assert cov.driver_count == 2
            assert cov.has_weather is True
            assert cov.has_rainfall is True
            assert cov.has_race_control is True
            assert cov.race_control_count == 1
            assert cov.has_radio is True
            assert cov.radio_clip_count == 1
        finally:
            with db_engine.begin() as conn:
                conn.execute(text("DELETE FROM lap_times WHERE session_key = 88001"))
                conn.execute(
                    text("DELETE FROM weather_events WHERE session_key = 88001")
                )
                conn.execute(
                    text("DELETE FROM race_control_events WHERE session_key = 88001")
                )
                conn.execute(text("DELETE FROM team_radio WHERE session_key = 88001"))


class TestRunDataAvailability:
    def test_run_lists_and_reports_coverage(self, db_engine, catalog_sessions):
        routed = types.RoutedQuestion(
            intent=types.Intent.DATA_AVAILABILITY,
            gp_name="Monaco",
            year=YEAR,
        )
        answer = orchestrator._run_data_availability("Do you have Monaco 2099?", routed)
        assert answer.catalog is not None
        assert answer.catalog.total == 2
        assert answer.coverage is not None
        assert answer.coverage.session_key in {88001, 88002}
        assert "session" in answer.answer.lower()

    def test_run_no_results_refuses_to_guess(self, db_engine, catalog_sessions):
        routed = types.RoutedQuestion(
            intent=types.Intent.DATA_AVAILABILITY,
            gp_name="Nowhere",
            year=YEAR,
        )
        answer = orchestrator._run_data_availability("Nowhere 2099?", routed)
        assert answer.catalog is not None
        assert answer.catalog.total == 0
        assert "do not hold" in answer.answer.lower()


# -- thin wrappers so the test reads as catalog behaviour, not tool plumbing --


def tools_list(inp):
    from backend.agent import tools

    return tools.list_available_sessions(inp)


def tools_search(inp):
    from backend.agent import tools

    return tools.search_sessions(inp)


def tools_coverage(inp):
    from backend.agent import tools

    return tools.describe_session_coverage(inp)
