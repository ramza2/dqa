"""Active Catalog management: READY-only activation with append-only audit."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.adapters.catalog.activation_errors import (
    CatalogActivationError,
    CatalogActivationErrorCode,
)
from app.models.catalog_active import CatalogActivationEvent, CatalogActiveRevision
from app.models.catalog_import import CatalogImportRevision
from app.repositories.catalog_active import CatalogActiveRepository
from app.repositories.catalog_import import CatalogImportRepository


@dataclass(frozen=True)
class ActivationResult:
    """Outcome of an activate request (pointer + optional switch metadata)."""

    source_name: str
    active_revision_id: int
    previous_revision_id: int | None
    schema_fingerprint: str
    package_readiness: str
    package_version: str
    activated_at: datetime
    changed: bool


@dataclass(frozen=True)
class ActiveCatalogView:
    """Metadata for one currently active source pointer."""

    source_name: str
    revision_id: int
    schema_fingerprint: str
    package_version: str
    package_readiness: str
    activated_at: datetime


def activate_catalog_revision(
    session: Session,
    revision_id: int,
    *,
    _race_retries: int = 1,
) -> ActivationResult:
    """Activate a READY+VALID import revision for its own source_name.

    Pointer update and activation-event insert run in the caller's transaction.
    Concurrent first-activations for the same source are serialized via
    UNIQUE(source_name) plus SELECT FOR UPDATE on the existing pointer row.
    """
    import_repo = CatalogImportRepository(session)
    active_repo = CatalogActiveRepository(session)

    revision = import_repo.get_by_id(revision_id)
    if revision is None:
        raise CatalogActivationError(
            CatalogActivationErrorCode.IMPORT_NOT_FOUND,
            "import revision not found",
        )

    _assert_activatable(revision)

    source_name = revision.source_name
    now = datetime.now(timezone.utc)

    pointer = active_repo.get_active_by_source_name(source_name, for_update=True)
    if pointer is not None and pointer.catalog_import_revision_id == revision.id:
        return ActivationResult(
            source_name=source_name,
            active_revision_id=revision.id,
            previous_revision_id=revision.id,
            schema_fingerprint=revision.schema_fingerprint,
            package_readiness=revision.package_readiness,
            package_version=revision.package_version,
            activated_at=pointer.activated_at,
            changed=False,
        )

    previous_id: int | None
    if pointer is None:
        previous_id = None
        pointer = CatalogActiveRevision(
            source_name=source_name,
            catalog_import_revision_id=revision.id,
            activated_at=now,
            created_at=now,
            updated_at=now,
        )
        try:
            active_repo.add_active(pointer)
        except IntegrityError:
            # Competing first-activation inserted the source_name row.
            session.rollback()
            if _race_retries <= 0:
                raise
            return activate_catalog_revision(
                session,
                revision_id,
                _race_retries=_race_retries - 1,
            )
    else:
        previous_id = pointer.catalog_import_revision_id
        pointer.catalog_import_revision_id = revision.id
        pointer.activated_at = now
        pointer.updated_at = now
        session.flush()

    active_repo.add_event(
        CatalogActivationEvent(
            source_name=source_name,
            previous_revision_id=previous_id,
            activated_revision_id=revision.id,
            activated_at=now,
        )
    )

    return ActivationResult(
        source_name=source_name,
        active_revision_id=revision.id,
        previous_revision_id=previous_id,
        schema_fingerprint=revision.schema_fingerprint,
        package_readiness=revision.package_readiness,
        package_version=revision.package_version,
        activated_at=now,
        changed=True,
    )


def list_active_catalogs(session: Session) -> list[ActiveCatalogView]:
    active_repo = CatalogActiveRepository(session)
    import_repo = CatalogImportRepository(session)
    views: list[ActiveCatalogView] = []
    for pointer in active_repo.list_active():
        revision = import_repo.get_by_id(pointer.catalog_import_revision_id)
        if revision is None:
            continue
        views.append(_to_view(pointer, revision))
    return views


def get_active_catalog(session: Session, source_name: str) -> ActiveCatalogView:
    active_repo = CatalogActiveRepository(session)
    pointer = active_repo.get_active_by_source_name(source_name)
    if pointer is None:
        raise CatalogActivationError(
            CatalogActivationErrorCode.ACTIVE_REVISION_NOT_FOUND,
            "active catalog revision not found for source",
        )
    revision = CatalogImportRepository(session).get_by_id(pointer.catalog_import_revision_id)
    if revision is None:
        raise CatalogActivationError(
            CatalogActivationErrorCode.ACTIVE_REVISION_NOT_FOUND,
            "active catalog revision not found for source",
        )
    return _to_view(pointer, revision)


def list_activation_events(
    session: Session,
    *,
    source_name: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[CatalogActivationEvent]:
    return CatalogActiveRepository(session).list_events(
        source_name=source_name,
        limit=limit,
        offset=offset,
    )


def _assert_activatable(revision: CatalogImportRevision) -> None:
    if revision.validation_status != "VALID" or revision.package_readiness != "READY":
        raise CatalogActivationError(
            CatalogActivationErrorCode.REVISION_NOT_ACTIVATABLE,
            "revision is not activatable",
        )


def _to_view(pointer: CatalogActiveRevision, revision: CatalogImportRevision) -> ActiveCatalogView:
    return ActiveCatalogView(
        source_name=pointer.source_name,
        revision_id=revision.id,
        schema_fingerprint=revision.schema_fingerprint,
        package_version=revision.package_version,
        package_readiness=revision.package_readiness,
        activated_at=pointer.activated_at,
    )
