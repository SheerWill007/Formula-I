"""Model files round-trip through Postgres (ml_model_files)."""

import pytest
from sqlalchemy import create_engine, inspect

from ml import model_store
from ml.config import settings


def _has_table() -> bool:
    try:
        engine = create_engine(settings.db_url)
        try:
            return inspect(engine).has_table("ml_model_files")
        finally:
            engine.dispose()
    except Exception:
        return False


@pytest.mark.skipif(not _has_table(), reason="needs a migrated Postgres")
def test_publish_then_restore_round_trip(tmp_path, monkeypatch):
    src = tmp_path / "src"
    (src / "gp").mkdir(parents=True)
    (src / "race_predictor.pkl").write_bytes(b"\x80\x04model")
    (src / "gp" / "monaco.json").write_text('{"gp_name": "Monaco"}')

    monkeypatch.setattr(model_store, "MODEL_DIR", src)
    assert model_store.publish_models_to_db() == 2

    dst = tmp_path / "dst"
    monkeypatch.setattr(model_store, "MODEL_DIR", dst)
    assert model_store.restore_models_from_db(force=True) == 2
    assert (dst / "race_predictor.pkl").read_bytes() == b"\x80\x04model"
    assert (dst / "gp" / "monaco.json").read_text() == '{"gp_name": "Monaco"}'


def test_restore_never_raises_without_db(monkeypatch):
    monkeypatch.setattr(model_store, "_engine", lambda: (_ for _ in ()).throw(RuntimeError("no db")))
    assert model_store.restore_models_from_db(force=True) == 0
