"""Role -> permission resolution (deterministic; no HTTP / LLM)."""

from __future__ import annotations

from collections.abc import Iterable

from app.auth.models import AuthenticatedActor, Permission, Role

ROLE_PERMISSIONS: dict[Role, frozenset[Permission]] = {
    Role.VIEWER: frozenset({Permission.TEMPLATE_READ}),
    Role.TEMPLATE_AUTHOR: frozenset(
        {Permission.TEMPLATE_READ, Permission.TEMPLATE_AUTHOR}
    ),
    Role.TEMPLATE_APPROVER: frozenset(
        {
            Permission.TEMPLATE_READ,
            Permission.TEMPLATE_APPROVE,
            Permission.AUDIT_READ,
        }
    ),
    Role.QUERY_OPERATOR: frozenset({Permission.QUERY_OPERATE}),
    Role.AUDITOR: frozenset({Permission.TEMPLATE_READ, Permission.AUDIT_READ}),
    # Administrator is resolved specially to all declared permissions.
    Role.ADMINISTRATOR: frozenset(Permission),
}

ALL_PERMISSIONS: frozenset[Permission] = frozenset(Permission)


def permissions_for_roles(roles: Iterable[Role]) -> frozenset[Permission]:
    """Resolve the union of permissions for the given roles.

    ``administrator`` always grants every declared ``Permission`` value so newly
    added permissions are covered without per-route special cases.
    """
    role_set = frozenset(roles)
    if Role.ADMINISTRATOR in role_set:
        return ALL_PERMISSIONS
    granted: set[Permission] = set()
    for role in role_set:
        granted |= ROLE_PERMISSIONS.get(role, frozenset())
    return frozenset(granted)


def actor_has_permission(actor: AuthenticatedActor, permission: Permission) -> bool:
    """Return True when the actor's resolved permissions include ``permission``."""
    return permission in permissions_for_roles(actor.roles)
