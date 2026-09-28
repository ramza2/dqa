"""Authentication and RBAC foundation (IdentityProvider -> actor -> permissions)."""

from app.auth.models import AuthenticatedActor, Permission, Role
from app.auth.rbac import actor_has_permission, permissions_for_roles

__all__ = [
    "AuthenticatedActor",
    "Permission",
    "Role",
    "actor_has_permission",
    "permissions_for_roles",
]
