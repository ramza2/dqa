"""S-04-C-2B-2B: read-only binding from stored Snapshot to offline contract.

Internal service only; no API, no Oracle access, no active Catalog mutation.
The source-restricted S-04-C-2A integrity preview is mandatory before
constructing SnapshotPreflightContext; neither mock matching nor an
administrator change-review event authenticates an external DBA issuer.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.services.schema_preflight_contract import (
    EvidenceProvider,
    PreflightContractResult,
    SnapshotPreflightContext,
    check_preflight_evidence_contract,
)
from app.services.schema_snapshot_history import (
    get_snapshot_revision, list_snapshot_revisions,
)
from app.services.schema_snapshot_review import (
    SnapshotReviewError, preview_snapshot_review,
)


def check_stored_snapshot_preflight_contract(
    session: Session,
    *,
    source_name: str,
    revision_id: int,
    provider: EvidenceProvider | None = None,
    now: datetime | None = None,
) -> PreflightContractResult:
    """Verify stored snapshot first, then compare only an untrusted evidence claim.

    A production trusted issuer/provider does NOT yet exist. This read-only
    bridge has no caller-facing route, approved external principal, or write
    path. The optional provider injection is for synthetic tests; default
    provider=None is fail closed. Recheck latest revision after any provider
    operation so an overlapping newer capture cannot return a stale
    structural_match=True. This is NOT a transactional approval/activation gate.
    """
    # Preview enforces immutable target/fingerprint/counts/diff integrity and
    # validates the offline Catalog v2 WARNING candidate, without writing.
    preview = preview_snapshot_review(
        session, source_name=source_name, revision_id=revision_id,
    )
    if not preview.is_latest:
        return PreflightContractResult(
            reason_code="SUPERSEDED_SNAPSHOT", structural_match=False,
        )

    try:
        row = get_snapshot_revision(
            session, revision_id, source_name=source_name,
        )
        if row is None:
            raise SnapshotReviewError("SNAPSHOT_REVISION_NOT_FOUND")
        if (
            row.id != preview.revision_id
            or row.source_name != preview.source_name
            or row.schema_fingerprint != preview.schema_fingerprint
            or row.captured_at != preview.captured_at
        ):
            raise SnapshotReviewError("SNAPSHOT_REVIEW_UNVERIFIABLE")

        context = SnapshotPreflightContext(
            source_name=preview.source_name,
            revision_id=row.id,
            latest_revision_id=preview.latest_revision_id,
            schema_fingerprint=preview.schema_fingerprint,
            db_type=row.db_type,
            database_name=row.database_name,
            schema_name=row.schema_name,
            captured_at=preview.captured_at,
            snapshot_verified=preview.snapshot_verified,
        )
        result = check_preflight_evidence_contract(
            context, provider=provider, now=now,
        )

        # Second source-scoped read protects against provider-induced
        # concurrent changes in normal READ COMMITTED execution. Do not
        # misrepresent it as a durable lock or DB-approved attestation.
        latest = list_snapshot_revisions(
            session, source_name=source_name, limit=1,
        )
        if (
            not latest
            or latest[0].id != preview.revision_id
            or latest[0].schema_fingerprint != preview.schema_fingerprint
        ):
            return PreflightContractResult(
                reason_code="SUPERSEDED_SNAPSHOT", structural_match=False,
            )
        return result
    except SnapshotReviewError:
        raise
    except Exception:
        # Never expose SQL/Oracle/provider exception body.
        raise SnapshotReviewError("SNAPSHOT_PREFLIGHT_CONTEXT_UNAVAILABLE") from None
