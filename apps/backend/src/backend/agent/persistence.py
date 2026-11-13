"""Persist agent runs and tool-call traces (L8).

Tables come from migration 0019. Runs attach to the local user row
matching the verified clerk_user_id passed by the API layer.
"""

from __future__ import annotations
from datetime import datetime
import json

from sqlalchemy import text

from backend.agent import types
from backend import extensions
from backend.config import settings


def ensure_user(conn, clerk_user_id: str) -> int:
    """Return the id of the user with this clerk id, creating it if absent."""
    conn.execute(
        text(
            """
            INSERT INTO users (clerk_user_id, email, name)
            VALUES (:clerk_user_id, 'demo@pitwall.local', 'Demo User')
            ON CONFLICT (clerk_user_id) DO NOTHING
            """
        ),
        {"clerk_user_id": clerk_user_id},
    )
    row = conn.execute(
        text("SELECT id FROM users WHERE clerk_user_id = :clerk_user_id"),
        {"clerk_user_id": clerk_user_id},
    ).first()
    return row.id


def _insert_tool_call(conn, run_id: int, record: types.ToolCallRecord) -> None:
    conn.execute(
        text(
            """
            INSERT INTO agent_tool_calls (
                run_id, tool_name, input_json, output_summary_json,
                status, duration_ms
            ) VALUES (
                :run_id, :tool_name, :input_json, :output_summary_json,
                :status, :duration_ms
            )
            """
        ),
        {
            "run_id": run_id,
            "tool_name": record.tool_name.value,
            "input_json": json.dumps({"summary": record.input_summary}, sort_keys=True),
            "output_summary_json": (
                json.dumps({"summary": record.output_summary}, sort_keys=True)
                if record.output_summary
                else None
            ),
            "status": record.status,
            "duration_ms": int(record.duration_ms) if record.duration_ms else None,
        },
    )


def persist_run(
    answer: types.AgentAnswer,
    started_at: datetime,
    clerk_user_id: str,
    conversation_id: int | None = None,
) -> int:
    """Insert one agent_runs row plus every tool call in the trace.

    Returns the new run id. Links to conversation_id when provided.
    """
    with extensions.engine.begin() as conn:
        user_id = ensure_user(conn, clerk_user_id)
        row = conn.execute(
            text(
                """
                INSERT INTO agent_runs (
                    conversation_id, user_id, status, model,
                    started_at, completed_at, cost_estimate_usd, error, context_json
                ) VALUES (
                    :conversation_id, :user_id, :status, NULL, :started_at,
                    :completed_at, :cost_estimate_usd, :error, CAST(:context_json AS JSONB)
                )
                RETURNING id
                """
            ),
            {
                "conversation_id": conversation_id,
                "user_id": user_id,
                "status": "refused" if answer.refusals else "completed",
                "started_at": started_at,
                "completed_at": datetime.now(started_at.tzinfo),
                "cost_estimate_usd": answer.cost_usd,
                "error": answer.refusals[0] if answer.refusals else None,
                "context_json": json.dumps(answer.routing_context, default=str)
                if answer.routing_context
                else None,
            },
        ).first()

        run_id = row.id
        for call in answer.trace:
            _insert_tool_call(conn, run_id, call)
    return run_id


def load_last_context(conversation_id: int, clerk_user_id: str) -> dict | None:
    """The most recent routing context persisted for this conversation.
    Returns None when there's nothing to merge against (fresh conversation,
    or the last run carried no context).
    """
    with extensions.engine.connect() as conn:
        row = conn.execute(
            text(
                """
                SELECT r.context_json
                FROM agent_runs r
                JOIN agent_conversations c ON c.id = r.conversation_id
                JOIN users u ON u.id = c.user_id
                WHERE r.conversation_id = :cid
                  AND u.clerk_user_id = :clerk_user_id
                  AND r.context_json IS NOT NULL
                ORDER BY r.id DESC
                LIMIT 1
                """
            ),
            {"cid": conversation_id, "clerk_user_id": clerk_user_id},
        ).first()
        return row.context_json if row else None


def count_runs_today(clerk_user_id: str) -> int:
    """Count this user's agent runs recorded since local midnight."""
    with extensions.engine.connect() as conn:
        return conn.execute(
            text(
                """
                SELECT COUNT(*) FROM agent_runs r
                JOIN users u ON u.id = r.user_id
                WHERE u.clerk_user_id = :clerk_user_id
                  AND r.started_at >= date_trunc('day', NOW())
                """
            ),
            {"clerk_user_id": clerk_user_id},
        ).scalar_one()


