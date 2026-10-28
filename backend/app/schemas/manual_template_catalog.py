"""Approved Query Template catalog for model-free manual selection.

No raw SQL, patient records, credential information, or execution authority.
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.recommendation import RecommendedTemplate


class ManualTemplateListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_name: str
    catalog_revision_id: int
    schema_fingerprint: str
    total: int = Field(ge=0)
    limit: int = Field(ge=1, le=100)
    offset: int = Field(ge=0)
    items: list[RecommendedTemplate]
