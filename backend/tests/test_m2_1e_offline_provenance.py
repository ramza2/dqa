"""M2-1E: untrusted provenance claim is bound but NEVER approved. Pure offline."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone

import pytest

from app.cli.offline_metadata_preview import main
from app.services.dba_metadata_offline import validate_offline_metadata_export
from app.services.offline_metadata_provenance import (
    CLAIM_FORMAT, ProvenanceClaimError, check_offline_provenance_claim,
)
from tests.test_m2_1d_offline_metadata_export import encode, envelope

NOW = datetime(2026, 10, 27, 8, 0, tzinfo=timezone.utc)


def fixture_claim(metadata: bytes):
    preview = validate_offline_metadata_export(metadata)
    return {
        "format": CLAIM_FORMAT,
        "source_name": "oracle_demis_mock",
        "db_type": "oracle",
        "database_name": "FREEPDB1",
        "schema_name": "DEMIS_OWNER",
        "metadata_file_sha256": hashlib.sha256(metadata).hexdigest(),
        "schema_fingerprint": preview.fingerprint,
        "claimed_issuer_id": "SYNTHETIC-DBA-ONLY",
        "claimed_reference": "SYNTHETIC-TEST-CLAIM-1",
        "claimed_issued_at": "2026-10-27T06:00:00Z",
        "coverage": [
            "tables", "columns", "primary_keys", "unique_constraints",
            "foreign_keys", "indexes",
        ],
        "omissions": [],
    }


def raw_claim(data):
    return json.dumps(data, ensure_ascii=False, sort_keys=True).encode("utf-8")


def check(raw, claim):
    return check_offline_provenance_claim(
        raw, validate_offline_metadata_export(raw), raw_claim(claim), now=NOW,
    )


def test_matching_sidecar_is_not_dba_authentication_or_approval():
    raw = encode(envelope())
    result = check(raw, fixture_claim(raw))
    assert result.claim_binding == "MATCHED_UNTRUSTED"
    assert result.issuer_authenticated is False
    assert result.independent_preflight_verified is False
    assert result.review_status == "NOT_REVIEWED"
    assert result.approval_verified is False
    assert result.activation_eligible is False


@pytest.mark.parametrize("mutator,code", [
    (lambda x: x.update({"extra": {"patient_name": "SECRET"}}), "INVALID_CLAIM_FIELDS"),
    (lambda x: x.update({"source_name": "demis_prod"}), "CLAIM_TARGET_MISMATCH"),
    (lambda x: x.update({"schema_name": "SYS"}), "CLAIM_TARGET_MISMATCH"),
    (lambda x: x.update({"schema_fingerprint": "f" * 64}), "CLAIM_DIGEST_MISMATCH"),
    (lambda x: x.update({"metadata_file_sha256": "f" * 64}), "CLAIM_DIGEST_MISMATCH"),
    (lambda x: x.update({"claimed_issuer_id": "someone@example.com"}), "INVALID_CLAIM_FIELDS"),
    (lambda x: x.update({"claimed_issued_at": "2026-10-27T12:00:00Z"}), "CLAIM_FUTURE_TIMESTAMP"),
    (lambda x: x.update({"claimed_issued_at": "2026-10-27T06:00:00"}), "INVALID_CLAIM_TIME"),
    (lambda x: x.update({"coverage": ["tables", "columns"]}), "CLAIM_INCOMPLETE_COVERAGE"),
    (lambda x: x.update({"omissions": ["missing_fk"]}), "CLAIM_INCOMPLETE_COVERAGE"),
])
def test_untrusted_sidecar_fails_closed(mutator, code):
    raw = encode(envelope())
    claim = fixture_claim(raw)
    mutator(claim)
    with pytest.raises(ProvenanceClaimError, match=f"^{code}$"):
        check(raw, claim)


def test_claim_bound_to_exact_raw_bytes_not_just_canonical_fingerprint():
    raw = encode(envelope())
    claim = fixture_claim(raw)
    same_meaning_different_bytes = json.dumps(envelope(), indent=2).encode("utf-8")
    preview = validate_offline_metadata_export(same_meaning_different_bytes)
    assert preview.fingerprint == claim["schema_fingerprint"]
    with pytest.raises(ProvenanceClaimError, match="CLAIM_DIGEST_MISMATCH"):
        check_offline_provenance_claim(
            same_meaning_different_bytes, preview, raw_claim(claim), now=NOW,
        )


def test_duplicate_claim_keys_invalid_utf8_nan_and_oversize():
    raw = encode(envelope())
    claim = fixture_claim(raw)
    duplicate = raw_claim(claim).replace(
        b'"format":', b'"format":"duplicate", "format":', 1,
    )
    for payload, code in [
        (duplicate, "DUPLICATE_CLAIM_KEY"),
        (b"\xff", "INVALID_CLAIM_JSON"),
        (b'{"x":NaN}', "INVALID_CLAIM_CONSTANT"),
        (b"a" * 16_385, "INVALID_CLAIM_SIZE"),
    ]:
        with pytest.raises(ProvenanceClaimError, match=code):
            check_offline_provenance_claim(
                raw, validate_offline_metadata_export(raw), payload, now=NOW,
            )


def test_cli_with_absent_claim_keeps_m2_1d_success(tmp_path, capsys):
    raw = encode(envelope())
    metadata = tmp_path / "m2-1e-mock.json"
    metadata.write_bytes(raw)
    assert main(["--input", str(metadata)]) == 0
    out = capsys.readouterr().out
    assert "M2_1D_OFFLINE_SHAPE_PASS" in out
    assert "PROVENANCE_CLAIM_BINDING=ABSENT" in out
    assert "METADATA_REVIEW_STATUS=NOT_REVIEWED" in out


def test_cli_untrusted_claim_never_approves_and_rejects_tamper(tmp_path, capsys):
    raw = encode(envelope())
    metadata = tmp_path / "m2-1e-mock.json"
    metadata.write_bytes(raw)
    claim_path = tmp_path / "m2-1e-claim.json"
    claim = fixture_claim(raw)
    claim_path.write_bytes(raw_claim(claim))
    assert main(["--input", str(metadata), "--claim", str(claim_path)]) == 0
    out = capsys.readouterr().out
    assert "PROVENANCE_CLAIM_BINDING=MATCHED_UNTRUSTED" in out
    assert "PROVENANCE_ISSUER_AUTHENTICATED=false" in out
    assert "METADATA_REVIEW_STATUS=NOT_REVIEWED" in out
    assert "CATALOG_PACKAGE_READINESS=WARNING" in out
    assert "CATALOG_ACTIVATED=false" in out
    claim["metadata_file_sha256"] = "0" * 64
    claim_path.write_bytes(raw_claim(claim))
    assert main(["--input", str(metadata), "--claim", str(claim_path)]) == 1
    response = capsys.readouterr()
    assert "M2_1E_BLOCKED=CLAIM_DIGEST_MISMATCH" in response.err
    assert "SYNTHETIC-DBA-ONLY" not in response.err


def test_cli_missing_claim_path_fails_without_metadata_success(tmp_path, capsys):
    metadata = tmp_path / "metadata.json"
    metadata.write_bytes(encode(envelope()))
    result = main(["--input", str(metadata), "--claim", str(tmp_path / "missing.json")])
    assert result == 1
    out = capsys.readouterr()
    assert "M2_1D_OFFLINE_SHAPE_PASS" not in out.out
    assert "M2_1D_BLOCKED=UNREADABLE_OR_INVALID_INPUT" in out.err
