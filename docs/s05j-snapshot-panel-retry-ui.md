# S-05-J — Snapshot 상세 패널별 오류 재조회 (조회 전용)

> 2026-10-19, 기준 `main@8cae439`. S-05-I의 독립 GET 완료 처리에 이어
> 실패한 Snapshot 상세 패널만 명시적으로 다시 조회하는 Frontend 안전·운영성 보완.
> 이 기능은 실제 DEMIS 승인·독립 DBA Preflight·Catalog READY/Activation을 발급하거나 우회하지 않는다.

## 배경 및 구현

Snapshot 상세 화면은 3개 독립 GET으로 메타데이터 Diff, Review Preview/Gates, Review Journal을 표시한다.
S-05-I에서는 한 GET의 지연/오류가 다른 패널의 렌더링을 막지 않도록 개선했으나,
실패한 특정 패널을 다시 보려면 Snapshot 상세 보기를 다시 클릭하여 **3개 GET을 모두 다시 호출**해야 했다.

- 각 패널이 오류인 경우에만 `변경 Diff 다시 조회`,
  `검토 미리보기 다시 조회`, `변경 검토 이력 다시 조회` 버튼을 노출.
- 버튼은 기존 해당 **GET 하나만** 다시 호출한다.
  정상인 두 패널 및 사용자 선택, Catalog Import/Activation 이력은 초기화하지 않는다.
- 요청 동안 해당 패널만 Loading 처리한다. 재성공 시 기존 상태·계약 검사를 거친 안전한 결과만 렌더링.
  재실패/변조 응답은 해당 패널을 오류로 유지해 fail-closed.
- 기존 `detailSeq`(Snapshot 선택)과 `sourceRef`(Source 선택) 검사에
  **패널별 요청 순번**을 추가. 재조회 이전의 늦은 응답, Snapshot 재선택·Source 입력 변경·페이지 이동·언마운트 이후
  도착한 응답이 새로운 패널 상태를 덮어쓰지 못하도록 한다.
- 변경 검토 `ACKNOWLEDGED`는 DBA 독립 Preflight 검증/실제 승인 근거가 아님.

## 변경 범위

- `frontend/src/components/SchemaSnapshotHistory.tsx`: 세 GET 로딩 함수를 재사용 가능하게 분리,
  패널 전용 retry·sequence guard·버튼 추가.
- `frontend/src/test/SchemaSnapshotHistory.test.tsx`: Diff/Preview/Journal 별도 retry와
  다른 GET 미재호출 검증 3건 + Source 변경 중 pending retry 폐기 1건.
- 이 문서.

새 Backend API·권한, DB/Alembic, Credential/Oracle Adapter, 스키마 수집/Capture/Review POST,
Catalog Import/READY/Activate, 임상 데이터 조회·쓰기·승인 UI, Docker 운영설정 변경 없음.
기존 `CATALOG_READ`로 조회되는 정보 외 노출 없음.

## 서버 Acceptance — 미실행

기준 Frontend **15 Test Files / 130 tests**, 신규 통합 4건 추가 후
**예상 15 Test Files / 134 tests**. 실제 운영 컨테이너와 DB는 그대로 두고 detached Worktree에서만 검증:

```bash
cd ~/dqa && git fetch origin && \
git worktree add --detach /tmp/dqa-s05j-review \
  origin/feature/s05j-snapshot-panel-retry && \
(
  cd /tmp/dqa-s05j-review/frontend && \
  npm ci && \
  npm run build && \
  npm run lint && \
  npm test -- --run
) && \
git -C /tmp/dqa-s05j-review diff --check 8cae439 HEAD && \
echo DQA_S05J_REVIEW_PASS
```

- 최종 PASS 마커 이전에는 테스트 수용을 주장하지 않는다.
- GitHub Actions CI·운영 Docker 배포·실 Oracle/DEMIS·군/DBA Preflight·G1/G5 인수는 별도.
- 사용자 명시 승인 전 `main` Squash Merge/운영 배포 금지.
