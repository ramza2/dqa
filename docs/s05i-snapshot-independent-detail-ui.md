# S-05-I — Snapshot 상세 GET 독립 완료 처리 (읽기 전용)

> 2026-10-19 기준 `main@4afe786` (S-05-H 병합 이후). Frontend-only 성능·응답 지연 안전성 개선.
> 군·DBA 승인, 독립 Preflight, 실제 DEMIS/Oracle 접근 및 Catalog READY/Activation 상태를 변경하지 않는다.

## 공백 및 목표

Data Discovery → Snapshot History에서 Snapshot Revision의 **상세 Diff**, **Review Preview/Gates**, **변경 검토 저널**은 서로 독립적인 기존 `CATALOG_READ` GET API다.
기존 `Promise.allSettled([detail,preview,reviews])`는 세 API의 **모든 응답 완료 전까지 어떤 패널에도 결과를 반영하지 않아서**, 하나가 느리거나 응답하지 않으면 다른 정상 응답도 표시하지 못한다.

이 단계는 기존 세 GET의 검증·표시 정책은 유지하면서, 각 응답이 **독립적으로 완료·실패**하도록 바꾼다.

- 클릭 시 Diff·Preview·Review Journal을 각각 Loading 상태로 초기화하고 기존 세 GET을 병렬 발행한다.
- GET 성공 시 **해당 패널만** 기존 Source/Revision/Fingerprint/변경 합계/게이트·저널 계약을 검증해 상태 갱신.
- 한 GET이 실패하거나 오래 지연되어도 **나머지 두 패널은 즉시 표시**한다. 느린 패널은 개별 로딩 안내 유지.
- 상세 선택 시 발급한 `detailSeq` 토큰과 `sourceRef`를 세 응답·오류 처리 각각에서 확인.
  같은 Source에서 같은 Snapshot 재선택을 포함하여, 이전 클릭의 뒤늦은 성공·실패는 새 선택/상태에 영향을 주지 않는다.
- 기존 Source 입력 수정·페이지 이동·화면 해제 시 모든 구 응답 무효화 정책 유지.
- 검토 저널의 `ACKNOWLEDGED`, WARNING 후보는 독립 DBA Preflight·Catalog READY·활성화 증빙이 아니다.

## 변경 범위

- `frontend/src/components/SchemaSnapshotHistory.tsx`: 기존 `Promise.allSettled` 집계 배리어를 제거하고 세 GET의 성공·실패를 별도 처리. 기존 validation guard는 그대로 유지.
- `frontend/src/test/SchemaSnapshotHistory.test.tsx`: 느린 Preview, 느린/실패 Diff, 같은 Source·Snapshot 재선택 시 늦게 도착한 변조 응답 차단 3건.
- 이 문서.

추가 Backend Endpoint, DB/Alembic Migration, Oracle/Credential/Query Core, Catalog Import/Activation, Snapshot Capture/Review POST, 임상 Write/UI, 보안/승인 정책, Docker/서버 설정 변경 없음.

## 서버 Acceptance — PASS (2026-10-19)

- **검증 HEAD `711e6a3`**, 독립 detached `/tmp/dqa-s05i-review`, 기준 `main@4afe786`.
- `npm ci`: **PASS** (258 packages added / 259 packages audited, **0 vulnerabilities**). `whatwg-encoding` 및 ESLint deprecation 안내는 비차단 경고.
- `npm run build`: **PASS** — TypeScript와 Vite 6.4.3 production build, 65 modules transformed.
- `npm run lint`: **PASS**.
- `npm test -- --run`: **15 Test Files / 130 Tests PASS**. SchemaSnapshotHistory 21 tests 및 기존 Frontend 전체 회귀 확인.
- `git diff --check 4afe786 HEAD`: **PASS**, 최종 출력 **`DQA_S05I_REVIEW_PASS`** 확인.
- 본 결과 기록은 **문서만 변경하는 후속 커밋**으로, 검증한 Frontend 코드·테스트·의존성은 그대로 유지.
- GitHub Actions CI/운영 Docker 배포/실제 DEMIS 조회/군·DBA 독립 Preflight·G1/G5 및 외부 DEC-01/02/08/10 승인은 별도 검증 대상.
- **사용자 명시 승인 전 `main` 머지 및 운영 배포 금지**.

## 서버 Acceptance — 실행했던 Worktree 명령

기준 Frontend **15 files / 127 tests**, 신규 통합 3건 추가 후 **15 files / 130 tests PASS** 확인.

실제 운영 컨테이너, DEMIS/DB 및 기존 `~/dqa/frontend/node_modules`를 변경하지 않는 detached Worktree 검증:

```bash
cd ~/dqa && git fetch origin && \
git worktree add --detach /tmp/dqa-s05i-review \
  origin/feature/s05i-snapshot-independent-detail-load && \
(
  cd /tmp/dqa-s05i-review/frontend && \
  npm ci && \
  npm run build && \
  npm run lint && \
  npm test -- --run
) && \
git -C /tmp/dqa-s05i-review diff --check 4afe786 HEAD && \
echo DQA_S05I_REVIEW_PASS
```

- Build, Lint, Vitest, diff 검사와 최종 PASS 마커를 모두 확인했다.
- GitHub Actions CI, 운영 Docker 빌드·재배포, 실제 DEMIS/Oracle 및 외부 G1/G5·DEC-01/02/08/10 승인은 별도.
- 사용자 명시 승인 전 Draft→Ready 여부와 무관하게 `main` Squash Merge 또는 운영 배포 금지.
