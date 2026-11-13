from __future__ import annotations

import json
import re
from pathlib import Path

from ml.config import settings

MODEL_DIR = Path(settings.ml_models_dir)
GLOBAL_MODEL_PATH = MODEL_DIR / "race_predictor.pkl"
GP_MODEL_DIR = MODEL_DIR / "gp"

MODEL_DIR.mkdir(parents=True, exist_ok=True)
GP_MODEL_DIR.mkdir(parents=True, exist_ok=True)


def slugify_gp_name(gp_name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", gp_name.lower()).strip("-")
    return slug or "unknown-gp"


def gp_model_path(gp_name: str) -> Path:
    return GP_MODEL_DIR / f"{slugify_gp_name(gp_name)}.pkl"


def global_metadata_path() -> Path:
    return MODEL_DIR / "race_predictor.json"


def gp_metadata_path(gp_name: str) -> Path:
    return GP_MODEL_DIR / f"{slugify_gp_name(gp_name)}.json"


def save_metadata(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2))


def load_metadata(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError:
        return None


# ── Database-backed persistence ──────────────────────────────────────────────
# Trained models are small pickles + JSON metadata. On hosts without a
# persistent disk (Render free tier) the training job publishes every file
# under MODEL_DIR to the `ml_model_files` table and the API restores them.

_restore_attempted = False


def _engine():
    from sqlalchemy import create_engine

    return create_engine(settings.db_url, pool_pre_ping=True)


def publish_models_to_db() -> int:
    """Upload every file under MODEL_DIR to Postgres. Returns files written."""
    from sqlalchemy import text

    files = [p for p in MODEL_DIR.rglob("*") if p.is_file()]
    if not files:
        return 0
    engine = _engine()
    try:
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM ml_model_files"))
            for path in files:
                conn.execute(
                    text(
                        "INSERT INTO ml_model_files (rel_path, content, updated_at) "
                        "VALUES (:p, :c, now())"
                    ),
                    {"p": path.relative_to(MODEL_DIR).as_posix(), "c": path.read_bytes()},
                )
    finally:
        engine.dispose()
    return len(files)


def restore_models_from_db(force: bool = False) -> int:
    """Download model files from Postgres into MODEL_DIR (once per process).

    Never raises: a missing table or unreachable DB just means no model yet.
    """
    global _restore_attempted
    if _restore_attempted and not force:
        return 0
    _restore_attempted = True

    from sqlalchemy import text

    try:
        engine = _engine()
        try:
            with engine.connect() as conn:
                rows = conn.execute(
                    text("SELECT rel_path, content FROM ml_model_files")
                ).fetchall()
        finally:
            engine.dispose()
    except Exception:
        return 0

    root = MODEL_DIR.resolve()
    written = 0
    for rel_path, content in rows:
        target = (MODEL_DIR / rel_path).resolve()
        if root not in target.parents:  # never write outside MODEL_DIR
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(bytes(content))
        written += 1
    return written
