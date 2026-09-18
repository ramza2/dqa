"""SQLAlchemy engine and session helpers for DQA PostgreSQL."""

from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings, get_settings


@lru_cache
def get_engine(database_url: str | None = None) -> Engine:
    """Create (or reuse) the SQLAlchemy engine for the DQA database."""
    settings = get_settings()
    url = database_url or settings.database_url
    return create_engine(
        url,
        pool_pre_ping=True,
        future=True,
    )


@lru_cache
def get_session_factory(database_url: str | None = None) -> sessionmaker[Session]:
    """Return a session factory bound to the DQA engine."""
    engine = get_engine(database_url)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


@contextmanager
def session_scope(database_url: str | None = None) -> Iterator[Session]:
    """Provide a transactional scope around a series of operations."""
    session = get_session_factory(database_url)()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def check_database_connectivity(
    settings: Settings | None = None,
    *,
    timeout_seconds: float = 3.0,
) -> None:
    """Verify that the DQA PostgreSQL database accepts connections.

    Raises sqlalchemy.exc.SQLAlchemyError (or subclass) on failure.
    """
    cfg = settings or get_settings()
    engine = create_engine(
        cfg.sqlalchemy_database_url,
        pool_pre_ping=True,
        future=True,
        connect_args={"connect_timeout": max(1, int(timeout_seconds))},
    )
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    finally:
        engine.dispose()
