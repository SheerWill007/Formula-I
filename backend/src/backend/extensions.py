"""
Flask extensions — initialised here, configured in create_app().

Why define them separately from create_app()?
So that blueprints can import them without importing the app itself.
Importing the app creates circular import problems.

Usage in blueprints:
    from backend.extensions import engine, get_engine
"""
from sqlalchemy.engine import Engine
from typing import Optional

# Placeholder — replaced with real engine in create_app()
_engine: Optional[Engine] = None


def get_engine() -> Engine:
    """
    Get the database engine. Raises a clear error if called before create_app().
    Use this in blueprints instead of accessing engine directly.
    """
    if _engine is None:
        raise RuntimeError(
            "Database engine not initialized. "
            "Ensure create_app() has been called before accessing the database."
        )
    return _engine


def set_engine(new_engine: Engine) -> None:
    """Set the database engine. Called by create_app()."""
    global _engine
    _engine = new_engine


# Legacy compatibility: direct access (deprecated, use get_engine() instead)
engine = property(lambda self: get_engine())

