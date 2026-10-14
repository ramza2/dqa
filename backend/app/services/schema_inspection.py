"""Explicit, default-disabled, admin-only Oracle metadata inspection.

This service accepts no caller target/SQL/schema overrides, uses a distinct
inspector credential namespace, creates a short-lived bounded engine and returns
only aggregate metadata counts. No Catalog, patient row or DEMIS writes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from sqlalchemy import create_engine, event
from sqlalchemy.engine import URL
from sqlalchemy.pool import NullPool

from app.adapters.demis.env_credentials import EnvironmentCredentialResolver
from app.adapters.schema_inspector.oracle import OracleSchemaInspector, SYSTEM_SCHEMAS
from app.core.config import Settings
from app.schemas.schema_inspector import SchemaInspectionSummary

# Separate from DEMIS_SECRET_ used by live read Query Connection Profiles.
INSPECTOR_CREDENTIAL_PREFIX = "DEMIS_INSPECT_SECRET_"
_ALLOWED_IDENTIFIER = re.compile(r"^[A-Za-z][A-Za-z0-9_$#]{0,127}$")
_ALLOWED_SOURCE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,254}$")
_CONNECT_TIMEOUT_SECONDS = 5
_CALL_TIMEOUT_MS = 15_000


class SchemaInspectionError(Exception):
    """Internal error code only; never include secrets or connection exceptions."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


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
    # Service/host/username are operator-only config, never request inputs.
    # Avoid accidental inline DSN/credential URI interpretation.
    if any(x in host for x in "/:@?\\") or any(x in service for x in "/:@?\\"):
        raise SchemaInspectionError("INSPECTOR_NOT_CONFIGURED")
    if not ref.startswith("env:" + INSPECTOR_CREDENTIAL_PREFIX):
        raise SchemaInspectionError("INSPECTOR_NOT_CONFIGURED")
    return _InspectorTarget(
        source_name=source, schema_name=schema, host=host,
        port=settings.schema_inspector_port, service_name=service,
        username=username, credential_ref=ref,
    )


def inspect_configured_schema(settings: Settings) -> SchemaInspectionSummary:
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

    return SchemaInspectionSummary(
        source_name=target.source_name,
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
