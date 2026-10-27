"""M2-1E: untrusted *claimed* provenance for M2-1D offline metadata exports.

The claim is a self-asserted, unsigned sidecar. Digest/identity checks detect
mismatched bytes; they NEVER authenticate a DBA or confer independent preflight,
review approval, Catalog READY, import or activation. Pure offline computation.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from app.services.dba_metadata_offline import (
    DATABASE, SCHEMA, SOURCE, OfflinePreview,
)

CLAIM_FORMAT = "dqa-offline-oracle-provenance-claim-v1"
MAX_CLAIM_BYTES = 16_384
_REQUIRED_COVERAGE = frozenset({
    "tables", "columns", "primary_keys", "unique_constraints",
    "foreign_keys", "indexes",
})
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,126}[A-Za-z0-9]$")
_FIELDS = frozenset({
    "format", "source_name", "db_type", "database_name", "schema_name",
    "metadata_file_sha256", "schema_fingerprint", "claimed_issuer_id",
    "claimed_reference", "claimed_issued_at", "coverage", "omissions",
})


class ProvenanceClaimError(ValueError):
    """Stable non-sensitive failure code, never include untrusted text."""


@dataclass(frozen=True)
class ProvenanceClaimReview:
    """Structural claim match only. Never an authorization or approval."""

    bound_metadata_sha256: str
    schema_fingerprint: str
    claim_binding: str = "MATCHED_UNTRUSTED"
    issuer_authenticated: bool = False
    independent_preflight_verified: bool = False
    review_status: str = "NOT_REVIEWED"
    approval_verified: bool = False
    activation_eligible: bool = False


def _no_duplicates(items: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in items:
        if key in result:
            raise ProvenanceClaimError("DUPLICATE_CLAIM_KEY")
        result[key] = value
    return result


def _no_constants(_raw: str) -> None:
    raise ProvenanceClaimError("INVALID_CLAIM_CONSTANT")


def _timestamp(value: object) -> datetime:
    if not isinstance(value, str) or len(value) > 35:
        raise ProvenanceClaimError("INVALID_CLAIM_TIME")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError("timezone required")
        return parsed.astimezone(timezone.utc)
    except (ValueError, OverflowError):
        raise ProvenanceClaimError("INVALID_CLAIM_TIME") from None


def check_offline_provenance_claim(
    raw_metadata: bytes,
    preview: OfflinePreview,
    raw_claim: bytes,
    *,
    now: datetime | None = None,
) -> ProvenanceClaimReview:
    """Check that a claimed sidecar matches EXACT export bytes and scope.

    This is not a cryptographic signature: anyone who edits a file can update
    its hashes. A human DBA name/reference in JSON is merely an untrusted claim.
    """
    if not isinstance(raw_metadata, bytes) or not isinstance(preview, OfflinePreview):
        raise ProvenanceClaimError("INVALID_CLAIM_CONTEXT")
    if not isinstance(raw_claim, bytes) or not 0 < len(raw_claim) <= MAX_CLAIM_BYTES:
        raise ProvenanceClaimError("INVALID_CLAIM_SIZE")
    try:
        claim = json.loads(
            raw_claim.decode("utf-8", "strict"),
            object_pairs_hook=_no_duplicates, parse_constant=_no_constants,
        )
    except ProvenanceClaimError:
        raise
    except (ValueError, UnicodeError, TypeError):
        raise ProvenanceClaimError("INVALID_CLAIM_JSON") from None

    if not isinstance(claim, dict) or set(claim) != _FIELDS:
        raise ProvenanceClaimError("INVALID_CLAIM_FIELDS")
    for name in ("claimed_issuer_id", "claimed_reference"):
        if (
            not isinstance(claim[name], str) or len(claim[name]) > 128
            or not _ID.fullmatch(claim[name])
        ):
            raise ProvenanceClaimError("INVALID_CLAIM_FIELDS")

    if (
        claim["format"] != CLAIM_FORMAT or claim["source_name"] != SOURCE
        or claim["db_type"] != "oracle"
        or claim["database_name"] != DATABASE or claim["schema_name"] != SCHEMA
        or preview.source_name != SOURCE
        or preview.snapshot.db_type != "oracle"
        or preview.snapshot.database_name != DATABASE
        or preview.snapshot.schema_name != SCHEMA
    ):
        raise ProvenanceClaimError("CLAIM_TARGET_MISMATCH")

    declared_file_digest = claim["metadata_file_sha256"]
    declared_fingerprint = claim["schema_fingerprint"]
    if (
        not isinstance(declared_file_digest, str)
        or _SHA256.fullmatch(declared_file_digest) is None
        or not isinstance(declared_fingerprint, str)
        or _SHA256.fullmatch(declared_fingerprint) is None
        or declared_file_digest != hashlib.sha256(raw_metadata).hexdigest()
        or declared_fingerprint != preview.fingerprint
    ):
        raise ProvenanceClaimError("CLAIM_DIGEST_MISMATCH")

    coverage, omissions = claim["coverage"], claim["omissions"]
    if (
        not isinstance(coverage, list) or any(not isinstance(x, str) for x in coverage)
        or len(coverage) != len(_REQUIRED_COVERAGE)
        or frozenset(coverage) != _REQUIRED_COVERAGE
        or not isinstance(omissions, list) or omissions != []
    ):
        raise ProvenanceClaimError("CLAIM_INCOMPLETE_COVERAGE")

    stamped_at = _timestamp(claim["claimed_issued_at"])
    try:
        reference = now if now is not None else datetime.now(timezone.utc)
        if not isinstance(reference, datetime) or reference.tzinfo is None:
            raise ValueError("timezone required")
        current = reference.astimezone(timezone.utc)
    except (ValueError, TypeError, OverflowError):
        raise ProvenanceClaimError("INVALID_CLAIM_CONTEXT") from None
    # Sanity limit only. Even a well-formed date provides NO issuer proof.
    if stamped_at > current + timedelta(minutes=5):
        raise ProvenanceClaimError("CLAIM_FUTURE_TIMESTAMP")

    return ProvenanceClaimReview(
        bound_metadata_sha256=declared_file_digest,
        schema_fingerprint=declared_fingerprint,
    )
