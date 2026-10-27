#!/usr/bin/env bash
# M2-1C: READ-ONLY inspection of the isolated synthetic Oracle Free Mock.
# No user/grant/schema/DQA changes. Always invoke via 'bash SCRIPT', not source.
set -euo pipefail
set +x
die() { echo "M2_1C_BLOCKED: $1" >&2; exit 1; }

container=demis-oracle-test
secret_file="$HOME/.config/dqa/m2-1b-mock-inspector.env"
command -v docker >/dev/null || die "Docker not found"
command -v stat >/dev/null || die "stat not found"
image="$(docker inspect -f '{{.Config.Image}}' "$container" 2>/dev/null)" || die "Mock unavailable"
health="$(docker inspect -f '{{.State.Health.Status}}' "$container" 2>/dev/null)" || die "Mock health unavailable"
[[ "$image" == "container-registry.oracle.com/database/free:latest-lite" ]] || die "Mock image mismatch"
[[ "$health" == healthy ]] || die "Mock not healthy"
[[ -f "$secret_file" && ! -L "$secret_file" ]] || die "Private secret file missing"
[[ "$(stat -c %a "$secret_file")" == 600 ]] || die "Secret file must be chmod 600"
[[ "$(stat -c %u "$secret_file")" == "$(id -u)" ]] || die "Secret ownership mismatch"
secret="$(cat "$secret_file")" || die "Cannot read secret file"
[[ "$secret" =~ ^DEMIS_INSPECT_SECRET_MOCK=[0-9a-f]{48}$ ]] || die "Unexpected secret format"
pw="$(printf '%s' "$secret" | cut -d= -f2)"
unset secret
echo "M2_1C_MOCK_VERIFIED"

echo "===== MOCK ACCOUNT AND GRANT BASELINE ====="
if ! baseline_output="$(docker exec -i "$container" bash -lc 'sqlplus -s / as sysdba' <<'SQL'
WHENEVER SQLERROR EXIT FAILURE
WHENEVER OSERROR EXIT FAILURE
SET FEEDBACK OFF
SET ECHO OFF
SET VERIFY OFF
SET HEADING OFF
ALTER SESSION SET CONTAINER=FREEPDB1;
-- Switching PDB can reset DBMS_OUTPUT; enable AFTER ALTER SESSION.
SET SERVEROUTPUT ON
DECLARE
 t NUMBER; c NUMBER; g NUMBER; u NUMBER; s NUMBER; x NUMBER; r NUMBER; o NUMBER;
BEGIN
 IF SYS_CONTEXT('USERENV','DB_NAME') <> 'FREEPDB1'
    OR SYS_CONTEXT('USERENV','CON_NAME') <> 'FREEPDB1'
    OR SYS_CONTEXT('USERENV','CDB_NAME') <> 'FREE' THEN
  RAISE_APPLICATION_ERROR(-20041,'IDENTITY_NOT_SYNTHETIC');
 END IF;
 SELECT COUNT(*) INTO t FROM DBA_TABLES WHERE OWNER='DEMIS_OWNER';
 SELECT COUNT(*) INTO c FROM DBA_TAB_COLUMNS WHERE OWNER='DEMIS_OWNER';
 SELECT COUNT(*) INTO g FROM DBA_TAB_PRIVS
 WHERE OWNER='DEMIS_OWNER' AND GRANTEE='DEMIS_RO' AND PRIVILEGE='SELECT';
 SELECT COUNT(*) INTO u FROM DBA_USERS
 WHERE USERNAME='DEMIS_INSPECT_RO' AND ACCOUNT_STATUS='OPEN';
 SELECT COUNT(*) INTO s FROM DBA_SYS_PRIVS
 WHERE GRANTEE='DEMIS_INSPECT_RO' AND PRIVILEGE='CREATE SESSION';
 SELECT COUNT(*) INTO x FROM DBA_SYS_PRIVS
 WHERE GRANTEE='DEMIS_INSPECT_RO' AND PRIVILEGE<>'CREATE SESSION';
 SELECT COUNT(*) INTO r FROM DBA_ROLE_PRIVS WHERE GRANTEE='DEMIS_INSPECT_RO';
 SELECT COUNT(*) INTO o FROM DBA_TAB_PRIVS
 WHERE GRANTEE='DEMIS_INSPECT_RO' AND PRIVILEGE<>'REFERENCES';
 IF t<>25 OR c<>206 OR g<>25 OR u<>1 OR s<>1 OR x<>0 OR r<>0 OR o<>0 THEN
  RAISE_APPLICATION_ERROR(-20042,'UNEXPECTED_MOCK_GRANTS');
 END IF;
 DBMS_OUTPUT.PUT_LINE('M2_1C_DBA_BASELINE_PASS');
