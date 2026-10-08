"""Opaque AES-GCM execution tokens for MCP Template Query (Phase 28-C).

Security properties:
- Authenticated encryption (AES-256-GCM) with a dedicated configured secret
- Random 96-bit nonce per token; short TTL (default <= 5 minutes)
- Subject binding (actor_id + provider)
- Connection Profile binding: profile id + fingerprint of execution-relevant
  non-secret configuration (includes credential *reference*, never secret value)
- Resolved parameters live only inside the token ciphertext (AES-GCM). This does
  **not** encrypt the caller's original ``tools/call`` JSON arguments on the wire.
- Fail closed when the key is missing/invalid
- Stateless: no process-local token store (safe for multi-worker deployments)

Limitation (documented): tokens are not single-use. Replay within TTL is
possible; every ``demis.execute_query`` independently revalidates eligibility,
profile/catalog binding, and writes durable audit. Do not claim single-use.

Never log the raw token or decrypted payload.
"""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.auth.models import AuthenticatedActor
from app.core.config import Settings
from app.models.connection_profile import ConnectionProfile

TOKEN_PREFIX = "dqa1."
TOKEN_VERSION = 2
_NONCE_BYTES = 12
_KEY_BYTES = 32


class McpExecutionTokenError(Exception):
    """Fail-closed token crypto/validation error (sanitized public code only)."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class McpExecutionTokenErrorCode:
    KEY_UNAVAILABLE = "MCP_EXECUTION_TOKEN_KEY_UNAVAILABLE"
    INVALID = "MCP_EXECUTION_TOKEN_INVALID"
    EXPIRED = "MCP_EXECUTION_TOKEN_EXPIRED"
    SUBJECT_MISMATCH = "MCP_EXECUTION_TOKEN_SUBJECT_MISMATCH"


@dataclass(frozen=True)
class ExecutionTokenClaims:
    """Decrypted, validated execution token claims."""

    actor_id: str
    provider: str
    source_name: str
    environment: str
    template_id: int
    version_id: int
    catalog_revision_id: int
    catalog_fingerprint: str
    connection_profile_id: int
    connection_profile_fingerprint: str
    parameters: dict[str, Any]
    sensitive_parameter_names: list[str]
    issued_at: datetime
    expires_at: datetime


def connection_profile_binding_fingerprint(profile: ConnectionProfile) -> str:
    """SHA-256 of execution-relevant, non-secret Connection Profile fields.

    Includes ``credential_secret_ref`` (reference identifier only). Never hashes
    or embeds credential secret values.
    """
    payload = {
        "credential_secret_ref": profile.credential_secret_ref,
        "database_name": profile.database_name,
        "dbms_type": profile.dbms_type,
        "enabled": bool(profile.enabled),
        "environment": profile.environment,
        "host": profile.host,
        "port": profile.port,
        "source_name": profile.source_name,
        "username": profile.username,
    }
    canonical = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _load_aes_key(settings: Settings) -> bytes:
    secret = settings.dqa_mcp_execution_token_key
    if secret is None:
        raise McpExecutionTokenError(McpExecutionTokenErrorCode.KEY_UNAVAILABLE)
    raw = secret.get_secret_value().strip()
    if not raw:
        raise McpExecutionTokenError(McpExecutionTokenErrorCode.KEY_UNAVAILABLE)
    key: bytes | None = None
    # Prefer URL-safe or std base64 (32 raw bytes). Fall back to hex.
    for decoder in (
        lambda s: base64.urlsafe_b64decode(s + "=" * (-len(s) % 4)),
        lambda s: base64.b64decode(s + "=" * (-len(s) % 4)),
        bytes.fromhex,
    ):
        try:
            candidate = decoder(raw)
        except Exception:
            continue
        if len(candidate) == _KEY_BYTES:
            key = candidate
            break
    if key is None:
        raise McpExecutionTokenError(McpExecutionTokenErrorCode.KEY_UNAVAILABLE)
    return key


def issue_execution_token(
    *,
    actor: AuthenticatedActor,
    source_name: str,
    environment: str,
    template_id: int,
    version_id: int,
    catalog_revision_id: int,
    catalog_fingerprint: str,
    connection_profile_id: int,
    connection_profile_fingerprint: str,
    parameters: dict[str, Any],
    sensitive_parameter_names: list[str],
    settings: Settings,
) -> tuple[str, datetime]:
    """Issue a compact opaque token. Returns (token, expires_at)."""
    key = _load_aes_key(settings)
    now = datetime.now(UTC)
    ttl = int(settings.dqa_mcp_execution_token_ttl_seconds)
    expires_at = now + timedelta(seconds=ttl)
    fingerprint = (connection_profile_fingerprint or "").strip()
    if not fingerprint:
        raise McpExecutionTokenError(McpExecutionTokenErrorCode.INVALID)
    payload = {
        "v": TOKEN_VERSION,
        "actor_id": actor.actor_id,
        "provider": actor.provider,
        "source_name": source_name,
        "environment": environment,
        "template_id": int(template_id),
        "version_id": int(version_id),
        "catalog_revision_id": int(catalog_revision_id),
        "catalog_fingerprint": catalog_fingerprint,
        "connection_profile_id": int(connection_profile_id),
        "connection_profile_fingerprint": fingerprint,
        "parameters": parameters,
        "sensitive_parameter_names": list(sensitive_parameter_names),
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
    }
    plaintext = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode(
        "utf-8"
    )
    nonce = secrets.token_bytes(_NONCE_BYTES)
    ciphertext = AESGCM(key).encrypt(nonce, plaintext, None)
    token = TOKEN_PREFIX + base64.urlsafe_b64encode(nonce + ciphertext).decode("ascii")
    return token, expires_at


def verify_execution_token(
    token: str,
    *,
    actor: AuthenticatedActor,
    settings: Settings,
) -> ExecutionTokenClaims:
    """Decrypt and validate a token; bind to the current authenticated actor."""
    key = _load_aes_key(settings)
    if not isinstance(token, str) or not token.startswith(TOKEN_PREFIX):
        raise McpExecutionTokenError(McpExecutionTokenErrorCode.INVALID)
    blob = token[len(TOKEN_PREFIX) :]
    try:
        raw = base64.urlsafe_b64decode(blob + "=" * (-len(blob) % 4))
    except Exception as exc:
        raise McpExecutionTokenError(McpExecutionTokenErrorCode.INVALID) from exc
    if len(raw) <= _NONCE_BYTES:
        raise McpExecutionTokenError(McpExecutionTokenErrorCode.INVALID)
    nonce, ciphertext = raw[:_NONCE_BYTES], raw[_NONCE_BYTES:]
    try:
        plaintext = AESGCM(key).decrypt(nonce, ciphertext, None)
        payload = json.loads(plaintext.decode("utf-8"))
    except Exception as exc:
        raise McpExecutionTokenError(McpExecutionTokenErrorCode.INVALID) from exc

    if not isinstance(payload, dict) or payload.get("v") != TOKEN_VERSION:
        raise McpExecutionTokenError(McpExecutionTokenErrorCode.INVALID)

    try:
        actor_id = str(payload["actor_id"])
        provider = str(payload["provider"])
        exp = int(payload["exp"])
        iat = int(payload["iat"])
        parameters = payload["parameters"]
        if not isinstance(parameters, dict):
            raise TypeError("parameters")
        profile_fp = str(payload["connection_profile_fingerprint"]).strip()
        if not profile_fp:
            raise TypeError("connection_profile_fingerprint")
        claims = ExecutionTokenClaims(
            actor_id=actor_id,
            provider=provider,
            source_name=str(payload["source_name"]),
            environment=str(payload["environment"]),
            template_id=int(payload["template_id"]),
            version_id=int(payload["version_id"]),
            catalog_revision_id=int(payload["catalog_revision_id"]),
            catalog_fingerprint=str(payload["catalog_fingerprint"]),
            connection_profile_id=int(payload["connection_profile_id"]),
            connection_profile_fingerprint=profile_fp,
            parameters=dict(parameters),
            sensitive_parameter_names=[
                str(name) for name in (payload.get("sensitive_parameter_names") or [])
            ],
            issued_at=datetime.fromtimestamp(iat, tz=UTC),
            expires_at=datetime.fromtimestamp(exp, tz=UTC),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise McpExecutionTokenError(McpExecutionTokenErrorCode.INVALID) from exc

    now = datetime.now(UTC)
    if claims.expires_at <= now or claims.issued_at > now + timedelta(seconds=30):
        raise McpExecutionTokenError(McpExecutionTokenErrorCode.EXPIRED)

    if claims.actor_id != actor.actor_id or claims.provider != actor.provider:
        raise McpExecutionTokenError(McpExecutionTokenErrorCode.SUBJECT_MISMATCH)

    return claims
