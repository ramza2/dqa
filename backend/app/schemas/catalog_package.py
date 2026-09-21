"""Pydantic schemas for Catalog Package v2 validation API and manifest parsing."""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

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
    def path_must_be_relative(cls, value: str) -> str:
        cleaned = value.strip().lstrip("./")
        if not cleaned or cleaned.startswith("/") or "\\" in cleaned or ".." in cleaned.split("/"):
            raise ValueError("manifest file path must be a safe package-relative path")
        return cleaned.replace("\\", "/")

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


# --- Minimal JSON document shapes (extra fields allowed; do not invent required fields) ---


class DatabaseDocument(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: PackageSourceIdentity | None = None
    latest_analysis: dict[str, Any] | None = None


class LatestRunDocument(BaseModel):
    model_config = ConfigDict(extra="allow")

    schema_fingerprint: str | None = None
