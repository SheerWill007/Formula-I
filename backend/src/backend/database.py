"""
Database session management and utilities.
"""
from contextlib import contextmanager
from typing import Generator
from sqlalchemy.orm import Session, sessionmaker

from backend.extensions import get_engine


def get_session_factory() -> sessionmaker:
    """Get SQLAlchemy session factory."""
    engine = get_engine()
    return sessionmaker(bind=engine, autocommit=False, autoflush=False, expire_on_commit=False)


@contextmanager
def get_db_session() -> Generator[Session, None, None]:
    """
    Context manager for database sessions.
    Automatically commits on success, rolls back on error.
    
    Usage:
        with get_db_session() as db:
            # do database operations
            pass
    """
    SessionFactory = get_session_factory()
    session = SessionFactory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_db() -> Generator[Session, None, None]:
    """
    Dependency injection function for Flask routes.
    
    Usage in route:
        db = next(get_db())
        try:
            # use db
        finally:
            db.close()
    """
    SessionFactory = get_session_factory()
    session = SessionFactory()
    try:
        yield session
    finally:
        session.close()
