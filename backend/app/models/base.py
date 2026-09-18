"""Declarative base for DQA persistence models.

Domain tables (catalog revisions, templates, audit) are added in later PRs.
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Shared SQLAlchemy declarative base."""
