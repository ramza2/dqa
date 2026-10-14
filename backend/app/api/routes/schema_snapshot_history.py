"""Read-only Schema Snapshot revision history; capture is not an HTTP API."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.adapters.db.deps import get_db_session
from app.auth.dependencies import require_permission
from app.auth.models import AuthenticatedActor, Permission
from app.models.schema_snapshot_revision import SchemaSnapshotRevision
from app.schemas.schema_snapshot_history import (
    SchemaSnapshotRevisionDetail,
    SchemaSnapshotRevisionSummary,
)
from app.services.schema_snapshot_history import (
    get_snapshot_revision,
    list_snapshot_revisions,
)

router = APIRouter(
    prefix="/api/v1/schema-inspector/snapshots",
    tags=["schema-snapshot-history"],
)


def _summary(row: SchemaSnapshotRevision) -> SchemaSnapshotRevisionSummary:
    diff = row.diff_summary_json
    return SchemaSnapshotRevisionSummary(
        id=row.id,
        source_name=row.source_name,
        db_type=row.db_type,
        database_name=row.database_name,
        schema_name=row.schema_name,
        schema_fingerprint=row.schema_fingerprint,
        previous_revision_id=row.previous_revision_id,
        captured_by=row.captured_by,
        captured_at=row.captured_at,
        counts=row.counts_json,
        diff_status=diff["status"],
        total_changes=diff.get("total_changes"),
    )


@router.get("", response_model=list[SchemaSnapshotRevisionSummary])
def list_snapshots(
    source_name: str = Query(min_length=1, max_length=255, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,254}$"),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_db_session),
    _actor: AuthenticatedActor = Depends(require_permission(Permission.CATALOG_READ)),
) -> list[SchemaSnapshotRevisionSummary]:
    return [
        _summary(row) for row in list_snapshot_revisions(
            session, source_name=source_name, limit=limit, offset=offset,
        )
    ]


@router.get("/{revision_id}", response_model=SchemaSnapshotRevisionDetail)
def get_snapshot(
    revision_id: int,
    source_name: str = Query(min_length=1, max_length=255, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,254}$"),
    session: Session = Depends(get_db_session),
    _actor: AuthenticatedActor = Depends(require_permission(Permission.CATALOG_READ)),
) -> SchemaSnapshotRevisionDetail:
    row = get_snapshot_revision(session, revision_id, source_name=source_name)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "SNAPSHOT_REVISION_NOT_FOUND", "message": "snapshot revision not found"},
        )
    data = _summary(row).model_dump()
    return SchemaSnapshotRevisionDetail(
        **data,
        diff_counts=row.diff_summary_json.get("counts", {}),
        changes=row.diff_summary_json.get("changes", []),
    )
