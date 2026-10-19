# S-05-H — Snapshot History 목록 응답 무결성 검증 (GET-only)

> 2026-10-19, 기준 `main@c6fe161` (S-05-G 머지 후).
> Frontend 조회 화면의 **계약 검증·안전한 장애 격리**에 국한한다.
> 군/DBA 독립 Preflight, READY·Catalog Activation·실 DEMIS 연결은 승인되지 않았으며 이 단계의 대상이 아니다.

## 목표 및 기존 공백

현재 Data Discovery → Snapshot History는
`GET /api/v1/schema-inspector/snapshots?source_name=...&offset=...&limit=50`
결과에 대해 `rows.every(row => row.source_name === requested)`만 검사한다.
형식이 잘못된 JSON, null 행, 중복/역순 Revision, 부정확한 Fingerprint,
비정상 Diff 상태/건수는 목록과 후속 상세 조회의 상태 혼선을 초래할 수 있다.

기존 API를 바꾸지 않고 **리스트가 안전한 SnapshotSummary[]인지** 런타임에서 검증한다.

- 응답이 배열인지, 최대 50건인지, 행별 Source가 요청과 일치하는지 확인.
- 각 Revision ID는 양의 Safe Integer; `previous_revision_id`는 null 또는 현재 ID 미만의 양의 ID.
- 정상 Source-scoped, 최신 ID 내림차순 목록은 동일 Source의 연속 행이 서로 predecessor로 연결되어야 한다.
  전역 ID에는 다른 Source의 Snapshot이 섞여 **숫자 자체가 연속될 필요는 없다**.
  마지막 행의 predecessor는 다음 페이지에 있을 수 있어 검사를 생략한다.
- Fingerprint는 SHA-256 소문자 64자리; Database/Schema/DB Type/Actor/캡처 일시/객체별 Count는 안전한 원시 형식만 허용.
- `NO_BASELINE`은 이전 Revision 및 `total_changes` 모두 null. `COMPARED`는 이전 Revision과 0 이상의 정수형 변경 건수가 필수.
- 실패 시 **조회 목록 전체를 fail-closed**하고 일반화된 오류만 표시한다. 해당 Source의 Catalog/Detail 패널을 표시하지 않는다.
- 명시적으로 다시 조회했을 때는 새로운 정상 응답을 표시할 수 있다. 기존 Source 전환·늦은 응답 방지 시퀀스는 유지한다.

## 파일 및 검증 범위

- `frontend/src/utils/snapshotHistoryList.ts` — 조회 전용 계약 검증.
- `frontend/src/components/SchemaSnapshotHistory.tsx` — 요청 Source 기준 검증 후에만 목록 상태 반영.
- `frontend/src/test/SnapshotHistoryList.test.ts` — 형식/범위/정렬/Source/Predecessor/상태 검증 7건.
- `frontend/src/test/SchemaSnapshotHistory.test.tsx` — 비정상 배열·연결 오류·명시 재조회 복구 3건.
- 이 문서.

Backend route/DB/DDL/Oracle Adapter/권한·Credential·Query Core/LLM·MCP/FHIR 및 Docker 운영 구성 변경 없음.
Snapshot Capture/Review POST, Catalog Import/Activate, 외부 Approval, 임상 환자 조회·쓰기 경로를 추가하지 않는다.

## 서버 Acceptance — 1차 실패 및 재검증 대기 (2026-10-19)

- 최초 검증 코드 HEAD `ddd0a4e`, 격리된 `/tmp/dqa-s05h-review` Worktree.
- `npm ci`: **PASS**, 258개 패키지 설치, 259개 감사 기준 **0 vulnerabilities**.
- `npm run build`의 TypeScript `TS2698` 1건으로 중단 (`SnapshotHistoryList.test.ts:59`): 테스트의 `patch`를 `unknown`으로 선언하고 `...patch`로 전개한 타입 오류.
- 객체 패치 테스트 배열을 `Record<string, unknown>[]`로 좁혀 실제 payload의 `unknown` 검증 계약은 유지하고 테스트 컴파일 오류만 수정.
- 기존 Source 불일치 회귀 테스트의 오류 메시지 단언도 새 공통 fail-closed 메시지(`응답 정합성`)와 정합화.
- Lint, Vitest, Git whitespace 최종 `DQA_S05H_REVIEW_PASS`는 **아직 미확인**. 검증 전 PASS/머지/배포 주장 금지.

## 재검증 명령 — 기존 Worktree 사용

```bash
cd ~/dqa && git fetch origin && \
git -C /tmp/dqa-s05h-review switch --detach \
  origin/feature/s05h-snapshot-list-contract-guards && \
(
  cd /tmp/dqa-s05h-review/frontend && \
  npm run build && npm run lint && npm test -- --run
) && \
git -C /tmp/dqa-s05h-review diff --check c6fe161 HEAD && \
echo DQA_S05H_REVIEW_PASS
```

변경은 TypeScript 테스트 코드와 문서에만 국한된다. 1차 `npm ci` 완료 이후 의존성 정의/lockfile 변경이 없으므로 재설치 없이 수용 검사를 재실행한다.

## 서버 Acceptance — 원래 명령 (1차 빌드 실패)


기존 Frontend 14 files/117 tests에 단위 7건, 화면 통합 3건 추가.
**예상 15 files/127 tests**. 별도 Detached Worktree에서만 실행:

```bash
cd ~/dqa && git fetch origin && \
git worktree add --detach /tmp/dqa-s05h-review \
  origin/feature/s05h-snapshot-list-contract-guards && \
(
  cd /tmp/dqa-s05h-review/frontend && \
  npm ci && \
  npm run build && \
  npm run lint && \
  npm test -- --run
) && \
git -C /tmp/dqa-s05h-review diff --check c6fe161 HEAD && \
echo DQA_S05H_REVIEW_PASS
```

- `npm ci`, TypeScript+Vite Build, ESLint, 전체 Vitest, Git whitespace 검사를 모두 통과하고
  `DQA_S05H_REVIEW_PASS`가 출력돼야 수용.
- GitHub Actions CI, 실제 운영 Docker 배포, Oracle/DEMIS 실측, 군·DBA 승인 및 G1/G5 인수는 **별개**.
- 사용자 명시 승인 전에는 Draft→Ready 판단과 관계없이 `main` Merge 및 운영 배포 금지.
