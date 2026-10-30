"""Static safety checks for M4-A harness/smoke scripts (no DB / no network)."""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
ISOLATED = ROOT / "scripts" / "m4a-test-isolated.sh"
SMOKE = ROOT / "scripts" / "dqa-m4a-llmfree-smoke.sh"


@pytest.fixture(scope="module")
def isolated_text() -> str:
    return ISOLATED.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def smoke_text() -> str:
    return SMOKE.read_text(encoding="utf-8")


def test_isolated_diff_check_is_fail_closed(isolated_text: str) -> None:
    assert "git diff --check" in isolated_text
    assert "git diff --check 79210d1 HEAD || true" not in isolated_text
    assert "git diff --check 79210d1 HEAD ||true" not in isolated_text.replace(" ", "")


def test_isolated_never_claims_review_or_live_pass_on_tcp_only(isolated_text: str) -> None:
    assert "M4A_API_CONTRACT_PASS" in isolated_text
    assert "LIVE_E2E=NOT_RUN" in isolated_text
    assert "M4A_ISOLATED_HARNESS_COMPLETE" in isolated_text
    # TCP reachable must not be emitted as overall review / live E2E PASS.
    assert 'echo "M4A_REVIEW_PASS"' not in isolated_text
    assert "echo M4A_REVIEW_PASS" not in isolated_text
    assert 'echo "LIVE_E2E=PASS"' not in isolated_text
    assert "echo LIVE_E2E=PASS" not in isolated_text
    assert "ORACLE_MOCK_REACHABLE" in isolated_text
    # Positive live/review pass labels belong only to the separate live smoke.
    for line in isolated_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        assert "M4A_REVIEW_PASS" not in stripped
        assert "LIVE_E2E=PASS" not in stripped


def test_isolated_refuses_busy_or_shared_postgres(isolated_text: str) -> None:
    assert "port 5432 is in use; refuse existing/shared DB" in isolated_text
    assert "tmpfs" in isolated_text
    assert "127.0.0.1:5432:5432" in isolated_text


def test_isolated_mock_host_port_not_interpolated_into_python(isolated_text: str) -> None:
    # Must use a quoted heredoc + os.environ (no "${MOCK_HOST}" inside Python).
    assert "<<'PY'" in isolated_text
    assert 'host = "${MOCK_HOST}"' not in isolated_text
    assert 'port = int("${MOCK_PORT}")' not in isolated_text
    assert 'os.environ["DQA_M4A_ORACLE_MOCK_HOST"]' in isolated_text


def test_smoke_requires_explicit_live_allow_and_allowlisted_target(smoke_text: str) -> None:
    assert "DQA_M4A_ALLOW_LIVE_ORACLE_MOCK=1" in smoke_text
    assert 'ALLOWED_MOCK_HOST="demis-oracle-test"' in smoke_text
    assert 'ALLOWED_MOCK_PORT="1521"' in smoke_text
    assert 'ALLOWED_SOURCE="oracle_demis_mock"' in smoke_text
    assert 'ALLOWED_ENVIRONMENT="development"' in smoke_text
    assert "dev_headers" in smoke_text
    assert "<<'PY'" in smoke_text
    assert 'host = "${MOCK_HOST}"' not in smoke_text


def test_smoke_errors_do_not_echo_http_bodies(smoke_text: str) -> None:
    assert "body[:500]" not in smoke_text
    assert "exc.read().decode" not in smoke_text
    assert 'fail(f"{verb} {path} returned HTTP {exc.code}")' in smoke_text
    assert "_ = exc.read()" in smoke_text


def test_smoke_live_pass_label_is_distinct(smoke_text: str) -> None:
    assert "LIVE_E2E=PASS" in smoke_text
    assert "LIVE_E2E=RUNNING" in smoke_text
    assert "M4A_ORACLE_MOCK_BLOCKED" in smoke_text


