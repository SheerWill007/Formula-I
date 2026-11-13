import pytest

from backend.analyst.checker import (
    annotate,
    evidence_values,
    extract_claims,
    find_unverified,
)
from backend.analyst.client import Reply, ToolCall
from backend.analyst.loop import run_analyst
from backend.analyst.tools import ToolOutput


def _tool(text):
    return {"role": "tool", "tool_call_id": "c", "content": text}


def test_only_decimals_and_united_numbers_are_claims():
    text = "In 2026, stint 2 on lap 18: 22.5 s, +0.112 s/lap, r2 0.72, 305 km/h, 38 °C.\n1. Done"
    assert [c.raw for c in extract_claims(text)] == [
        "22.5 s",
        "+0.112 s/lap",
        "0.72",
        "305 km/h",
        "38 °C",
    ]


def test_file_names_and_code_blocks_are_not_claims():
    assert extract_claims("See laps_11388_44.json\n```\nx = 1.5\n```") == []


def test_lap_times_become_seconds():
    [claim] = extract_claims("Pole was 1:29.123")
    assert claim.value == pytest.approx(89.123)


@pytest.mark.parametrize(
    "answer,output",
    [
        ("Deg is +0.112 s/lap", "2 SOFT +0.112 s/lap r2=0.72"),
        ("Deg is 0.11 s/lap", "2 SOFT +0.112 s/lap"),  # rounded in the answer
        ("It fell by 0.035 s/lap", "stint 1 -0.035 s/lap"),  # sign may be reworded
        ("Slope 126.5 ms per lap", "slope 0.1265"),  # unit conversion
        ("Lap of 1:29.123", "lap_time_ms 89123"),
        ("Humidity 55%", "humidity 0.55"),
    ],
)
def test_supported_numbers_pass(answer, output):
    assert find_unverified(answer, [_tool(output)]) == []


def test_invented_number_is_flagged_once():
    assert find_unverified("Loss 31.7 s, again 31.7 s", [_tool("loss 22.5 s")]) == [
        "31.7 s"
    ]


def test_the_british_gp_case_a_sample_row_is_not_evidence():
    # A real run reported the first weather row as the race average.
    loader = (
        'weather.json: 156 rows. First row: {"track_temp_c": 37.9, "rainfall": false}'
    )
    assert find_unverified("Average track temperature 37.9 °C", [_tool(loader)]) == [
        "37.9 °C"
    ]
    computed = _tool("OK (0.4s)\nstdout:\navg track 40.0")
    assert (
        find_unverified("Average track temperature 40.0 °C", [_tool(loader), computed])
        == []
    )


def test_failed_scripts_and_run_durations_are_not_evidence():
    assert 3.3 not in evidence_values([_tool("ERROR (0.4s)\nstderr: value 3.3")])
    assert 0.46 not in evidence_values([_tool("OK (0.46s)\nstdout:\n1")])


def test_numbers_from_the_question_and_the_fuel_assumption_are_allowed():
    messages = [{"role": "user", "content": "What if pit loss were 18.5 s?"}]
    assert find_unverified("At 18.5 s, using 0.05 s/lap fuel", messages) == []
    assert find_unverified("r2 is under 0.3, so noisy", []) == []


def test_feedback_text_does_not_count_as_evidence():
    messages = [{"role": "user", "content": "Review feedback, please revise: 31.7 s"}]
    assert find_unverified("31.7 s", messages) == ["31.7 s"]


def test_annotate_keeps_the_answer_and_lists_numbers():
    out = annotate("Answer.", ["31.7 s"])
    assert out.startswith("Answer.") and "Unverified" in out and "31.7 s" in out


class ScriptedLLM:
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    def chat(self, messages, tools):
        self.calls.append(list(messages))
        return self.replies.pop(0)


class Box:
    def call(self, name, args):
        return ToolOutput("OK (0.1s)\nstdout:\navg 40.0", title=name)


def _final(id_, text):
    return Reply("", (ToolCall(id_, "final_answer", '{"markdown": "%s"}' % text),))


def _script():
    return Reply("", (ToolCall("c0", "run_python", '{"code": "print(40.0)"}'),))


def test_loop_sends_an_untraceable_answer_back_and_accepts_the_fix():
    llm = ScriptedLLM(
        [_script(), _final("c1", "Avg 37.9 C"), _final("c2", "Avg 40.0 C")]
    )
    result = run_analyst("q", llm=llm, toolbox=Box(), check_numbers=True)
    assert result.answer == "Avg 40.0 C" and result.unverified == []
    assert "37.9" in llm.calls[2][-1]["content"]
    assert any(
        e["type"] == "thought" and "Number check" in e["text"] for e in result.events
    )


def test_loop_labels_numbers_the_model_still_cannot_support():
    llm = ScriptedLLM(
        [_script(), _final("c1", "Avg 37.9 C"), _final("c2", "Avg 37.9 C")]
    )
    result = run_analyst("q", llm=llm, toolbox=Box(), check_numbers=True)
    assert result.unverified == ["37.9"]
    assert "Unverified" in result.answer
    assert len(llm.calls) == 3  # one revision only, so it cannot loop forever
    assert [e for e in result.events if e["type"] == "final"][0]["unverified"]
