"""M2-1F: untrusted manual-review DRAFT bound to an offline metadata export.

This is not administrator authentication, an authorized review event, independent
DBA evidence, a production preflight, or a Catalog approval/activation mechanism.
No persistence, network access or database connections.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from app.services.dba_metadata_offline import OfflinePreview, SOURCE
from app.services.offline_metadata_provenance import ProvenanceClaimReview

FORMAT = "dqa-offline-metadata-review-draft-v1"
MAX_REVIEW_DRAFT_BYTES = 8192
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,126}[A-Za-z0-9]$")
_FIELDS = frozenset({
    "format", "source_name", "metadata_file_sha256", "claim_file_sha256",
    "schema_fingerprint", "claimed_reviewer_id", "decision", "reason_code",
    "claimed_reviewed_at",
})
_DECISIONS = {
    "ACKNOWLEDGED": frozenset({"REVIEWED_METADATA"}),
    "CHANGES_REQUESTED": frozenset({"RECHECK_REQUIRED", "SCOPE_UNCLEAR"}),
}


class OfflineReviewDraftError(ValueError):
    """Stable codes only; no raw fields, identities, file paths, or patient data."""


@dataclass(frozen=True)
class OfflineReviewDraftResult:
    """Describes a draft only; NEVER gives approval eligibility."""

    draft_status: str
    file_binding: str = "MATCHED_UNTRUSTED"
    actor_authenticated: bool = False
    site_approval_verified: bool = False
    independent_preflight_verified: bool = False
    catalog_ready: bool = False
    activation_eligible: bool = False


def _parse_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for name, item in pairs:
        if name in value:
            raise OfflineReviewDraftError("DUPLICATE_REVIEW_FIELD")
        value[name] = item
    return value


def _invalid_constant(_raw: str) -> None:
    raise OfflineReviewDraftError("INVALID_REVIEW_JSON_CONSTANT")


def _parse_time(value: object) -> datetime:
    if not isinstance(value, str) or len(value) > 35:
        raise OfflineReviewDraftError("INVALID_REVIEW_TIME")
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if stamp.tzinfo is None or stamp.utcoffset() is None:
            raise ValueError("timezone required")
        return stamp.astimezone(timezone.utc)
    except (ValueError, OverflowError):
        raise OfflineReviewDraftError("INVALID_REVIEW_TIME") from None


def check_offline_review_draft(
    raw_metadata: bytes,
    preview: OfflinePreview,
    raw_claim: bytes,
    claim: ProvenanceClaimReview,
    raw_review: bytes,
    *,
    now: datetime | None = None,
) -> OfflineReviewDraftResult:
    """Check draft structure/binding only; never authenticate a reviewer."""
    if (
        not isinstance(raw_metadata, bytes)
        or not isinstance(preview, OfflinePreview)
        or not isinstance(raw_claim, bytes)
        or not isinstance(claim, ProvenanceClaimReview)
        or claim.claim_binding != "MATCHED_UNTRUSTED"
        or not isinstance(raw_review, bytes)
    ):
        raise OfflineReviewDraftError("INVALID_REVIEW_CONTEXT")
    if not 0 < len(raw_review) <= MAX_REVIEW_DRAFT_BYTES:
        raise OfflineReviewDraftError("INVALID_REVIEW_SIZE")

    try:
        data = json.loads(
            raw_review.decode("utf-8", "strict"),
            object_pairs_hook=_parse_pairs, parse_constant=_invalid_constant,
        )
    except OfflineReviewDraftError:
        raise
    except (ValueError, UnicodeError, TypeError):
        raise OfflineReviewDraftError("INVALID_REVIEW_JSON") from None

    if not isinstance(data, dict) or set(data) != _FIELDS:
        raise OfflineReviewDraftError("INVALID_REVIEW_FIELDS")
    if (
        data["format"] != FORMAT or data["source_name"] != SOURCE
        or preview.source_name != SOURCE
        or not isinstance(data["claimed_reviewer_id"], str)
        or len(data["claimed_reviewer_id"]) > 128
        or _SAFE_ID.fullmatch(data["claimed_reviewer_id"]) is None
    ):
        raise OfflineReviewDraftError("INVALID_REVIEW_FIELDS")

    decision, reason_code = data["decision"], data["reason_code"]
    if (
        not isinstance(decision, str)
        or decision not in _DECISIONS
        or not isinstance(reason_code, str)
        or reason_code not in _DECISIONS[decision]
    ):
        raise OfflineReviewDraftError("INVALID_REVIEW_DECISION")

    expected = (
        hashlib.sha256(raw_metadata).hexdigest(),
        hashlib.sha256(raw_claim).hexdigest(),
        preview.fingerprint,
    )
    values = (
        data["metadata_file_sha256"],
        data["claim_file_sha256"],
        data["schema_fingerprint"],
    )
    if any(
        not isinstance(value, str) or _SHA256.fullmatch(value) is None
        for value in values
    ) or values != expected or (
        claim.bound_metadata_sha256 != expected[0]
        or claim.schema_fingerprint != expected[2]
    ):
        raise OfflineReviewDraftError("REVIEW_BINDING_MISMATCH")

    stamp = _parse_time(data["claimed_reviewed_at"])
    try:
        moment = now if now is not None else datetime.now(timezone.utc)
        if not isinstance(moment, datetime) or moment.tzinfo is None or moment.utcoffset() is None:
            raise ValueError("bad clock")
        current = moment.astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError):
        raise OfflineReviewDraftError("INVALID_REVIEW_CONTEXT") from None
    if stamp > current + timedelta(minutes=5):
        raise OfflineReviewDraftError("REVIEW_FUTURE_TIMESTAMP")

    # Even a self-declared ACKNOWLEDGED never marks trusted review complete.
    return OfflineReviewDraftResult(
        draft_status=(
            "ACKNOWLEDGED_UNVERIFIED"
            if data["decision"] == "ACKNOWLEDGED"
            else "CHANGES_REQUESTED_UNVERIFIED"
        ),
    )
