"""Golden evaluation set (T0.1) -- regression floor for every future planner.

Each question from golden_set.json is routed through the CURRENT planner (the
hardcoded build_dag) and we assert the tool sequence overlaps the expected one
-- PURE, no DB needed: build_dag only reads the routed intent. One
representative DAG (pit_stop_speed_delta, the most complex) runs end-to-end
through _execute_dag to prove the evidence gate still passes. This is the
baseline T1.1's LLM planner must at least match.
"""

import gzip
import json
from pathlib import Path

import pytest
from sqlalchemy import text

from backend.agent import orchestrator, types
from backend.config import settings

GOLDEN_SET = json.loads((Path(__file__).parent / "golden_set.json").read_text())[
    "questions"
]
TOOL_OVERLAP_THRESHOLD = 0.5

SESSION_KEY = 99998  # unique across the suite; no collision with other test files


# ── DB helpers for the evidence-gate spot-check ─────────────────────────────


def _insert_session_and_driver(db_engine):
    """Seed a minimal session + driver so tools don't raise NotFoundError."""
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
                INSERT INTO drivers (driver_number, session_key, full_name,
                                     abbreviation, team_name, team_colour)
                VALUES (44, :sk, 'Lewis Hamilton', 'HAM', 'Mercedes', '#00D2BE')
                """
            ),
            {"sk": SESSION_KEY},
        )


def _insert_laps(db_engine, n=10):
    """Laps 1..n with a pit stop on lap 5/6, SOFT -> HARD."""
    with db_engine.begin() as conn:
        for lap in range(1, n + 1):
            compound = "SOFT" if lap <= 5 else "HARD"
            pit_in = 123456.0 if lap == 5 else None
            pit_out = 234567.0 if lap == 6 else None
            conn.execute(
                text(
                    """
                    INSERT INTO lap_times (
                        session_key, driver_number, lap_number, lap_time_ms,
                        compound, pit_in_time_ms, pit_out_time_ms,
                        is_personal_best, deleted, recorded_at
                    ) VALUES (:sk, 44, :lap, 100000, :compound, :pit_in, :pit_out,
                              false, false, NOW())
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
    """Write a real artifact file for the before/after speed windows."""
    storage_key = f"telemetry/session_{SESSION_KEY}/driver_44/lap_{lap_number}.json.gz"
    path = Path(tmp_path) / storage_key
    path.parent.mkdir(parents=True, exist_ok=True)
    samples = [{"speed_kmh": s, "distance_m": 100.0} for s in speeds]
    with gzip.open(path, "wb") as f:
        f.write(
            json.dumps(
                {
                    "session_key": SESSION_KEY,
                    "driver_number": 44,
                    "lap_number": lap_number,
                    "samples": samples,
                }
            ).encode("utf-8")
        )
    return storage_key, path.stat().st_size


def _insert_artifacts(db_engine, tmp_path):
    """Artifacts for the before window (2,3,4) and after window (7,8,9) -- the
    laps _pit_laps() picks around the lap 5/6 stop with the default window."""
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
                        :sk, 44, :lap, :key, 'local', 'json.gz', :count, :size, 'test'
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


def _routed(intent, **kw):
    """Build a RoutedQuestion like the existing test_agent_dag helpers."""
    base = dict(driver_name="Hamilton", gp_name="Monaco", year=2026)
    base.update(kw)
    return types.RoutedQuestion(intent=types.Intent(intent), **base)


def _tool_sequence(dag):
    """Return the tool names of a DAG in deterministic topological order."""
    order = orchestrator.topo_sort(dag)
    node_map = {n.id: n for n in dag.nodes}
    return [node_map[nid].tool_name.value for nid in order]


def _tool_overlap(actual, expected):
    """What fraction of the expected tools appear in the actual sequence? (0.0-1.0)"""
    actual_set = set(actual)
    expected_set = set(expected)
    if not expected_set:
        return 1.0
    return len(actual_set & expected_set) / len(expected_set)


# ── evidence-gate spot-check (DB-backed) ────────────────────────────────────


def test_evidence_gate_passes_for_representative_dag(
    app, db_engine, monkeypatch, tmp_path
):
    """The most complex hardcoded DAG executes end-to-end and its evidence gate
    passes -- the recall baseline every future planner must at least match. A
    spot-check, not per golden question: running all 46 end-to-end would be slow
    and the hardcoded planner is deterministic anyway."""
    _insert_session_and_driver(db_engine)
    _insert_laps(db_engine)
    _insert_artifacts(db_engine, tmp_path)
    monkeypatch.setattr(settings, "telemetry_artifact_dir", str(tmp_path))
    try:
        routed = _routed("pit_stop_speed_delta")
        dag = orchestrator.build_dag(routed)
        trace, env, failed_ids = orchestrator._execute_dag(dag, routed, None)
        verify = env["verify"]

        assert verify is not None, "expected a verify node in the DAG output"
        assert verify.passed, f"evidence gate refused: {verify.refusal_reason}"
        assert failed_ids == set(), f"unexpected failed nodes: {failed_ids}"
    finally:
        _cleanup(db_engine)


# ── the golden-set checks (pure -- no DB) ───────────────────────────────────


class TestGoldenSet:
    """Run every question from golden_set.json through the current planner."""

    @pytest.mark.parametrize(
        "entry",
        GOLDEN_SET,
        ids=[e["question"][:60] for e in GOLDEN_SET],
    )
    def test_build_dag_tool_sequence(self, entry):
        """The hardcoded planner picks the right tools for this question."""
        routed = _routed(
            entry["expected_intent"],
            **{k: v for k, v in entry.get("routed_params", {}).items()},
        )
        dag = orchestrator.build_dag(routed)
        actual_tools = _tool_sequence(dag)
        overlap = _tool_overlap(actual_tools, entry["expected_tools"])

        assert overlap >= TOOL_OVERLAP_THRESHOLD, (
            f"Tool overlap {overlap:.0%} below threshold {TOOL_OVERLAP_THRESHOLD:.0%}\n"
            f"  question: {entry['question']}\n"
            f"  expected: {entry['expected_tools']}\n"
            f"  actual:   {actual_tools}"
        )

    @pytest.mark.parametrize(
        "entry",
        GOLDEN_SET,
        ids=[e["question"][:60] for e in GOLDEN_SET],
    )
    def test_golden_question_has_expected_intent(self, entry):
        """Verify our golden set entries have valid intents."""
        assert entry["expected_intent"] in [i.value for i in types.Intent]

    def test_golden_set_size(self):
        """Sanity check: we have enough questions to be useful."""
        assert len(GOLDEN_SET) >= 30, (
            f"Golden set too small: {len(GOLDEN_SET)} questions"
        )
        assert len(GOLDEN_SET) <= 60, (
            f"Golden set too large: {len(GOLDEN_SET)} questions"
        )

    def test_golden_set_covers_all_intents(self):
        """Every non-UNSUPPORTED intent appears at least 3 times."""
        covered = {}
        for entry in GOLDEN_SET:
            intent = entry["expected_intent"]
            covered[intent] = covered.get(intent, 0) + 1
        for intent in types.Intent:
            if intent == types.Intent.UNSUPPORTED:
                continue
            assert intent.value in covered, (
                f"Intent {intent.value} not covered in golden set"
            )
            assert covered[intent.value] >= 3, (
                f"Intent {intent.value} only has {covered[intent.value]} questions, need >= 3"
            )
