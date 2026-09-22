"""Pydantic response models for Active Catalog query APIs."""

from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class CatalogQueryEnvelope(BaseModel, Generic[T]):
    """Common envelope tying list/detail results to one resolved active revision."""

    source_name: str
    revision_id: int
    schema_fingerprint: str
    total: int
    limit: int
    offset: int
    items: list[T]


class CatalogTableItem(BaseModel):
    """Table metadata subset from tables.json (producer field names preserved)."""

    model_config = ConfigDict(extra="forbid")

    schema_name: str = Field(description="Producer table.schema")
    name: str
    comment: str | None = None
    table_type: str | None = None
    category_ids: list[str] = Field(default_factory=list)


class CatalogTableDetail(CatalogTableItem):
    """Single-table detail (same metadata surface as list item for now)."""


class CatalogColumnItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_name: str | None = None
    table_name: str
    name: str
    ordinal: int | None = None
    data_type: str | None = None
    comment: str | None = None
    nullable: bool | None = None
    is_primary_key: bool | None = None
    is_unique: bool | None = None
    default: str | None = None


class CatalogRelationColumnMapping(BaseModel):
    model_config = ConfigDict(extra="forbid")

    column: str
    referenced_column: str


class CatalogRelationItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    schema_name: str | None = None
    table_name: str
    referenced_schema_name: str | None = None
    referenced_table_name: str
    columns: list[CatalogRelationColumnMapping] = Field(default_factory=list)


class CatalogIndexItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    schema_name: str | None = None
    table_name: str
    unique: bool | None = None
    columns: list[str] = Field(default_factory=list)
    method: str | None = None


class CatalogCategoryAssignment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_name: str | None = None
    table_name: str
    provenance: str | None = None
    is_primary: bool | None = None
    confidence: float | int | str | None = None
    note: str | None = None


class CatalogCategoryItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str | None = None
    description: str | None = None
    assignments: list[CatalogCategoryAssignment] = Field(default_factory=list)


# Concrete envelope aliases for OpenAPI / response_model clarity.
class CatalogTableListResponse(CatalogQueryEnvelope[CatalogTableItem]):
    pass


class CatalogTableDetailResponse(BaseModel):
    source_name: str
    revision_id: int
    schema_fingerprint: str
    item: CatalogTableDetail


class CatalogColumnListResponse(CatalogQueryEnvelope[CatalogColumnItem]):
    pass


class CatalogRelationListResponse(CatalogQueryEnvelope[CatalogRelationItem]):
    pass


class CatalogIndexListResponse(CatalogQueryEnvelope[CatalogIndexItem]):
    pass


class CatalogCategoryListResponse(CatalogQueryEnvelope[CatalogCategoryItem]):
    pass
