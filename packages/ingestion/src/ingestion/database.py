"""
SQLAlchemy database engine and session factory.

We use SQLAlchemy Core (not ORM) for inserts — it's faster for bulk
operations because it doesn't instantiate Python objects per row.
"""
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection

from ingestion.config import settings

# create_engine sets up the connection pool.
# pool_size=5: keep 5 connections open permanently.
# max_overflow=10: allow up to 10 extra connections under load.
engine = create_engine(
    settings.database_url,
    pool_size=5,
    max_overflow=10,
    pool_pre_ping=True,   # test connections before using them
)


@contextmanager
def get_connection() -> Generator[Connection, None, None]:
    """
    Context manager that gives you a database connection.
    Automatically commits on success, rolls back on exception.

    Usage:
        with get_connection() as conn:
            conn.execute(text("SELECT 1"))
    """
    with engine.begin() as conn:
        yield conn


def check_connection() -> bool:
    """Verify the database is reachable. Used in health checks."""
    try:
        with get_connection() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
