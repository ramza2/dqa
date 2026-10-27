"""M2-1G: read-only structural comparison of M2-1D/E/F bundle to stored Snapshot.

Internal service only. Caller must independently authorize access to Snapshot
metadata and supply its existing scoped Session. No API, Oracle, database writes,
approval, READY Catalog, import or activation. A matching structure is NOT
independent DBA preflight and does not authenticate any sidecar/actor.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from sqlalchemy.orm import Session

from app.services.dba_metadata_offline import (
    SOURCE, OfflineMetadataError, validate_offline_metadata_export,
)
from app.services.offline_metadata_provenance import (
    ProvenanceClaimError, check_offline_provenance_claim,
)
from app.services.offline_metadata_review_draft import (
    OfflineReviewDraftError, check_offline_review_draft,
)
from app.services.schema_snapshot_diff import compare_schema_snapshots
from app.services.schema_snapshot_history import (
    _snapshot_from_payload, get_snapshot_revision, list_snapshot_revisions,
)
from app.services.schema_snapshot_review import (
    SnapshotReviewError, preview_snapshot_review,
)


class OfflineSnapshotLinkError(ValueError):
    """Public codes only; never expose source metadata or DB error details."""


LinkStatus = Literal[
    "STRUCTURAL_MATCH_UNTRUSTED",
    "STRUCTURAL_DIFFERENCE_UNTRUSTED",
    "SUPERSEDED",
]


@dataclass(frozen=True)
class OfflineSnapshotLinkPreview:
    source_name: str
    revision_id: int
    latest_revision_id: int
    link_status: LinkStatus
    identical: bool | None
    total_changes: int | None
    review_draft_status: str
    stored_review_status: str
    stored_snapshot_verified: bool = True
    issuer_authenticated: bool = False
    review_actor_authenticated: bool = False
    independent_preflight_verified: bool = False
    site_approval_verified: bool = False
    catalog_package_readiness: Literal["WARNING"] = "WARNING"
    catalog_ready: bool = False
    activation_eligible: bool = False


def _superseded(
    *,
    revision_id: int,
    latest_revision_id: int,
    draft_status: str,
) -> OfflineSnapshotLinkPreview:
    return OfflineSnapshotLinkPreview(
        source_name=SOURCE, revision_id=revision_id,
        latest_revision_id=latest_revision_id,
        link_status="SUPERSEDED", identical=None, total_changes=None,
        review_draft_status=draft_status, stored_review_status="SUPERSEDED",
    )


def preview_offline_snapshot_link(
    session: Session,
    *,
    source_name: str,
    revision_id: int,
    raw_metadata: bytes,
    raw_claim: bytes,
    raw_review_draft: bytes,
    now: datetime | None = None,
) -> OfflineSnapshotLinkPreview:
    """Compare validated untrusted bundle with a verified source-scoped Snapshot.

    No capture, no review-event mutation, no Catalog operations. This function
    checks latest again after comparison, but is NOT a transactional approval
    or capture gate. Synthetic tests mock the database Session.
    """
    if source_name != SOURCE or type(revision_id) is not int or revision_id <= 0:
        raise OfflineSnapshotLinkError("INVALID_SNAPSHOT_LINK_TARGET")

    try:
        offline = validate_offline_metadata_export(raw_metadata)
        claim = check_offline_provenance_claim(
            raw_metadata, offline, raw_claim, now=now,
        )
        draft = check_offline_review_draft(
            raw_metadata, offline, raw_claim, claim, raw_review_draft, now=now,
        )
    except (OfflineMetadataError, ProvenanceClaimError, OfflineReviewDraftError):
        raise OfflineSnapshotLinkError("INVALID_OFFLINE_REVIEW_BUNDLE") from None
    except Exception:
        raise OfflineSnapshotLinkError("INVALID_OFFLINE_REVIEW_BUNDLE") from None

    try:
        stored = preview_snapshot_review(
            session, source_name=source_name, revision_id=revision_id,
        )
        if (
            stored.source_name != SOURCE
            or stored.revision_id != revision_id
            or not stored.snapshot_verified
            or not stored.candidate_package_valid
            or stored.candidate_package_readiness != "WARNING"
            or stored.preflight_status != "NOT_VERIFIED"
            or stored.activation_eligible
        ):
            raise ValueError("invalid snapshot review result")

        if not stored.is_latest:
            return _superseded(
                revision_id=revision_id, latest_revision_id=stored.latest_revision_id,
                draft_status=draft.draft_status,
            )

        row = get_snapshot_revision(session, revision_id, source_name=source_name)
        if (
            row is None or row.id != revision_id or row.source_name != SOURCE
            or row.schema_fingerprint != stored.schema_fingerprint
            or row.captured_at != stored.captured_at
            or row.db_type != offline.snapshot.db_type
            or row.database_name != offline.snapshot.database_name
            or row.schema_name != offline.snapshot.schema_name
        ):
            raise ValueError("stored revision context mismatch")

        base = _snapshot_from_payload(row.snapshot_json)
        comparison = compare_schema_snapshots(base, offline.snapshot)
        if (
            comparison.base_fingerprint != stored.schema_fingerprint
            or comparison.target_fingerprint != offline.fingerprint
            or comparison.identical != (comparison.total_changes == 0)
        ):
            raise ValueError("inconsistent Snapshot comparison")

        # Read again: a concurrent capture may supersede the preview. No
        # positive authorization claim is made even for a latest match.
        latest = list_snapshot_revisions(
            session, source_name=source_name, limit=1,
        )
        if not latest:
            raise ValueError("snapshot history disappeared")
        if (
            latest[0].id != revision_id
            or latest[0].source_name != SOURCE
            or latest[0].schema_fingerprint != stored.schema_fingerprint
            or latest[0].captured_at != stored.captured_at
        ):
            return _superseded(
                revision_id=revision_id, latest_revision_id=latest[0].id,
                draft_status=draft.draft_status,
            )

        return OfflineSnapshotLinkPreview(
            source_name=SOURCE, revision_id=revision_id,
            latest_revision_id=revision_id,
            link_status=(
                "STRUCTURAL_MATCH_UNTRUSTED" if comparison.identical
                else "STRUCTURAL_DIFFERENCE_UNTRUSTED"
            ),
            identical=comparison.identical,
            total_changes=comparison.total_changes,
            review_draft_status=draft.draft_status,
            stored_review_status=stored.review_status,
        )
    except SnapshotReviewError as exc:
        if exc.code == "SNAPSHOT_REVISION_NOT_FOUND":
            raise OfflineSnapshotLinkError("SNAPSHOT_REVISION_NOT_FOUND") from None
        raise OfflineSnapshotLinkError("SNAPSHOT_LINK_UNVERIFIABLE") from None
    except Exception:
        raise OfflineSnapshotLinkError("SNAPSHOT_LINK_UNVERIFIABLE") from None
