"""M2-1D pure offline export validation: NO Oracle, PG, network or files."""
from __future__ import annotations
import json
from dataclasses import replace

import pytest
from app.services.dba_metadata_offline import (
    FORMAT, SOURCE, OfflineMetadataError, validate_offline_metadata_export,
)
from app.services.schema_catalog_candidate import _fingerprint, _physical_payload
from app.services.catalog_package_validation import validate_catalog_package_bytes
from tests.test_schema_catalog_candidate import _snapshot


def envelope(snapshot=None):
    body = _physical_payload(snapshot or _snapshot())
    return {
        "format": FORMAT, "source_name": SOURCE, "metadata_only": True,
        "claimed_fingerprint": _fingerprint(body), "snapshot": body,
    }


def encode(data):
    return json.dumps(data, ensure_ascii=False, sort_keys=True).encode("utf-8")


def test_valid_synthetic_snapshot_yields_warning_not_ready():
    parsed = validate_offline_metadata_export(encode(envelope()))
    assert parsed.source_name == SOURCE
    assert len(parsed.snapshot.tables) == 2
    assert len(parsed.snapshot.columns) == 5
    assert parsed.preflight_verified is False
    assert parsed.issuer_authenticated is False
    assert parsed.activation_eligible is False
    package = validate_catalog_package_bytes(parsed.candidate_zip)
    assert package.package_readiness == "WARNING"
    assert package.activation_eligible is False
    assert package.schema_fingerprint == parsed.fingerprint


@pytest.mark.parametrize("change,code", [
    (lambda x: x.update({"patient_rows": [{"name": "REAL_NAME"}]}), "INVALID_EXPORT_FIELDS"),
    (lambda x: x.update({"metadata_only": False}), "INVALID_EXPORT_IDENTITY"),
    (lambda x: x.update({"source_name": "demis_live"}), "INVALID_EXPORT_IDENTITY"),
    (lambda x: x.update({"claimed_fingerprint": "0" * 64}), "FINGERPRINT_MISMATCH"),
    (lambda x: x["snapshot"].update({"database_name": "OTHER_PDB"}), "INVALID_SNAPSHOT_IDENTITY"),
    (lambda x: x["snapshot"].update({"schema_name": "SYS"}), "INVALID_SNAPSHOT_IDENTITY"),
    (lambda x: x["snapshot"]["tables"][0].update({"rows": [{"patient": "X"}]}), "INVALID_METADATA_RECORDS"),
    (lambda x: x["snapshot"]["columns"][0].update({"default_value": "secret"}), "INVALID_METADATA_RECORDS"),
    (lambda x: x["snapshot"]["indexes"][0].update({"index_definition": "select *"}), "INVALID_METADATA_RECORDS"),
])
def test_reject_untrusted_payload_fields(change, code):
    data = envelope()
    change(data)
    with pytest.raises(OfflineMetadataError, match=f"^{code}$"):
        validate_offline_metadata_export(encode(data))


def test_duplicate_json_keys_rejected_at_parse_boundary():
    good = encode(envelope())
    # Same key repeated even with identical values must not be last-write-wins.
    raw = good.replace(b'"metadata_only": true', b'"metadata_only": true, "metadata_only": true')
    assert raw != good
    with pytest.raises(OfflineMetadataError, match="DUPLICATE_JSON_KEY"):
        validate_offline_metadata_export(raw)


def test_reject_invalid_utf8_nan_and_oversize():
    for raw, reason in [
        (b"\xff", "INVALID_EXPORT_JSON"),
        (b'{"x":NaN}', "INVALID_JSON_CONSTANT"),
        (b"x" * 4_000_001, "INVALID_EXPORT_SIZE"),
    ]:
        with pytest.raises(OfflineMetadataError, match=reason):
            validate_offline_metadata_export(raw)


def test_reject_dangling_key_reference_after_hash_recomputed():
    data = envelope()
    data["snapshot"]["columns"][0]["table_name"] = "NOT_A_TABLE"
    data["claimed_fingerprint"] = _fingerprint(data["snapshot"])
    with pytest.raises(OfflineMetadataError, match="INVALID_REFERENCE"):
        validate_offline_metadata_export(encode(data))


def test_reject_duplicate_table_after_hash_recomputed():
    data = envelope()
    data["snapshot"]["tables"].append(dict(data["snapshot"]["tables"][0]))
    data["claimed_fingerprint"] = _fingerprint(data["snapshot"])
    with pytest.raises(OfflineMetadataError, match="DUPLICATE_OBJECT"):
        validate_offline_metadata_export(encode(data))


def test_reject_wrong_field_types_with_claimed_hash():
    data = envelope()
    data["snapshot"]["columns"][0]["ordinal_position"] = True
    with pytest.raises(OfflineMetadataError, match="INVALID_METADATA_RECORDS"):
        validate_offline_metadata_export(encode(data))


def test_stable_fingerprint_under_record_reordering():
    snap = _snapshot()
    original = validate_offline_metadata_export(encode(envelope(snap)))
    snap.tables.reverse()
    snap.columns.reverse()
    snap.primary_keys.reverse()
    reordered = validate_offline_metadata_export(encode(envelope(snap)))
    assert original.fingerprint == reordered.fingerprint
    assert original.candidate_readiness == reordered.candidate_readiness == "WARNING"
