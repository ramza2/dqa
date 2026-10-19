#!/usr/bin/env bash
# Inspect npm advisories for the locked DQA frontend dependency tree.
# Read-only: no npm install/fix, package edits, Docker or database calls.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FRONTEND="${ROOT}/frontend"
for tool in npm python3; do
  command -v "${tool}" >/dev/null 2>&1 || { echo "DQA_FRONTEND_AUDIT_ERROR: missing ${tool}" >&2; exit 2; }
done
[[ -f "${FRONTEND}/package-lock.json" ]] || {
  echo "DQA_FRONTEND_AUDIT_ERROR: missing package-lock.json" >&2
  exit 2
}

scratch="$(mktemp -d "${TMPDIR:-/tmp}/dqa-frontend-audit.XXXXXXXX")"
trap 'rm -rf -- "${scratch}"' EXIT

for scope in all production; do
  options=(--json --package-lock-only)
  if [[ "${scope}" == "production" ]]; then
    options+=(--omit=dev)
  else
    options+=(--include=dev)
  fi
  set +e
  (cd "${FRONTEND}" && npm audit "${options[@]}") >"${scratch}/${scope}.json" 2>"${scratch}/${scope}.stderr"
  status=$?
  set -e
  if (( status > 1 )); then
    echo "DQA_FRONTEND_AUDIT_ERROR: ${scope} npm audit failed (exit ${status}); check registry access" >&2
    exit 2
  fi
done

python3 - "${scratch}/all.json" "${scratch}/production.json" <<'PY'
import json
import sys
from pathlib import Path

for scope, path in zip(("all", "production"), sys.argv[1:]):
    try:
        audit = json.loads(Path(path).read_text(encoding="utf-8"))
        vulnerabilities = audit["vulnerabilities"]
        counters = audit["metadata"]["vulnerabilities"]
        if not isinstance(vulnerabilities, dict) or not isinstance(counters, dict):
            raise ValueError("invalid audit schema")
    except (ValueError, KeyError, TypeError, OSError) as exc:
        print(f"DQA_FRONTEND_AUDIT_ERROR: invalid {scope} audit report ({type(exc).__name__})", file=sys.stderr)
        sys.exit(2)

    counts = " ".join(f"{level}={int(counters.get(level, 0))}"
                      for level in ("info", "low", "moderate", "high", "critical", "total"))
    print(f"DQA_FRONTEND_AUDIT_SCOPE scope={scope} {counts}")
    for name, issue in sorted(vulnerabilities.items()):
        if not isinstance(issue, dict):
            print("DQA_FRONTEND_AUDIT_ERROR: invalid vulnerability entry", file=sys.stderr)
            sys.exit(2)
        fix = issue.get("fixAvailable", False)
        if isinstance(fix, dict):
            fix_text = f"target:{fix.get('name', '?')}@{fix.get('version', '?')};major:{fix.get('isSemVerMajor', '?')}"
        else:
            fix_text = str(bool(fix)).lower()
        via = issue.get("via", [])
        via_names = [v if isinstance(v, str) else v.get("name", "?")
                     for v in via if isinstance(v, (str, dict))]
        print(f"  {name}: severity={issue.get('severity', '?')} direct={str(issue.get('isDirect', False)).lower()} "
              f"range={issue.get('range', '?')} fix={fix_text} via={','.join(via_names[:8])}")

print("DQA_FRONTEND_AUDIT_READONLY_DONE")
PY
