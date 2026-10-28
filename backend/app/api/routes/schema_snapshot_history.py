"""Snapshot history, read-only preview, and explicitly gated review journal."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.adapters.db.deps import get_db_session
from app.core.config import Settings, get_settings
from app.auth.dependencies import require_permission
from app.auth.models import AuthenticatedActor, Permission
from app.models.schema_snapshot_revision import SchemaSnapshotRevision
from app.schemas.schema_snapshot_history import (
    SchemaSnapshotRevisionDetail,
    SchemaSnapshotRevisionSummary,
    SchemaSnapshotReviewPreview,
    SnapshotErdResponse,
    SnapshotChangeReviewRequest,
    SnapshotChangeReviewEventResponse,
)
from app.services.schema_snapshot_history import (
    get_snapshot_revision,
    list_snapshot_revisions,
)
from app.services.schema_snapshot_erd import SnapshotErdError, build_snapshot_erd
from app.services.schema_snapshot_report import SnapshotReportError, build_snapshot_table_docx
from app.services.schema_snapshot_review import (
    SnapshotReviewError, preview_snapshot_review,
)
from app.services.schema_snapshot_review_events import (
    SnapshotReviewEventError, list_review_events, record_review_event,
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


@router.get("/{revision_id}/review", response_model=SchemaSnapshotReviewPreview)
def get_snapshot_review_preview(
    revision_id: int,
    source_name: str = Query(
        min_length=1, max_length=255,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,254}$",
    ),
    session: Session = Depends(get_db_session),
    _actor: AuthenticatedActor = Depends(require_permission(Permission.CATALOG_READ)),
) -> SchemaSnapshotReviewPreview:
    """Read-only Snapshot and offline v2 WARNING candidate checks.

    This does not constitute independent preflight, review approval or READY.
    """
    try:
        result = preview_snapshot_review(
            session, source_name=source_name, revision_id=revision_id,
        )
    except SnapshotReviewError as exc:
        if exc.code == "SNAPSHOT_REVISION_NOT_FOUND":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "code": "SNAPSHOT_REVISION_NOT_FOUND",
                    "message": "snapshot revision not found",
                },
            ) from None
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "SNAPSHOT_REVIEW_UNVERIFIABLE",
                "message": "snapshot review preview cannot be verified",
            },
        ) from None
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "code": "SNAPSHOT_REVIEW_FAILED",
                "message": "snapshot review preview failed",
            },
        ) from None
    return SchemaSnapshotReviewPreview(**result.__dict__)


def _review_event_response(row, created=None) -> SnapshotChangeReviewEventResponse:
    return SnapshotChangeReviewEventResponse(
        id=row.id,
        source_name=row.source_name,
        snapshot_revision_id=row.snapshot_revision_id,
        schema_fingerprint=row.schema_fingerprint,
        previous_review_event_id=row.previous_review_event_id,
        decision=row.decision,
        reason_code=row.reason_code,
        reviewed_by=row.reviewed_by,
        reviewed_at=row.reviewed_at,
        created=created,
    )


@router.get(
    "/{revision_id}/reviews",
    response_model=list[SnapshotChangeReviewEventResponse],
)
def get_change_review_events(
    revision_id: int,
    source_name: str = Query(
        min_length=1, max_length=255,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,254}$",
    ),
    session: Session = Depends(get_db_session),
    _actor: AuthenticatedActor = Depends(require_permission(Permission.CATALOG_READ)),
) -> list[SnapshotChangeReviewEventResponse]:
    try:
        events = list_review_events(
            session, source_name=source_name, snapshot_revision_id=revision_id,
        )
    except SnapshotReviewEventError:
        raise HTTPException(
            status_code=404,
            detail={"code": "SNAPSHOT_REVISION_NOT_FOUND", "message": "snapshot revision not found"},
        ) from None
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "code": "SNAPSHOT_REVIEW_HISTORY_FAILED",
                "message": "schema change review history could not be read",
            },
        ) from None
    return [_review_event_response(row) for row in events]


@router.post(
    "/{revision_id}/reviews",
    response_model=SnapshotChangeReviewEventResponse,
)
def post_change_review_event(
    revision_id: int,
    body: SnapshotChangeReviewRequest,
    source_name: str = Query(
        min_length=1, max_length=255,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,254}$",
    ),
    session: Session = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
    actor: AuthenticatedActor = Depends(require_permission(Permission.CATALOG_MANAGE)),
) -> SnapshotChangeReviewEventResponse:
    """Acknowledge/request changes only. Not DBA preflight or Catalog READY."""
    if (
        settings.app_env not in ("test", "development")
        or not settings.schema_snapshot_review_enabled
    ):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "SNAPSHOT_REVIEW_WRITES_DISABLED",
                "message": "schema change review recording is disabled",
            },
        )
    try:
        result = record_review_event(
            session,
            source_name=source_name,
            snapshot_revision_id=revision_id,
            expected_schema_fingerprint=body.expected_schema_fingerprint,
            review_request_id=body.review_request_id,
            expected_previous_review_event_id=body.expected_previous_review_event_id,
            decision=body.decision,
            reason_code=body.reason_code,
            reviewed_by=actor.actor_id,
        )
    except SnapshotReviewEventError as exc:
        if exc.code == "SNAPSHOT_REVISION_NOT_FOUND":
            code, http_status = exc.code, status.HTTP_404_NOT_FOUND
        elif exc.code in ("INVALID_SOURCE", "INVALID_FINGERPRINT",
                          "INVALID_REQUEST_ID", "INVALID_ACTOR",
                          "INVALID_PREDECESSOR", "INVALID_DECISION"):
            code, http_status = exc.code, status.HTTP_422_UNPROCESSABLE_CONTENT
        else:
            code, http_status = exc.code, status.HTTP_409_CONFLICT
        raise HTTPException(
            status_code=http_status,
            detail={"code": code, "message": "schema change review request rejected"},
        ) from None
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "code": "SNAPSHOT_REVIEW_RECORD_FAILED",
                "message": "schema change review recording failed",
            },
        ) from None
    return _review_event_response(result.event, result.created)


_DOCX_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
)


@router.get("/{revision_id}/report.docx")
def download_snapshot_table_report(
    revision_id: int,
    source_name: str = Query(
        min_length=1, max_length=255,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,254}$",
    ),
    schema_name: str = Query(min_length=1, max_length=255),
    table_name: str = Query(min_length=1, max_length=255),
    session: Session = Depends(get_db_session),
    _actor: AuthenticatedActor = Depends(require_permission(Permission.CATALOG_MANAGE)),
) -> Response:
    """Privileged metadata export; no source SQL, no Oracle and no activation."""
    row = get_snapshot_revision(session, revision_id, source_name=source_name)
    if row is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "SNAPSHOT_REVISION_NOT_FOUND", "message": "snapshot not found"},
        )
    try:
        content = build_snapshot_table_docx(
            row, schema_name=schema_name, table_name=table_name,
        )
    except SnapshotReportError as exc:
        if exc.code == "SNAPSHOT_REPORT_TABLE_NOT_FOUND":
            code, http_status = exc.code, 404
        elif exc.code == "SNAPSHOT_REPORT_SCOPE_TOO_LARGE":
            code, http_status = exc.code, 413
        elif exc.code == "SNAPSHOT_REPORT_UNVERIFIABLE":
            code, http_status = exc.code, 409
        else:
            code, http_status = "SNAPSHOT_REPORT_RENDER_FAILED", 500
        raise HTTPException(
            status_code=http_status,
            detail={"code": code, "message": "snapshot report unavailable"},
        ) from None
    return Response(
        content=content,
        media_type=_DOCX_CONTENT_TYPE,
        headers={
            "Content-Disposition": (
                f'attachment; filename="dqa-snapshot-{revision_id}-table-analysis.docx"'
            ),
            "Cache-Control": "no-store",
            "Pragma": "no-cache",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/{revision_id}/erd", response_model=SnapshotErdResponse)
def get_snapshot_erd(
    revision_id: int,
    source_name: str = Query(
        min_length=1, max_length=255,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,254}$",
    ),
    q: str | None = Query(default=None, max_length=128),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=30, ge=1, le=50),
    focus_schema: str | None = Query(default=None, min_length=1, max_length=255),
    focus_table: str | None = Query(default=None, min_length=1, max_length=255),
    session: Session = Depends(get_db_session),
    _actor: AuthenticatedActor = Depends(require_permission(Permission.CATALOG_READ)),
) -> SnapshotErdResponse:
    """Bounded physical metadata preview from a stored Snapshot, NOT Catalog."""
    row = get_snapshot_revision(session, revision_id, source_name=source_name)
    if row is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "SNAPSHOT_REVISION_NOT_FOUND", "message": "snapshot not found"},
        )
    try:
        projection = build_snapshot_erd(
            row, query=q, offset=offset, limit=limit,
            focus_schema=focus_schema, focus_table=focus_table,
        )
    except SnapshotErdError as exc:
        if exc.code == "SNAPSHOT_ERD_TABLE_NOT_FOUND":
            code, http_status = exc.code, 404
        elif exc.code == "SNAPSHOT_ERD_INVALID_FOCUS":
            code, http_status = exc.code, 422
        else:
            code, http_status = "SNAPSHOT_ERD_UNVERIFIABLE", 409
        raise HTTPException(
            status_code=http_status,
            detail={"code": code, "message": "snapshot ERD preview unavailable"},
        ) from None
    return SnapshotErdResponse(**projection)


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