def sum_cost_today(clerk_user_id: str) -> float:
    """The users total agent spent cost recorded since local midnight."""
    with extensions.engine.connect() as conn:
        return float(
            conn.execute(
                text(
                    """ 
                        SELECT COALESCE(SUM(cost_estimate_usd), 0)
                        FROM agent_runs r
                        JOIN users u ON u.id = r.user_id
                        WHERE u.clerk_user_id = :clerk_user_id
                        AND r.started_at >= date_trunc('day', NOW())
                    """
                ),
                {"clerk_user_id": clerk_user_id},
            ).scalar_one()
            or 0.0
        )


def get_usage_summary(clerk_user_id: str) -> dict:
    """Return { used, limit, remaining } for the current day."""
    used = count_runs_today(clerk_user_id)
    limit = settings.agent_free_daily_limit
    cost = sum_cost_today(clerk_user_id)
    return {
        "used": used,
        "limit": limit,
        "remaining": max(0, limit - used),
        "cost_usd_today": round(cost, 4),
        "cost_limit_usd": settings.agent_free_daily_cost_usd,
        "remaining_cost_usd": round(
            max(0.0, settings.agent_free_daily_cost_usd - cost), 4
        ),
    }


def get_admin_stats() -> dict:
    """Aggregate admin-facing stats: total runs, cost, breakdown by status."""
    with extensions.engine.connect() as conn:
        row = conn.execute(
            text(
                """
                SELECT
                    COUNT(*)                            AS total_runs,
                    COALESCE(SUM(cost_estimate_usd), 0) AS total_cost_usd,
                    COUNT(*) FILTER (WHERE status = 'completed') AS completed,
                    COUNT(*) FILTER (WHERE status = 'refused')   AS refused
                FROM agent_runs
                WHERE started_at >= date_trunc('day', NOW())
                """
            )
        ).first()
        return {
            "total_runs": row.total_runs,
            "total_cost_usd": round(float(row.total_cost_usd), 4),
            "completed": row.completed,
            "refused": row.refused,
        }


# ── Conversation persistence (L16) ─────────────────────────────────────────


def create_conversation(conn, user_id: int, title: str) -> int:
    """Create a new conversation thread and return its id."""
    row = conn.execute(
        text(
            """
            INSERT INTO agent_conversations (user_id, title)
            VALUES (:user_id, :title)
            RETURNING id
            """
        ),
        {"user_id": user_id, "title": title},
    ).first()
    return row.id


def insert_message(conn, conversation_id: int, role: str, content: str) -> None:
    """Insert one message (user or assistant) into a conversation."""
    conn.execute(
        text(
            """
            INSERT INTO agent_messages (conversation_id, role, content)
            VALUES (:conversation_id, :role, :content)
            """
        ),
        {"conversation_id": conversation_id, "role": role, "content": content},
    )
    # Touch updated_at on the parent conversation so it sorts first in lists.
    conn.execute(
        text("UPDATE agent_conversations SET updated_at = NOW() WHERE id = :cid"),
        {"cid": conversation_id},
    )


