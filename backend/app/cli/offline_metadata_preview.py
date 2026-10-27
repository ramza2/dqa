"""Offline metadata file check. No Oracle, PostgreSQL, HTTP or Catalog mutation."""
from __future__ import annotations

import argparse
import os
import stat
import sys

from app.services.dba_metadata_offline import (
    MAX_EXPORT_BYTES, OfflineMetadataError, validate_offline_metadata_export,
)
from app.services.catalog_package_validation import validate_catalog_package_bytes
from app.services.offline_metadata_provenance import (
    MAX_CLAIM_BYTES, ProvenanceClaimError, check_offline_provenance_claim,
)


def _read_bounded_regular_file(path: str, max_bytes: int) -> bytes:
    """Use one FD to avoid a symlink race; never return file contents in errors."""
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= max_bytes:
            raise OfflineMetadataError("INVALID_EXPORT_FILE")
        with os.fdopen(fd, "rb", closefd=False) as stream:
            return stream.read(max_bytes + 1)
    finally:
        os.close(fd)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate synthetic Oracle metadata export offline")
    parser.add_argument("--input", required=True, help="locally supplied metadata JSON path")
    parser.add_argument("--claim", help="optional untrusted provenance sidecar JSON")
    args = parser.parse_args(argv)
    claim = None
    try:
        raw = _read_bounded_regular_file(args.input, MAX_EXPORT_BYTES)
        result = validate_offline_metadata_export(raw)
        package = validate_catalog_package_bytes(result.candidate_zip)
        if args.claim is not None:
            claim_raw = _read_bounded_regular_file(args.claim, MAX_CLAIM_BYTES)
            claim = check_offline_provenance_claim(raw, result, claim_raw)
    except ProvenanceClaimError as exc:
        print(f"M2_1E_BLOCKED={str(exc)}", file=sys.stderr)
        return 1
    except OfflineMetadataError as exc:
        print(f"M2_1D_BLOCKED={str(exc)}", file=sys.stderr)
        return 1
    except (OSError, ValueError, TypeError):
        print("M2_1D_BLOCKED=UNREADABLE_OR_INVALID_INPUT", file=sys.stderr)
        return 1

    print("M2_1D_OFFLINE_SHAPE_PASS")
    print("SOURCE=oracle_demis_mock")
    print(f"TABLE_COUNT={len(result.snapshot.tables)}")
    print(f"COLUMN_COUNT={len(result.snapshot.columns)}")
    print(f"FINGERPRINT={result.fingerprint}")
    print(f"CATALOG_PACKAGE_READINESS={package.package_readiness}")
    print("INDEPENDENT_DBA_PREFLIGHT=NOT_VERIFIED")
    print("ISSUER_AUTHENTICATED=false")
    print("CATALOG_ACTIVATED=false")
    print(f"PROVENANCE_CLAIM_BINDING={claim.claim_binding if claim is not None else 'ABSENT'}")
    print("PROVENANCE_ISSUER_AUTHENTICATED=false")
    print("METADATA_REVIEW_STATUS=NOT_REVIEWED")
    print("PROVENANCE_APPROVAL_VERIFIED=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
