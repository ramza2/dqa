"""Explicit, default-disabled, admin-only Oracle metadata inspection.

This service accepts no caller target/SQL/schema overrides, uses a distinct
inspector credential namespace, creates a short-lived bounded engine and returns
only aggregate metadata counts. No Catalog, patient row or DEMIS writes.
"""

from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass
from sqlalchemy import create_engine, event
from sqlalchemy.engine import URL
from sqlalchemy.pool import NullPool

from app.adapters.demis.env_credentials import (
    EnvironmentCredentialResolver, validate_demis_credential_env_prefix,
)
from app.adapters.schema_inspector.base import SchemaSnapshot
from app.adapters.schema_inspector.oracle import OracleSchemaInspector, SYSTEM_SCHEMAS
from app.core.config import Settings
from app.schemas.schema_inspector import SchemaInspectionSummary

# Separate from DEMIS_SECRET_ used by live read Query Connection Profiles.
INSPECTOR_CREDENTIAL_PREFIX = "DEMIS_INSPECT_SECRET_"
_ALLOWED_IDENTIFIER = re.compile(r"^[A-Za-z][A-Za-z0-9_$#]{0,127}$")
_ALLOWED_SOURCE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,254}$")
_ALLOWED_HOST_LABEL = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$")
_ALLOWED_SERVICE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,254}$")
_ALLOWED_SECRET_REF = re.compile(
    r"^env:DEMIS_INSPECT_SECRET_[A-Z0-9_]+$"
)
_CONNECT_TIMEOUT_SECONDS = 5
_CALL_TIMEOUT_MS = 15_000


