"""Task 6 -- Deterministic strategy analysis.

Pure helpers are unit-tested without a DB; the tool itself is exercised against
seeded lap times, a safety-car event, and a rain sample. The contract: every
number is measured or explicitly None -- never an LLM guess.
"""

import pytest
from sqlalchemy import text

from backend.agent import strategy, tools, types

SESSION_KEY = 88010


# ── pure helpers ─────────────────────────────────────────────────────────────


class TestClassifyPitCondition:
    def test_green_when_no_flags(self):
        assert strategy.classify_pit_condition([]) == "green"
        assert strategy.classify_pit_condition([None, ""]) == "green"

    def test_safety_car_outranks_everything(self):
        assert strategy.classify_pit_condition(["YELLOW", "SC"]) == "sc"
        assert strategy.classify_pit_condition(["SAFETY CAR"]) == "sc"

    def test_vsc(self):
        assert strategy.classify_pit_condition(["VSC"]) == "vsc"
        assert strategy.classify_pit_condition(["VIRTUAL SAFETY CAR"]) == "vsc"

    def test_red_and_yellow(self):
        assert strategy.classify_pit_condition(["RED"]) == "red"
        assert strategy.classify_pit_condition(["yellow"]) == "yellow"


class TestPitLossMs:
    def test_computes_in_out_minus_two_clean(self):
        assert strategy.pit_loss_ms(120000, 110000, 100000) == 30000

    def test_missing_input_returns_none(self):
        assert strategy.pit_loss_ms(None, 110000, 100000) is None
        assert strategy.pit_loss_ms(120000, None, 100000) is None
        assert strategy.pit_loss_ms(120000, 110000, None) is None


class TestSummarizePitLosses:
    def test_groups_and_averages(self):
        estimates = strategy.summarize_pit_losses(
            [("green", 20000), ("green", 24000), ("sc", 9000), ("green", None)]
        )
        by_cond = {e.condition: e for e in estimates}
        assert by_cond["green"].sample_count == 2
        assert by_cond["green"].mean_pit_loss_ms == 22000
        assert by_cond["sc"].mean_pit_loss_ms == 9000

    def test_no_samples_is_empty(self):
        assert strategy.summarize_pit_losses([("green", None)]) == ()


class TestBuildScenarios:
    def _scenarios(self, **overrides):
        params = dict(
            current_lap=30,
            total_laps=60,
            remaining_laps=30,
            compound="MEDIUM",
            degradation_slope_ms_per_lap=100.0,
            pit_loss_green_ms=20000,
            pit_loss_vsc_ms=12000,
            pit_loss_sc_ms=8000,
            rain_in_session=False,
            safety_car_periods=1,
        )
        params.update(overrides)
        return strategy.build_scenarios(**params)

    def test_deltas_are_relative_to_stay_out(self):
        scenarios, assumptions, _ = self._scenarios()
        by_name = {s.name: s for s in scenarios}
        assert by_name["stay_out"].projected_delta_ms == 0
        # deg over 30 laps = 3000ms; pit_now_green = 20000 - 3000
        assert by_name["pit_now_green"].projected_delta_ms == 17000
        assert by_name["pit_now_sc"].projected_delta_ms == 5000

    def test_missing_pit_loss_is_not_costed(self):
        scenarios, _, notes = self._scenarios(pit_loss_vsc_ms=None, pit_loss_sc_ms=None)
        by_name = {s.name: s for s in scenarios}
        assert by_name["pit_now_vsc"].projected_delta_ms is None
        assert by_name["pit_now_sc"].projected_delta_ms is None
        assert any("not fully observed" in n for n in notes)

    def test_missing_slope_leaves_degradation_uncosted(self):
        scenarios, assumptions, _ = self._scenarios(degradation_slope_ms_per_lap=None)
        by_name = {s.name: s for s in scenarios}
        assert by_name["pit_now_green"].projected_delta_ms is None
        assert any("degradation" in a for a in assumptions)

    def test_rain_and_safety_car_notes(self):
        _, _, notes = self._scenarios(rain_in_session=True)
        assert any("rainfall" in n for n in notes)
        assert any("safety-car" in n for n in notes)


# ── DB-backed tool ───────────────────────────────────────────────────────────


