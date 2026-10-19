# Frontend 개발·테스트 의존성 취약점 보완 — 2026-10-19

기준: `main@b0efc1b`. 참조: [PR #114 npm read-only audit](https://github.com/ramza2/dqa/pull/114).

## 서버에서 검증된 초기 문제

`DQA_FRONTEND_AUDIT_READONLY_DONE` 완료:
- `all`: moderate 1, high 1, critical 2 (총 4건).
- `production --omit=dev`: **0건**.
- Lockfile: `vitest@3.2.7`, `@vitest/mocker@3.2.7`, `tinypool@1.1.1`, `source-map-js@1.2.1`.
- 최종 frontend는 Nginx 정적 배포; 테스트/빌드 도구와 실제 프로덕션 의존성을 구분.

## 수정 의도

- `vitest`: 직접 개발 의존성을 `4.1.12`로 최소 메이저 이동 (3 → 4; npm 자동 제안인 5.0.5는 이번 범위 제외).
- `source-map-js`: npm `overrides`로 `^1.2.2` 하한 적용. 기존 1.2.1의 취약점 패치.
- npm upstream Vitest 4 요구 Node >=20, Vite >=6; 현재 Vite lock 6.4.3. 서버 Node 버전을 테스트에서 확인.
- **이 PR은 lockfile 미생성 상태의 준비 브랜치**에서 시작한다. 정상적인 `npm ci` 실행 전에 별도 worktree에서 `npm install --package-lock-only`로 lockfile을 재생성해 커밋해야 한다.
- 이 변경은 앱 기능, Backend, API, DB, Oracle/DEMIS, Runtime/Compose 배포에 영향을 주지 않는다.

## 단일 서버 수용 (안전한 별도 worktree, 미실행)

```bash
cd ~/dqa && git fetch origin && \
git worktree add --detach /tmp/dqa-frontend-secfix-review \
  origin/fix/frontend-devdep-security-20261019 && \
bash -euo pipefail <<'DQA_SECURITY_ACCEPT'
cd /tmp/dqa-frontend-secfix-review/frontend
node --version
npm install --package-lock-only --ignore-scripts --no-audit --no-fund
npm ci
npm run build
npm run lint
npm test -- --run
npm audit --audit-level=moderate
npm audit --omit=dev --audit-level=moderate
node - <<'JS'
const p = require("./package-lock.json").packages;
if (p["node_modules/vitest"]?.version !== "4.1.12") throw Error("Vitest version mismatch");
if (p["node_modules/@vitest/mocker"]?.version !== "4.1.12") throw Error("Mocker version mismatch");
const version = p["node_modules/source-map-js"]?.version || "";
if (Number(version.split(".")[0]) < 1 ||
    (version.startsWith("1.") && Number(version.split(".")[1]) < 2) ||
    (version.startsWith("1.2.") && Number(version.split(".")[2]) < 2)) {
  throw Error("source-map-js is not patched");
}
const pool = p["node_modules/tinypool"]?.version;
if (pool && Number(pool.split(".")[0]) < 2) throw Error("Old tinypool remains");
console.log("DQA_FRONTEND_PATCH_VERSIONS_OK", {vitest: p["node_modules/vitest"].version, sourceMap: version, tinypool: pool || "absent"});
JS
cd /tmp/dqa-frontend-secfix-review
git diff --check
test "$(git status --porcelain)" = " M frontend/package-lock.json"
git add frontend/package-lock.json
git commit -m "chore(frontend): lock patched test dependencies"
git push origin HEAD:refs/heads/fix/frontend-devdep-security-20261019
echo DQA_FRONTEND_SECURITY_REVIEW_PASS
DQA_SECURITY_ACCEPT
```

**위 명령은 사용자 실행을 전제로 제시**: npm registry에 대한 정상적 접속·개발 의존성 다운로드가 필요하다. 마지막 `push`는 모든 검사 성공 후에만 해당 **feature branch**로 커밋하며 main을 수정하거나 PR을 머지하지 않는다. `npm audit fix --force` 절대 사용 금지. 실제 DEMIS/Oracle/Postgres, 기존 컨테이너, 운영 서비스에 접근하지 않는다.

## 검증·승인

- 두 npm audit에서 각각 취약점 **0건**, Vitest 전체 suite와 Build/Lint 통과, 버전 확인, diff 검사 및 최종 `DQA_FRONTEND_SECURITY_REVIEW_PASS` 확인 전에는 완료 주장 금지.
- 실패 시 푸시 금지; 실행 로그를 검토해 동일 Draft PR에서만 최소 수정.
- 운영 서버 배포, 다른 패키지 광범위 갱신, GitHub `main` Merge는 별도 사용자 승인 후 진행.