def list_conversations(clerk_user_id: str) -> list[dict]:
    """Return conversations for this user, newest first.

    Each row includes: id, title, message_count, last_message_preview,
    created_at, updated_at.
    """
    with extensions.engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT
                    c.id,
                    c.title,
                    COUNT(m.id) AS message_count,
                    (
                        SELECT content FROM agent_messages
                        WHERE conversation_id = c.id
                        ORDER BY id DESC LIMIT 1
                    ) AS last_message_preview,
                    c.created_at,
                    c.updated_at
                FROM agent_conversations c
                JOIN users u ON u.id = c.user_id
                LEFT JOIN agent_messages m ON m.conversation_id = c.id
                WHERE u.clerk_user_id = :clerk_user_id
                  AND c.deleted_at IS NULL
                GROUP BY c.id
                ORDER BY c.updated_at DESC, c.id DESC
                """
            ),
            {"clerk_user_id": clerk_user_id},
        ).fetchall()
        return [
            {
                "id": r.id,
                "title": r.title,
                "message_count": r.message_count,
                "last_message_preview": r.last_message_preview,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "updated_at": r.updated_at.isoformat() if r.updated_at else None,
            }
            for r in rows
        ]


def get_conversation_messages(conversation_id: int, clerk_user_id: str) -> dict | None:
    """Return a conversation with all its messages, or None if not found / not owned.

    Output: { id, title, created_at, messages: [{ role, content, created_at }] }
    """
    with extensions.engine.connect() as conn:
        # Verify ownership first.
        owner = conn.execute(
            text(
                """
                SELECT c.id, c.title, c.created_at
                FROM agent_conversations c
                JOIN users u ON u.id = c.user_id
                WHERE c.id = :cid AND u.clerk_user_id = :clerk_user_id
                  AND c.deleted_at IS NULL
                """
            ),
            {"cid": conversation_id, "clerk_user_id": clerk_user_id},
        ).first()
        if owner is None:
            return None

        messages = conn.execute(
            text(
                """
                SELECT role, content, created_at
                FROM agent_messages
                WHERE conversation_id = :cid
                ORDER BY id ASC
                """
            ),
            {"cid": conversation_id},
        ).fetchall()

        return {
            "id": owner.id,
            "title": owner.title,
            "created_at": owner.created_at.isoformat() if owner.created_at else None,
            "messages": [
                {
                    "role": m.role,
                    "content": m.content,
                    "created_at": m.created_at.isoformat() if m.created_at else None,
                }
                for m in messages
            ],
        }


def upsert_run_feedback(
    run_id: int, clerk_user_id: str, rating: int, comment: str | None = None
) -> bool:
    """Rate a run (upsert — one vote per user per run). Returns False when the
    run does not exist or is not owned by this user, so the caller can 404."""
    with extensions.engine.begin() as conn:
        owner = conn.execute(
            text(
                """
                SELECT ar.id, u.id AS user_id
                FROM agent_runs ar
                JOIN users u ON u.id = ar.user_id
                WHERE ar.id = :run_id AND u.clerk_user_id = :clerk_user_id
                """
            ),
            {"run_id": run_id, "clerk_user_id": clerk_user_id},
        ).first()
        if owner is None:
            return False

        conn.execute(
            text(
                """
                INSERT INTO agent_run_feedback (run_id, user_id, rating, comment)
                VALUES (:run_id, :user_id, :rating, :comment)
                ON CONFLICT (run_id, user_id) DO UPDATE SET
                    rating = EXCLUDED.rating,
                    comment = EXCLUDED.comment,
                    updated_at = NOW()
                """
            ),
            {
                "run_id": run_id,
                "user_id": owner.user_id,
                "rating": rating,
                "comment": comment,
            },
        )
        return True


def delete_run_feedback(run_id: int, clerk_user_id: str) -> bool:
    """Clear this user's vote on a run. Returns False when nothing was deleted."""
    with extensions.engine.begin() as conn:
        result = conn.execute(
            text(
                """
                DELETE FROM agent_run_feedback f
                USING agent_runs ar, users u
                WHERE f.run_id = ar.id
                  AND ar.user_id = u.id
                  AND ar.id = :run_id
                  AND u.clerk_user_id = :clerk_user_id
                """
            ),
            {"run_id": run_id, "clerk_user_id": clerk_user_id},
        )
        return result.rowcount > 0


def get_feedback_stats() -> dict:
    """Admin aggregate: total up and down votes across all users."""
    with extensions.engine.connect() as conn:
        row = conn.execute(
            text(
                """
                SELECT
                    COUNT(*) FILTER (WHERE rating = 1)  AS up_votes,
                    COUNT(*) FILTER (WHERE rating = -1) AS down_votes
                FROM agent_run_feedback
                """
            )
        ).first()
        return {"up": row.up_votes, "down": row.down_votes}


def lock_user_and_count_conversations(conn, user_id: int) -> int:
    """Lock the user row so two parallel requests cannot both create the next chat."""
    conn.execute(
        text("SELECT id FROM users WHERE id = :uid FOR UPDATE"), {"uid": user_id}
    )
    return conn.execute(
        text(
            "SELECT COUNT(*) FROM agent_conversations "
            "WHERE user_id = :uid AND deleted_at IS NULL"
        ),
        {"uid": user_id},
    ).scalar_one()


def delete_conversation(conversation_id: int, clerk_user_id: str) -> bool:
    """Soft-delete a chat the user owns. Run rows stay so daily counters are intact."""
    with extensions.engine.begin() as conn:
        result = conn.execute(
            text(
                """
                UPDATE agent_conversations c
                SET deleted_at = NOW()
                FROM users u
                WHERE c.id = :cid AND c.user_id = u.id
                  AND u.clerk_user_id = :clerk_user_id
                  AND c.deleted_at IS NULL
                """
            ),
            {"cid": conversation_id, "clerk_user_id": clerk_user_id},
        )
        return result.rowcount > 0
