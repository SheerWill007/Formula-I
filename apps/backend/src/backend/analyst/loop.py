"""The analyst loop: the model picks tools, sees results, and decides what to do next.

One engine, a dynamic graph: every tool call is a node, calls issued in the
same model turn are siblings, and the next turn depends on all of them. The
loop reports progress as plain event dicts (see EVENT TYPES) so the same
stream drives the live canvas, the persisted run and replay.

EVENT TYPES (all carry seq and t_ms):
  run_start{question}  thought{round,text}  tool_start{round,call_id,tool,title,preview}
  tool_end{round,call_id,ok,duration_ms,summary,title,preview}
  chart{round,call_id,title,option}  final{markdown,cost_usd,steps}  error{message}
"""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from backend.analyst import checker
from backend.analyst.client import AnalystLLMError, ChatClient, Reply
from backend.analyst.prompt import SYSTEM_PROMPT
from backend.analyst.tools import TOOL_SCHEMAS, ToolBox, describe_call, parse_args

Emit = Callable[[dict], None]
# Extension point: return feedback text to make the model revise, or None to accept.
Reviewer = Callable[[str, list[dict]], str | None]

_FORCE_FINAL = (
    "Step or cost budget reached. Write the final answer now using only what you "
    "computed. Say clearly what you could not establish. Do not call tools."
)


@dataclass
class AnalystResult:
    answer: str
    cost_usd: float
    steps: int
    events: list[dict] = field(default_factory=list)
    charts: list[dict] = field(default_factory=list)
    error: str | None = None
    unverified: list[str] = field(default_factory=list)
    incomplete: bool = False


def _assistant_message(reply: Reply) -> dict:
    message: dict = {"role": "assistant", "content": reply.content or None}
    if reply.tool_calls:
        message["tool_calls"] = [
            {
                "id": c.id,
                "type": "function",
                "function": {"name": c.name, "arguments": c.arguments},
            }
            for c in reply.tool_calls
        ]
    return message


def _partial_answer(messages: list[dict]) -> str:
    """When no conclusion was written, show the latest results instead of nothing."""
    results = [
        m["content"]
        for m in messages
        if m.get("role") == "tool"
        and str(m.get("content", "")).startswith(("OK", "Race of"))
    ]
    if not results:
        return "I could not complete this analysis before reaching its limit."
    body = "\n\n".join(r[:1500] for r in results[-2:])
    return (
        "**Analysis incomplete.** The run reached its limit before writing a conclusion. "
        f"These are the last results it computed, unreviewed:\n\n```text\n{body}\n```"
    )


