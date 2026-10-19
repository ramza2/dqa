# DQA Frontend npm Dependency Audit — read-only triage

기준: `main@b0efc1b`, 2026-10-19. S-05-C2 서버 `npm ci` 경고: 총 4건 (moderate 1 / high 1 / critical 2). **개별 취약 패키지, 영향 범위 및 수정 가능성은 현장 audit 실행 전 미확정**.

## 목표와 경계

- `frontend/package-lock.json`을 기준으로 **전체 트리**와 `--omit=dev` **배포 의존성 트리**를 별도로 검사한다.
- `frontend/Dockerfile`은 Node 빌드 후 **Nginx static runtime**으로 배포한다. 따라서 개발 의존성만 취약하다고 해서 사용자 런타임 영향이라고 주장하지 않는다. 반대로 빌드 파이프라인 영향은 별도로 검토한다.
- Audit는 의존성 메타데이터를 현재 설정된 npm Registry로 전송하므로 승인된 사내/외부 Registry 정책에 맞는 환경에서만 실행한다.
- 스크립트는 **npm audit 조회만 수행**한다. `npm audit fix`, `--force`, `npm ci`, 파일 수정, 컨테이너/DB 접근, Credential 출력 없음. 임시 JSON/에러 출력은 trap으로 삭제한다.
- 패키지별 결과는 **보안 경고 목록**일 뿐 자동 수정·수용·실환경 검증을 의미하지 않는다.

## 2026-10-19 서버 감사 결과 — PASS (읽기 전용)

실행 HEAD: `63ff6d1` (분리된 `/tmp/dqa-frontend-audit-review` worktree).
- `bash -n` PASS, `DQA_FRONTEND_AUDIT_READONLY_DONE` 수신.
- `scope=all`: `moderate=1 high=1 critical=2 total=4`.
- `scope=production`: `moderate=0 high=0 critical=0 total=0`.
- 패키지: `@vitest/mocker` moderate, `source-map-js` high, `tinypool` critical, `vitest` critical.
- 현재 잠금: `vitest=3.2.7`, `@vitest/mocker=3.2.7`, `tinypool=1.1.1`, `source-map-js=1.2.1`.
- 원인 수정은 독립 PR #115에서 `vitest=4.1.12`, `source-map-js>=1.2.2` 및 잠금 파일 재생성/전체 테스트로 처리 중. **현재 PR #114는 수정 완료가 아니라 조회 스크립트 검증 완료**.

## 서버 조회

```bash
cd ~/dqa && git fetch origin && \
git worktree add --detach /tmp/dqa-frontend-audit-review \
  origin/chore/frontend-audit-readonly && \
bash /tmp/dqa-frontend-audit-review/scripts/dqa-frontend-audit-readonly.sh
```

예상 표식은 `DQA_FRONTEND_AUDIT_SCOPE scope=all`, `scope=production`, `DQA_FRONTEND_AUDIT_READONLY_DONE`. 보고된 패키지별 `severity`, `direct`, `range`, `fix`, `via`는 **실행 결과로만 확정**한다. 네트워크/권한 오류 또는 JSON 비정상은 `DQA_FRONTEND_AUDIT_ERROR`로 실패 처리한다.

## 보고 이후 처리

1. `production` 의존성 영향과 `all` 빌드/개발 도구 영향을 구분한다.
2. 실제 Advisory의 영향 조건 및 안전한 수정 범위를 확인한다.
3. 필요 최소 버전/lockfile 변경만 별도 PR에 반영한다. SemVer major의 경우 별도 호환성 검토.
4. 격리 작업 디렉터리에서 `npm ci`, Build, Lint, Vitest, 두 범위 재감사 수행.
5. 사용자 명시적 승인 전 Merge·실환경 Frontend 재배포 금지.
