import threading

from backend import create_app
from backend.config import settings


def test_app_factory_does_not_start_an_ingestion_thread(monkeypatch):
    monkeypatch.setattr(settings, "testing", False)
    monkeypatch.setattr(settings, "debug", False)
    existing_threads = {thread.ident for thread in threading.enumerate()}

    create_app()

    new_ingestion_threads = [
        thread
        for thread in threading.enumerate()
        if thread.ident not in existing_threads and thread.name == "pitwall-auto-ingest"
    ]
    assert new_ingestion_threads == []


def test_personal_memory_endpoint_is_not_registered():
    response = create_app().test_client().delete(
        "/api/v1/agent/memory", headers={"Authorization": "Bearer test-token"}
    )

    assert response.status_code == 404