def test_smoke_does_not_default_app_env_or_auth_provider(smoke_text: str) -> None:
    # Missing values must BLOCKED — never invent development/dev_headers.
    assert "${app_env:-development}" not in smoke_text
    assert "${auth_provider:-dev_headers}" not in smoke_text
    assert 'app_env:-development' not in smoke_text.replace(" ", "")
    assert "running backend APP_ENV is missing" in smoke_text
    assert "running backend DQA_AUTH_PROVIDER is missing" in smoke_text


def test_smoke_rejects_shell_env_overrides_as_environment_proof(smoke_text: str) -> None:
    assert "DQA_M4A_APP_ENV/DQA_M4A_AUTH_PROVIDER overrides are not accepted as environment proof" in smoke_text
    assert 'label=com.docker.compose.service=backend' in smoke_text
    assert "docker inspect" in smoke_text


def test_smoke_blocks_arbitrary_smoke_base_url(smoke_text: str) -> None:
    assert "DQA_SMOKE_BASE_URL must exactly match env-file LAN frontend URL" in smoke_text
    assert "derived_base_url=" in smoke_text
    assert 'dqa_env_value DQA_LAN_BIND_IP ""' in smoke_text
    assert 'dqa_env_value DQA_FRONTEND_PORT ""' in smoke_text
    assert "DQA_LAN_BIND_IP/DQA_FRONTEND_PORT missing from env file" in smoke_text
    # No silent 127.0.0.1/8080 defaults for the live smoke entrypoint.
    assert 'dqa_env_value DQA_LAN_BIND_IP 127.0.0.1' not in smoke_text
    assert 'dqa_env_value DQA_FRONTEND_PORT 8080' not in smoke_text


def test_smoke_oracle_preflight_runs_in_verified_backend(smoke_text: str) -> None:
    """Container-only DNS/secret checks; host environment cannot prove readiness."""
    assert 'docker exec -i "$backend_cid" python - <<\'PY\'' in smoke_text
    assert 'if ! docker exec -i "$backend_cid"' in smoke_text
    assert 'M4A_ORACLE_MOCK_BLOCKED: verified backend credential or Oracle Mock TCP preflight failed' in smoke_text
    assert 'socket.create_connection((mock_host, mock_port)' not in smoke_text
    assert 'def oracle_mock_ready()' not in smoke_text
    assert 'M4A_ORACLE_MOCK_REACHABLE: allowlisted mock TCP ok (verified backend)' in smoke_text


@pytest.mark.parametrize(
    ("secret_present", "tcp_ok", "expected_exit"),
    [(False, True, 2), (True, False, 3), (True, True, 0)],
)
def test_smoke_backend_preflight_fails_closed_without_secret_or_tcp(
    smoke_text: str,
    monkeypatch: pytest.MonkeyPatch,
    secret_present: bool,
    tcp_ok: bool,
    expected_exit: int,
) -> None:
    """Exercise the exact Python fed to docker exec, without Docker or Oracle."""
    import re
    import socket

    match = re.search(
        r'if ! docker exec -i "\$backend_cid" python - <<\'PY\' >/dev/null 2>&1\n(.*?)\nPY\nthen',
        smoke_text,
        re.DOTALL,
    )
    assert match is not None
    probe_code = match.group(1)

    if secret_present:
        monkeypatch.setenv("DEMIS_SECRET_ORACLE_PASSWORD", "synthetic-test-only")
    else:
        monkeypatch.delenv("DEMIS_SECRET_ORACLE_PASSWORD", raising=False)

    calls = []

    class _Socket:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    def fake_connect(address, timeout):
        calls.append((address, timeout))
        if not tcp_ok:
            raise OSError("synthetic TCP unavailable")
        return _Socket()

    monkeypatch.setattr(socket, "create_connection", fake_connect)

    try:
        exec(compile(probe_code, "<backend-oracle-mock-preflight>", "exec"), {})
    except SystemExit as exc:
        actual_exit = exc.code
    else:
        actual_exit = 0

    assert actual_exit == expected_exit
    assert calls == (
        [(("demis-oracle-test", 1521), 3)] if secret_present else []
    )
