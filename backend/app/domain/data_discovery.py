"""Data Discovery domain contracts (Phase 27-A).

Search documents are revision-scoped derived artifacts from immutable
CatalogImportRevision JSON. This module defines identity, fingerprints, and
embedding *model metadata* contracts — not search execution or vectors.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import StrEnum
from typing import Any


BUILDER_VERSION = "1.0.0"


class DiscoveryObjectType(StrEnum):
    TABLE = "TABLE"
    COLUMN = "COLUMN"


class DiscoveryIdentityKind(StrEnum):
    """PHYSICAL documents are built in 27-A; LOGICAL identities are Phase 29-A.

    LOGICAL search-document materialization remains a future Discovery concern.
    Semantic resource contracts live in ``app.domain.semantic_resource``.
    """

    PHYSICAL = "PHYSICAL"
    LOGICAL = "LOGICAL"


class DataDiscoverySearchMode(StrEnum):
    KEYWORD = "keyword"
    SEMANTIC = "semantic"
    HYBRID = "hybrid"


@dataclass(frozen=True)
class PhysicalDiscoveryIdentity:
    """Public physical identity — no DB surrogate table/column ids."""

    source_name: str
    catalog_revision_id: int
    schema_fingerprint: str
    schema_name: str
    table_name: str
    column_name: str | None = None


@dataclass(frozen=True)
class SearchDocumentDraft:
    """Deterministic in-memory search document prior to persistence."""

    document_key: str
    object_type: DiscoveryObjectType
    identity_kind: DiscoveryIdentityKind
    source_name: str
    catalog_revision_id: int
    schema_fingerprint: str
    schema_name: str
    table_name: str
    column_name: str | None
    searchable_text: str
    source_fingerprint: str
    document_fingerprint: str
    builder_version: str


def canonical_digest(payload: Any) -> str:
    """SHA-256 hex digest of canonical JSON (sorted keys, compact separators)."""
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def physical_document_key(
    object_type: DiscoveryObjectType,
    *,
    schema_name: str,
    table_name: str,
    column_name: str | None = None,
) -> str:
    """Stable physical key without revision or DB surrogate ids.

    Examples:
    - TABLE:DEMIS_OWNER.TB_ADM_HIST
    - COLUMN:DEMIS_OWNER.TB_ADM_HIST.WARD_CD
    """
    if object_type is DiscoveryObjectType.TABLE:
        return f"TABLE:{schema_name}.{table_name}"
    if not column_name:
        raise ValueError("column_name is required for COLUMN document_key")
    return f"COLUMN:{schema_name}.{table_name}.{column_name}"


def document_fingerprint_for(
    *,
    document_key: str,
    searchable_text: str,
    builder_version: str,
) -> str:
    return canonical_digest(
        {
            "document_key": document_key,
            "searchable_text": searchable_text,
            "builder_version": builder_version,
        }
    )


def build_embedding_model_key(
    *,
    provider: str,
    model_name: str,
    model_revision: str | None,
    dimension: int,
    normalized: bool,
    query_prefix: str | None,
    document_prefix: str | None,
) -> str:
    """Deterministic model identity from semantic configuration only.

    Must not include endpoint URL, API key, secret, or filesystem path.
    """
    return canonical_digest(
        {
            "provider": provider,
            "model_name": model_name,
            "model_revision": model_revision,
            "dimension": dimension,
            "normalized": normalized,
            "query_prefix": query_prefix,
            "document_prefix": document_prefix,
        }
    )


__all__ = [
    "BUILDER_VERSION",
    "DataDiscoverySearchMode",
    "DiscoveryIdentityKind",
    "DiscoveryObjectType",
    "PhysicalDiscoveryIdentity",
    "SearchDocumentDraft",
    "build_embedding_model_key",
    "canonical_digest",
    "document_fingerprint_for",
    "physical_document_key",
]
