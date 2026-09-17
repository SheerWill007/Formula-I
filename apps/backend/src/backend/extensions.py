"""
Flask extensions — initialised here, configured in create_app().

Why define them separately from create_app()?
So that blueprints can import them without importing the app itself.
Importing the app creates circular import problems.

Usage in blueprints:
    from backend.extensions import engine
"""
from sqlalchemy.engine import Engine

# Placeholder — replaced with real engine in create_app()
engine: Engine = None  # type: ignore[assignment]
