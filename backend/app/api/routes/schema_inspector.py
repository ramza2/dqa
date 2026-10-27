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
from app.services.mock_inspector_binding import (
    MockInspectorBindingError, require_mock_inspector_binding,
)

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


_MOCK_BINDING_ERRORS = {
    "MOCK_INSPECTOR_DISABLED": PublicErrorSpec(
        status.HTTP_403_FORBIDDEN, "mock Inspector integration is disabled",
    ),
    "MOCK_PROFILE_NOT_FOUND": PublicErrorSpec(
        status.HTTP_404_NOT_FOUND, "connection profile not found",
    ),
    "MOCK_PROFILE_MISMATCH": PublicErrorSpec(
        status.HTTP_409_CONFLICT, "profile is not the pinned development mock",
    ),
    "MOCK_PROFILE_INACTIVE": PublicErrorSpec(
        status.HTTP_409_CONFLICT, "mock profile is not active",
    ),
    "MOCK_INSPECTOR_TARGET_MISMATCH": PublicErrorSpec(
        status.HTTP_409_CONFLICT, "mock Inspector target does not match selected profile",
    ),
    "MOCK_INSPECTOR_ACCOUNT_NOT_SEPARATE": PublicErrorSpec(
        status.HTTP_409_CONFLICT, "Inspector requires a distinct metadata account",
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


# M2-1B: explicit Mock-only selector. Legacy configured-only routes remain
# available under their original independent gates for compatibility.
def _mock_binding_http_error(exc: MockInspectorBindingError) -> HTTPException:
    return build_public_http_error(
        error_code=exc.code,
        contracts={**_PUBLIC_ERRORS, **_MOCK_BINDING_ERRORS},
        fallback_code="MOCK_INSPECTOR_BLOCKED",
        fallback_status_code=status.HTTP_409_CONFLICT,
        fallback_message="selected Mock cannot be inspected",
    )


@router.get("/mock-targets/{profile_id}/readiness")
def mock_inspector_readiness(
    profile_id: int,
    session: Session = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
    _catalog_actor: AuthenticatedActor = Depends(
        require_permission(Permission.CATALOG_MANAGE)
    ),
    _profile_actor: AuthenticatedActor = Depends(
        require_permission(Permission.CONNECTION_PROFILE_MANAGE)
    ),
) -> dict:
    """Configuration-only, sanitized readiness, NOT a live connection or approval."""
    try:
        require_mock_inspector_binding(session, profile_id, settings)
    except MockInspectorBindingError as exc:
        return {
            "profile_id": profile_id, "ready": False, "reason_code": exc.code,
            "schema_name": None, "live_connection_tested": False,
            "site_approved": False, "catalog_activated": False,
        }
    return {
        "profile_id": profile_id, "ready": True, "reason_code": "READY_FOR_DEV_INSPECTION",
        "schema_name": settings.schema_inspector_schema_name,
        "live_connection_tested": False,
        "site_approved": False, "catalog_activated": False,
    }


@router.post(
    "/mock-targets/{profile_id}/inspect", response_model=SchemaInspectionSummary,
)
def inspect_selected_mock(
    profile_id: int,
    _body: SchemaInspectionRequest,
    session: Session = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
    _catalog_actor: AuthenticatedActor = Depends(
        require_permission(Permission.CATALOG_MANAGE)
    ),
    _profile_actor: AuthenticatedActor = Depends(
        require_permission(Permission.CONNECTION_PROFILE_MANAGE)
    ),
) -> SchemaInspectionSummary:
    """Explicit metadata-only scan; caller NEVER supplies target, schema or SQL."""
    try:
        require_mock_inspector_binding(session, profile_id, settings)
        return inspect_configured_schema(settings)
    except MockInspectorBindingError as exc:
        raise _mock_binding_http_error(exc) from None
    except SchemaInspectionError as exc:
        raise build_public_http_error(
            error_code=exc.code, contracts=_PUBLIC_ERRORS,
            fallback_code="INSPECTOR_INTERNAL_ERROR",
            fallback_status_code=500, fallback_message="schema inspection failed",
        ) from None
    except Exception:
        raise HTTPException(status_code=500, detail={
            "code": "INSPECTOR_INTERNAL_ERROR", "message": "schema inspection failed",
        }) from None


@router.post(
    "/mock-targets/{profile_id}/snapshots/capture",
    response_model=SchemaSnapshotCaptureResponse,
)
def capture_selected_mock(
    profile_id: int,
    body: SchemaSnapshotCaptureRequest,
    session: Session = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
    actor: AuthenticatedActor = Depends(require_permission(Permission.CATALOG_MANAGE)),
    _profile_actor: AuthenticatedActor = Depends(
        require_permission(Permission.CONNECTION_PROFILE_MANAGE)
    ),
) -> SchemaSnapshotCaptureResponse:
    """Selected Mock metadata Snapshot only; append-only; never Catalog activation."""
    try:
        require_mock_inspector_binding(session, profile_id, settings)
        saved = capture_configured_schema(
            settings, session, captured_by=actor.actor_id,
            capture_request_id=body.capture_request_id,
            expected_previous_revision_id=body.expected_previous_revision_id,
        )
        row = saved.revision
        diff = row.diff_summary_json
        return SchemaSnapshotCaptureResponse(
            id=row.id, source_name=row.source_name, db_type=row.db_type,
            database_name=row.database_name, schema_name=row.schema_name,
            schema_fingerprint=row.schema_fingerprint,
            previous_revision_id=row.previous_revision_id,
            captured_by=row.captured_by, captured_at=row.captured_at,
            counts=row.counts_json, diff_status=diff["status"],
            total_changes=diff.get("total_changes"), created=saved.created,
        )
    except MockInspectorBindingError as exc:
        raise _mock_binding_http_error(exc) from None
    except (SchemaInspectionError, SnapshotHistoryError) as exc:
        raise build_public_http_error(
            error_code=exc.code, contracts=_CAPTURE_ERRORS,
            fallback_code="SNAPSHOT_CAPTURE_FAILED",
            fallback_status_code=500, fallback_message="schema Snapshot capture failed",
        ) from None
    except Exception:
        raise HTTPException(status_code=500, detail={
            "code": "SNAPSHOT_CAPTURE_FAILED", "message": "schema Snapshot capture failed",
        }) from None
