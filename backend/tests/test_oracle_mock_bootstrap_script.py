"""Isolated contract test for the Oracle mock metadata bootstrap script."""

from __future__ import annotations

import json
import os
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


class _State:
    def __init__(self) -> None:
        self.profile: dict[str, Any] | None = None
        self.template: dict[str, Any] | None = None
        self.calls: list[tuple[str, str]] = []


def _handler_for(state: _State):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            return

        def _path(self) -> str:
            return urlsplit(self.path).path

        def _read_json(self) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length) if length else b"{}"
            parsed = json.loads(raw.decode("utf-8"))
            assert isinstance(parsed, dict)
            return parsed

        def _send(self, status: int, payload: dict[str, Any]) -> None:
            raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self) -> None:  # noqa: N802 - stdlib HTTP handler contract
            path = self._path()
            state.calls.append(("GET", path))

            if path == "/api/v1/catalog/active/oracle_demis_mock":
                self._send(
                    200,
                    {
                        "source_name": "oracle_demis_mock",
                        "revision_id": 1,
                        "schema_fingerprint": "fixture-fingerprint",
                        "package_readiness": "READY",
                    },
                )
                return

            if path == "/api/v1/connection-profiles":
                items = [] if state.profile is None else [state.profile]
                self._send(
                    200,
                    {
                        "total": len(items),
                        "limit": 100,
                        "offset": 0,
                        "items": items,
                    },
                )
                return

            if path == "/api/v1/query-templates":
                items = []
                if state.template is not None:
                    items.append(
                        {
                            "id": state.template["id"],
                            "stable_key": state.template["stable_key"],
                        }
                    )
                self._send(
                    200,
                    {
                        "total": len(items),
                        "limit": 100,
                        "offset": 0,
                        "items": items,
                    },
                )
                return

            if (
                state.template is not None
                and path == f"/api/v1/query-templates/{state.template['id']}"
            ):
                self._send(200, state.template)
                return

            self._send(404, {"detail": {"code": "NOT_FOUND"}})

        def do_POST(self) -> None:  # noqa: N802 - stdlib HTTP handler contract
            path = self._path()
            state.calls.append(("POST", path))

            if path == "/api/v1/connection-profiles":
                payload = self._read_json()
                assert payload == {
                    "name": "DEMIS Oracle Mock - Development",
                    "source_name": "oracle_demis_mock",
                    "environment": "development",
                    "dbms_type": "oracle",
                    "host": "demis-oracle-test",
                    "port": 1521,
                    "database_name": "FREEPDB1",
                    "username": "DEMIS_RO",
                    "credential_secret_ref": "env:DEMIS_SECRET_ORACLE_PASSWORD",
                }
                state.profile = {
                    **payload,
                    "id": 101,
                    "enabled": False,
                }
                self._send(201, state.profile)
                return

            if (
                state.profile is not None
                and path
                == f"/api/v1/connection-profiles/{state.profile['id']}/enable"
            ):
                state.profile["enabled"] = True
                self._send(200, state.profile)
                return

            if path == "/api/v1/query-templates":
                payload = self._read_json()
                state.template = {
                    "id": 202,
                    "stable_key": payload["stable_key"],
                    "name": payload["name"],
                    "description": payload["description"],
                    "source_name": payload["source_name"],
                    "target_schemas": payload["target_schemas"],
                    "enabled": False,
                    "approval_status": "DRAFT",
                    "version": {
                        "id": 303,
                        "version": 1,
                        "sql_text": payload["sql_text"],
                        "parameter_schema": payload["parameter_schema"],
                        "row_limit": payload["row_limit"],
                        "timeout_seconds": payload["timeout_seconds"],
                        "approval_status": "DRAFT",
                        "compatibility": {
                            "mode": "EXACT_FINGERPRINT",
                            "compatible": True,
                            "pinned_revision_id": 1,
                            "pinned_schema_fingerprint": "fixture-fingerprint",
                            "current_revision_id": 1,
                            "current_schema_fingerprint": "fixture-fingerprint",
                        },
                    },
                }
                self._send(201, state.template)
                return

            if state.template is not None:
                template_id = state.template["id"]

                if path == f"/api/v1/query-templates/{template_id}/submit-review":
                    state.template["approval_status"] = "IN_REVIEW"
                    state.template["version"]["approval_status"] = "IN_REVIEW"
                    self._send(200, state.template)
                    return

                if path == f"/api/v1/query-templates/{template_id}/approve":
                    state.template["approval_status"] = "APPROVED"
                    state.template["version"]["approval_status"] = "APPROVED"
                    self._send(200, state.template)
                    return

                if path == f"/api/v1/query-templates/{template_id}/enable":
                    state.template["enabled"] = True
                    self._send(200, state.template)
                    return

            self._send(404, {"detail": {"code": "NOT_FOUND"}})

    return Handler


def _run_bootstrap(repo_root: Path, base_url: str, env_file: Path) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["DQA_ENV_FILE"] = str(env_file)
    env["DQA_SMOKE_BASE_URL"] = base_url

    return subprocess.run(
        ["bash", str(repo_root / "scripts" / "dqa-oracle-mock-bootstrap.sh")],
        cwd=repo_root,
        env=env,
        text=True,
        encoding="utf-8",
        capture_output=True,
        timeout=30,
        check=False,
    )


def test_oracle_mock_bootstrap_fresh_then_idempotent(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[2]

    env_file = tmp_path / ".env.onprem"
    env_file.write_text(
        "DQA_LAN_BIND_IP=127.0.0.1\n"
        "DQA_FRONTEND_PORT=1\n",
        encoding="utf-8",
    )

    state = _State()
    server = ThreadingHTTPServer(("127.0.0.1", 0), _handler_for(state))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        host, port = server.server_address
        base_url = f"http://{host}:{port}"

        first = _run_bootstrap(repo_root, base_url, env_file)
        assert first.returncode == 0, first.stdout + first.stderr

        assert "PASS: created Connection Profile id=101" in first.stdout
        assert "PASS: enabled Connection Profile id=101" in first.stdout
        assert "PASS: created Query Template id=202" in first.stdout
        assert "PASS: Query Template submitted for review" in first.stdout
        assert "PASS: Query Template approved" in first.stdout
        assert "PASS: Query Template enabled" in first.stdout
        assert "PASS: Oracle mock DQA metadata bootstrap complete" in first.stdout

        assert state.profile is not None
        assert state.profile["enabled"] is True
        assert state.template is not None
        assert state.template["approval_status"] == "APPROVED"
        assert state.template["enabled"] is True

        first_post_paths = [
            path for method, path in state.calls if method == "POST"
        ]
        assert first_post_paths == [
            "/api/v1/connection-profiles",
            "/api/v1/connection-profiles/101/enable",
            "/api/v1/query-templates",
            "/api/v1/query-templates/202/submit-review",
            "/api/v1/query-templates/202/approve",
            "/api/v1/query-templates/202/enable",
        ]

        before_second = len(state.calls)

        second = _run_bootstrap(repo_root, base_url, env_file)
        assert second.returncode == 0, second.stdout + second.stderr

        assert "PASS: existing Connection Profile id=101 matches fixture" in second.stdout
        assert "PASS: Connection Profile id=101 already enabled" in second.stdout
        assert "PASS: existing Query Template id=202 matches fixture" in second.stdout
        assert "PASS: Query Template already enabled" in second.stdout
        assert "PASS: Oracle mock DQA metadata bootstrap complete" in second.stdout

        second_calls = state.calls[before_second:]
        assert all(method == "GET" for method, _path in second_calls)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