def run_analyst(
    question: str,
    *,
    llm: ChatClient,
    toolbox: ToolBox,
    emit: Emit | None = None,
    max_steps: int = 10,
    max_cost_usd: float = 0.03,
    max_runtime_s: float = 150.0,
    reviewer: Reviewer | None = None,
    check_numbers: bool = False,
) -> AnalystResult:
    started = time.perf_counter()
    events: list[dict] = []
    charts: list[dict] = []

    lock = threading.Lock()  # tools of one turn report from several threads

    def record(type_: str, **data) -> None:
        with lock:
            event = {
                "type": type_,
                "seq": len(events),
                "t_ms": round((time.perf_counter() - started) * 1000),
            }
            event.update(data)
            events.append(event)
            if emit:
                try:
                    emit(event)
                except Exception:  # a broken consumer must never kill the run
                    pass

    messages: list[dict] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": question},
    ]
    cost = 0.0
    answer: str | None = None
    reviewed = False
    numbers_checked = False
    last_call_cost = 0.0
    incomplete = False
    bad_final = False  # the model produced an unusable final_answer
    rounds = 0
    record("run_start", question=question)

    try:
        while (
            answer is None
            and not bad_final
            and rounds < max_steps
            # keep room for this call and a closing one; calls grow as context grows
            and cost + 2 * last_call_cost < max_cost_usd
            and time.perf_counter() - started < max_runtime_s
        ):
            reply = llm.chat(messages, TOOL_SCHEMAS)
            cost += reply.cost_usd
            last_call_cost = reply.cost_usd
            messages.append(_assistant_message(reply))

            if not reply.tool_calls:
                answer = reply.content.strip() or None
                if answer is None:
                    break
            else:
                if reply.content.strip():
                    record("thought", round=rounds, text=reply.content.strip())
                pending: list[tuple] = []
                for call in reply.tool_calls:
                    args = parse_args(call.arguments)
                    if call.name == "final_answer":
                        answer = (
                            str(args.get("markdown", "")).strip()
                            or reply.content.strip()
                            or None
                        )
                        messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": call.id,
                                "content": "answer recorded"
                                if answer
                                else "final_answer was empty or invalid JSON; write the answer as plain text",
                            }
                        )
                        if answer is None:
                            bad_final = True
                        continue
                    title, preview = describe_call(call.name, args)
                    record(
                        "tool_start",
                        round=rounds,
                        call_id=call.id,
                        tool=call.name,
                        title=title,
                        preview=preview,
                    )
                    pending.append((call, args, title, preview))

                def run_one(item: tuple, turn: int = rounds) -> tuple:
                    call, args, title, preview = item
                    t0 = time.perf_counter()
                    out = toolbox.call(call.name, args)
                    record(
                        "tool_end", round=turn, call_id=call.id, ok=out.ok,
                        duration_ms=round((time.perf_counter() - t0) * 1000),
                        summary=out.text[:300], title=out.title or title, preview=out.preview or preview,
                    )  # fmt: skip
                    for chart in out.charts:
                        charts.append(chart)
                        record(
                            "chart",
                            round=turn,
                            call_id=call.id,
                            title=chart.get("title", "chart"),
                            option=chart.get("option", {}),
                        )
                    return call.id, out

                # Independent loaders run together. run_python shares replayed state, so
                # it runs afterwards, one at a time.
                loaders = [item for item in pending if item[0].name != "run_python"]
                scripts = [item for item in pending if item[0].name == "run_python"]
                results: dict[str, object] = {}
                if len(loaders) > 1:
                    with ThreadPoolExecutor(max_workers=min(4, len(loaders))) as pool:
                        results.update(pool.map(run_one, loaders))
                else:
                    results.update(run_one(item) for item in loaders)
                results.update(run_one(item) for item in scripts)
                for call, *_ in pending:
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": call.id,
                            "content": results[call.id].text,  # type: ignore[attr-defined]
                        }
                    )
                rounds += 1 if answer is None else 0

            if answer is not None and check_numbers and not numbers_checked:
                numbers_checked = True
                unverified = checker.find_unverified(answer, messages)
                if unverified:
                    note = checker.feedback(unverified)
                    record("thought", round=rounds, text=f"Number check: {note}")
                    messages.append(
                        {
                            "role": "user",
                            "content": f"Review feedback, please revise: {note}",
                        }
                    )
                    answer = None
                    continue

            if answer is not None and reviewer is not None and not reviewed:
                reviewed = True
                feedback = reviewer(answer, messages)
                if feedback:
                    record("thought", round=rounds, text=f"Reviewer: {feedback}")
                    messages.append(
                        {
                            "role": "user",
                            "content": f"Review feedback, please revise: {feedback}",
                        }
                    )
                    answer = None

        if answer is None:
            closing = ""
            if cost + last_call_cost <= max_cost_usd:
                messages.append({"role": "user", "content": _FORCE_FINAL})
                final = llm.chat(messages, None)
                cost += final.cost_usd
                closing = final.content.strip()
            incomplete = not closing
            answer = closing or _partial_answer(messages)
    except AnalystLLMError as exc:
        record("error", message=str(exc))
        return AnalystResult(
            answer="I could not complete this analysis because the language model was unavailable.",
            cost_usd=round(cost, 6), steps=rounds, events=events, charts=charts, error=str(exc),
        )  # fmt: skip

    unverified = checker.find_unverified(answer, messages) if check_numbers else []
    if unverified:
        answer = checker.annotate(answer, unverified)
    record(
        "final",
        unverified=unverified,
        incomplete=incomplete,
        markdown=answer,
        cost_usd=round(cost, 6),
        steps=rounds,
    )
    return AnalystResult(
        answer,
        round(cost, 6),
        rounds,
        events,
        charts,
        unverified=unverified,
        incomplete=incomplete,
    )


def dump_events(events: list[dict]) -> str:
    return json.dumps(events, default=str)
