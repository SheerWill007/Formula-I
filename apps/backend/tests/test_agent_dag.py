"""dynamic DAG planner + concurrent runner."""

import time
from types import SimpleNamespace
from sqlalchemy import text

from backend.agent import orchestrator, types

SESSION_KEY = 99995


def _insert_session_and_driver(db_engine):
    with db_engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO sessions (session_key, year, gp_name, session_type, session_name)
                VALUES (:sk, 2026, 'Monaco Grand Prix', 'R', 'Race')
                """
            ),
            {"sk": SESSION_KEY},
        )
        conn.execute(
            text(
                """
                INSERT INTO drivers (driver_number, session_key, full_name, abbreviation, team_name, team_colour)
                VALUES (55, :sk, 'Carlos Sainz', 'SAI', 'Ferrari', '#DC0000')
                """
            ),
            {"sk": SESSION_KEY},
        )


def _insert_laps(db_engine):
    """Laps 1-8; pit stop on lap 5 (pit_in) / 6 (pit_out), SOFT -> HARD."""
    with db_engine.begin() as conn:
        for lap, compound, pit_in, pit_out in [
            (1, "SOFT", None, None),
            (2, "SOFT", None, None),
            (3, "SOFT", None, None),
            (4, "SOFT", None, None),
            (5, "SOFT", 123456.0, None),
            (6, "HARD", None, 234567.0),
            (7, "HARD", None, None),
            (8, "HARD", None, None),
        ]:
            conn.execute(
                text(
                    """
                    INSERT INTO lap_times (
                        session_key, driver_number, lap_number, lap_time_ms,
                        compound, pit_in_time_ms, pit_out_time_ms,
                        is_personal_best, deleted, recorded_at
                    ) VALUES (:sk, 55, :lap, 100000, :compound, :pit_in, :pit_out, false, false, NOW())
                    """
                ),
                {
                    "sk": SESSION_KEY,
                    "lap": lap,
                    "compound": compound,
                    "pit_in": pit_in,
                    "pit_out": pit_out,
                },
            )


def _cleanup(db_engine):
    with db_engine.begin() as conn:
        conn.execute(
            text("DELETE FROM lap_times WHERE session_key = :sk"), {"sk": SESSION_KEY}
        )
        conn.execute(
            text("DELETE FROM drivers WHERE session_key = :sk"), {"sk": SESSION_KEY}
        )
        conn.execute(
            text("DELETE FROM sessions WHERE session_key = :sk"), {"sk": SESSION_KEY}
        )


def _routed(intent, **kw):
    base = dict(driver_name="Sainz", gp_name="Monaco", year=2026)
    base.update(kw)
    return types.RoutedQuestion(intent=types.Intent(intent), **base)


def _fake_route(monkeypatch, routed):
    monkeypatch.setattr(orchestrator.llm, "route_question", lambda q: (routed, 0.0))


def _fake_compose(monkeypatch, text):
    monkeypatch.setattr(
        orchestrator.llm, "compose_answer", lambda q, e, **kwargs: (text, 0.0)
    )


def test_build_dag_pit_stop_shape():
    dag = orchestrator.build_dag(_routed("pit_stop_speed_delta"))
    assert [n.tool_name.value for n in dag.nodes] == [
        "resolve_session",
        "resolve_driver",
        "find_pit_stops",
        "get_lap_telemetry_artifacts",
        "compute_speed_window",
        "verify_evidence",
    ]
    by_id = {n.id: n for n in dag.nodes}
    assert by_id["window"].depends_on == ("pits",)
    assert by_id["verify"].depends_on == ("artifacts", "window")
    assert types.DAGEdge(source="pits", target="window") in dag.edges
    assert types.DAGEdge(source="pits", target="artifacts") in dag.edges


def test_build_dag_lap_event_shape():
    dag = orchestrator.build_dag(_routed("lap_event_investigation", target_lap=34))
    by_id = {n.id: n for n in dag.nodes}
    assert by_id["laps"].tool_name is types.ToolName.INSPECT_LAP_EVENTS
    assert by_id["laps"].input_params == {"target_lap": 34, "laps_window": 3}
    assert by_id["verify"].depends_on == ("session", "driver")


def test_build_dag_telemetry_compare_spawns_second_driver_branch():
    dag = orchestrator.build_dag(
        _routed("telemetry_comparison", target_lap=34, compare_driver_name="Leclerc")
    )
    by_id = {n.id: n for n in dag.nodes}
    assert by_id["driver_cmp"].depends_on == ("session",)
    assert by_id["telemetry"].depends_on == ("session", "driver", "driver_cmp")
    assert by_id["driver_cmp"].input_params == {"name": "Leclerc"}


def test_build_dag_team_radio_shape():
    dag = orchestrator.build_dag(_routed("team_radio"))
    by_id = {n.id: n for n in dag.nodes}
    assert by_id["radio"].tool_name is types.ToolName.FETCH_RADIO_MESSAGES
    assert by_id["radio"].depends_on == ("pits",)
    assert by_id["pits"].depends_on == ("session", "driver")
    assert by_id["verify"].depends_on == ("pits", "radio")


def test_build_dag_weather_correlation_shape():
    dag = orchestrator.build_dag(_routed("weather_correlation"))
    by_id = {n.id: n for n in dag.nodes}
    assert by_id["weather"].tool_name is types.ToolName.FETCH_WEATHER_WINDOW
    assert by_id["weather"].depends_on == ("pits",)
    assert by_id["verify"].depends_on == ("pits", "weather")


def test_compose_carries_radio_and_weather_payloads(monkeypatch):
    _fake_compose(monkeypatch, "debug")
    routed = _routed("team_radio")
    radio = types.RadioWindowResult(
        driver_number=55,
        from_lap=13,
        to_lap=15,
        messages=(
            types.RadioMessage(
                date="2024-07-07T13:00:00Z", recording_url="https://cdn.f1.com/a.mp3"
            ),
        ),
        clip_count=1,
    )
    weather = types.WeatherWindowResult(
        from_lap=13,
        to_lap=15,
        samples=(),
        rainfall_laps=0,
        total_laps=0,
        rain_share_pct=0.0,
        track_temp_delta_c=None,
    )
    outputs = {
        "session": types.ResolvedSession(
            session_key=1,
            year=2026,
            gp_name="Monaco",
            session_type=types.SessionType.RACE,
        ),
        "driver": types.ResolvedDriver(
            driver_number=55, abbreviation="SAI", full_name="Carlos Sainz"
        ),
        "pits": types.PitStopsResult(
            driver_number=55,
            pit_stops=(types.PitStop(stop_index=1, pit_in_lap=13, pit_out_lap=14),),
        ),
        "radio": radio,
        "weather": weather,
        "verify": types.VerifyEvidenceResult(passed=True, checks=()),
    }

    answer = orchestrator._compose("q", routed, outputs, set(), ())
    assert answer.team_radio is radio
    assert answer.weather is weather


def test_run_team_radio_through_dag(app, db_engine, monkeypatch):
    _insert_session_and_driver(db_engine)
    _insert_laps(db_engine)
    with db_engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO team_radio (
                    session_key, driver_number, lap_number, date, recording_url, transcript
                ) VALUES (:sk, 55, 5, NOW(), 'https://cdn.f1.com/box.mp3', 'Box box box')
                """
            ),
            {"sk": SESSION_KEY},
        )
    _fake_route(monkeypatch, _routed("team_radio"))
    _fake_compose(monkeypatch, "Carlos's engineer called him in.")

    try:
        answer = orchestrator.run(
            "What did Sainz's engineer say before the pit in Monaco 2026?"
        )
        assert answer.refusals == ()
        assert answer.intent is types.Intent.TEAM_RADIO
        assert answer.team_radio is not None
        assert answer.team_radio.clip_count == 1
        assert all(r.status == "ok" for r in answer.trace)
    finally:
        with db_engine.begin() as conn:
            conn.execute(
                text("DELETE FROM team_radio WHERE session_key = :sk"),
                {"sk": SESSION_KEY},
            )
        _cleanup(db_engine)


