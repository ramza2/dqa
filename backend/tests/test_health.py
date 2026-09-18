"""Health and readiness endpoint tests."""

from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError


def test_health_returns_ok(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["service"] == "DEMIS Query Assistant"
    assert payload["environment"] == "test"


def test_health_ready_succeeds_when_database_is_up(client: TestClient) -> None:
    response = client.get("/health/ready")
    assert response.status_code == 200
    payload = response.json()
    assert payload == {"status": "ready", "database": "ok"}


def test_health_ready_returns_503_when_database_is_down(client: TestClient) -> None:
    with patch(
        "app.api.routes.health.check_database_connectivity",
        side_effect=OperationalError("SELECT 1", {}, Exception("connection refused")),
    ):
        response = client.get("/health/ready")

    assert response.status_code == 503
    payload = response.json()
    assert payload["status"] == "not_ready"
    assert payload["database"] == "unavailable"
    assert "password" not in payload["detail"].lower()
    assert "dqa" not in payload["detail"]
