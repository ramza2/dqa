"""Connection Profile persistence (no live DEMIS credentials or execution)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ConnectionProfile(Base):
    """Logical Catalog source/environment binding to a live DEMIS target.

    Stores only non-secret connection metadata and a credential *reference*.
    Never stores password, token, or full DSN secret values.
    """

    __tablename__ = "connection_profiles"
    __table_args__ = (
        UniqueConstraint(
            "source_name",
            "environment",
            name="uq_connection_profiles_source_environment",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    environment: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # DBMS-neutral label only (e.g. "oracle", "postgresql"); never selects a driver.
    dbms_type: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # Non-secret target metadata for operator configuration (not used for live connect yet).
    host: Mapped[str | None] = mapped_column(String(255), nullable=True)
    port: Mapped[int | None] = mapped_column(Integer, nullable=True)
    database_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    username: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Secret-store / env reference key only — never a password or DSN value.
    credential_secret_ref: Mapped[str | None] = mapped_column(String(512), nullable=True)

    created_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    updated_by: Mapped[str | None] = mapped_column(String(255), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
