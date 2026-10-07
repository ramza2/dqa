"""Shared fail-closed mapping for public HTTP error contracts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from fastapi import HTTPException


@dataclass(frozen=True)
class PublicErrorSpec:
    """Reviewed public status/message pair for one stable error code."""

    status_code: int
    message: str
    public_code: str | None = None


def build_public_http_error(
    *,
    error_code: str,
    contracts: Mapping[str, PublicErrorSpec],
    fallback_code: str,
    fallback_status_code: int,
    fallback_message: str,
) -> HTTPException:
    """Build a public error without trusting internal exception text.

    Unknown or unreviewed codes fail closed to the caller-supplied fallback
    contract. Only reviewed code/status/message values can cross this boundary.
    """

    spec = contracts.get(error_code)
    if spec is None:
        public_code = fallback_code
        status_code = fallback_status_code
        message = fallback_message
    else:
        public_code = spec.public_code or error_code
        status_code = spec.status_code
        message = spec.message

    return HTTPException(
        status_code=status_code,
        detail={"code": public_code, "message": message},
    )
