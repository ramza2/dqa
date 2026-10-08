"""Semantic Resource domain contracts (Phase 29-A).

Logical resources/fields bind explicitly to one Active Catalog revision.
No clinical meaning is inferred from column names or LLM output.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.domain.data_discovery import DiscoveryIdentityKind

# Format version for explicit in-memory / test mapping documents.
# Persistence and approval workflow are a future boundary (not authority here).
MAPPING_FORMAT_VERSION = "1.0.0"

# Stable allowlist — unknown values are rejected by default.
APPROVED_FIELD_CAPABILITIES: frozenset[str] = frozenset(
    {
        "SELECT",
        "FILTER",
        "SORT",
        "GROUP_BY",
        "AGGREGATE",
    }
)


class FieldCapability(StrEnum):
    """Executable field capabilities approved for future Dynamic Query plans."""

    SELECT = "SELECT"
    FILTER = "FILTER"
    SORT = "SORT"
    GROUP_BY = "GROUP_BY"
    AGGREGATE = "AGGREGATE"


class SemanticMappingStatus(StrEnum):
    """Resolution outcome for one source's semantic mapping vs Active Catalog."""

    NOT_CONFIGURED = "NOT_CONFIGURED"
    INVALID = "INVALID"
    STALE = "STALE"
    VALID = "VALID"


class SemanticIssueCode(StrEnum):
    """Deterministic validation issue codes (no LLM judgment)."""

    NOT_CONFIGURED = "NOT_CONFIGURED"
    ACTIVE_CATALOG_NOT_FOUND = "ACTIVE_CATALOG_NOT_FOUND"
    CROSS_SOURCE = "CROSS_SOURCE"
    STALE_REVISION = "STALE_REVISION"
    STALE_FINGERPRINT = "STALE_FINGERPRINT"
    DUPLICATE_RESOURCE_KEY = "DUPLICATE_RESOURCE_KEY"
    DUPLICATE_FIELD_KEY = "DUPLICATE_FIELD_KEY"
    DUPLICATE_RELATIONSHIP_KEY = "DUPLICATE_RELATIONSHIP_KEY"
    MISSING_TABLE = "MISSING_TABLE"
    MISSING_COLUMN = "MISSING_COLUMN"
    MISSING_FK = "MISSING_FK"
    AMBIGUOUS_TABLE = "AMBIGUOUS_TABLE"
    AMBIGUOUS_COLUMN = "AMBIGUOUS_COLUMN"
    AMBIGUOUS_FK = "AMBIGUOUS_FK"
    UNKNOWN_CAPABILITY = "UNKNOWN_CAPABILITY"
    INVALID_RELATIONSHIP = "INVALID_RELATIONSHIP"
    UNSUPPORTED_MAPPING_VERSION = "UNSUPPORTED_MAPPING_VERSION"


@dataclass(frozen=True)
class LogicalDiscoveryIdentity:
    """Logical identity aligned with DiscoveryIdentityKind.LOGICAL (Phase 29-A).

    Complements PhysicalDiscoveryIdentity. Search-document materialization of
    LOGICAL identities remains a future Discovery concern.
    """

    identity_kind: DiscoveryIdentityKind
    source_name: str
    catalog_revision_id: int
    schema_fingerprint: str
    resource_key: str
    field_key: str | None = None

    def __post_init__(self) -> None:
        if self.identity_kind is not DiscoveryIdentityKind.LOGICAL:
            raise ValueError("LogicalDiscoveryIdentity requires identity_kind=LOGICAL")


def is_approved_capability(value: str) -> bool:
    return value in APPROVED_FIELD_CAPABILITIES


__all__ = [
    "APPROVED_FIELD_CAPABILITIES",
    "MAPPING_FORMAT_VERSION",
    "FieldCapability",
    "LogicalDiscoveryIdentity",
    "SemanticIssueCode",
    "SemanticMappingStatus",
    "is_approved_capability",
]