END;
/
EXIT;
SQL
)"; then
 die "Mock identity/schema/privileges failed"
fi
if ! grep -Fxq 'M2_1C_DBA_BASELINE_PASS' <<< "$baseline_output"; then
  die "DBA baseline success marker missing (DBMS_OUTPUT suppressed or block not executed)"
fi
printf '%s\n' 'M2_1C_DBA_BASELINE_PASS'
unset baseline_output

echo "===== INSPECTOR READ-ONLY METADATA ====="
if ! inspector_output="$(docker exec -i "$container" bash -lc 'sqlplus -s -L /nolog' <<SQL
WHENEVER SQLERROR EXIT FAILURE
WHENEVER OSERROR EXIT FAILURE
SET FEEDBACK OFF
SET ECHO OFF
SET VERIFY OFF
SET HEADING OFF
CONNECT DEMIS_INSPECT_RO/"$pw"@//127.0.0.1:1521/FREEPDB1
SET SERVEROUTPUT ON
SET TRANSACTION READ ONLY;
DECLARE
 t NUMBER; c NUMBER; f NUMBER; i NUMBER; unused_count NUMBER;
BEGIN
 IF SYS_CONTEXT('USERENV','SESSION_USER') <> 'DEMIS_INSPECT_RO'
    OR SYS_CONTEXT('USERENV','CON_NAME') <> 'FREEPDB1' THEN
  RAISE_APPLICATION_ERROR(-20043,'UNEXPECTED_SESSION_USER');
 END IF;
 SELECT COUNT(*) INTO t FROM ALL_TABLES WHERE OWNER='DEMIS_OWNER';
 SELECT COUNT(*) INTO c FROM ALL_TAB_COLUMNS WHERE OWNER='DEMIS_OWNER';
 SELECT COUNT(*) INTO f FROM ALL_CONSTRAINTS
 WHERE OWNER='DEMIS_OWNER' AND CONSTRAINT_TYPE='R';
 SELECT COUNT(*) INTO i FROM ALL_INDEXES WHERE OWNER='DEMIS_OWNER';
 DBMS_OUTPUT.PUT_LINE('VISIBLE_TABLES='||t);
 DBMS_OUTPUT.PUT_LINE('VISIBLE_COLUMNS='||c);
 DBMS_OUTPUT.PUT_LINE('VISIBLE_FKS='||f);
 DBMS_OUTPUT.PUT_LINE('VISIBLE_INDEXES='||i);
 BEGIN
  -- Privilege/parse test only. WHERE 1=0 never retrieves a business row.
  EXECUTE IMMEDIATE
   'SELECT COUNT(*) FROM DEMIS_OWNER.TB_PT_MST WHERE 1=0' INTO unused_count;
  RAISE_APPLICATION_ERROR(-20044,'BUSINESS_ROW_READ_NOT_DENIED');
 EXCEPTION
  WHEN OTHERS THEN
   IF SQLCODE <> -942 THEN RAISE; END IF;
 END;
 DBMS_OUTPUT.PUT_LINE('M2_1C_BUSINESS_ROW_SELECT_DENIED');
 IF t=25 AND c=206 AND f>0 AND i>0 THEN
  DBMS_OUTPUT.PUT_LINE('M2_1C_METADATA_READY');
 ELSE
  DBMS_OUTPUT.PUT_LINE('M2_1C_METADATA_INCOMPLETE');
 END IF;
END;
/
EXIT;
SQL
)"; then
 unset pw
 die "Inspector login/metadata/row-denial verification failed"
fi
unset pw
if ! grep -Fxq 'M2_1C_BUSINESS_ROW_SELECT_DENIED' <<< "$inspector_output"; then
 die "business row SELECT denial proof missing"
fi
if ! grep -Eq '^M2_1C_METADATA_(READY|INCOMPLETE)
 <<< "$inspector_output"; then
 die "metadata result marker missing"
fi
if grep -q '^M2_1C_METADATA_READY
 <<< "$inspector_output" &&
   grep -q '^M2_1C_METADATA_INCOMPLETE
 <<< "$inspector_output"; then
 die "contradictory metadata results"
fi
# Whitelist only non-sensitive counters and result tokens for console output.
grep -E '^(VISIBLE_(TABLES|COLUMNS|FKS|INDEXES)=[0-9]+|M2_1C_BUSINESS_ROW_SELECT_DENIED|M2_1C_METADATA_(READY|INCOMPLETE))
 <<< "$inspector_output"
unset inspector_output
echo "M2_1C_READ_ONLY_DIAGNOSTIC_COMPLETED"
