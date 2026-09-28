"""Unit tests for role -> permission resolution."""

from __future__ import annotations

from app.auth.models import AuthenticatedActor, Permission, Role
from app.auth.rbac import ALL_PERMISSIONS, actor_has_permission, permissions_for_roles


def test_viewer_permissions() -> None:
    assert permissions_for_roles({Role.VIEWER}) == frozenset({Permission.TEMPLATE_READ})


def test_template_author_permissions() -> None:
    assert permissions_for_roles({Role.TEMPLATE_AUTHOR}) == frozenset(
        {Permission.TEMPLATE_READ, Permission.TEMPLATE_AUTHOR}
    )


def test_template_approver_permissions() -> None:
    assert permissions_for_roles({Role.TEMPLATE_APPROVER}) == frozenset(
        {
            Permission.TEMPLATE_READ,
            Permission.TEMPLATE_APPROVE,
            Permission.AUDIT_READ,
        }
    )


def test_query_operator_permissions() -> None:
    assert permissions_for_roles({Role.QUERY_OPERATOR}) == frozenset(
        {Permission.QUERY_OPERATE}
    )


def test_auditor_permissions() -> None:
    assert permissions_for_roles({Role.AUDITOR}) == frozenset(
        {Permission.TEMPLATE_READ, Permission.AUDIT_READ}
    )


def test_administrator_has_all_declared_permissions() -> None:
    granted = permissions_for_roles({Role.ADMINISTRATOR})
    assert granted == ALL_PERMISSIONS
    assert granted == frozenset(Permission)
    for permission in Permission:
        assert permission in granted


def test_multi_role_union() -> None:
    granted = permissions_for_roles({Role.VIEWER, Role.QUERY_OPERATOR})
    assert granted == frozenset(
        {Permission.TEMPLATE_READ, Permission.QUERY_OPERATE}
    )


def test_actor_has_permission_helper() -> None:
    actor = AuthenticatedActor(
        actor_id="a1",
        roles=frozenset({Role.TEMPLATE_AUTHOR}),
        provider="dev_headers",
    )
    assert actor_has_permission(actor, Permission.TEMPLATE_AUTHOR) is True
    assert actor_has_permission(actor, Permission.TEMPLATE_APPROVE) is False
