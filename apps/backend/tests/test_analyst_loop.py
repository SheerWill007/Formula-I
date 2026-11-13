"""Analyst loop tests with a scripted model and a stub toolbox (no network, no Docker)."""

from backend.analyst.client import AnalystLLMError, Reply, ToolCall
from backend.analyst.loop import run_analyst
from backend.analyst.tools import ToolOutput


class ScriptedLLM:
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []  # (messages snapshot, tools)

    def chat(self, messages, tools):
        self.calls.append((list(messages), tools))
        item = self.replies.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class StubToolBox:
    def __init__(self, outputs=None):
        self.outputs = outputs or {}
        self.called = []

    def call(self, name, args):
        self.called.append((name, args))
        return self.outputs.get(name, ToolOutput(f"{name} ok", title=name))


def _call(id_, name, args="{}"):
    return ToolCall(id_, name, args)


def _types(result):
    return [e["type"] for e in result.events]


def test_tool_then_final_answer_emits_ordered_events_and_sums_cost():
    chart = {"title": "Deg", "option": {"series": []}}
    llm = ScriptedLLM(
        [
            Reply(
                "Load laps first.",
                (_call("c1", "load_laps", '{"session_key": 1}'),),
                cost_usd=0.001,
            ),
            Reply(
                "",
                (_call("c2", "run_python", '{"code": "# fit\\nprint(1)"}'),),
                cost_usd=0.002,
            ),
            Reply(
                "",
                (_call("c3", "final_answer", '{"markdown": "Deg is 0.08 s/lap."}'),),
                cost_usd=0.001,
            ),
        ]
    )
    box = StubToolBox({"run_python": ToolOutput("OK", title="fit", charts=[chart])})
    seen = []
    result = run_analyst("q", llm=llm, toolbox=box, emit=seen.append)

    assert result.answer == "Deg is 0.08 s/lap."
    assert result.cost_usd == 0.004
    assert _types(result) == [
        "run_start", "thought", "tool_start", "tool_end",
        "tool_start", "tool_end", "chart", "final",
    ]  # fmt: skip
    assert [e["seq"] for e in result.events] == list(range(len(result.events)))
    assert seen == result.events
    assert result.charts == [chart]
    assert box.called[0] == ("load_laps", {"session_key": 1})


def test_plain_text_reply_is_accepted_as_the_answer():
    llm = ScriptedLLM([Reply("Just an answer.")])
    result = run_analyst("hi", llm=llm, toolbox=StubToolBox())
    assert result.answer == "Just an answer."
    assert _types(result) == ["run_start", "final"]


def test_budget_keeps_room_for_a_closing_answer():
    llm = ScriptedLLM(
        [
            Reply("", (_call("c1", "load_laps"),), cost_usd=0.01),
            Reply("Closing answer.", cost_usd=0.01),
        ]
    )
    result = run_analyst("q", llm=llm, toolbox=StubToolBox(), max_cost_usd=0.03)
    assert result.answer == "Closing answer." and not result.incomplete
    assert llm.calls[-1][1] is None  # no tools offered on the closing turn
    assert "budget" in llm.calls[-1][0][-1]["content"].lower()
    assert result.cost_usd <= 0.03


def test_no_call_is_made_once_the_budget_is_gone_and_results_are_shown():
    llm = ScriptedLLM(
        [Reply("", (_call("c1", "run_python", '{"code": "print(1)"}'),), cost_usd=0.05)]
    )
    box = StubToolBox(
        {"run_python": ToolOutput("OK (0.1s)\nstdout:\n0.112", title="fit")}
    )
    result = run_analyst("q", llm=llm, toolbox=box, max_cost_usd=0.03)
    assert len(llm.calls) == 1
    assert result.incomplete and "0.112" in result.answer


def test_empty_closing_answer_shows_results_instead_of_nothing():
    llm = ScriptedLLM(
        [
            Reply(
                "", (_call("c1", "run_python", '{"code": "print(1)"}'),), cost_usd=0.001
            ),
            Reply(""),
            Reply(""),
        ]
    )
    box = StubToolBox(
        {"run_python": ToolOutput("OK (0.1s)\nstdout:\n0.112", title="fit")}
    )
    result = run_analyst("q", llm=llm, toolbox=box)
    assert (
        result.incomplete
        and "Analysis incomplete" in result.answer
        and "0.112" in result.answer
    )


def test_with_no_results_the_limit_is_stated_plainly():
    result = run_analyst(
        "q", llm=ScriptedLLM([Reply(""), Reply("")]), toolbox=StubToolBox()
    )
    assert result.incomplete and "limit" in result.answer


def test_step_limit_forces_a_final_answer():
    llm = ScriptedLLM(
        [
            Reply("", (_call("a", "load_laps"),)),
            Reply("", (_call("b", "load_laps"),)),
            Reply("Done."),
        ]
    )
    result = run_analyst("q", llm=llm, toolbox=StubToolBox(), max_steps=2)
    assert result.answer == "Done."
    assert result.steps == 2


def test_llm_failure_becomes_an_error_event_not_an_exception():
    llm = ScriptedLLM([AnalystLLMError("boom")])
    result = run_analyst("q", llm=llm, toolbox=StubToolBox())
    assert result.error == "boom"
    assert "unavailable" in result.answer
    assert _types(result)[-1] == "error"


