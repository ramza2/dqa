"""Detect forbidden secret/credential key names in Catalog Package JSON (keys only)."""

from __future__ import annotations

from typing import Any

# Exact normalized key names (case-insensitive). No substring matching.
_FORBIDDEN_SECRET_KEYS = frozenset(
    {
        "password",
        "passwd",
        "pwd",
        "api_key",
        "apikey",
        "access_token",
        "refresh_token",
        "client_secret",
        "private_key",
        "credential",
        "credentials",
    }
)


def find_forbidden_secret_key(document: Any) -> bool:
    """Return True if document contains a forbidden key name anywhere in the tree."""
    return _walk(document) is not None


def _walk(node: Any) -> str | None:
    if isinstance(node, dict):
        for key, value in node.items():
            if isinstance(key, str) and _is_forbidden_key(key):
                return key
            if _walk(value) is not None:
                return "nested"
        return None
    if isinstance(node, list):
        for item in node:
            if _walk(item) is not None:
                return "nested"
        return None
    return None


def _is_forbidden_key(key: str) -> bool:
    normalized = key.strip().lower()
    return normalized in _FORBIDDEN_SECRET_KEYS
