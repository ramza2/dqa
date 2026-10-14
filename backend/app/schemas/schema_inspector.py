"""Only sanitized, aggregate metadata-inspection API contracts."""

from pydantic import BaseModel, ConfigDict, Field


class SchemaInspectionRequest(BaseModel):
    """Required empty body: callers may not choose a DB target, schema or SQL."""

    model_config = ConfigDict(extra="forbid")


class SchemaInspectionSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str = "INSPECTED"
    source_name: str
    schema_name: str
    table_count: int = Field(ge=0)
    column_count: int = Field(ge=0)
    primary_key_column_count: int = Field(ge=0)
    unique_key_column_count: int = Field(ge=0)
    foreign_key_count: int = Field(ge=0)
    index_count: int = Field(ge=0)
    imported: bool = False
    activated: bool = False
