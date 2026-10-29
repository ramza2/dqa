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
