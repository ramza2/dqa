# S-05-K — Snapshot 상세 GET 응답 시간 제한 및 개별 재조회 (조회 전용)

> 2026-10-19, 기준 `main@93ca45a` (S-05-J 병합 및 서버 소스 동기화 완료).
> 실제 DEMIS/Oracle 연결·군 승인·독립 DBA Preflight·READY/Activation을 구현하거나 우회하지 않는 Frontend 안전성 개선.

## 현황 및 목표

S-05-I의 GET 3개 독립 완료와 S-05-J의 오류 패널 개별 재조회로,
Diff/Review Preview/Review Journal 중 하나만 오류라면 나머지는 정상 표시·유지할 수 있다.
단, GET이 응답하지 않고 계속 대기하면 해당 패널의 상태는 `loading`으로 남아
S-05-J의 **오류 상태에서만 표시되는 재조회 버튼을 사용할 수 없다**.

이 작업은 **Snapshot 상세 조회 3개 GET에만 15초 Frontend deadline**을 적용한다.

- 기존 `apiGet` 및 각 Snapshot API가 지원하는 `RequestInit.signal`을 활용해 `AbortController`를 연결한다.
- 15초 안에 정상 완료/실패하면 deadline timer를 정리하고 종전 정합성·HTTP 오류 정책을 그대로 적용.
- 15초 내 응답하지 않으면 `SnapshotPanelTimeoutError`로 실패시키고 해당 fetch에 abort를 요청한다.
  fetch mock이나 비정상 구현체가 abort를 무시해도 `Promise.race`에서 **deadline 결과를 우선 적용**한다.
  abort는 브라우저 측 요청 중단이며 서버 작업 종료를 보장하지 않는다.
- 오류 메시지 `Snapshot 상세 조회 응답 시간이 초과됐습니다. 해당 항목을 다시 조회하세요.`는 해당 패널에만 보인다.
  기존 S-05-J의 Diff/Preview/Journal 오류별 `다시 조회` 버튼으로 **해당 GET 하나만** 다시 시도한다.
- 이미 표시된 다른 두 패널, Source/Revision 선택 및 별도 Catalog 이력은 변경하지 않는다.
  timeout 이후 늦게 돌아온 이전 GET 응답·오류는 표시하지 않는다.
- Source 변경·Snapshot 재선택/언마운트 시 기존 `detailSeq/sourceRef` 안전 검사 유지.
  리스트 GET 자체나 Catalog API, 보안 권한·서버 timeout 정책은 범위에서 제외.

## 변경 파일

- `frontend/src/utils/snapshotPanelDeadline.ts`: deadline, abort, timer 정리와 timeout 예외.
- `frontend/src/components/SchemaSnapshotHistory.tsx`: 세 독립 상세 GET에만 deadline 적용.
- `frontend/src/test/SnapshotPanelDeadline.test.ts`: 정상 종료/시간초과/즉시 실패/동기 예외/늦은 응답 테스트 **5건**.
- `frontend/src/test/SchemaSnapshotHistory.test.tsx`: Diff 지연 후 오류·개별 재조회 및 Preview 지연·늦은 안전하지 않은 응답 차단 **2건**.
- 본 문서.

**Backend/API 경로·DB/Alembic Migration·Oracle/DEMIS Adapter·Credential/Query Core·
기존 Snapshot Capture/Review POST·Catalog Import/READY/Activation·MCP·환자 쓰기 및 군/HITL 승인·운영 Docker 설정은 변경하지 않는다.**

## 서버 Acceptance — 미실행

기준 Frontend **15 files / 134 tests**.
신규 helper 테스트 5건 + 화면 통합 2건 → **예상 16 files / 141 tests**.

```bash
cd ~/dqa && git fetch origin && \
git worktree add --detach /tmp/dqa-s05k-review \
  origin/feature/s05k-snapshot-panel-deadline && \
(
  cd /tmp/dqa-s05k-review/frontend && \
  npm ci && \
  npm run build && \
  npm run lint && \
  npm test -- --run
) && \
git -C /tmp/dqa-s05k-review diff --check 93ca45a HEAD && \
echo DQA_S05K_REVIEW_PASS
```

검증된 코드 HEAD 및 전체 수치를 기록하기 전에는 테스트 완료라고 주장하지 않는다.
이번 검증은 synthetic mock 기반 Frontend 테스트이며, 실제 15초 네트워크 지연·Oracle 권한
테스트 또는 군/DBA Preflight 승인을 의미하지 않는다. GitHub Actions CI, 운영 Docker 배포,
실 DEMIS 연계 및 G1/G5 수용은 별도다.

**사용자 명시 승인 전 Draft→Ready 여부와 무관하게 `main` Merge 또는 운영 배포 금지.**
