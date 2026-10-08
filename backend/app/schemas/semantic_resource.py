"""Pydantic contracts for Semantic Resource mappings (Phase 29-A).

These define the explicit mapping document shape used for validation and
read-only resolution. They are not an approved persistence authority.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.domain.semantic_resource import (
    APPROVED_FIELD_CAPABILITIES,
    MAPPING_FORMAT_VERSION,
    FieldCapability,
    SemanticIssueCode,
    SemanticMappingStatus,
)

FieldCapabilityLiteral = Literal["SELECT", "FILTER", "SORT", "GROUP_BY", "AGGREGATE"]
SemanticStatusLiteral = Literal["NOT_CONFIGURED", "INVALID", "STALE", "VALID"]


class PhysicalTableRef(BaseModel):
    """Physical table reference within one Catalog source/revision."""

    model_config = ConfigDict(extra="forbid")

    schema_name: str = Field(min_length=1, max_length=255)
    table_name: str = Field(min_length=1, max_length=255)


class PhysicalColumnRef(BaseModel):
    """Physical column reference within one Catalog source/revision."""

    model_config = ConfigDict(extra="forbid")

    schema_name: str = Field(min_length=1, max_length=255)
    table_name: str = Field(min_length=1, max_length=255)
    column_name: str = Field(min_length=1, max_length=255)


class CatalogFkColumnBinding(BaseModel):
    """One ordered FK column pair as recorded in Catalog relations metadata."""

    model_config = ConfigDict(extra="forbid")

    source_column: str = Field(min_length=1, max_length=255)
    target_column: str = Field(min_length=1, max_length=255)


class CatalogFkBinding(BaseModel):
    """Binding to Catalog-supported FOREIGN_KEY metadata (not inferred JOINs)."""

    model_config = ConfigDict(extra="forbid")

    constraint_name: str = Field(min_length=1, max_length=255)
    source_schema_name: str = Field(min_length=1, max_length=255)
    source_table_name: str = Field(min_length=1, max_length=255)
    target_schema_name: str = Field(min_length=1, max_length=255)
    target_table_name: str = Field(min_length=1, max_length=255)
    column_mappings: list[CatalogFkColumnBinding] = Field(min_length=1)


class MappingProvenance(BaseModel):
    """Human/operator provenance for an explicit mapping document."""

    model_config = ConfigDict(extra="forbid")

    author: str | None = Field(default=None, max_length=255)
    note: str | None = Field(default=None, max_length=2000)
    review_status: Literal["UNREVIEWED", "DRAFT", "TEST_ONLY"] = "TEST_ONLY"


class LogicalFieldDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field_key: str = Field(min_length=1, max_length=255, pattern=r"^[A-Za-z][A-Za-z0-9_]*$")
    description: str | None = Field(default=None, max_length=2000)
    data_type: str = Field(min_length=1, max_length=128)
    physical_column: PhysicalColumnRef
    capabilities: list[FieldCapability | FieldCapabilityLiteral] = Field(min_length=1)

    @field_validator("capabilities")
    @classmethod
    def capabilities_must_be_approved(
        cls, value: list[FieldCapability | str]
    ) -> list[FieldCapability]:
        normalized: list[FieldCapability] = []
        seen: set[str] = set()
        for item in value:
            text = str(item)
            if text not in APPROVED_FIELD_CAPABILITIES:
                raise ValueError(f"unapproved field capability: {text}")
            if text in seen:
                continue
            seen.add(text)
            normalized.append(FieldCapability(text))
        if not normalized:
            raise ValueError("capabilities must not be empty")
        return normalized


class LogicalRelationshipDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    relationship_key: str = Field(
        min_length=1, max_length=255, pattern=r"^[A-Za-z][A-Za-z0-9_]*$"
    )
    description: str | None = Field(default=None, max_length=2000)
    from_resource_key: str = Field(min_length=1, max_length=255)
    to_resource_key: str = Field(min_length=1, max_length=255)
    catalog_fk: CatalogFkBinding


class LogicalResourceDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resource_key: str = Field(
        min_length=1, max_length=255, pattern=r"^[A-Za-z][A-Za-z0-9_.]*$"
    )
    description: str | None = Field(default=None, max_length=2000)
    physical_table: PhysicalTableRef
    fields: list[LogicalFieldDefinition] = Field(min_length=1)
    relationships: list[LogicalRelationshipDefinition] = Field(default_factory=list)


class SemanticMappingDocument(BaseModel):
    """Explicit semantic mapping for one Catalog source + revision snapshot.

    Not treated as approved production authority. Approval/persistence is a
    documented future boundary.
    """

    model_config = ConfigDict(extra="forbid")

    mapping_format_version: str = Field(default=MAPPING_FORMAT_VERSION, min_length=1)
    mapping_version: str = Field(min_length=1, max_length=64)
    source_name: str = Field(min_length=1, max_length=255)
    catalog_revision_id: int = Field(ge=1)
    schema_fingerprint: str = Field(min_length=1, max_length=128)
    provenance: MappingProvenance = Field(default_factory=MappingProvenance)
    resources: list[LogicalResourceDefinition] = Field(default_factory=list)


class SemanticValidationIssue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: SemanticIssueCode | str
    message: str
    resource_key: str | None = None
    field_key: str | None = None
    relationship_key: str | None = None


class ResolvedLogicalField(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field_key: str
    description: str | None = None
    data_type: str
    physical_column: PhysicalColumnRef
    catalog_data_type: str | None = None
    capabilities: list[FieldCapabilityLiteral]


class ResolvedLogicalRelationship(BaseModel):
    model_config = ConfigDict(extra="forbid")

    relationship_key: str
    description: str | None = None
    from_resource_key: str
    to_resource_key: str
    catalog_fk: CatalogFkBinding


class ResolvedLogicalResource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resource_key: str
    description: str | None = None
    physical_table: PhysicalTableRef
    fields: list[ResolvedLogicalField]
    relationships: list[ResolvedLogicalRelationship]


class SemanticResolutionResult(BaseModel):
    """Read-only resolution outcome against one Active Catalog revision."""

    model_config = ConfigDict(extra="forbid")

    status: SemanticMappingStatus | SemanticStatusLiteral
    source_name: str
    catalog_revision_id: int | None = None
    schema_fingerprint: str | None = None
    mapping_version: str | None = None
    mapping_format_version: str | None = None
    resources: list[ResolvedLogicalResource] = Field(default_factory=list)
    issues: list[SemanticValidationIssue] = Field(default_factory=list)


__all__ = [
    "CatalogFkBinding",
    "CatalogFkColumnBinding",
    "LogicalFieldDefinition",
    "LogicalRelationshipDefinition",
    "LogicalResourceDefinition",
    "MappingProvenance",
    "PhysicalColumnRef",
    "PhysicalTableRef",
    "ResolvedLogicalField",
    "ResolvedLogicalRelationship",
    "ResolvedLogicalResource",
    "SemanticMappingDocument",
    "SemanticResolutionResult",
    "SemanticValidationIssue",
]
