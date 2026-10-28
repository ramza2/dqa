"""M3-B Catalog-bound single-table SELECT preview only (never executable)."""
from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

PreviewOperator = Literal["EQ", "NE", "LT", "LE", "GT", "GE", "LIKE", "IS_NULL", "IS_NOT_NULL"]


class CatalogPreviewPredicate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    column: str = Field(min_length=1, max_length=128)
    operator: PreviewOperator


class CatalogPreviewRequest(BaseModel):
    """No caller SQL, SQL expressions, freeform joins or patient values."""
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    source_name: str = Field(min_length=1, max_length=255)
    catalog_revision_id: int = Field(gt=0)
    schema_fingerprint: str = Field(min_length=1, max_length=128)
    schema_name: str = Field(min_length=1, max_length=128)
    table_name: str = Field(min_length=1, max_length=128)
    columns: list[str] = Field(min_length=1, max_length=16)
    predicates: list[CatalogPreviewPredicate] = Field(default_factory=list, max_length=4)
    row_limit: int = Field(default=50, ge=1, le=100)

    @model_validator(mode="after")
    def reject_duplicate_columns(self):
        if len(self.columns) != len(set(self.columns)):
            raise ValueError("selected column names must be unique")
        if any(not isinstance(s, str) or not s.strip() for s in self.columns):
            raise ValueError("selected columns must not be blank")
        return self


class CatalogPreviewParameter(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    column: str | None = None
    type: str


class CatalogPreviewResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_name: str
    catalog_revision_id: int
    schema_fingerprint: str
    sql_text: str
    parameters: list[CatalogPreviewParameter]
    preview_only: Literal[True] = True
    executable: Literal[False] = False
    approved: Literal[False] = False
    template_id: None = None
