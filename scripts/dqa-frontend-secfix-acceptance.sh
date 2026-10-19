#!/usr/bin/env bash
# Isolated frontend dependency remediation acceptance.
# No production deploy, no DB access, no forced lockfile updates.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BRANCH="fix/frontend-devdep-security-20261019"
die() { printf 'DQA_FRONTEND_SECURITY_REFUSED: %s\n' "$*" >&2; exit 2; }

[[ "$ROOT" == "/tmp/dqa-frontend-secfix-review" ]] || die "run only from dedicated review worktree"
[[ -f "$ROOT/frontend/package.json" && -f "$ROOT/frontend/package-lock.json" ]] || die "frontend files missing"
[[ "$(git -C "$ROOT" branch --show-current)" == "" ]] || die "worktree must be detached"
[[ -z "$(git -C "$ROOT" status --porcelain)" ]] || die "worktree has uncommitted changes"
[[ "$(git -C "$ROOT" rev-parse HEAD)" == "$(git -C "$ROOT" rev-parse "origin/$BRANCH")" ]] ||
  die "review HEAD must match latest fetched origin/$BRANCH"
for cmd in node npm npx; do command -v "$cmd" >/dev/null || die "$cmd is required"; done

cd "$ROOT/frontend"
echo "DQA_FRONTEND_SECURITY_NODE $(node --version)"
echo "DQA_FRONTEND_SECURITY_SYSTEM_NPM $(npm --version)"

# npm 10 Arborist can crash on Vitest 4 peers (edgesOut). Scoped npm 11 only.
npx --yes npm@11.6.0 --version
npx --yes npm@11.6.0 install --package-lock-only --ignore-scripts --no-audit --no-fund

# The default npm ci must still pass for the current frontend/Dockerfile.
npm ci
npm run build
npm run lint
npm test -- --run
npx --yes npm@11.6.0 audit --audit-level=moderate
npx --yes npm@11.6.0 audit --omit=dev --audit-level=moderate

node <<'JS'
const p = require("./package-lock.json").packages;
function version(name) { return p["node_modules/" + name]?.version; }
if (version("vitest") !== "4.1.12" || version("@vitest/mocker") !== "4.1.12") {
  throw Error("Vitest/mocker version mismatch");
}
const patched = version("source-map-js");
if (!patched || !/^\d+\.\d+\.\d+$/.test(patched)) throw Error("Invalid source-map-js");
const [major, minor, patch] = patched.split(".").map(Number);
if (major < 1 || (major === 1 && (minor < 2 || (minor === 2 && patch < 2)))) {
  throw Error("Vulnerable source-map-js remains");
}
const pool = version("tinypool");
if (pool && /^\d+\.\d+\.\d+$/.test(pool)) {
  const [maj, min, pat] = pool.split(".").map(Number);
  if (maj < 2 || (maj === 2 && (min < 1 || (min === 1 && pat <= 1)))) {
    throw Error("Vulnerable tinypool remains");
  }
}
console.log("DQA_FRONTEND_PATCH_VERSIONS_OK", {vitest: version("vitest"), sourceMap: patched, tinypool: pool || "absent"});
JS

cd "$ROOT"
git diff --check
[[ "$(git status --porcelain)" == " M frontend/package-lock.json" ]] ||
  die "only frontend/package-lock.json may be modified"
git add -- frontend/package-lock.json
git commit -m "chore(frontend): lock patched test dependencies"
git push origin "HEAD:refs/heads/$BRANCH"
echo "DQA_FRONTEND_SECURITY_REVIEW_PASS"
