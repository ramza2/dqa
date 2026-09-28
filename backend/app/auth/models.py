"""Authenticated actor, roles, and permissions."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Role(str, Enum):
    """Application roles (identity claims; not checked directly in routes)."""

    VIEWER = "viewer"
    TEMPLATE_AUTHOR = "template_author"
    TEMPLATE_APPROVER = "template_approver"
    QUERY_OPERATOR = "query_operator"
    AUDITOR = "auditor"
    ADMINISTRATOR = "administrator"


class Permission(str, Enum):
    """Fine-grained permissions resolved from roles."""

    TEMPLATE_READ = "TEMPLATE_READ"
    TEMPLATE_AUTHOR = "TEMPLATE_AUTHOR"
    TEMPLATE_APPROVE = "TEMPLATE_APPROVE"
    QUERY_OPERATE = "QUERY_OPERATE"
    AUDIT_READ = "AUDIT_READ"


@dataclass(frozen=True)
class AuthenticatedActor:
    """Authenticated caller identity (no credentials; no request-body actor)."""

    actor_id: str
    roles: frozenset[Role]
    provider: str
    display_name: str | None = None
