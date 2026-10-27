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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate synthetic Oracle metadata export offline")
    parser.add_argument("--input", required=True, help="locally supplied metadata JSON path")
    args = parser.parse_args(argv)
    try:
        fd = os.open(args.input, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= MAX_EXPORT_BYTES:
                raise OfflineMetadataError("INVALID_EXPORT_FILE")
            with os.fdopen(fd, "rb", closefd=False) as stream:
                raw = stream.read(MAX_EXPORT_BYTES + 1)
        finally:
            os.close(fd)
        result = validate_offline_metadata_export(raw)
        package = validate_catalog_package_bytes(result.candidate_zip)
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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
