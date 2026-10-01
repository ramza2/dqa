"""DEMIS read-only adapter boundary (DBMS-neutral contracts + Oracle thin adapter)."""

from __future__ import annotations

from app.adapters.demis.credential_factory import create_credential_resolver
from app.adapters.demis.credentials import CredentialMaterial, CredentialResolver
from app.adapters.demis.env_credentials import EnvironmentCredentialResolver
from app.adapters.demis.errors import DemisAdapterError, DemisAdapterErrorCode
from app.adapters.demis.factory import (
    create_readonly_demis_adapter,
    is_concrete_demis_adapter_available,
    required_adapter_config_present,
)
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
    "EnvironmentCredentialResolver",
    "ReadOnlyDemisAdapter",
    "ReadonlyQueryRequest",
    "ReadonlyQueryResult",
    "create_credential_resolver",
    "create_readonly_demis_adapter",
    "is_concrete_demis_adapter_available",
    "required_adapter_config_present",
]
