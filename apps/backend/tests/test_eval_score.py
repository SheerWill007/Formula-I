"""Unit tests for the eval scorer (pure, no DB, no LLM)."""

import json

import pytest

from evals import score


def _q(**overrides):
    base = {
        "id": "t-01",
        "tier": "supported",
        "question": "q",
        "must_mention": ["degradation"],
        "numeric_checks": [{"name": "deg", "unit": "s/lap", "min": 0.0, "max": 0.6}],
        "needs_chart": False,
        "expect_refusal": False,
        "rubric": [],
    }
    base.update(overrides)
    return base


def test_real_question_file_is_valid():
    questions = score.load_questions()
    assert len(questions) >= 20
    assert {q["tier"] for q in questions} == set(score.TIERS)


def test_extract_numbers_reads_value_before_unit():
    assert score.extract_numbers("deg was 0.08 s/lap then 0,12 s/lap", "s/lap") == [
        0.08,
        0.12,
    ]
    assert score.extract_numbers("no units here 0.08", "s/lap") == []


def test_extract_numbers_converts_aliases_to_canonical_unit():
    assert score.extract_numbers("slope -126.51 ms per lap", "s/lap") == [
        pytest.approx(-0.12651)
    ]
    assert score.extract_numbers("slope −0.08 s per lap", "s/lap") == [-0.08]
    assert score.extract_numbers("top speed 313 kph", "km/h") == [313.0]


def test_seconds_unit_does_not_match_inside_other_units():
    assert score.extract_numbers("deg 0.08 s/lap", "s") == []
    assert score.extract_numbers("pit loss 22.5 s under green", "s") == [22.5]
    assert score.extract_numbers("gap 1200 ms", "s") == [pytest.approx(1.2)]


def test_alias_value_is_range_checked_after_conversion():
    # -126 ms/lap is -0.126 s/lap: outside [0, 0.6], so it must fail, not be missed
    run = {
        "answer": "Degradation slope was -126.51 ms per lap.",
        "refusals": [],
        "trace": [],
    }
    result = score.score_run(_q(), run)
    assert not result.passed
    assert any("outside" in f for f in result.failures)


def test_admitting_missing_evidence_fails_even_if_other_checks_pass():
    run = {
        "answer": "Degradation 0.08 s/lap. Piastri: not provided in the gathered evidence.",
        "refusals": [],
        "trace": [],
    }
    result = score.score_run(_q(), run)
    assert not result.passed
    assert any("missing evidence" in f for f in result.failures)


def test_good_answer_passes():
    run = {"answer": "Tyre degradation was 0.08 s/lap.", "refusals": [], "trace": []}
    assert score.score_run(_q(), run).passed


def test_out_of_range_number_fails():
    run = {"answer": "Degradation was 3.5 s/lap.", "refusals": [], "trace": []}
    result = score.score_run(_q(), run)
    assert not result.passed
    assert any("outside" in f for f in result.failures)


def test_missing_number_fails():
    run = {"answer": "There was some degradation.", "refusals": [], "trace": []}
    assert not score.score_run(_q(), run).passed


def test_refusal_on_answerable_question_fails():
    run = {"answer": "I could not answer", "refusals": ["missing_driver"], "trace": []}
    assert not score.score_run(_q(must_mention=[], numeric_checks=[]), run).passed


def test_trap_passes_only_when_refused():
    trap = _q(tier="trap", expect_refusal=True, must_mention=[], numeric_checks=[])
    assert score.score_run(trap, {"answer": "x", "refusals": ["no data"]}).passed
    assert not score.score_run(trap, {"answer": "It was 1:29.1", "refusals": []}).passed


def test_tool_error_fails_run():
    run = {
        "answer": "Degradation was 0.08 s/lap.",
        "refusals": [],
        "trace": [{"status": "error"}],
    }
    assert not score.score_run(_q(), run).passed


def test_summary_groups_by_tier():
    a = score.QuestionScore(
        id="a", tier="supported", passed=True, refused=False, latency_s=2
    )
    b = score.QuestionScore(
        id="b", tier="trap", passed=False, refused=False, latency_s=4
    )
    summary = score.summarize([a, b])
    assert summary["overall"]["pass_rate"] == 0.5
    assert summary["supported"]["passed"] == 1
    assert summary["analytical"] == {"n": 0}


def test_validation_rejects_trap_without_refusal(tmp_path):
    path = tmp_path / "q.json"
    path.write_text(json.dumps({"questions": [_q(tier="trap", expect_refusal=False)]}))
    with pytest.raises(ValueError):
        score.load_questions(path)


def test_recovered_tool_error_is_counted_but_does_not_fail_the_run():
    run = {
        "answer": "Degradation was 0.08 s/lap.",
        "refusals": [],
        "trace": [{"status": "error"}, {"status": "ok"}],
    }
    result = score.score_run(_q(), run)
    assert result.passed
    assert result.checks["tool_error_count"] == 1


def test_a_polite_non_answer_does_not_pass_just_because_it_mentions_the_topic():
    run = {
        "answer": "I was unable to determine whether there was a degradation stint issue.",
        "refusals": [],
        "trace": [],
    }
    q = _q(numeric_checks=[])
    assert not score.score_run(q, run).passed


def _facts_q(**facts):
    return _q(must_mention=[], facts=facts)


def test_facts_replace_range_and_tool_checks():
    q = _facts_q(
        numbers=[{"name": "deg", "unit": "s/lap", "value": 0.112, "tol": 0.005}]
    )
    run = {
        "answer": "Raw -0.5 s/lap, corrected +0.112 s/lap.",
        "refusals": [],
        "trace": [{"status": "error"}],
    }
    assert score.score_run(
        q, run
    ).passed  # raw value and a failed last call do not matter


def test_wrong_fact_fails_even_if_it_looks_plausible():
    q = _facts_q(numbers=[{"name": "temp", "unit": "°C", "value": 40.0, "tol": 0.1}])
    assert not score.score_run(
        q, {"answer": "Average 37.9 °C", "refusals": [], "trace": []}
    ).passed


def test_confident_contradiction_of_the_data_fails():
    q = _facts_q(any_of=[["deployed"]], forbidden=["no safety car"])
    wrong = {"answer": "There was no safety car.", "refusals": [], "trace": []}
    right = {
        "answer": "The safety car was deployed twice.",
        "refusals": [],
        "trace": [],
    }
    assert not score.score_run(q, wrong).passed
    assert score.score_run(q, right).passed


def test_an_incomplete_run_does_not_pass():
    run = {
        "answer": "**Analysis incomplete.** degradation",
        "refusals": [],
        "trace": [],
    }
    assert not score.score_run(_q(numeric_checks=[]), run).passed


def test_lap_times_written_as_minutes_are_read_as_seconds():
    assert score.extract_numbers("Fastest was 1:37.221 and 99.4 s", "s") == [
        97.221,
        99.4,
    ]
    assert score.extract_numbers("at 12:30 pm", "s") == [
        750.0
    ]  # a clock time is a rare false match


def test_facts_can_require_an_order():
    q = _facts_q(in_order=[["medium", "hard"]])
    ok = {"answer": "He used Medium then Hard.", "refusals": [], "trace": []}
    bad = {"answer": "Hard first, then Medium.", "refusals": [], "trace": []}
    assert score.score_run(q, ok).passed and not score.score_run(q, bad).passed


def test_simple_tier_exists_and_has_facts_for_every_question():
    simple = [x for x in score.load_questions() if x["tier"] == "simple"]
    assert len(simple) >= 10 and all(x.get("facts") for x in simple)
