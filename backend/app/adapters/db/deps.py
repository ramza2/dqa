"""Database session FastAPI dependencies and schema bootstrap helpers."""

from __future__ import annotations

from collections.abc import Generator

from sqlalchemy.orm import Session

from app.adapters.db.session import get_engine, get_session_factory
from app.models import Base


def init_db_schema() -> None:
    """Create application tables if they do not already exist.

    This project does not yet use Alembic. Schema creation is intentional for the
    early roadmap and is a known limitation until a migration framework lands.
    """
    # Import models so metadata is populated.
    import app.models  # noqa: F401

    Base.metadata.create_all(bind=get_engine())


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
