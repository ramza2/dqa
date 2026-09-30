"""DEMIS read-only adapter foundation (DBMS-neutral; no concrete driver yet)."""

from __future__ import annotations

from app.adapters.demis.credentials import CredentialMaterial, CredentialResolver
from app.adapters.demis.errors import DemisAdapterError, DemisAdapterErrorCode
from app.adapters.demis.factory import create_readonly_demis_adapter
from app.adapters.demis.profile import ConnectionProfileSnapshot
from app.adapters.demis.protocol import ReadOnlyDemisAdapter
from app.adapters.demis.types import (
    DemisAdapterDiagnostics,
    ReadonlyQueryRequest,
    ReadonlyQueryResult,
)

__all__ = [
    "ConnectionProfileSnapshot",
    "CredentialMaterial",
    "CredentialResolver",
    "DemisAdapterDiagnostics",
    "DemisAdapterError",
    "DemisAdapterErrorCode",
    "ReadOnlyDemisAdapter",
    "ReadonlyQueryRequest",
    "ReadonlyQueryResult",
    "create_readonly_demis_adapter",
]
