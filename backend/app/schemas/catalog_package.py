"""Pydantic schemas for Catalog Package v2 validation API and manifest parsing."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

PackageReadiness = Literal["READY", "WARNING", "BLOCKED"]
SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")


class PackageSourceIdentity(BaseModel):
    """Source identity shared by manifest and database.json."""

    model_config = ConfigDict(extra="allow")

    source_name: str
    db_type: str
    database_name: str | None = None
    default_schema: str | None = None


class ManifestFileEntry(BaseModel):
    """One manifest-managed file descriptor."""

    model_config = ConfigDict(extra="allow")

    path: str
    sha256: str
    bytes: int = Field(ge=0)

    @field_validator("path")
    @classmethod
    def path_must_be_safe_relative(cls, value: str) -> str:
        """Reject unsafe paths. Never rewrite/normalize attacker-controlled input."""
        if not isinstance(value, str):
            raise ValueError("manifest file path must be a string")

        # Do not strip/lstrip/repair — reject malformed forms outright.
        if value == "" or value in {".", ".."}:
            raise ValueError("manifest file path must be a safe package-relative path")
        if value.startswith("/") or value.startswith("\\"):
            raise ValueError("manifest file path must not be absolute")
        if "\\" in value:
            raise ValueError("manifest file path must not contain backslash")
        if len(value) >= 2 and value[1] == ":" and value[0].isalpha():
            raise ValueError("manifest file path must not be a Windows drive path")
        if value.startswith("./"):
            raise ValueError("manifest file path must not start with ./")

        parts = value.split("/")
        if any(part == "" for part in parts):
            raise ValueError("manifest file path must not contain empty segments")
        if any(part in {".", ".."} for part in parts):
            raise ValueError("manifest file path must not contain parent traversal")

        return value

    @field_validator("sha256")
    @classmethod
    def sha256_hex(cls, value: str) -> str:
        if not SHA256_RE.fullmatch(value):
            raise ValueError("sha256 must be a 64-character hex digest")
        return value.lower()


class CatalogPackageManifest(BaseModel):
    """Subset of Catalog Package v2 manifest.json used by DQA validation."""

    model_config = ConfigDict(extra="allow")

    package_format: str
    package_version: str
    package_readiness: PackageReadiness
    source: PackageSourceIdentity
    schema_fingerprint: str
    files: list[ManifestFileEntry]
    counts: dict[str, Any] = Field(default_factory=dict)

    @field_validator("schema_fingerprint")
    @classmethod
    def fingerprint_non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("schema_fingerprint must be non-empty")
        return value


class CatalogPackageErrorBody(BaseModel):
    """Structured API error for package validation failures."""

    code: str
    message: str
    path: str | None = None


class CatalogPackageValidateResponse(BaseModel):
    """Successful validation response (READY / WARNING / BLOCKED structurally OK)."""

    valid: bool = True
    package_format: str
    package_version: str
    package_readiness: PackageReadiness
    activation_eligible: bool
    source: PackageSourceIdentity
    schema_fingerprint: str
    archive_sha256: str
    manifest_sha256: str
    counts: dict[str, Any] = Field(default_factory=dict)
    files_validated: int
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class CatalogImportRevisionSummary(BaseModel):
    """Metadata-only import revision representation (no stored JSON bodies)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    source_name: str
    db_type: str
    database_name: str | None = None
    default_schema: str | None = None
    package_format: str
    package_version: str
    package_readiness: PackageReadiness
    activation_eligible: bool
    schema_fingerprint: str
    archive_sha256: str
    manifest_sha256: str
    validation_status: str
    generated_at: datetime | None = None
    imported_at: datetime
    table_count: int
    column_count: int
    relation_count: int
    index_count: int
    category_count: int
    category_assignment_count: int
    managed_file_count: int
    created: bool | None = None


class CatalogImportRevisionDetail(CatalogImportRevisionSummary):
    """Detail metadata for one import revision (still excludes raw JSON documents)."""

    created_at: datetime


# --- Producer-aligned minimal JSON document shapes (extra fields allowed) ---


class DatabaseDocument(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: PackageSourceIdentity
    latest_analysis: dict[str, Any] | None = None


class TablesDocument(BaseModel):
    model_config = ConfigDict(extra="allow")

    tables: list[Any]


class ColumnsDocument(BaseModel):
    model_config = ConfigDict(extra="allow")

    columns: list[Any]


class RelationsDocument(BaseModel):
    model_config = ConfigDict(extra="allow")

    relations: list[Any]


class IndexesDocument(BaseModel):
    model_config = ConfigDict(extra="allow")

    indexes: list[Any]


class CategoriesDocument(BaseModel):
    model_config = ConfigDict(extra="allow")

    categories: list[Any]
    table_assignments: list[Any] | None = None


class ErdDocument(BaseModel):
    model_config = ConfigDict(extra="allow")

    nodes: list[Any]
    edges: list[Any]


class LatestRunDocument(BaseModel):
    """Producer v2 shape: {available, run?: {schema_fingerprint, ...}}."""

    model_config = ConfigDict(extra="allow")

    available: bool
    run: dict[str, Any] | None = None

    @model_validator(mode="after")
    def run_required_when_available(self) -> LatestRunDocument:
        if self.available and not isinstance(self.run, dict):
            raise ValueError("analysis/latest_run.json requires run object when available=true")
        return self


class SchemaSnapshotDocument(BaseModel):
    """Producer v2 wrapper: {available, run_id?, payload?}."""

    model_config = ConfigDict(extra="allow")

    available: bool
    run_id: int | None = None
    payload: dict[str, Any] | None = None

    @model_validator(mode="after")
    def payload_required_when_available(self) -> SchemaSnapshotDocument:
        if self.available and not isinstance(self.payload, dict):
            raise ValueError(
                "analysis/schema_snapshot.json requires payload object when available=true"
            )
        return self


class PreflightDocument(BaseModel):
    model_config = ConfigDict(extra="allow")

    available: bool
    status: str | None = None


class DiffLatestDocument(BaseModel):
    model_config = ConfigDict(extra="allow")

    available: bool