@pytest.fixture
def strategy_session(app, db_engine):
    """Session with clean laps, one pit stop, and an SC period on lap 5/6."""
    with db_engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO sessions (
                    session_key, year, gp_name, session_type, session_name
                ) VALUES (:sk, 2099, 'Strategy GP', 'R', 'Race')
                ON CONFLICT (session_key) DO NOTHING
                """
            ),
            {"sk": SESSION_KEY},
        )
        conn.execute(
            text(
                """
                INSERT INTO drivers (
                    driver_number, session_key, full_name, abbreviation, team_name, team_colour
                ) VALUES (44, :sk, 'Lewis Hamilton', 'HAM', 'Mercedes', '#00D2BE')
                ON CONFLICT DO NOTHING
                """
            ),
            {"sk": SESSION_KEY},
        )
        for lap in range(1, 11):
            compound = "SOFT" if lap <= 5 else "HARD"
            stint = 1 if lap <= 5 else 2
            pit_in = 123456.0 if lap == 5 else None
            pit_out = 234567.0 if lap == 6 else None
            lap_time = 100000 if lap not in (5, 6) else 130000
            conn.execute(
                text(
                    """
                    INSERT INTO lap_times (
                        session_key, driver_number, lap_number, lap_time_ms,
                        compound, stint, pit_in_time_ms, pit_out_time_ms,
                        is_personal_best, deleted, recorded_at
                    ) VALUES (:sk, 44, :lap, :lt, :compound, :stint, :pin, :pout,
                              false, false, NOW())
                    """
                ),
                {
                    "sk": SESSION_KEY,
                    "lap": lap,
                    "lt": lap_time,
                    "compound": compound,
                    "stint": stint,
                    "pin": pit_in,
                    "pout": pit_out,
                },
            )
        conn.execute(
            text(
                """
                INSERT INTO race_control_events (session_key, category, flag, lap_number)
                VALUES (:sk, 'Flag', 'SC', 5)
                """
            ),
            {"sk": SESSION_KEY},
        )
        conn.execute(
            text(
                """
                INSERT INTO weather_events (session_key, timestamp, lap_number, rainfall)
                VALUES (:sk, NOW(), 1, true)
                """
            ),
            {"sk": SESSION_KEY},
        )
    yield SESSION_KEY
    with db_engine.begin() as conn:
        conn.execute(
            text("DELETE FROM lap_times WHERE session_key = :sk"), {"sk": SESSION_KEY}
        )
        conn.execute(
            text("DELETE FROM race_control_events WHERE session_key = :sk"),
            {"sk": SESSION_KEY},
        )
        conn.execute(
            text("DELETE FROM weather_events WHERE session_key = :sk"),
            {"sk": SESSION_KEY},
        )
        conn.execute(
            text("DELETE FROM drivers WHERE session_key = :sk"), {"sk": SESSION_KEY}
        )
        conn.execute(
            text("DELETE FROM sessions WHERE session_key = :sk"), {"sk": SESSION_KEY}
        )


class TestEstimatePitLoss:
    def test_measures_green_and_sc_loss(self, strategy_session):
        result = tools.estimate_pit_loss(
            types.EstimatePitLossInput(session_key=SESSION_KEY, driver_number=44)
        )
        conditions = {e.condition for e in result.estimates}
        assert "sc" in conditions
        assert result.baseline_clean_lap_ms == 100000
        assert all(e.sample_count >= 1 for e in result.estimates)

    def test_empty_session_raises(self, db_engine, strategy_session):
        with pytest.raises(types.NotFoundError):
            tools.estimate_pit_loss(
                types.EstimatePitLossInput(session_key=999123, driver_number=44)
            )


class TestCompareStrategyScenarios:
    def test_returns_bounded_scenarios(self, strategy_session):
        result = tools.compare_strategy_scenarios(
            types.CompareStrategyScenariosInput(
                session_key=SESSION_KEY, driver_number=44, current_lap=7
            )
        )
        assert result.session_key == SESSION_KEY
        names = {s.name for s in result.scenarios}
        assert {
            "stay_out",
            "pit_now_green",
            "pit_now_vsc",
            "pit_now_sc",
            "extend_stint",
        } <= names
        assert result.rain_in_session is True
        assert result.safety_car_periods >= 1
        assert result.assumptions  # always explains itself

    def test_missing_driver_laps_raises(self, db_engine, strategy_session):
        with pytest.raises(types.NotFoundError):
            tools.compare_strategy_scenarios(
                types.CompareStrategyScenariosInput(
                    session_key=SESSION_KEY, driver_number=99
                )
            )
