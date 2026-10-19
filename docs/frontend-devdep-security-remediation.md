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
- **이 PR은 lockfile 미생성 상태의 준비 브랜치**에서 시작한다. 별도 worktree에서 npm 11.6.0으로 lockfile을 재생성해 `fd17aa3`으로 커밋·푸시했다.
- 이 변경은 앱 기능, Backend, API, DB, Oracle/DEMIS, Runtime/Compose 배포에 영향을 주지 않는다.

## 실패 분석 (2026-10-19)

Node v22.14.0 서버에서 1차 `npm install --package-lock-only`가 `Cannot read properties of null (reading 'edgesOut')`로 중단되었다. 따라서 npm ci/Build/Lint/Vitest/Audit 및 패치 lockfile push는 **미실행**이다. 이 오류는 npm 10 Arborist의 Vitest 4 peer dependency 재귀 해석 버그와 일치한다. npm/cli #9787, #8261 및 fix #8448 참고. npm 11.6.0 이상에는 관련 수정 포함.

보완: 운영 npm/Node 변경 없이 `npx --yes npm@11.6.0`으로 **잠금 파일 생성과 감사만** 실행하고, 기존 `npm ci`도 반드시 검사한다. 구버전 npm ci가 실패한다면 현재 Dockerfile/CI 호환성이 확보되지 않은 것이므로, **커밋/푸시 전에 중단**한다. `--legacy-peer-deps` 및 `--force`로 우회하지 않는다.

## 서버 수용 재시도 (2026-10-19 실행 PASS)

PR 브랜치에 `scripts/dqa-frontend-secfix-acceptance.sh`를 추가했다. 기존 `/tmp/dqa-frontend-secfix-review` worktree를 **재사용**한다.

```bash
cd ~/dqa && git fetch origin && \
git -C /tmp/dqa-frontend-secfix-review switch --detach \
  origin/fix/frontend-devdep-security-20261019 && \
bash -n /tmp/dqa-frontend-secfix-review/scripts/dqa-frontend-secfix-acceptance.sh && \
bash /tmp/dqa-frontend-secfix-review/scripts/dqa-frontend-secfix-acceptance.sh
```

스크립트는 다음을 검증한다.
- 대상 worktree가 정확히 분리된 HEAD이며, 원격 PR HEAD와 일치하고 수정 파일이 없는 상태인지 확인.
- npm 11.6.0을 임시 npx 실행 (전역 npm 설치·업그레이드 없음), `package-lock.json`만 생성.
- **기본 npm의** `npm ci`, build, lint, **전체** Vitest 테스트.
- npm 11로 전체/production `audit --audit-level=moderate`를 각각 확인. 취약점 0건 필수.
- `vitest/@vitest/mocker=4.1.12`, `source-map-js>=1.2.2`, 취약 `tinypool` 잔존 여부를 잠금 파일에서 검사.
- 검증 통과 및 `frontend/package-lock.json` 단일 파일 변경 확인 후에만 그 파일을 **PR 기능 브랜치로** commit/push; main은 변경하지 않음.

**2026-10-19 서버 실행 결과 (검증 코드 `f462a9b`, 생성된 잠금 파일 푸시 `fd17aa3`)**
- 서버 Node `v22.14.0`, 기본 npm `10.9.2`, 임시 npm `11.6.0`.
- npm 11 lockfile generation PASS; **기본 npm 10.9.2 `npm ci` PASS** (258 packages; 0 vulnerabilities).
- `npm run build` PASS (Vite 6.4.3), `npm run lint` PASS.
- 전체 Vitest `10 files / 86 tests passed` (`vitest@4.1.12`).
- 두 npm audit 모두 `found 0 vulnerabilities` (전체 + `--omit=dev`).
- 잠금 검증 `DQA_FRONTEND_PATCH_VERSIONS_OK`: `vitest=4.1.12`, `source-map-js=1.2.2`, `tinypool=absent`.
- `git diff --check` PASS; **frontend/package-lock.json 단일 변경** 후 브랜치에 `fd17aa3` 커밋·푸시 완료.
- 최종 `DQA_FRONTEND_SECURITY_REVIEW_PASS` 수신.
- 검증 이후 본 문서 내용 수정만 별도 commit. GitHub Actions CI 실행 및 실제 운영 Docker 이미지 빌드/배포/런타임 검증은 수행하지 않음.

참고: 수용 스크립트는 처음 잠금 파일을 생성·푸시하는 **1회용 검증 절차**이다. 잠금 파일이 이미 반영된 현재 PR HEAD에서 같은 스크립트를 다시 실행하면 단일 파일 변경 확인이 실패하므로, 재검증 시에는 lockfile 생성/커밋 단계 없이 `npm ci`/빌드/린트/테스트/audit만 별도로 실행한다.

## 검증·승인

- 두 npm audit에서 각각 취약점 **0건**, Vitest 전체 suite와 Build/Lint 통과, 버전 확인, diff 검사 및 최종 `DQA_FRONTEND_SECURITY_REVIEW_PASS` 확인 전에는 완료 주장 금지.
- 실패 시 푸시 금지; 실행 로그를 검토해 동일 Draft PR에서만 최소 수정.
- 운영 서버 배포, 다른 패키지 광범위 갱신, GitHub `main` Merge는 별도 사용자 승인 후 진행.
