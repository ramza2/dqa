"""Unit tests for role -> permission resolution and actor normalization."""

from __future__ import annotations

import pytest

from app.auth.actor import normalize_authenticated_actor
from app.auth.errors import AuthError, AuthErrorCode
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


@pytest.mark.parametrize(
    "actor_id",
    ["", "   ", "a" * 256, "bad\nid", "bad\x00id", "bad\x7fid"],
)
def test_normalize_actor_rejects_invalid_actor_id(actor_id: str) -> None:
    with pytest.raises(AuthError) as exc_info:
        normalize_authenticated_actor(
            AuthenticatedActor(
                actor_id=actor_id,
                roles=frozenset({Role.VIEWER}),
                provider="stub",
            )
        )
    assert exc_info.value.code == AuthErrorCode.AUTHENTICATION_INVALID


def test_normalize_actor_rejects_blank_provider_and_unknown_role() -> None:
    with pytest.raises(AuthError) as exc_info:
        normalize_authenticated_actor(
            AuthenticatedActor(
                actor_id="ok",
                roles=frozenset({Role.VIEWER}),
                provider="  ",
            )
        )
    assert exc_info.value.code == AuthErrorCode.AUTHENTICATION_INVALID

    with pytest.raises(AuthError) as exc_info:
        normalize_authenticated_actor(
            AuthenticatedActor(
                actor_id="ok",
                roles=frozenset({"not_a_role"}),  # type: ignore[arg-type]
                provider="stub",
            )
        )
    assert exc_info.value.code == AuthErrorCode.AUTHENTICATION_INVALID


def test_normalize_actor_trims_and_freezes_roles() -> None:
    normalized = normalize_authenticated_actor(
        AuthenticatedActor(
            actor_id="  actor-1  ",
            roles=[Role.VIEWER, Role.VIEWER, "template_author"],  # type: ignore[arg-type]
            provider=" stub ",
        )
    )
    assert normalized.actor_id == "actor-1"
    assert normalized.provider == "stub"
    assert isinstance(normalized.roles, frozenset)
    assert normalized.roles == frozenset({Role.VIEWER, Role.TEMPLATE_AUTHOR})
