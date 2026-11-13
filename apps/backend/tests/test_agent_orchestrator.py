"""Integration test for v1 of agent orchestrator."""

import gzip
import json
from pathlib import Path
from sqlalchemy import text
from backend.agent import orchestrator, types
from backend.config import settings

SESSION_KEY = 99994


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
    """Laps 1-8; pit stop on lap 5 (pit_in) / lap 6 (pit_out), SOFT -> HARD."""
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
                    ) VALUES (
                        :sk, 55, :lap, 100000, :compound, :pit_in, :pit_out,
                        false, false, NOW()
                    )
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


def _write_gz_artifact(tmp_path, lap_number, speeds):
    storage_key = f"telemetry/session_{SESSION_KEY}/driver_55/lap_{lap_number}.json.gz"
    path = Path(tmp_path) / storage_key
    path.parent.mkdir(parents=True, exist_ok=True)
    samples = [{"speed_kmh": s, "distance_m": 100.0} for s in speeds]
    with gzip.open(path, "wb") as f:
        f.write(
            json.dumps(
                {
                    "session_key": SESSION_KEY,
                    "driver_number": 55,
                    "lap_number": lap_number,
                    "samples": samples,
                }
            ).encode("utf-8")
        )
    with path.open("rb") as f:
        size = len(f.read())
    return storage_key, size


def _insert_artifacts(db_engine, tmp_path):
    """Artifacts for the before window (2,3,4) and after window (7,8,9)."""
    entries = []
    for lap_number, speeds in [
        (2, [200.0, 210.0]),
        (3, [210.0, 220.0]),
        (4, [220.0, 230.0]),
        (7, [240.0, 250.0]),
        (8, [250.0, 260.0]),
        (9, [260.0, 270.0]),
    ]:
        storage_key, size = _write_gz_artifact(tmp_path, lap_number, speeds)
        entries.append((lap_number, storage_key, size, len(speeds)))
    with db_engine.begin() as conn:
        for lap_number, storage_key, size, count in entries:
            conn.execute(
                text(
                    """
                    INSERT INTO telemetry_artifacts (
                        session_key, driver_number, lap_number,
                        storage_key, storage_backend, format,
                        sample_count, size_bytes, checksum_sha256
                    ) VALUES (
                        :sk, 55, :lap, :key, 'local', 'json.gz', :count, :size, 'test'
                    )
                    """
                ),
                {
                    "sk": SESSION_KEY,
                    "lap": lap_number,
                    "key": storage_key,
                    "count": count,
                    "size": size,
                },
            )


def _cleanup(db_engine):
    with db_engine.begin() as conn:
        conn.execute(
            text("DELETE FROM telemetry_artifacts WHERE session_key = :sk"),
            {"sk": SESSION_KEY},
        )
        conn.execute(
            text("DELETE FROM lap_times WHERE session_key = :sk"), {"sk": SESSION_KEY}
        )
        conn.execute(
            text("DELETE FROM drivers WHERE session_key = :sk"), {"sk": SESSION_KEY}
        )
        conn.execute(
            text("DELETE FROM sessions WHERE session_key = :sk"), {"sk": SESSION_KEY}
        )


def _fake_route(monkeypatch, intent, driver="Sainz", year=2026, gp="Monaco"):
    monkeypatch.setattr(
        orchestrator.llm,
        "route_question",
        lambda q: (
            types.RoutedQuestion(
                intent=types.Intent(intent), driver_name=driver, gp_name=gp, year=year
            ),
            0.0,
        ),
    )


def _fake_compose(monkeypatch, text):
    monkeypatch.setattr(
        orchestrator.llm, "compose_answer", lambda q, e, **kwargs: (text, 0.0)
    )