class SchemaInspectionError(Exception):
    """Internal error code only; never include secrets or connection exceptions."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _valid_host(host: str) -> bool:
    """Only a literal IP or a bounded DNS hostname, never a URL/DSN."""
    if not host or len(host) > 253:
        return False
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        return all(
            _ALLOWED_HOST_LABEL.fullmatch(label) is not None
            for label in host.split(".")
        )


@dataclass(frozen=True)
class _InspectorTarget:
    source_name: str
    schema_name: str
    host: str
    port: int
    service_name: str
    username: str
    credential_ref: str


def _target_from_settings(settings: Settings) -> _InspectorTarget:
    """Fail closed before resolving credentials or opening any connection."""
    if not settings.schema_inspector_enabled:
        raise SchemaInspectionError("INSPECTOR_DISABLED")
    # Production is intentionally blocked until approved authentication and
    # military DBA metadata privilege acceptance are provided in a future PR.
    if settings.app_env not in ("development", "test"):
        raise SchemaInspectionError("INSPECTOR_ENV_NOT_ALLOWED")

    values = (
        settings.schema_inspector_source_name,
        settings.schema_inspector_schema_name,
        settings.schema_inspector_host,
        settings.schema_inspector_service_name,
        settings.schema_inspector_username,
        settings.schema_inspector_credential_ref,
    )
    if any(not isinstance(v, str) or not v.strip() or v != v.strip() for v in values):
        raise SchemaInspectionError("INSPECTOR_NOT_CONFIGURED")
    if settings.schema_inspector_port is None:
        raise SchemaInspectionError("INSPECTOR_NOT_CONFIGURED")

    source, schema, host, service, username, ref = values
    if not _ALLOWED_SOURCE.fullmatch(source):
        raise SchemaInspectionError("INSPECTOR_NOT_CONFIGURED")
    if not _ALLOWED_IDENTIFIER.fullmatch(schema) or schema.upper() in SYSTEM_SCHEMAS:
        raise SchemaInspectionError("INSPECTOR_NOT_CONFIGURED")
    # Validate *all* operator config before credential dereference/DB connect.
    # The hostname parser deliberately does not resolve DNS or certify the
    # military DBA's actual host/schema allowlist (that requires G0 approval).
    if not _valid_host(host) or _ALLOWED_SERVICE.fullmatch(service) is None:
        raise SchemaInspectionError("INSPECTOR_NOT_CONFIGURED")
    if (
        _ALLOWED_IDENTIFIER.fullmatch(username) is None
        or username.upper() in SYSTEM_SCHEMAS
    ):
        raise SchemaInspectionError("INSPECTOR_NOT_CONFIGURED")
    if _ALLOWED_SECRET_REF.fullmatch(ref) is None:
        raise SchemaInspectionError("INSPECTOR_NOT_CONFIGURED")

    # A configurable Query Connection Profile prefix must never encompass the
    # fixed Inspector namespace, and vice versa. Prevent credential-domain
    # overlap even when the *individual* inspector ref is otherwise valid.
    try:
        read_prefix = validate_demis_credential_env_prefix(
            settings.dqa_demis_credential_env_prefix
        )
    except Exception:
        raise SchemaInspectionError("INSPECTOR_NOT_CONFIGURED") from None
    if (
        read_prefix.startswith(INSPECTOR_CREDENTIAL_PREFIX)
        or INSPECTOR_CREDENTIAL_PREFIX.startswith(read_prefix)
    ):
        raise SchemaInspectionError("INSPECTOR_NOT_CONFIGURED")
    return _InspectorTarget(
        source_name=source, schema_name=schema, host=host,
        port=settings.schema_inspector_port, service_name=service,
        username=username, credential_ref=ref,
    )


@dataclass(frozen=True)
class CollectedSchemaSnapshot:
    """Configured source identity paired with inspected physical metadata."""

    source_name: str
    snapshot: SchemaSnapshot


def collect_configured_schema_snapshot(settings: Settings) -> CollectedSchemaSnapshot:
    """Collect a non-persistent metadata Snapshot from one allowlisted schema.

    Only call from an authorized admin route. An active Catalog revision can
    change solely via the existing separate READY package activation path.
    """
    target = _target_from_settings(settings)
    try:
        # Reuses approved env: scheme resolution, but only the independent
        # INSPECTOR prefix can be dereferenced.
        credential = EnvironmentCredentialResolver(
            env_prefix=INSPECTOR_CREDENTIAL_PREFIX
        ).resolve(target.credential_ref)
    except Exception:
        raise SchemaInspectionError("INSPECTOR_NOT_CONFIGURED") from None

    engine = None
    try:
        url = URL.create(
            drivername="oracle+oracledb",
            username=target.username,
            password=credential.get_secret(),
            host=target.host,
            port=target.port,
            query={"service_name": target.service_name},
        )
        engine = create_engine(
            url,
            poolclass=NullPool,
            connect_args={"tcp_connect_timeout": _CONNECT_TIMEOUT_SECONDS},
        )

        @event.listens_for(engine, "connect")
        def _set_call_timeout(dbapi_connection, _connection_record):
            dbapi_connection.call_timeout = _CALL_TIMEOUT_MS

        snapshot = OracleSchemaInspector(engine, target.service_name).inspect(
            target.schema_name
        )
    except Exception:
        # DB/driver exception bodies can include host, SQL, credentials or schema.
        raise SchemaInspectionError("INSPECTOR_METADATA_FAILED") from None
    finally:
        if engine is not None:
            engine.dispose()

    return CollectedSchemaSnapshot(
        source_name=target.source_name,
        snapshot=snapshot,
    )


def inspect_configured_schema(settings: Settings) -> SchemaInspectionSummary:
    """Return aggregate-only metadata without persistence (legacy behavior)."""
    collected = collect_configured_schema_snapshot(settings)
    snapshot = collected.snapshot
    return SchemaInspectionSummary(
        source_name=collected.source_name,
        schema_name=snapshot.schema_name,
        table_count=len(snapshot.tables),
        column_count=len(snapshot.columns),
        primary_key_column_count=len(snapshot.primary_keys),
        unique_key_column_count=len(snapshot.unique_constraints),
        foreign_key_count=len(snapshot.foreign_keys),
        index_count=len(snapshot.indexes),
        imported=False,
        activated=False,
    )
