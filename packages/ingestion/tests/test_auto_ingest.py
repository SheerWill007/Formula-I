from ingestion.auto_ingest import sessions_for_event


def test_sessions_for_conventional_event():
    sessions = sessions_for_event({"event_format": "conventional"})

    assert [session_type for session_type, _ in sessions] == ["FP1", "FP2", "FP3", "Q", "R"]


def test_sessions_for_sprint_event():
    sessions = sessions_for_event({"event_format": "sprint"})

    assert [session_type for session_type, _ in sessions] == ["FP1", "Q", "SQ", "SS", "R"]
