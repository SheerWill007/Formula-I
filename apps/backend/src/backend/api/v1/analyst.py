"""Analyst engine API: live event stream, replay and run history.

Additive: it reuses the agent API's request validation, conversation
bookkeeping and admin check, and leaves the existing /agent endpoints alone.
"""

from __future__ import annotations

import queue
import threading

import structlog
from flask import Blueprint, Response, g, jsonify, stream_with_context

from backend import auth, extensions
from backend.agent import concurrency
from backend.agent import persistence as agent_persistence
from backend.analyst import persistence
from backend.analyst.client import ChatClient, OpenRouterClient
from backend.analyst.loop import run_analyst
from backend.analyst.sandbox import Sandbox, Workspace, default_sandbox
from backend.analyst.tools import ToolBox
from backend.api.v1.agent import (
    _is_admin,
    _prepare_conversation,
    _sse,
    _validate_question_payload,
)
from backend.config import settings

log = structlog.get_logger()
analyst_bp = Blueprint("analyst", __name__)


# Seams for tests and for swapping the sandbox implementation.
def make_llm() -> ChatClient:
    return OpenRouterClient()


def make_sandbox() -> Sandbox:
    sandbox = default_sandbox()
    if sandbox is None:
        raise RuntimeError("no analysis sandbox is available on this host")
    return sandbox


def sandbox_ready() -> bool:
    return default_sandbox() is not None


@analyst_bp.before_request
def require_clerk_session():
    return auth.require_api_auth()


def _limit_error(clerk_user_id: str):
    with extensions.engine.connect() as conn:
        runs, cost = persistence.usage_today(conn, clerk_user_id)
    if runs >= settings.agent_free_daily_limit:
        return jsonify(
            {"error": "Daily question limit reached. Try again tomorrow."}
        ), 429
    if cost >= settings.agent_free_daily_cost_usd:
        return jsonify(
            {"error": "Daily usage cost limit reached. Try again tomorrow."}
        ), 429
    return None


@analyst_bp.post("/agent/analyst/stream")
def analyst_stream():
    payload, error_response = _validate_question_payload()
    if error_response:
        return error_response
    question = payload["question"].strip()

    if not _is_admin(g.clerk_user_id):
        limited = _limit_error(g.clerk_user_id)
        if limited is not None:
            return limited
    if not sandbox_ready():
        return jsonify({"error": "Analysis sandbox is unavailable"}), 503

    if not concurrency.try_acquire(g.clerk_user_id):
        return jsonify({"error": "You already have a run in progress"}), 429
    conv_id, _context, error_response = _prepare_conversation(payload, question)
    if error_response:
        concurrency.release(g.clerk_user_id)
        return error_response

    clerk_user_id = g.clerk_user_id
    events: queue.Queue[tuple[str, dict]] = queue.Queue()

    def worker():
        workspace = Workspace()
        try:
            toolbox = ToolBox(
                workspace,
                make_sandbox(),
                sandbox_timeout_s=settings.analyst_sandbox_timeout_seconds,
            )
            result = run_analyst(
                question,
                llm=make_llm(),
                toolbox=toolbox,
                emit=lambda e: events.put(("analyst", e)),
                max_steps=settings.analyst_max_steps,
                max_cost_usd=settings.analyst_max_cost_usd,
                check_numbers=True,
            )
            with extensions.engine.begin() as conn:
                user_id = agent_persistence.ensure_user(conn, clerk_user_id)
                run_id = persistence.save_run(conn, user_id, conv_id, question, result)
                agent_persistence.insert_message(
                    conn, conv_id, "assistant", result.answer
                )
            events.put(("saved", {"run_id": run_id, "conversation_id": conv_id}))
        except Exception as exc:
            log.exception("analyst.stream_failed", error=str(exc))
            events.put(("error", {"error": "Analysis failed"}))
        finally:
            workspace.cleanup()
            concurrency.release(clerk_user_id)
            events.put(("done", {}))

    threading.Thread(target=worker, name="pitwall-analyst-stream", daemon=True).start()

    @stream_with_context
    def generate():
        while True:
            event, data = events.get()
            if event == "done":
                yield _sse("done", {})
                break
            yield _sse(event, data)

    return Response(generate(), mimetype="text/event-stream")


@analyst_bp.get("/agent/analyst/runs")
def list_analyst_runs():
    with extensions.engine.connect() as conn:
        return jsonify(persistence.list_runs(conn, g.clerk_user_id))


@analyst_bp.get("/agent/analyst/runs/<int:run_id>")
def get_analyst_run(run_id: int):
    with extensions.engine.connect() as conn:
        run = persistence.get_run(conn, run_id, g.clerk_user_id)
    if run is None:
        return jsonify({"error": "Run not found"}), 404
    return jsonify(run)


__all__ = ["analyst_bp"]
