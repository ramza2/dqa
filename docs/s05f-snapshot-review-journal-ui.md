# S-05-F — Snapshot 변경 검토 이벤트 연결성 표시·검증 (조회 전용)

> 2026-10-19 기준 `main@2280f06`. DQA S-05 후속 UI의 안전성·가시성 단계.
> 이 기능은 **조회된 이벤트 목록의 형식·연결 관계를 확인**할 뿐, 외부 독립 감사/DBA Preflight 및 Catalogue READY·운영 승인을 발급하거나 검증하지 않는다.

## 기존 공백 및 구현

S-05-A~E 화면에서 `GET /api/v1/schema-inspector/snapshots/{revision_id}/reviews?source_name=...` 응답은 Decision, Reason, Reviewer와 시간만 표시한다. Backend는 `schema_snapshot_review_events`를 **append-only, latest ID 순, 최대 100건**, `previous_review_event_id`로 연결해 반환한다.

이번 PR:
- 기존 GET만 호출하고 추가 네트워크 요청 없이 Event ID, Previous Event ID, 검토 시각/Decision/Reason/Reviewer를 나란히 표시.
- `ACKNOWLEDGED`는 **Snapshot 변경 검토 기록**이지 DBA Preflight `VERIFIED` 또는 Catalog READY/Activation 근거가 아니라는 문구 표시.
- 응답이 비배열/101건 이상, 다른 Source·Snapshot ID·Fingerprint, 잘못된 Event ID/Predecessor, 중복·역순·연결 불일치, 허용 외 Decision/Reason 조합, 비정상 Reviewer/시각이거나 `independent_preflight_verified=true` 등 권한 상승 플래그가 포함되면 **검토 이벤트 목록만 fail-closed**.
- 목록은 최신 100건으로 제한: 연속 100건의 마지막 이전 Event ID가 조회 범위 밖이면 허용하되 UI에 부분 조회 가능성을 알림. 100건 미만에는 최초 Event가 `previous_review_event_id=null`로 끝나야 한다.
- Diff와 WARNING Preview, Gate 안내 및 별도 Catalog Import/Activation 이력은 **검토 이력 응답 실패 때문에 감추지 않는다**.
- Back-end 실제 GET 스키마에는 Preflight/READY/Activated boolean이 없으므로 Frontend `SnapshotReviewEvent`의 해당 필드는 기존 합성 Fixture 호환을 위한 optional false로 정합화; 누락은 절대로 true/승인으로 처리하지 않는다.

## 변경 파일

- `frontend/src/utils/snapshotReviewJournal.ts`: 순수 read-only 계약·연결 검증.
- `frontend/src/components/SchemaSnapshotHistory.tsx`: 기존 GET 결과 검증, Event/이전 Event 식별자 및 범위 제한 안내.
- `frontend/src/types/schemaSnapshot.ts`: 실제 Backend GET에서 반환하지 않는 세 개의 boolean 필드 optional 처리.
- `frontend/src/test/SnapshotReviewJournal.test.ts`: 정상/변조/연결 중단/100건 절단/승인 오인 방지 6건.
- `frontend/src/test/SchemaSnapshotHistory.test.tsx`: 정상 체인 렌더·실패 격리 통합 테스트 2건.
- 이 문서.

신규 Backend API, DB/Migration, Inspector Capture, Snapshot Review POST, Catalog Import/Activate, DEMIS/Oracle/임상 데이터, Credential 처리, Docker 배포 설정 변경 없음. 기존 `CATALOG_READ` 권한만 사용.

## 서버 Acceptance — 미실행

기존 운영 컨테이너/DB와 분리된 worktree에서 Frontend 검증:

```bash
cd ~/dqa && git fetch origin && \
git worktree add --detach /tmp/dqa-s05f-review \
  origin/feature/s05f-snapshot-review-journal-integrity && \
(
  cd /tmp/dqa-s05f-review/frontend && \
  npm ci && npm run build && npm run lint && npm test -- --run
) && \
git -C /tmp/dqa-s05f-review diff --check 2280f06 HEAD && \
echo DQA_S05F_REVIEW_PASS
```

기준 Frontend **12 files / 100 tests**; 신규 순수 Helper 테스트 6건 및 통합 2건으로 **예상 13 files / 108 tests**.
기존 Snapshot, Import, Data Discovery 테스트를 포함해 전체 통과 필수. PASS 출력 전 기능 수용을 주장하지 않음.

GitHub Actions CI, 실 운영 Docker 빌드·배포, 실제 DEMIS 연계, 외부 `DEC-01/02/08/10` 승인 및 G1/G5 인수는 모두 별도다. 사용자 명시적 승인 전 Merge/운영 배포 금지.
