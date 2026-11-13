"""Agent API endpoint exposing the rule based orchestrator"""

from dataclasses import asdict
from datetime import datetime
import json
import queue
import structlog
import threading
from flask import Blueprint, Response, g, jsonify, request, stream_with_context

from backend import auth, extensions
from backend.agent import concurrency, orchestrator, persistence, rate_limit
from backend.config import settings
from sqlalchemy import text as sql_text

log = structlog.get_logger()
agent_bp = Blueprint("agent", __name__)


def _admin_ids() -> set[str]:
    """Parse the comma-separated admin allowlist from settings."""
    return {s.strip() for s in settings.clerk_admin_user_ids.split(",") if s.strip()}


def _is_admin(clerk_user_id: str) -> bool:
    return clerk_user_id in _admin_ids()


def _public_tool_summary(call) -> str:
    summaries = {
        "resolve_session": "Race context resolved",
        "resolve_driver": "Driver identity resolved",
        "find_pit_stops": "Pit stop evidence checked",
        "get_lap_telemetry_artifacts": "Telemetry artifacts found",
        "compute_speed_window": "Speed comparison computed",
        "verify_evidence": "Evidence gate completed",
    }
    return summaries.get(call.tool_name.value, "Tool completed")


def _serialize_answer(
    answer,
    *,
    conversation_id: int | None,
    run_id: int | None,
    include_trace_details: bool,
):
    response = asdict(answer)
    response["conversation_id"] = conversation_id
    response["run_id"] = run_id
    response["trace_visibility"] = "full" if include_trace_details else "evidence"
    if not include_trace_details:
        response["trace"] = [
            {
                "tool_name": call.tool_name.value,
                "status": call.status,
                "input_summary": "",
                "output_summary": _public_tool_summary(call),
                "error": "A required evidence step failed" if call.error else None,
                "duration_ms": call.duration_ms,
            }
            for call in answer.trace
        ]
    return response


def _sse(event: str, payload: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, default=str)}\n\n"


def _validate_question_payload():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return None, (jsonify({"error": "Request body must be a JSON object"}), 400)

    question = payload.get("question")
    if not isinstance(question, str) or not question.strip():
        return None, (
            jsonify({"error": "question is required and must be a non-empty string"}),
            400,
        )
    if len(question) > settings.agent_max_question_chars:
        return None, (
            jsonify(
                {
                    "error": f"Question is too long (max {settings.agent_max_question_chars} characters)"
                }
            ),
            400,
        )
    conv_id = payload.get("conversation_id")
    if conv_id is not None and (
        isinstance(conv_id, bool) or not isinstance(conv_id, int)
    ):
        return None, (jsonify({"error": "conversation_id must be an integer"}), 400)
    return payload, None


def _prepare_conversation(payload: dict, question: str):
    incoming_conv_id = payload.get("conversation_id")
    with extensions.engine.begin() as conn:
        user_id = persistence.ensure_user(conn, g.clerk_user_id)

        if incoming_conv_id is not None:
            owner = conn.execute(
                sql_text(
                    """
                    SELECT c.id FROM agent_conversations c
                    WHERE c.id = :cid AND c.user_id = :uid
                      AND c.deleted_at IS NULL
                    """
                ),
                {"cid": incoming_conv_id, "uid": user_id},
            ).first()
            if owner is None:
                return None, None, (jsonify({"error": "Conversation not found"}), 404)
            conv_id = int(incoming_conv_id)
        else:
            used = persistence.lock_user_and_count_conversations(conn, user_id)
            if used >= settings.agent_max_conversations and not _is_admin(
                g.clerk_user_id
            ):
                return None, None, (
                    jsonify(
                        {
                            "error": f"Chat limit reached ({settings.agent_max_conversations} chats per account). Delete a chat to start a new one.",
                            "limit": settings.agent_max_conversations,
                        }
                    ),
                    429,
                )
            title = question.strip()[:80]
            conv_id = persistence.create_conversation(conn, user_id, title)

        persistence.insert_message(conn, conv_id, "user", question.strip())

    context = (
        persistence.load_last_context(conv_id, g.clerk_user_id)
        if incoming_conv_id is not None
        else None
    )
    return conv_id, context, None


def _finalize_run(answer, started_at, clerk_user_id: str, conv_id: int):
    with extensions.engine.begin() as conn:
        persistence.insert_message(conn, conv_id, "assistant", answer.answer)

    run_id = persistence.persist_run(
        answer, started_at, clerk_user_id, conversation_id=conv_id
    )

    for call in answer.trace:
        log.info(
            "agent.tool_call",
            tool=call.tool_name.value,
            status=call.status,
            duration_ms=call.duration_ms,
            error=call.error,
        )

    log.info(
        "agent.run",
        run_id=run_id,
        conversation_id=conv_id,
        intent=answer.intent.value,
        refused=bool(answer.refusals),
        refusals=list(answer.refusals),
    )
    return run_id


@agent_bp.before_request
def require_clerk_session():
    """Reject the request before the view unless a valid Clerk token is present."""
    return auth.require_api_auth()


@agent_bp.post("/agent/query")
def agent_query():
    payload, error_response = _validate_question_payload()
    if error_response:
        return error_response
    question = payload["question"]

    if not _is_admin(g.clerk_user_id):
        limit_response = rate_limit.limit_response(g.clerk_user_id)
        if limit_response is not None:
            log.info("agent.limit_hit", user=g.clerk_user_id)
            return limit_response

    if not concurrency.try_acquire(g.clerk_user_id):
        return jsonify({"error": "You already have a run in progress"}), 429
    try:
        conv_id, context, error_response = _prepare_conversation(payload, question)
        if error_response:
            return error_response

        # ── Run the orchestrator ────────────────────────────────────────
        started_at = datetime.now().astimezone()
        answer = orchestrator.run(question.strip(), context=context)

        # ── Store the assistant message + persist run ───────────────────
        run_id = _finalize_run(answer, started_at, g.clerk_user_id, conv_id)

        response = _serialize_answer(
            answer,
            conversation_id=conv_id,
            run_id=run_id,
            include_trace_details=_is_admin(g.clerk_user_id),
        )
        return jsonify(response)
    finally:
        concurrency.release(g.clerk_user_id)


