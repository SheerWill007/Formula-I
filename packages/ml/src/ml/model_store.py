from __future__ import annotations

import json
import os
import re
from pathlib import Path

MODEL_DIR = Path(os.getenv("ML_MODELS_DIR", "./ml_models"))
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
