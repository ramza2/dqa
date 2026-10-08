"""Revision-scoped Data Discovery embedding persistence (Phase 27-B)."""

from __future__ import annotations

from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

# Approved embedding width for this phase (BGE-M3). Fail closed on mismatch.
EMBEDDING_VECTOR_DIMENSION = 1024


class DataDiscoveryEmbedding(Base):
    """One embedding vector for a DataDiscoveryDocument under a model_key."""

    __tablename__ = "data_discovery_embeddings"
    __table_args__ = (
        UniqueConstraint(
            "data_discovery_document_id",
            "model_key",
            name="uq_data_discovery_embeddings_document_model_key",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    data_discovery_document_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("data_discovery_documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    model_key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(128), nullable=False)
    model_name: Mapped[str] = mapped_column(String(255), nullable=False)
    model_revision: Mapped[str | None] = mapped_column(String(128), nullable=True)
    dimension: Mapped[int] = mapped_column(Integer, nullable=False)
    normalized: Mapped[bool] = mapped_column(Boolean, nullable=False)

    document_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    embedding: Mapped[list[float]] = mapped_column(
        Vector(EMBEDDING_VECTOR_DIMENSION), nullable=False
    )

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
