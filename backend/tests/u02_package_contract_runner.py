"""U-02-B offline original-legacy / DQA Package-Fingerprint contract runner.

Used from two *isolated* Python subprocesses; neither creates a database
engine, HTTP client, ORM session or any external connection. Legacy imports
the original pinned implementation, not a reimplementation of its hash.
"""
from __future__ import annotations

import hashlib
import io
import json
import sys
import zipfile
from dataclasses import replace
from datetime import datetime, timezone

from u02_oracle_parity_runner import FakeEngine, _fixture


TIMESTAMP = datetime(2026, 10, 15, tzinfo=timezone.utc)
SENSITIVE_DEFAULT = "U02B_SENSITIVE_DEFAULT_SQL_SENTINEL"
SENSITIVE_INDEX = "U02B_SENSITIVE_INDEX_SQL_SENTINEL"


def run(mode: str, variation: str) -> dict:
    if mode == "legacy":
        from app.analyzers.oracle import OracleSchemaInspector
        from app.services.catalog_writer import schema_snapshot_fingerprint
    elif mode == "dqa":
        from app.adapters.schema_inspector.oracle import OracleSchemaInspector
        from app.adapters.catalog.limits import REQUIRED_RUNTIME_JSON_FILES
        from app.services.catalog_package_validation import validate_catalog_package_bytes
        from app.services.schema_catalog_candidate import build_catalog_v2_candidate
    else:
        raise ValueError("unknown mode")

    kind = "changed_comment" if variation == "comment" else "rich"
    engine = FakeEngine(_fixture(kind))
    snapshot = OracleSchemaInspector(engine, "FREEPDB1").inspect("DEMIS_OWNER")
    assert not engine.connected
    assert len(engine.calls) == 6

    if variation == "length":
        snapshot.columns[0] = replace(
            snapshot.columns[0], character_maximum_length=99,
        )
    elif variation == "precision":
        snapshot.columns[1] = replace(
            snapshot.columns[1], numeric_precision=10,
        )
    elif variation == "default":
        snapshot.columns[0] = replace(
            snapshot.columns[0], default_value=SENSITIVE_DEFAULT,
        )
    elif variation == "index_sql":
        snapshot.indexes[0] = replace(
            snapshot.indexes[0], index_definition=SENSITIVE_INDEX,
        )
    elif variation not in ("rich", "comment"):
        raise ValueError("unknown variation")

    if mode == "legacy":
        return {"fingerprint": schema_snapshot_fingerprint(snapshot)}

    output = build_catalog_v2_candidate(
        snapshot, source_name="oracle_demis_mock", generated_at=TIMESTAMP,
    )
    validated = validate_catalog_package_bytes(output)
    with zipfile.ZipFile(io.BytesIO(output)) as archive:
        names = archive.namelist()
        prefix = "demis_catalog_package/"
        files = {}
        for name in names:
            assert name.startswith(prefix), name
            relative = name[len(prefix):]
            assert relative not in files
            files[relative] = archive.read(name)
    manifest = json.loads(files.pop("manifest.json"))
    # Re-check the original archive bytes, not just a manifest projection.
    for entry in manifest["files"]:
        file_bytes = files[entry["path"]]
        assert len(file_bytes) == entry["bytes"]
        assert hashlib.sha256(file_bytes).hexdigest() == entry["sha256"]

    parsed = validated.parsed_documents
    fp = validated.schema_fingerprint
    no_sensitive_values = all(
        SENSITIVE_DEFAULT.encode() not in data and
        SENSITIVE_INDEX.encode() not in data
        for data in files.values()
    )
    return {
        "fingerprint": fp,
        "readiness": validated.package_readiness,
        "activation_eligible": validated.activation_eligible,
        "format": validated.package_format,
        "version": validated.package_version,
        "counts": validated.counts,
        "file_paths": sorted(files),
        "required_paths": sorted(REQUIRED_RUNTIME_JSON_FILES),
        "managed_file_count": len(manifest["files"]),
        "has_valid_file_digests": True,
        "has_consistent_fingerprints": (
            fp == manifest["schema_fingerprint"]
            == parsed["database.json"]["latest_analysis"]["schema_fingerprint"]
            == parsed["analysis/latest_run.json"]["run"]["schema_fingerprint"]
            == parsed["analysis/schema_snapshot.json"]["payload"]["schema_fingerprint"]
        ),
        "no_sensitive_values": no_sensitive_values,
        "physical": {
            "tables": parsed["tables.json"]["tables"],
            "columns": parsed["columns.json"]["columns"],
            "relations": parsed["relations.json"]["relations"],
            "indexes": parsed["indexes.json"]["indexes"],
        },
    }


if __name__ == "__main__":
    assert len(sys.argv) == 3
    print(json.dumps(run(sys.argv[1], sys.argv[2]), ensure_ascii=False, sort_keys=True))
