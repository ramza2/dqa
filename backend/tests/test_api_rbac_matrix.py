"""Cross-cutting API RBAC regression matrix.

Each representative protected route is exercised with every declared application
role. The expected role sets are hard-coded here so this suite catches both
route-permission wiring regressions and accidental role-grant expansion.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import FrozenSet

import pytest
from fastapi.testclient import TestClient

from app.auth.errors import AuthErrorCode
from app.auth.models import Role

pytestmark = pytest.mark.integration


@dataclass(frozen=True)
class ProtectedRouteCase:
    name: str
    method: str
    path: str
    allowed_roles: FrozenSet[Role]


ALL_ROLES = tuple(Role)
ADMIN_ONLY = frozenset({Role.ADMINISTRATOR})

CASES = (
    ProtectedRouteCase(
        name="template_read",
        method="GET",
        path="/api/v1/query-templates",
        allowed_roles=frozenset(
            {
                Role.VIEWER,
                Role.TEMPLATE_AUTHOR,
                Role.TEMPLATE_APPROVER,
                Role.AUDITOR,
                Role.ADMINISTRATOR,
            }
        ),
    ),
    ProtectedRouteCase(
        name="template_author",
        method="DELETE",
        path="/api/v1/query-templates/2147483647",
        allowed_roles=frozenset(
            {
                Role.TEMPLATE_AUTHOR,
                Role.ADMINISTRATOR,
            }
        ),
    ),
    ProtectedRouteCase(
        name="template_approve",
        method="POST",
        path="/api/v1/query-templates/2147483647/enable",
        allowed_roles=frozenset(
            {
                Role.TEMPLATE_APPROVER,
                Role.ADMINISTRATOR,
            }
        ),
    ),
    ProtectedRouteCase(
        name="query_operate",
        method="GET",
        path=(
            "/api/v1/query-executions/form"
            "?source_name=RBAC_MATRIX"
            "&template_id=2147483647"
            "&version_id=2147483647"
        ),
        allowed_roles=frozenset(
            {
                Role.QUERY_OPERATOR,
                Role.ADMINISTRATOR,
            }
        ),
    ),
    ProtectedRouteCase(
        name="audit_read",
        method="GET",
        path="/api/v1/audit-events?limit=1",
        allowed_roles=frozenset(
            {
                Role.TEMPLATE_APPROVER,
                Role.AUDITOR,
                Role.ADMINISTRATOR,
            }
        ),
    ),
    ProtectedRouteCase(
        name="connection_profile_manage",
        method="GET",
        path="/api/v1/connection-profiles?limit=1",
        allowed_roles=ADMIN_ONLY,
    ),
    ProtectedRouteCase(
        name="catalog_read",
        method="GET",
        path="/api/v1/catalog/active",
        allowed_roles=frozenset(ALL_ROLES),
    ),
    ProtectedRouteCase(
        name="catalog_manage",
        method="POST",
        path="/api/v1/catalog/imports/2147483647/activate",
        allowed_roles=ADMIN_ONLY,
    ),
)


def _headers(role: Role) -> dict[str, str]:
    return {
        "X-DQA-Dev-Actor": f"rbac-matrix-{role.value}",
        "X-DQA-Dev-Roles": role.value,
    }


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.name)
@pytest.mark.parametrize("role", ALL_ROLES, ids=lambda role: role.value)
def test_protected_route_role_matrix(
    unauth_db_client: TestClient,
    case: ProtectedRouteCase,
    role: Role,
) -> None:
    response = unauth_db_client.request(
        case.method,
        case.path,
        headers=_headers(role),
    )

    if role in case.allowed_roles:
        # Downstream domain failures (e.g. synthetic id not found) are allowed.
        # The role must have crossed the authentication/authorization boundary.
        assert response.status_code not in {401, 403}, response.text
        detail = response.json().get("detail") if response.content else None
        if isinstance(detail, dict):
            assert detail.get("code") not in {
                AuthErrorCode.AUTHENTICATION_REQUIRED,
                AuthErrorCode.AUTHENTICATION_INVALID,
                AuthErrorCode.AUTHORIZATION_DENIED,
            }
        return

    assert response.status_code == 403, response.text
    assert response.json()["detail"]["code"] == AuthErrorCode.AUTHORIZATION_DENIED


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.name)
def test_protected_route_missing_identity_fails_closed(
    unauth_db_client: TestClient,
    case: ProtectedRouteCase,
) -> None:
    response = unauth_db_client.request(case.method, case.path)

    assert response.status_code == 401, response.text
    assert response.json()["detail"]["code"] == AuthErrorCode.AUTHENTICATION_REQUIRED
