"""Database session FastAPI dependencies."""

from __future__ import annotations

from collections.abc import Generator

from sqlalchemy.orm import Session

from app.adapters.db.session import get_session_factory


def get_db_session() -> Generator[Session, None, None]:
    """Yield a request-scoped SQLAlchemy session with commit/rollback."""
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
