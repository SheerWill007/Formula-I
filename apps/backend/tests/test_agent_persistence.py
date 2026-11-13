"""Unit tests for agent conversation persistence functions (L16)."""

from sqlalchemy import text

from backend.agent import persistence


def _cleanup(db_engine):
    with db_engine.begin() as conn:
        conn.execute(
            text(
                "DELETE FROM agent_messages WHERE conversation_id IN "
                "(SELECT id FROM agent_conversations WHERE user_id IN "
                "(SELECT id FROM users WHERE clerk_user_id = 'conv-test-user'))"
            )
        )
        conn.execute(
            text(
                "DELETE FROM agent_runs WHERE user_id IN "
                "(SELECT id FROM users WHERE clerk_user_id = 'conv-test-user')"
            )
        )
        conn.execute(
            text(
                "DELETE FROM agent_conversations WHERE user_id IN "
                "(SELECT id FROM users WHERE clerk_user_id = 'conv-test-user')"
            )
        )
        conn.execute(text("DELETE FROM users WHERE clerk_user_id = 'conv-test-user'"))


def _get_user_id(conn, clerk_user_id="conv-test-user"):
    persistence.ensure_user(conn, clerk_user_id)
    row = conn.execute(
        text("SELECT id FROM users WHERE clerk_user_id = :cid"),
        {"cid": clerk_user_id},
    ).first()
    return row.id


def test_create_conversation(db_engine):
    try:
        with db_engine.begin() as conn:
            user_id = _get_user_id(conn)
            conv_id = persistence.create_conversation(
                conn, user_id, "Test conversation"
            )
            assert isinstance(conv_id, int)
            assert conv_id > 0

            # Verify it exists in the database.
            row = conn.execute(
                text("SELECT title FROM agent_conversations WHERE id = :id"),
                {"id": conv_id},
            ).first()
            assert row is not None
            assert row.title == "Test conversation"
    finally:
        _cleanup(db_engine)


def test_insert_message(db_engine):
    try:
        with db_engine.begin() as conn:
            user_id = _get_user_id(conn)
            conv_id = persistence.create_conversation(conn, user_id, "Msg test")

            persistence.insert_message(conn, conv_id, "user", "Where did Sainz pit?")
            persistence.insert_message(
                conn, conv_id, "assistant", "Lap 22 into lap 23."
            )

            messages = conn.execute(
                text(
                    "SELECT role, content FROM agent_messages "
                    "WHERE conversation_id = :cid ORDER BY id ASC"
                ),
                {"cid": conv_id},
            ).fetchall()

            assert len(messages) == 2
            assert messages[0].role == "user"
            assert messages[0].content == "Where did Sainz pit?"
            assert messages[1].role == "assistant"
            assert messages[1].content == "Lap 22 into lap 23."

            # Verify updated_at was touched on the conversation.
            conv = conn.execute(
                text("SELECT updated_at FROM agent_conversations WHERE id = :id"),
                {"id": conv_id},
            ).first()
            assert conv is not None
            assert conv.updated_at is not None
    finally:
        _cleanup(db_engine)


def test_list_conversations(app, db_engine):
    try:
        with db_engine.begin() as conn:
            user_id = _get_user_id(conn)
            conv1 = persistence.create_conversation(conn, user_id, "First chat")
            persistence.insert_message(conn, conv1, "user", "Hello")
            conv2 = persistence.create_conversation(conn, user_id, "Second chat")
            persistence.insert_message(conn, conv2, "user", "Hi there")

        conversations = persistence.list_conversations("conv-test-user")
        assert len(conversations) >= 2

        # Newest first — second chat should be first.
        titles = [c["title"] for c in conversations]
        assert titles[0] == "Second chat"
        assert titles[1] == "First chat"

        # Each conversation has the expected keys.
        for conv in conversations:
            assert "id" in conv
            assert "title" in conv
            assert "message_count" in conv
            assert "last_message_preview" in conv
            assert "created_at" in conv
            assert "updated_at" in conv
    finally:
        _cleanup(db_engine)


def test_get_conversation_messages(app, db_engine):
    try:
        with db_engine.begin() as conn:
            user_id = _get_user_id(conn)
            conv_id = persistence.create_conversation(conn, user_id, "Detail test")
            persistence.insert_message(conn, conv_id, "user", "Question 1")
            persistence.insert_message(conn, conv_id, "assistant", "Answer 1")
            persistence.insert_message(conn, conv_id, "user", "Question 2")

        result = persistence.get_conversation_messages(conv_id, "conv-test-user")
        assert result is not None
        assert result["id"] == conv_id
        assert result["title"] == "Detail test"
        assert len(result["messages"]) == 3
        assert result["messages"][0]["role"] == "user"
        assert result["messages"][0]["content"] == "Question 1"
        assert result["messages"][1]["role"] == "assistant"
        assert result["messages"][1]["content"] == "Answer 1"
        assert result["messages"][2]["role"] == "user"
        assert result["messages"][2]["content"] == "Question 2"
    finally:
        _cleanup(db_engine)


def test_get_conversation_messages_wrong_owner(app, db_engine):
    try:
        with db_engine.begin() as conn:
            user_id = _get_user_id(conn, "conv-test-user")
            conv_id = persistence.create_conversation(conn, user_id, "Private chat")
            persistence.insert_message(conn, conv_id, "user", "Secret question")

        # A different user should get None.
        result = persistence.get_conversation_messages(conv_id, "wrong-user")
        assert result is None
    finally:
        _cleanup(db_engine)


def test_get_conversation_messages_nonexistent(app, db_engine):
    result = persistence.get_conversation_messages(999999, "conv-test-user")
    assert result is None


def test_list_conversations_empty(app, db_engine):
    conversations = persistence.list_conversations("nonexistent-user")
    assert conversations == []
