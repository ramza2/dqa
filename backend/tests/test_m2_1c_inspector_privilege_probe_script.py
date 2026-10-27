"""M2-1C: offline-only script safety checks; no Oracle or PG access."""
from pathlib import Path
import os
import subprocess
import stat

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/dqa-m2-1c-inspector-privilege-check.sh"


def test_bash_parses():
    done = subprocess.run(["bash", "-n", str(SCRIPT)], text=True, capture_output=True)
    assert done.returncode == 0, done.stderr


def test_synthetic_fixture_and_no_mutations():
    code = SCRIPT.read_text()
    assert "container=demis-oracle-test" in code
    assert "container-registry.oracle.com/database/free:latest-lite" in code
    assert "IDENTITY_NOT_SYNTHETIC" in code
    assert "t<>25 OR c<>206 OR g<>25" in code
    assert "CREATE USER DEMIS_INSPECT_RO" not in code
    assert "GRANT REFERENCES ON " not in code
    assert "GRANT SELECT ON " not in code
    assert "DROP USER " not in code
    assert "docker compose up" not in code


def test_privilege_separation_and_zero_row_protection():
    code = SCRIPT.read_text()
    assert "x<>0 OR r<>0 OR o<>0" in code
    assert "SET TRANSACTION READ ONLY;" in code
    assert "ALL_TABLES" in code and "ALL_TAB_COLUMNS" in code
    assert "ALL_CONSTRAINTS" in code and "ALL_INDEXES" in code
    assert "WHERE 1=0" in code and "BUSINESS_ROW_READ_NOT_DENIED" in code
    assert "M2_1C_METADATA_INCOMPLETE" in code
    assert "M2_1C_METADATA_READY" in code


def test_secret_file_is_checked_and_password_is_not_logged():
    code = SCRIPT.read_text()
    assert "set +x" in code
    assert 'stat -c %a "$secret_file"' in code
    assert 'stat -c %u "$secret_file"' in code
    assert "sqlplus -s -L /nolog" in code
    assert 'CONNECT DEMIS_INSPECT_RO/"$pw"@' in code
    assert 'echo "$pw"' not in code


def test_both_sqlplus_proof_markers_required():
    code = SCRIPT.read_text()
    assert "grep -Fxq 'M2_1C_DBA_BASELINE_PASS'" in code
    assert "grep -Fxq 'M2_1C_BUSINESS_ROW_SELECT_DENIED'" in code
    assert "grep -Eq '^M2_1C_METADATA_(READY|INCOMPLETE)$'" in code
    assert "DBA baseline success marker missing" in code
    assert "business row SELECT denial proof missing" in code
    # On PDB switch, DBMS_OUTPUT needs to be explicitly enabled afterward.
    assert code.index("SET SERVEROUTPUT ON") > code.index("ALTER SESSION SET CONTAINER=FREEPDB1;")
    assert "grep -E '^(VISIBLE_(TABLES|COLUMNS|FKS|INDEXES)" in code


@pytest.mark.parametrize("mode,should_pass,reason", [
    ("silent_success", False, "DBA baseline success marker missing"),
    ("missing_denial", False, "business row SELECT denial proof missing"),
    ("valid_incomplete", True, "M2_1C_METADATA_INCOMPLETE"),
])
def test_false_success_never_masquerades_as_verified(tmp_path, mode, should_pass, reason):
    # Fake Docker executable: no network, Oracle or live containers are used.
    home = tmp_path / "home"
    secrets = home / ".config" / "dqa"
    secrets.mkdir(parents=True)
    secret_file = secrets / "m2-1b-mock-inspector.env"
    secret_file.write_text("DEMIS_INSPECT_SECRET_MOCK=" + "b" * 48 + "\n")
    secret_file.chmod(stat.S_IRUSR | stat.S_IWUSR)
    fakebin = tmp_path / "bin"
    fakebin.mkdir()
    fake_docker = fakebin / "docker"
    fake_docker.write_text("""#!/bin/bash
set -e
if [[ "$1" == "inspect" ]]; then
  if [[ "$*" == *".Config.Image"* ]]; then
    echo 'container-registry.oracle.com/database/free:latest-lite'
  else
    echo healthy
  fi
elif [[ "$1" == "exec" ]]; then
  cat >/dev/null
  if [[ "$*" == *"sqlplus -s / as sysdba"* ]]; then
    if [[ "$MOCK_PROOF_MODE" != "silent_success" ]]; then
      echo 'M2_1C_DBA_BASELINE_PASS'
    fi
  else
    printf 'VISIBLE_TABLES=0\\nVISIBLE_COLUMNS=0\\nVISIBLE_FKS=0\\nVISIBLE_INDEXES=0\\n'
    if [[ "$MOCK_PROOF_MODE" != "missing_denial" ]]; then
      echo 'M2_1C_BUSINESS_ROW_SELECT_DENIED'
    fi
    echo 'M2_1C_METADATA_INCOMPLETE'
  fi
else
  exit 2
fi
""")
    fake_docker.chmod(0o755)
    env = {**os.environ, "HOME": str(home),
           "PATH": str(fakebin) + os.pathsep + os.environ["PATH"],
           "MOCK_PROOF_MODE": mode}
    result = subprocess.run(
        ["bash", str(SCRIPT)], env=env, text=True, capture_output=True, timeout=10,
    )
    assert (result.returncode == 0) is should_pass, (result.stdout, result.stderr)
    combined = result.stdout + result.stderr
    assert reason in combined
    assert "b" * 48 not in combined
    if not should_pass:
        assert "M2_1C_READ_ONLY_DIAGNOSTIC_COMPLETED" not in combined