@agent_bp.post("/agent/query/stream")
def agent_query_stream():
    payload, error_response = _validate_question_payload()
    if error_response:
        return error_response
    question = payload["question"]

    if not _is_admin(g.clerk_user_id):
        limit_response = rate_limit.limit_response(g.clerk_user_id)
        if limit_response is not None:
            log.info("agent.limit_hit", user=g.clerk_user_id)
            return limit_response

    if not concurrency.try_acquire(g.clerk_user_id):
        return jsonify({"error": "You already have a run in progress"}), 429
    conv_id, context, error_response = _prepare_conversation(payload, question)
    if error_response:
        concurrency.release(g.clerk_user_id)
        return error_response

    clerk_user_id = g.clerk_user_id
    include_trace_details = _is_admin(clerk_user_id)
    started_at = datetime.now().astimezone()
    events: queue.Queue[tuple[str, dict]] = queue.Queue()

    def worker():
        try:
            answer = orchestrator.run(
                question.strip(),
                progress=lambda payload: events.put(("progress", payload)),
                context=context,
            )
            run_id = _finalize_run(answer, started_at, clerk_user_id, conv_id)
            events.put(
                (
                    "final",
                    _serialize_answer(
                        answer,
                        conversation_id=conv_id,
                        run_id=run_id,
                        include_trace_details=include_trace_details,
                    ),
                )
            )
        except Exception as exc:
            log.exception("agent.stream_failed", error=str(exc))
            events.put(("error", {"error": "Agent stream failed"}))
        finally:
            concurrency.release(clerk_user_id)
            events.put(("done", {}))

    threading.Thread(target=worker, name="pitwall-agent-stream", daemon=True).start()

    @stream_with_context
    def generate():
        yield _sse(
            "progress",
            {
                "type": "stage",
                "stage": "start",
                "status": "ok",
                "label": "Agent run started",
            },
        )
        while True:
            event, payload = events.get()
            if event == "done":
                yield _sse("done", {})
                break
            yield _sse(event, payload)

    return Response(generate(), mimetype="text/event-stream")


@agent_bp.get("/agent/conversations")
def list_conversations():
    """Return all conversations for the authenticated user, newest first."""
    conversations = persistence.list_conversations(g.clerk_user_id)
    return jsonify(conversations)


@agent_bp.get("/agent/conversations/<int:conv_id>")
def get_conversation(conv_id: int):
    """Return a single conversation with all its messages."""
    result = persistence.get_conversation_messages(conv_id, g.clerk_user_id)
    if result is None:
        return jsonify({"error": "Conversation not found"}), 404
    return jsonify(result)


@agent_bp.delete("/agent/conversations/<int:conv_id>")
def delete_conversation(conv_id: int):
    """Soft-delete one of the user's chats (usage counters keep their history)."""
    if not persistence.delete_conversation(conv_id, g.clerk_user_id):
        return jsonify({"error": "Conversation not found"}), 404
    return jsonify({"deleted": conv_id})


@agent_bp.get("/agent/usage")
def get_usage():
    """Returns the authenticated users daily usage summary"""
    summary = persistence.get_usage_summary(g.clerk_user_id)
    return jsonify(summary)


@agent_bp.get("/agent/admin/limits")
def get_limits():
    """Return the current authenticated user's daily agent allowance."""
    return jsonify(persistence.get_usage_summary(g.clerk_user_id))


@agent_bp.get("/agent/admin/stats")
def admin_stats():
    """Return aggregated stats. Only accessible to admin users"""
    if not _is_admin(g.clerk_user_id):
        return jsonify({"error": "Admin access required"}), 403
    stats = persistence.get_admin_stats()
    return jsonify(stats)


@agent_bp.post("/agent/runs/<int:run_id>/feedback")
def rate_run(run_id: int):
    """Set the authenticated user's vote on one of their runs."""
    payload = request.get_json(silent=True) or {}
    rating = payload.get("rating")
    if rating not in (1, -1):
        return jsonify({"error": "rating must be 1 (up) or -1 (down)"}), 400

    comment = payload.get("comment")
    if comment is not None and not isinstance(comment, str):
        return jsonify({"error": "comment must be a string or null"}), 400

    wrote = persistence.upsert_run_feedback(run_id, g.clerk_user_id, rating, comment)
    if not wrote:
        return jsonify({"error": "Run not found"}), 404

    log.info("agent.rated", run_id=run_id, rating=rating)
    return jsonify({"run_id": run_id, "rating": rating})


@agent_bp.delete("/agent/runs/<int:run_id>/feedback")
def clear_run_feedback(run_id: int):
    """Remove the authenticated user's vote on one of their runs."""
    deleted = persistence.delete_run_feedback(run_id, g.clerk_user_id)
    if not deleted:
        return jsonify({"error": "Feedback not found or not yours"}), 404

    log.info("agent.rating_cleared", run_id=run_id)
    return jsonify({"run_id": run_id, "rating": None})


@agent_bp.get("/agent/admin/feedback")
def admin_feedback():
    """Aggregate up/down votes. Admin only."""
    if not _is_admin(g.clerk_user_id):
        return jsonify({"error": "Admin access required"}), 403
    return jsonify(persistence.get_feedback_stats())