def test_run_pit_stop_question(app, db_engine, monkeypatch, tmp_path):
    _insert_session_and_driver(db_engine)
    _insert_laps(db_engine)
    _insert_artifacts(db_engine, tmp_path)
    monkeypatch.setattr(settings, "telemetry_artifact_dir", str(tmp_path))
    _fake_route(monkeypatch, "pit_stop_speed_delta")
    _fake_compose(monkeypatch, "Sainz pitted across laps 5 and 6.")

    try:
        answer = orchestrator.run(
            "On which lap did Sainz pit and what was his avg speed before and after?"
        )
        assert answer.intent is types.Intent.PIT_STOP_SPEED_DELTA
        assert answer.refusals == ()
        assert answer.answer == "Sainz pitted across laps 5 and 6."
        assert answer.pit_stop.compound_before == "SOFT"
        assert answer.pit_stop.compound_after == "HARD"
        assert answer.speed_window is not None
        assert answer.speed_window.before_avg_speed_kmh == 215.0
        assert answer.speed_window.after_avg_speed_kmh == 255.0
        assert answer.speed_window.delta_kmh == 40.0
        assert len(answer.trace) == 6
        assert all(r.status == "ok" for r in answer.trace)
        assert [r.tool_name for r in answer.trace] == [
            types.ToolName.RESOLVE_SESSION,
            types.ToolName.RESOLVE_DRIVER,
            types.ToolName.FIND_PIT_STOPS,
            types.ToolName.GET_LAP_TELEMETRY_ARTIFACTS,
            types.ToolName.COMPUTE_SPEED_WINDOW,
            types.ToolName.VERIFY_EVIDENCE,
        ]
    finally:
        _cleanup(db_engine)


def test_run_refuses_when_artifacts_missing(app, db_engine, monkeypatch, tmp_path):
    _insert_session_and_driver(db_engine)
    _insert_laps(db_engine)
    monkeypatch.setattr(settings, "telemetry_artifact_dir", str(tmp_path))
    _fake_route(monkeypatch, "pit_stop_speed_delta")

    try:
        answer = orchestrator.run(
            "On which lap did Sainz pit and what was his avg speed before and after?"
        )
        assert answer.refusals
        assert answer.answer
        assert answer.speed_window is None
        assert any(r.status == "error" for r in answer.trace)
    finally:
        _cleanup(db_engine)


def test_run_unsupported_question(monkeypatch):
    _fake_route(monkeypatch, "unsupported")
    answer = orchestrator.run("What is the weather?")
    assert answer.intent is types.Intent.UNSUPPORTED
    assert answer.refusals == ("unsupported question",)
    assert answer.trace == ()


def test_run_falls_back_to_template_when_llm_down(
    app, db_engine, monkeypatch, tmp_path
):
    _insert_session_and_driver(db_engine)
    _insert_laps(db_engine)
    _insert_artifacts(db_engine, tmp_path)
    monkeypatch.setattr(settings, "telemetry_artifact_dir", str(tmp_path))
    _fake_route(monkeypatch, "pit_stop_speed_delta")
    monkeypatch.setattr(settings, "openrouter_api_key", "")

    try:
        answer = orchestrator.run(
            "On which lap did Sainz pit and what was his avg speed before and after?"
        )
        assert answer.refusals == ()
        assert "lap 5" in answer.answer
        assert "SOFT to HARD" in answer.answer
        assert "215.0" in answer.answer

    finally:
        _cleanup(db_engine)


def test_run_refuses_when_router_fails(monkeypatch):
    def boom(question):
        raise types.LLMError("router down")

    monkeypatch.setattr(orchestrator.llm, "route_question", boom)
    answer = orchestrator.run("Who won the race?")
    assert answer.refusals == ("llm_router_unavailable",)
    assert answer.trace == ()


def test_run_asks_for_missing_driver(monkeypatch):
    _fake_route(monkeypatch, "pit_stop_speed_delta", driver=None)
    answer = orchestrator.run("Where did he pit?")
    assert answer.refusals == ("missing_driver",)
    assert answer.answer
    assert answer.trace == ()


def test_run_asks_for_missing_race(monkeypatch):
    _fake_route(monkeypatch, "pit_stop_speed_delta", gp=None, year=None)
    answer = orchestrator.run("On which lap did Sainz pit?")
    assert answer.refusals == ("missing_race",)
    assert answer.trace == ()


def test_run_pit_stop_resolves_gp_with_suffix(app, db_engine, monkeypatch, tmp_path):
    _insert_session_and_driver(db_engine)
    _insert_laps(db_engine)
    _insert_artifacts(db_engine, tmp_path)
    monkeypatch.setattr(settings, "telemetry_artifact_dir", str(tmp_path))
    # Pass 'Monaco GP' which should resolve to 'Monaco Grand Prix'
    _fake_route(monkeypatch, "pit_stop_speed_delta", gp="Monaco GP")
    _fake_compose(monkeypatch, "Sainz pitted across laps 5 and 6.")

    try:
        answer = orchestrator.run("What was Sainz pit stop speed in Monaco GP 2026?")
        assert answer.refusals == ()
        assert answer.session is not None
        assert answer.session.gp_name == "Monaco Grand Prix"
    finally:
        _cleanup(db_engine)