def test_run_weather_correlation_through_dag(app, db_engine, monkeypatch):
    _insert_session_and_driver(db_engine)
    _insert_laps(db_engine)
    with db_engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO weather_events (
                    session_key, timestamp, lap_number,
                    track_temp_c, air_temp_c, humidity_pct, rainfall, wind_speed_ms
                ) VALUES (:sk, NOW(), 5, 18.0, 14.0, 85.0, true, 4.0)
                """
            ),
            {"sk": SESSION_KEY},
        )
    _fake_route(monkeypatch, _routed("weather_correlation"))
    _fake_compose(monkeypatch, "It was raining when he pitted.")

    try:
        answer = orchestrator.run("Was it raining when Sainz pitted in Monaco 2026?")
        assert answer.refusals == ()
        assert answer.intent is types.Intent.WEATHER_CORRELATION
        assert answer.weather is not None
        assert answer.weather.rainfall_laps == 1
        assert all(r.status == "ok" for r in answer.trace)
    finally:
        with db_engine.begin() as conn:
            conn.execute(
                text("DELETE FROM weather_events WHERE session_key = :sk"),
                {"sk": SESSION_KEY},
            )
        _cleanup(db_engine)


# ── topo_sort ────────────────────────────────────────────────────────────────


def test_topo_sort_respects_dependencies():
    dag = types.ExecutionDAG(
        nodes=(
            types.DAGNode(
                id="c",
                tool_name=types.ToolName.VERIFY_EVIDENCE,
                label="",
                depends_on=("a", "b"),
            ),
            types.DAGNode(id="a", tool_name=types.ToolName.RESOLVE_SESSION, label=""),
            types.DAGNode(
                id="b",
                tool_name=types.ToolName.RESOLVE_DRIVER,
                label="",
                depends_on=("a",),
            ),
        )
    )
    order = orchestrator.topo_sort(dag)
    assert order.index("a") < order.index("b") < order.index("c")


def test_topo_sort_rejects_cycle():
    dag = types.ExecutionDAG(
        nodes=(
            types.DAGNode(
                id="a",
                tool_name=types.ToolName.RESOLVE_SESSION,
                label="",
                depends_on=("b",),
            ),
            types.DAGNode(
                id="b",
                tool_name=types.ToolName.RESOLVE_DRIVER,
                label="",
                depends_on=("a",),
            ),
        )
    )
    try:
        orchestrator.topo_sort(dag)
    except types.DataError:
        pass
    else:
        raise AssertionError("expected DataError for a cyclic DAG")


def test_compose_carries_chart_payloads(monkeypatch):
    """telemetry_overlay & stint_degradation come straight from DAG node outputs."""
    _fake_compose(monkeypatch, "debug")
    routed = _routed(
        "telemetry_comparison", target_lap=34, compare_driver_name="Leclerc"
    )
    telemetry = types.TelemetryInspectorResult(
        session_key=1,
        traces=(),
        speed_delta_apex_kmh=None,
        full_throttle_pct=42.5,
        heavy_braking_zones_count=3,
    )
    outputs = {
        "session": types.ResolvedSession(
            session_key=1,
            year=2026,
            gp_name="Monaco",
            session_type=types.SessionType.RACE,
        ),
        "driver": types.ResolvedDriver(
            driver_number=55, abbreviation="SAI", full_name="Carlos Sainz"
        ),
        "driver_cmp": types.ResolvedDriver(
            driver_number=16, abbreviation="LEC", full_name="Charles Leclerc"
        ),
        "telemetry": telemetry,
        "verify": types.VerifyEvidenceResult(passed=True, checks=()),
    }

    answer = orchestrator._compose("q", routed, outputs, set(), ())

    assert answer.telemetry_overlay is telemetry
    assert answer.stint_degradation is None


def test_execute_dag_runs_independent_nodes_in_parallel(monkeypatch):
    """Two root nodes must OVERLAP in time — that is the concurrency proof."""
    completion_lock = __import__("threading").Lock()
    started: list[float] = []
    finished: list[float] = []

    def slow_session(inp):
        with completion_lock:
            started.append(time.perf_counter())
        time.sleep(0.25)
        with completion_lock:
            finished.append(time.perf_counter())
        return SimpleNamespace(session_key=1)

    monkeypatch.setitem(
        orchestrator._TOOLS, types.ToolName.RESOLVE_SESSION, slow_session
    )

    dag = types.ExecutionDAG(
        nodes=(
            types.DAGNode(
                id="a",
                tool_name=types.ToolName.RESOLVE_SESSION,
                label="",
                input_params={"year": 2026, "gp_name": "Monaco"},
            ),
            types.DAGNode(
                id="b",
                tool_name=types.ToolName.RESOLVE_SESSION,
                label="",
                input_params={"year": 2025, "gp_name": "Monza"},
            ),
            types.DAGNode(
                id="c",
                tool_name=types.ToolName.RESOLVE_SESSION,
                label="",
                depends_on=("a", "b"),
                input_params={"year": 2024, "gp_name": "Silverstone"},
            ),
        )
    )
    trace, env, failed = orchestrator._execute_dag(dag, _routed("pit_stop_speed_delta"))
    assert failed == set()
    assert len(trace) == 3
    assert [t.node_id for t in trace] == ["a", "b", "c"]
    assert started[1] < finished[0]  # b began before a finished -> overlap


def test_execute_dag_fails_closed_on_dependency_error(monkeypatch):
    monkeypatch.setitem(
        orchestrator._TOOLS,
        types.ToolName.RESOLVE_SESSION,
        lambda inp: SimpleNamespace(session_key=1),
    )

    def boom(inp):
        raise types.NotFoundError("no such lap")

    monkeypatch.setitem(orchestrator._TOOLS, types.ToolName.INSPECT_LAP_EVENTS, boom)

    dag = types.ExecutionDAG(
        nodes=(
            types.DAGNode(
                id="session",
                tool_name=types.ToolName.RESOLVE_SESSION,
                label="",
                input_params={"year": 2026, "gp_name": "Monaco"},
            ),
            types.DAGNode(
                id="laps",
                tool_name=types.ToolName.INSPECT_LAP_EVENTS,
                label="",
                depends_on=("session",),
            ),
            types.DAGNode(
                id="verify",
                tool_name=types.ToolName.VERIFY_EVIDENCE,
                label="",
                depends_on=("laps",),
            ),
        )
    )
    trace, env, failed = orchestrator._execute_dag(
        dag, _routed("lap_event_investigation")
    )
    assert failed == {"laps", "verify"}
    error_calls = [t for t in trace if t.status == "error"]
    assert len(error_calls) == 2
    assert any("dependency failed" in (t.error or "") for t in error_calls)


def test_run_lap_event_through_dag(app, db_engine, monkeypatch):
    _insert_session_and_driver(db_engine)
    _insert_laps(db_engine)
    _fake_route(monkeypatch, _routed("lap_event_investigation", target_lap=4))
    _fake_compose(monkeypatch, "Lap 4 was within normal pace.")

    try:
        answer = orchestrator.run("Why was lap 4 slow for Sainz in Monaco 2026?")
        assert answer.refusals == ()
        assert answer.intent is types.Intent.LAP_EVENT_INVESTIGATION
        assert all(r.status == "ok" for r in answer.trace)
        assert [r.tool_name for r in answer.trace] == [
            types.ToolName.RESOLVE_SESSION,
            types.ToolName.RESOLVE_DRIVER,
            types.ToolName.INSPECT_LAP_EVENTS,
            types.ToolName.VERIFY_EVIDENCE,
        ]
        assert answer.evidence is not None
        assert answer.evidence.passed is True
    finally:
        _cleanup(db_engine)


def test_run_streams_dag_events_and_fails_closed(app, db_engine, monkeypatch):
    """Pit-stop question but NO artifacts -> artifacts/verify error, answer refused."""
    _insert_session_and_driver(db_engine)
    _insert_laps(db_engine)
    _fake_route(monkeypatch, _routed("pit_stop_speed_delta"))

    events: list[dict] = []

    def collect(payload):
        events.append(payload)

    try:
        answer = orchestrator.run(
            "Speed around the pit stop for Sainz in Monaco 2026?", progress=collect
        )
        assert answer.speed_window is None
        assert any(r.status == "error" for r in answer.trace)

        streamed = [e for e in events]
        assert "dag_init" in {e["type"] for e in streamed}
        assert "node_start" in {e["type"] for e in streamed}
        assert "node_error" in {e["type"] for e in streamed}
        node_ids = {e.get("node_id") for e in streamed if e.get("node_id")}
        assert {"session", "driver", "pits", "artifacts"} <= node_ids
    finally:
        _cleanup(db_engine)


def test_run_telemetry_compare_refuses_when_missing_compare_driver(monkeypatch):
    _fake_route(monkeypatch, _routed("telemetry_comparison", target_lap=10))
    answer = orchestrator.run("Compare lap 10 for Sainz in Monaco 2026?")
    assert answer.refusals == ("missing_compare_driver",)
    assert answer.trace == ()


def test_run_telemetry_compare_refuses_when_missing_lap(monkeypatch):
    _fake_route(
        monkeypatch, _routed("telemetry_comparison", compare_driver_name="Leclerc")
    )
    answer = orchestrator.run("Compare telemetry for Sainz vs Leclerc in Monaco 2026?")
    assert answer.refusals == ("missing_lap",)
