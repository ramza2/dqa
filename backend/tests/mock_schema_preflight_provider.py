"""Synthetic-only preflight evidence provider for unit tests.

This fake DOES NOT authenticate a DBA, sign evidence or guarantee that the
metadata were collected independently. Never import from production app code.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from app.adapters.schema_inspector.base import SchemaSnapshot
from app.services.schema_catalog_candidate import _fingerprint, _physical_payload
from app.services.schema_preflight_contract import (
    ProposedEvidenceEnvelope,
    REQUIRED_METADATA_CATEGORIES,
    SnapshotPreflightContext,
)


@dataclass
class SyntheticEvidenceProvider:
    independently_constructed_mock_snapshot: SchemaSnapshot
    evidence_id: UUID = UUID("cf7c53ac-5c7d-4c20-9d01-dc03eab4feff")
    issuer_id: str = "synthetic-dba-not-authenticated"
    coverage: frozenset[str] = REQUIRED_METADATA_CATEGORIES
    omissions: tuple[str, ...] = ()
    observed_at: datetime = datetime(2026, 10, 14, 10, 10, tzinfo=timezone.utc)
    issued_at: datetime = datetime(2026, 10, 14, 10, 15, tzinfo=timezone.utc)
    expires_at: datetime = datetime(2026, 10, 14, 12, 30, tzinfo=timezone.utc)
    fail: bool = False
    calls: int = 0

    def fetch(self, context: SnapshotPreflightContext) -> ProposedEvidenceEnvelope:
        self.calls += 1
        if self.fail:
            raise RuntimeError("private credential / host details must stay hidden")
        return ProposedEvidenceEnvelope(
            evidence_id=self.evidence_id,
            issuer_id=self.issuer_id,
            source_name=context.source_name,
            revision_id=context.revision_id,
            schema_fingerprint=context.schema_fingerprint,
            db_type=context.db_type,
            database_name=context.database_name,
            schema_name=context.schema_name,
            observed_fingerprint=_fingerprint(
                _physical_payload(self.independently_constructed_mock_snapshot)
            ),
            coverage=self.coverage,
            omissions=self.omissions,
            observed_at=self.observed_at,
            issued_at=self.issued_at,
            expires_at=self.expires_at,
        )
