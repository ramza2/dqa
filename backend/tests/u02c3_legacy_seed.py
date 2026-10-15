"""U-02-C-3 fixture seed: use original Legacy test data and finalizer only.

Mounted into an isolated PostgreSQL 16 container. Not an operational backup tool.
"""
from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import select

from app.db.session import get_catalog_session_factory
from app.models.catalog import CatalogSource
from app.services.catalog_package_finalizer import build_final_catalog_package
from legacy_seed import main as seed_inventory


OUTPUT = Path("/output")


def main() -> None:
    seed_inventory()  # U-02-C-2's actual ORM fixture + read-only count evidence.
    with get_catalog_session_factory()() as db:
        fixture = db.scalars(
            select(CatalogSource)
            .where(CatalogSource.source_name.startswith("final_package_"))
            .order_by(CatalogSource.id)
        ).all()
        assert len(fixture) == 2, "DISPOSABLE_SOURCE_COUNT_MISMATCH"
        package = build_final_catalog_package(db, fixture[0].id)

    assert package.manifest["package_version"] == "2.0"
    assert package.manifest["package_readiness"] == "READY"
    payload = package.content
    assert payload.startswith(b"PK")
    (OUTPUT / "legacy_final_ready.zip").write_bytes(payload)
    print(json.dumps({
        "status": "PASS", "fixture_sources": 2,
        "generated_zip": True, "legacy_ready_is_independent_approval": False,
    }))


if __name__ == "__main__":
    main()
