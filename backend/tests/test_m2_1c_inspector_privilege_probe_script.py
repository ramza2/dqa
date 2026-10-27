"""M2-1C: offline-only script safety checks; no Oracle or PG access."""
from pathlib import Path
import subprocess

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
