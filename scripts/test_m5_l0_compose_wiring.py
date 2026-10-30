#!/usr/bin/env python3
"""Verify M5-L0 probe flags are development-only in resolved on-prem Compose.

Uses synthetic values, reads no operator .env.onprem and starts no containers.
Requires Docker Compose v2. No network requests are made.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "docker-compose.onprem.yml"
DEV = ROOT / "docker-compose.onprem.dev.yml"
EXAMPLE = ROOT / ".env.onprem.example"
PROBE_FLAG = "DQA_DEV_LLM_CONNECTION_TEST_ENABLED"
PROBE_PIN = "DQA_DEV_LLM_CONNECTION_TEST_ALLOWED_BASE_URL"
PINNED_URL = "https://llm.example.invalid/v1"


def resolved(*, dev: bool, enabled: bool) -> dict:
    """Render Compose only; all credentials are replaced with safe fixture values."""
    env = os.environ.copy()
    env.update(
        DQA_DB_PASSWORD="m5-synthetic-test-only",
        DQA_LAN_BIND_IP="127.0.0.1",
        DQA_FRONTEND_PORT="18082",
        DQA_DEV_FRONTEND_ROLES="query_operator",
        LLM_BASE_URL=PINNED_URL,
        LLM_MODEL="synthetic-model",
        LLM_API_KEY="",
        EMBEDDING_API_KEY="",
        DQA_DEV_LLM_CONNECTION_TEST_ENABLED="true" if enabled else "false",
        DQA_DEV_LLM_CONNECTION_TEST_ALLOWED_BASE_URL=PINNED_URL if enabled else "",
    )
    command = ["docker", "compose", "-p", "dqa-m5-wiring-check", "-f", str(MAIN)]
    if dev:
        command += ["-f", str(DEV)]
    command += ["--env-file", str(EXAMPLE), "config", "--format", "json"]
    result = subprocess.run(
        command, env=env, cwd=ROOT, text=True, capture_output=True, check=False
    )
    if result.returncode != 0:
        # Do not echo Compose output: environment interpolation may include secrets.
        raise RuntimeError("Docker Compose configuration validation failed")
    return json.loads(result.stdout)


def main() -> None:
    prod = resolved(dev=False, enabled=True)
    prod_backend = prod["services"]["backend"]["environment"]
    assert prod_backend["APP_ENV"] == "production"
    assert prod_backend["DQA_AUTH_PROVIDER"] == "disabled"
    assert PROBE_FLAG not in prod_backend
    assert PROBE_PIN not in prod_backend

    dev_off = resolved(dev=True, enabled=False)
    dev_off_backend = dev_off["services"]["backend"]["environment"]
    assert dev_off_backend["APP_ENV"] == "development"
    assert dev_off_backend["DQA_AUTH_PROVIDER"] == "dev_headers"
    assert str(dev_off_backend[PROBE_FLAG]).lower() == "false"
    assert not dev_off_backend[PROBE_PIN]

    dev_on = resolved(dev=True, enabled=True)
    dev_backend = dev_on["services"]["backend"]["environment"]
    assert str(dev_backend[PROBE_FLAG]).lower() == "true"
    assert dev_backend[PROBE_PIN] == PINNED_URL
    assert dev_backend["LLM_BASE_URL"] == PINNED_URL
    assert dev_on["services"]["frontend"]["environment"]["VITE_DQA_DEV_ROLES"] == "query_operator"
    assert "ports" not in dev_on["services"]["backend"]
    assert "ports" not in dev_on["services"]["dqa-db"]
    print("DQA_M5_L0_ONPREM_DEV_WIRING_PASS")


if __name__ == "__main__":
    main()
