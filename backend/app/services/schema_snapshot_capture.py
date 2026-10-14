"""Authorize at the API edge; orchestrate explicit Inspector capture + durable commit.

This is an optional development/test feature, not automatic Catalog activation.
Target selection remains configured server-side and fail-closed.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.services.schema_inspection import collect_configured_schema_snapshot
from app.services.schema_snapshot_history import CaptureResult, capture_snapshot_revision


def capture_configured_schema(
    settings: Settings,
    session: Session,
    *,
    captured_by: str,
    capture_request_id: UUID,
    expected_previous_revision_id: int | None,
) -> CaptureResult:
    """Collect the configured Oracle metadata then append and *commit* to DQA.

    Caller has already authenticated with CATALOG_MANAGE. The collector
    enforces separate metadata credentials, feature flag and dev/test
    environment before any Oracle connection. The client cannot provide an
    Oracle target or SQL. If persistence fails, no successful HTTP result
    is returned. No import/readiness/activation changes.
    """
    collected = collect_configured_schema_snapshot(settings)
    try:
        result = capture_snapshot_revision(
            session,
            collected.snapshot,
            source_name=collected.source_name,
            captured_by=captured_by,
            capture_request_id=capture_request_id,
            expected_previous_revision_id=expected_previous_revision_id,
        )
        session.commit()
        return result
    except Exception:
        session.rollback()
        raise
