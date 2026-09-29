"""Connection Profile repository."""

from __future__ import annotations

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.models.connection_profile import ConnectionProfile


class ConnectionProfileRepository:
    """Persistence for ConnectionProfile rows."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_id(self, profile_id: int) -> ConnectionProfile | None:
        stmt = select(ConnectionProfile).where(ConnectionProfile.id == profile_id)
        return self._session.scalars(stmt).first()

    def get_by_id_for_update(self, profile_id: int) -> ConnectionProfile | None:
        stmt = (
            select(ConnectionProfile)
            .where(ConnectionProfile.id == profile_id)
            .with_for_update()
        )
        return self._session.scalars(stmt).first()

    def get_by_source_and_environment(
        self, source_name: str, environment: str
    ) -> ConnectionProfile | None:
        stmt = select(ConnectionProfile).where(
            ConnectionProfile.source_name == source_name,
            ConnectionProfile.environment == environment,
        )
        return self._session.scalars(stmt).first()

    def list_profiles(
        self,
        *,
        source_name: str | None = None,
        environment: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[ConnectionProfile]:
        stmt: Select[tuple[ConnectionProfile]] = select(ConnectionProfile)
        if source_name is not None:
            stmt = stmt.where(ConnectionProfile.source_name == source_name)
        if environment is not None:
            stmt = stmt.where(ConnectionProfile.environment == environment)
        stmt = (
            stmt.order_by(
                ConnectionProfile.updated_at.desc(), ConnectionProfile.id.desc()
            )
            .limit(limit)
            .offset(offset)
        )
        return list(self._session.scalars(stmt).all())

    def count_profiles(
        self,
        *,
        source_name: str | None = None,
        environment: str | None = None,
    ) -> int:
        stmt = select(func.count()).select_from(ConnectionProfile)
        if source_name is not None:
            stmt = stmt.where(ConnectionProfile.source_name == source_name)
        if environment is not None:
            stmt = stmt.where(ConnectionProfile.environment == environment)
        return int(self._session.scalar(stmt) or 0)

    def add(self, profile: ConnectionProfile) -> ConnectionProfile:
        self._session.add(profile)
        self._session.flush()
        return profile
