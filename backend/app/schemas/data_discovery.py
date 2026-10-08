"""Pydantic contracts for Data Discovery (Phase 27-A).

Defines search-document and future search-request shapes. No HTTP routes and
no search algorithm are implemented here.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.domain.data_discovery import (
    DataDiscoverySearchMode,
    DiscoveryIdentityKind,
    DiscoveryObjectType,
    build_embedding_model_key,
)

SearchModeLiteral = Literal["keyword", "semantic", "hybrid"]
ObjectTypeLiteral = Literal["TABLE", "COLUMN"]
IdentityKindLiteral = Literal["PHYSICAL", "LOGICAL"]


class PhysicalDiscoveryIdentityModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_name: str
    catalog_revision_id: int
    schema_fingerprint: str
    schema_name: str
    table_name: str
    column_name: str | None = None


class SearchDocumentContract(BaseModel):
    """API/domain contract for one revision-scoped search document."""

    model_config = ConfigDict(extra="forbid")

    document_key: str
    object_type: ObjectTypeLiteral
    identity_kind: IdentityKindLiteral
    source_name: str
    catalog_revision_id: int
    schema_fingerprint: str
    schema_name: str
    table_name: str
    column_name: str | None = None
    searchable_text: str
    source_fingerprint: str
    document_fingerprint: str
    builder_version: str


class EmbeddingModelMetadata(BaseModel):
    """Embedding *model* identity only — no vectors, endpoints, or secrets."""

    model_config = ConfigDict(extra="forbid")

    provider: str = Field(min_length=1, max_length=128)
    model_name: str = Field(min_length=1, max_length=255)
    model_revision: str | None = Field(default=None, max_length=128)
    dimension: int = Field(ge=1, le=16384)
    normalized: bool = False
    query_prefix: str | None = Field(default=None, max_length=512)
    document_prefix: str | None = Field(default=None, max_length=512)
    model_key: str = Field(min_length=64, max_length=64)

    @model_validator(mode="before")
    @classmethod
    def fill_model_key(cls, data: object) -> object:
        if not isinstance(data, dict):
            return data
        payload = dict(data)
        if not payload.get("model_key"):
            payload["model_key"] = build_embedding_model_key(
                provider=str(payload.get("provider") or ""),
                model_name=str(payload.get("model_name") or ""),
                model_revision=payload.get("model_revision"),
                dimension=int(payload.get("dimension") or 0),
                normalized=bool(payload.get("normalized", False)),
                query_prefix=payload.get("query_prefix"),
                document_prefix=payload.get("document_prefix"),
            )
        return payload

    @model_validator(mode="after")
    def model_key_matches_config(self) -> EmbeddingModelMetadata:
        expected = build_embedding_model_key(
            provider=self.provider,
            model_name=self.model_name,
            model_revision=self.model_revision,
            dimension=self.dimension,
            normalized=self.normalized,
            query_prefix=self.query_prefix,
            document_prefix=self.document_prefix,
        )
        if self.model_key != expected:
            raise ValueError("model_key does not match embedding semantic configuration")
        return self


class DataDiscoverySearchRequest(BaseModel):
    """Contract for a future search endpoint (27-B). Not wired to routes yet."""

    model_config = ConfigDict(extra="forbid")

    source_name: str = Field(min_length=1, max_length=255)
    query: str = Field(min_length=1, max_length=2000)
    mode: DataDiscoverySearchMode | SearchModeLiteral = DataDiscoverySearchMode.KEYWORD
    object_type: DiscoveryObjectType | ObjectTypeLiteral | None = None
    top_k: int = Field(default=10, ge=1, le=50)
    expand_terms: bool = False
    expand_relations: bool = False
    max_relation_hops: int = Field(default=0, ge=0, le=4)

    @field_validator("query")
    @classmethod
    def query_must_be_non_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("query must be non-empty")
        return value

    @field_validator("source_name")
    @classmethod
    def source_name_non_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("source_name must be non-empty")
        return value


class DataDiscoverySearchResultItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rank: int = Field(ge=1)
    identity: PhysicalDiscoveryIdentityModel
    document_key: str
    object_type: ObjectTypeLiteral
    keyword_score: float | None = None
    semantic_score: float | None = None
    rrf_score: float | None = None
    evidence_snippet: str | None = Field(default=None, max_length=2000)


class DataDiscoverySearchResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_name: str
    catalog_revision_id: int
    schema_fingerprint: str
    mode: SearchModeLiteral
    results: list[DataDiscoverySearchResultItem] = Field(default_factory=list)


__all__ = [
    "DataDiscoverySearchRequest",
    "DataDiscoverySearchResponse",
    "DataDiscoverySearchResultItem",
    "EmbeddingModelMetadata",
    "PhysicalDiscoveryIdentityModel",
    "SearchDocumentContract",
]