def test_bad_json_arguments_become_empty_args():
    llm = ScriptedLLM(
        [
            Reply("", (_call("c1", "load_laps", "{not json"),)),
            Reply("", (_call("c2", "final_answer", '{"markdown":"x"}'),)),
        ]
    )
    box = StubToolBox()
    run_analyst("q", llm=llm, toolbox=box)
    assert box.called == [("load_laps", {})]


def test_failed_tool_is_reported_to_the_model():
    llm = ScriptedLLM(
        [
            Reply("", (_call("c1", "run_python", '{"code":"1/0"}'),)),
            Reply("", (_call("c2", "final_answer", '{"markdown":"x"}'),)),
        ]
    )
    box = StubToolBox({"run_python": ToolOutput("ERROR boom", ok=False, title="calc")})
    result = run_analyst("q", llm=llm, toolbox=box)
    end = next(e for e in result.events if e["type"] == "tool_end")
    assert end["ok"] is False
    tool_msgs = [m for m in llm.calls[1][0] if m["role"] == "tool"]
    assert tool_msgs[0]["content"] == "ERROR boom"


def test_reviewer_can_send_the_answer_back_once():
    llm = ScriptedLLM(
        [
            Reply("", (_call("c1", "final_answer", '{"markdown":"first"}'),)),
            Reply("", (_call("c2", "final_answer", '{"markdown":"second"}'),)),
        ]
    )
    verdicts = iter(["numbers are unsourced", None])
    result = run_analyst(
        "q", llm=llm, toolbox=StubToolBox(), reviewer=lambda a, m: next(verdicts)
    )
    assert result.answer == "second"
    second_turn = llm.calls[1][0]
    # every assistant tool call must be answered by a tool message before the next turn
    assert second_turn[-3]["role"] == "assistant"
    assert second_turn[-2] == {
        "role": "tool",
        "tool_call_id": "c1",
        "content": "answer recorded",
    }
    assert second_turn[-1]["role"] == "user"


def test_a_crashing_emit_callback_does_not_stop_the_run():
    def bad_emit(_event):
        raise RuntimeError("client gone")

    result = run_analyst(
        "q", llm=ScriptedLLM([Reply("ok")]), toolbox=StubToolBox(), emit=bad_emit
    )
    assert result.answer == "ok"


def test_empty_final_answer_falls_back_to_a_plain_text_answer():
    llm = ScriptedLLM(
        [
            Reply("", (_call("c1", "final_answer", "{broken json"),)),
            Reply("Plain text answer."),
        ]
    )
    result = run_analyst("q", llm=llm, toolbox=StubToolBox())
    assert result.answer == "Plain text answer."
    forced = llm.calls[1]
    assert forced[1] is None  # the retry offers no tools
    assert "plain text" in forced[0][-2]["content"]  # the tool message explains why


def test_runtime_limit_forces_a_final_answer():
    llm = ScriptedLLM([Reply("Out of time answer.")])
    result = run_analyst("q", llm=llm, toolbox=StubToolBox(), max_runtime_s=0.0)
    assert result.answer == "Out of time answer."
    assert llm.calls[0][1] is None


class SlowBox:
    """Each loader takes 0.2 s; records when calls overlapped."""

    def __init__(self):
        import threading

        self.lock = threading.Lock()
        self.active = 0
        self.max_active = 0
        self.order = []

    def call(self, name, args):
        import time

        with self.lock:
            self.active += 1
            self.max_active = max(self.max_active, self.active)
            self.order.append(name)
        time.sleep(0.2)
        with self.lock:
            self.active -= 1
        return ToolOutput(f"{name} done", title=name)


def test_independent_tools_in_one_turn_run_in_parallel_with_ordered_messages():
    calls = (
        _call("a", "load_laps", '{"session_key": 1, "driver": "HAM"}'),
        _call("b", "load_laps", '{"session_key": 1, "driver": "RUS"}'),
        _call("c", "load_context", '{"session_key": 1}'),
    )
    llm = ScriptedLLM(
        [
            Reply("Load everything.", calls),
            Reply("", (_call("d", "final_answer", '{"markdown": "ok"}'),)),
        ]
    )
    box = SlowBox()
    result = run_analyst("q", llm=llm, toolbox=box)
    assert box.max_active == 3  # all three overlapped
    assert result.answer == "ok"
    starts = [e["call_id"] for e in result.events if e["type"] == "tool_start"]
    ends = [e["call_id"] for e in result.events if e["type"] == "tool_end"]
    assert starts == ["a", "b", "c"] and sorted(ends) == ["a", "b", "c"]
    assert (
        result.events.index(next(e for e in result.events if e["type"] == "tool_end"))
        > 3
    )  # all started first
    assert [e["seq"] for e in result.events] == list(range(len(result.events)))
    tool_msgs = [m["tool_call_id"] for m in llm.calls[1][0] if m["role"] == "tool"]
    assert tool_msgs == ["a", "b", "c"]  # one reply per call, in call order


def test_run_python_waits_for_the_loaders_of_its_turn():
    calls = (
        _call("p", "run_python", '{"code": "print(1)"}'),
        _call("l", "load_laps", '{"session_key": 1}'),
    )
    llm = ScriptedLLM(
        [
            Reply("", calls),
            Reply("", (_call("f", "final_answer", '{"markdown": "ok"}'),)),
        ]
    )
    box = SlowBox()
    run_analyst("q", llm=llm, toolbox=box)
    assert box.order == ["load_laps", "run_python"]
    assert box.max_active == 1
