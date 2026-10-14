"""Explicit administrator-only metadata inspection (no automatic Catalog import)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.adapters.db.deps import get_db_session

from app.api.public_errors import PublicErrorSpec, build_public_http_error
from app.auth.dependencies import require_permission
from app.auth.models import AuthenticatedActor, Permission
from app.core.config import Settings, get_settings
from app.schemas.schema_inspector import SchemaInspectionRequest, SchemaInspectionSummary
from app.schemas.schema_snapshot_history import (
    SchemaSnapshotCaptureRequest, SchemaSnapshotCaptureResponse,
)
from app.services.schema_snapshot_capture import capture_configured_schema
from app.services.schema_snapshot_history import SnapshotHistoryError
from app.services.schema_inspection import SchemaInspectionError, inspect_configured_schema

router = APIRouter(prefix="/api/v1/schema-inspector", tags=["schema-inspector"])

_PUBLIC_ERRORS = {
    "INSPECTOR_DISABLED": PublicErrorSpec(
        status.HTTP_503_SERVICE_UNAVAILABLE,
        "schema inspection is disabled",
    ),
    "INSPECTOR_ENV_NOT_ALLOWED": PublicErrorSpec(
        status.HTTP_503_SERVICE_UNAVAILABLE,
        "schema inspection is not approved for this environment",
    ),
    "INSPECTOR_NOT_CONFIGURED": PublicErrorSpec(
        status.HTTP_503_SERVICE_UNAVAILABLE,
        "schema inspection target is not configured",
    ),
    "INSPECTOR_METADATA_FAILED": PublicErrorSpec(
        status.HTTP_502_BAD_GATEWAY,
        "schema metadata collection failed",
    ),
}


_CAPTURE_ERRORS = {
    **_PUBLIC_ERRORS,
    "STALE_SNAPSHOT_REVISION": PublicErrorSpec(
        status.HTTP_409_CONFLICT, "the source Snapshot revision has changed",
    ),
    "CAPTURE_REQUEST_REUSED": PublicErrorSpec(
        status.HTTP_409_CONFLICT, "capture request id conflicts with an earlier capture",
    ),
    "TARGET_IDENTITY_MISMATCH": PublicErrorSpec(
        status.HTTP_409_CONFLICT, "source database or schema differs from recorded history",
    ),
    "CORRUPT_BASELINE": PublicErrorSpec(
        status.HTTP_409_CONFLICT, "previous Snapshot revision is not verifiable",
    ),
    "INVALID_SNAPSHOT": PublicErrorSpec(
        status.HTTP_422_UNPROCESSABLE_CONTENT, "collected schema Snapshot is invalid",
    ),
    "DIFF_TOO_LARGE": PublicErrorSpec(
        status.HTTP_413_CONTENT_TOO_LARGE, "schema change summary exceeds the limit",
    ),
}


@router.post("/inspect", response_model=SchemaInspectionSummary)
def inspect_schema(
    _body: SchemaInspectionRequest,
    settings: Settings = Depends(get_settings),
    _actor: AuthenticatedActor = Depends(require_permission(Permission.CATALOG_MANAGE)),
) -> SchemaInspectionSummary:
    """Inspect one server-configured schema only; do not persist or activate."""
    try:
        return inspect_configured_schema(settings)
    except SchemaInspectionError as exc:
        raise build_public_http_error(
            error_code=exc.code,
            contracts=_PUBLIC_ERRORS,
            fallback_code="INSPECTOR_INTERNAL_ERROR",
            fallback_status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            fallback_message="schema inspection failed",
        ) from None
    except Exception:
        # Ensure any unreviewed driver/programming failure never reaches a client.
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "code": "INSPECTOR_INTERNAL_ERROR",
                "message": "schema inspection failed",
            },
        ) from None


@router.post("/snapshots/capture", response_model=SchemaSnapshotCaptureResponse)
def capture_snapshot(
    body: SchemaSnapshotCaptureRequest,
    settings: Settings = Depends(get_settings),
    session: Session = Depends(get_db_session),
    actor: AuthenticatedActor = Depends(require_permission(Permission.CATALOG_MANAGE)),
) -> SchemaSnapshotCaptureResponse:
    """Explicit metadata-only capture, durable history; never Catalog activation.

    Target/credential/schema/source/SQL are read solely from server settings.
    The Inspector remains off by default and forbidden in production.
    """
    try:
        saved = capture_configured_schema(
            settings,
            session,
            captured_by=actor.actor_id,
            capture_request_id=body.capture_request_id,
            expected_previous_revision_id=body.expected_previous_revision_id,
        )
        row = saved.revision
        diff = row.diff_summary_json
        return SchemaSnapshotCaptureResponse(
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
            created=saved.created,
        )
    except (SchemaInspectionError, SnapshotHistoryError) as exc:
        raise build_public_http_error(
            error_code=exc.code,
            contracts=_CAPTURE_ERRORS,
            fallback_code="SNAPSHOT_CAPTURE_FAILED",
            fallback_status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            fallback_message="schema Snapshot capture failed",
        ) from None
    except Exception:
        # Never expose DB/Oracle exception bodies, credentials or metadata.
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "code": "SNAPSHOT_CAPTURE_FAILED",
                "message": "schema Snapshot capture failed",
            },
        ) from None
