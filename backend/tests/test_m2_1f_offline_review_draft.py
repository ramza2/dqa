"""M2-1F: no permission/approval is conferred by an offline review draft."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

import pytest

from app.cli.offline_metadata_preview import main
from app.services.dba_metadata_offline import validate_offline_metadata_export
from app.services.offline_metadata_provenance import check_offline_provenance_claim
from app.services.offline_metadata_review_draft import (
    FORMAT, OfflineReviewDraftError, check_offline_review_draft,
)
from tests.test_m2_1d_offline_metadata_export import encode, envelope
from tests.test_m2_1e_offline_provenance import fixture_claim, raw_claim

NOW = datetime(2026, 10, 27, 8, 0, tzinfo=timezone.utc)


def review_fixture(metadata, claim):
    parsed = validate_offline_metadata_export(metadata)
    return {
        "format": FORMAT,
        "source_name": "oracle_demis_mock",
        "metadata_file_sha256": hashlib.sha256(metadata).hexdigest(),
        "claim_file_sha256": hashlib.sha256(claim).hexdigest(),
        "schema_fingerprint": parsed.fingerprint,
        "claimed_reviewer_id": "SYNTHETIC-REVIEWER",
        "decision": "ACKNOWLEDGED",
        "reason_code": "REVIEWED_METADATA",
        "claimed_reviewed_at": "2026-10-27T06:05:00Z",
    }


def review(metadata, claim_bytes, review_data):
    preview = validate_offline_metadata_export(metadata)
    claim = check_offline_provenance_claim(metadata, preview, claim_bytes, now=NOW)
    return check_offline_review_draft(
        metadata, preview, claim_bytes, claim, encode(review_data), now=NOW,
    )


def test_acknowledgement_is_not_official_review_or_preflight():
    metadata = encode(envelope())
    claim = raw_claim(fixture_claim(metadata))
    result = review(metadata, claim, review_fixture(metadata, claim))
    assert result.draft_status == "ACKNOWLEDGED_UNVERIFIED"
    assert result.file_binding == "MATCHED_UNTRUSTED"
    assert result.actor_authenticated is False
    assert result.site_approval_verified is False
    assert result.independent_preflight_verified is False
    assert result.catalog_ready is False
    assert result.activation_eligible is False


def test_changes_requested_also_requires_review():
    metadata = encode(envelope())
    claim = raw_claim(fixture_claim(metadata))
    draft = review_fixture(metadata, claim)
    draft.update(decision="CHANGES_REQUESTED", reason_code="SCOPE_UNCLEAR")
    assert review(metadata, claim, draft).draft_status == "CHANGES_REQUESTED_UNVERIFIED"


@pytest.mark.parametrize("mutate,reason", [
    (lambda d: d.update({"approved": True}), "INVALID_REVIEW_FIELDS"),
    (lambda d: d.update({"source_name": "real_demis"}), "INVALID_REVIEW_FIELDS"),
    (lambda d: d.update({"metadata_file_sha256": "0" * 64}), "REVIEW_BINDING_MISMATCH"),
    (lambda d: d.update({"claim_file_sha256": "0" * 64}), "REVIEW_BINDING_MISMATCH"),
    (lambda d: d.update({"schema_fingerprint": "0" * 64}), "REVIEW_BINDING_MISMATCH"),
    (lambda d: d.update({"decision": "APPROVED"}), "INVALID_REVIEW_DECISION"),
    (lambda d: d.update({"reason_code": "RECHECK_REQUIRED"}), "INVALID_REVIEW_DECISION"),
    (lambda d: d.update({"claimed_reviewer_id": "a@example.com"}), "INVALID_REVIEW_FIELDS"),
    (lambda d: d.update({"claimed_reviewed_at": "2026-10-27T08:20:00Z"}), "REVIEW_FUTURE_TIMESTAMP"),
    (lambda d: d.update({"claimed_reviewed_at": "2026-10-27T06:05:00"}), "INVALID_REVIEW_TIME"),
])
def test_bad_draft_is_rejected(mutate, reason):
    metadata = encode(envelope())
    claim = raw_claim(fixture_claim(metadata))
    draft = review_fixture(metadata, claim)
    mutate(draft)
    with pytest.raises(OfflineReviewDraftError, match=f"^{reason}$"):
        review(metadata, claim, draft)


def test_review_is_bound_to_exact_claim_file_bytes():
    metadata = encode(envelope())
    claim = raw_claim(fixture_claim(metadata))
    draft = review_fixture(metadata, claim)
    updated = json.dumps(json.loads(claim), indent=2).encode("utf-8")
    assert updated != claim
    with pytest.raises(OfflineReviewDraftError, match="REVIEW_BINDING_MISMATCH"):
        review(metadata, updated, draft)


def test_parse_fail_closed_duplicate_keys_nonfinite_utf8_and_size():
    metadata = encode(envelope())
    claim = raw_claim(fixture_claim(metadata))
    preview = validate_offline_metadata_export(metadata)
    parsed_claim = check_offline_provenance_claim(metadata, preview, claim, now=NOW)
    good = encode(review_fixture(metadata, claim))
    duplicates = good.replace(b'"decision":', b'"decision":"X","decision":', 1)
    for raw, code in [
        (duplicates, "DUPLICATE_REVIEW_FIELD"),
        (b"\xff", "INVALID_REVIEW_JSON"),
        (b'{"v":NaN}', "INVALID_REVIEW_JSON_CONSTANT"),
        (b"x" * 8193, "INVALID_REVIEW_SIZE"),
    ]:
        with pytest.raises(OfflineReviewDraftError, match=f"^{code}$"):
            check_offline_review_draft(metadata, preview, claim, parsed_claim, raw, now=NOW)


def test_cli_synthetic_review_summary_unverified(tmp_path, capsys):
    metadata = encode(envelope())
    claim = raw_claim(fixture_claim(metadata))
    info = tmp_path / "metadata.json"
    sidecar = tmp_path / "claim.json"
    review_path = tmp_path / "review.json"
    info.write_bytes(metadata)
    sidecar.write_bytes(claim)
    review_path.write_bytes(encode(review_fixture(metadata, claim)))
    before = set(tmp_path.iterdir())
    assert main(["--input", str(info), "--claim", str(sidecar),
                 "--review-draft", str(review_path)]) == 0
    out = capsys.readouterr().out
    assert "REVIEW_DRAFT_STATUS=ACKNOWLEDGED_UNVERIFIED" in out
    assert "METADATA_REVIEW_STATUS=NOT_REVIEWED" in out
    assert "DBA_SITE_APPROVAL_VERIFIED=false" in out
    assert "CATALOG_PACKAGE_READINESS=WARNING" in out
    assert "CATALOG_READY=false" in out
    assert "CATALOG_ACTIVATED=false" in out
    assert "SYNTHETIC-REVIEWER" not in out
    assert set(tmp_path.iterdir()) == before


def test_cli_review_requires_claim_and_bad_files_fail(tmp_path, capsys):
    metadata = encode(envelope())
    info = tmp_path / "metadata.json"
    info.write_bytes(metadata)
    invalid = tmp_path / "missing.json"
    assert main(["--input", str(info), "--review-draft", str(invalid)]) == 1
    a = capsys.readouterr()
    assert "M2_1F_BLOCKED=REVIEW_CLAIM_REQUIRED" in a.err
    assert "M2_1D_OFFLINE_SHAPE_PASS" not in a.out

    claim = raw_claim(fixture_claim(metadata))
    sidecar = tmp_path / "claim.json"
    sidecar.write_bytes(claim)
    assert main(["--input", str(info), "--claim", str(sidecar),
                 "--review-draft", str(invalid)]) == 1
    b = capsys.readouterr()
    assert "M2_1D_BLOCKED=UNREADABLE_OR_INVALID_INPUT" in b.err
    assert "M2_1D_OFFLINE_SHAPE_PASS" not in b.out
