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

## 서버 Acceptance — 1차 TypeScript 오류 및 해결 이력

- 2026-10-19 최초 서버 검증 HEAD `f97b15a`, 별도 `/tmp/dqa-s05f-review`에서 `npm ci` **PASS**, npm audit **0 vulnerabilities** (259 packages).
- `npm run build` 중 `TS2367` **3건**으로 중단: 타입 `SnapshotReviewEvent`의 승인 표시 optional false 필드를 `=== true`로 비교해 TypeScript가 불가능 조건이라고 경고.
- 승인 표시를 검사에서 제거하지 않고, `snapshotReviewJournal.ts`에서 **서버 응답 원본 객체를 `Record<string, unknown>`으로 읽어** 필드가 없거나 실제 `false`인 경우만 허용하도록 변경. `true`, `"true"`, `1`, `null` 등 오염된 값은 모두 **fail-closed**.
- `SnapshotReviewJournal.test.ts` 기존 테스트 내부에 비정상 승인 필드 `"true"/1/null` 사례를 추가. 애플리케이션 API/권한/DB/DEMIS 연결 변경 없음.
- 당시 Lint, Vitest 및 최종 `DQA_S05F_REVIEW_PASS`는 **미실행**이었다. 이후 재검증에서 전부 PASS했으며 결과는 다음 절에 기록한다.

## 서버 Acceptance — 최종 재검증 PASS (2026-10-19)

- 검증 코드 HEAD **`073872e`**, `/tmp/dqa-s05f-review` detached Worktree. 기준 `main@2280f06`.
- `npm ci`는 1차 검증에서 **PASS**, 감사 대상 259개 패키지 기준 **취약점 0건**. 2차 검증은 동일 `node_modules` 재사용.
- `npm run build`: TypeScript + Vite 6.4.3 **PASS**, 63 modules transformed.
- `npm run lint`: ESLint **PASS**.
- `npm test -- --run`: **13 Test Files / 108 Tests PASS** — SnapshotReviewJournal 신규 6건, SchemaSnapshotHistory 통합 포함 12건과 전체 Frontend 회귀.
- `git diff --check 2280f06 HEAD`: **PASS**, 최종 **`DQA_S05F_REVIEW_PASS`** 확인.
- 본 문서 기록은 검증 코드 HEAD 이후 추가된 문서 전용 commit이며, **검증 대상 Frontend 코드·테스트·의존성은 변경하지 않는다**.
- GitHub Actions CI는 별도 실행 확인되지 않음. Docker 운영 배포/DEMIS 연결/실제 군·DBA Preflight 승인 및 G1/G5 인수는 테스트 범위에서 제외.
- 사용자 명시 승인 전에는 GitHub `main` 병합과 운영 배포를 진행하지 않는다.

## 서버 재검증 명령 — 실행 완료 (기존 worktree)

```bash
cd ~/dqa && git fetch origin && \
git -C /tmp/dqa-s05f-review switch --detach \
  origin/feature/s05f-snapshot-review-journal-integrity && \
(
  cd /tmp/dqa-s05f-review/frontend && \
  npm run build && npm run lint && npm test -- --run
) && \
git -C /tmp/dqa-s05f-review diff --check 2280f06 HEAD && \
echo DQA_S05F_REVIEW_PASS
```

1차 `npm ci` 성공 이후 package manifest/lockfile을 변경하지 않았으므로 설치된 `node_modules` 재사용. 실패 시 test/컴파일 로그를 수집하고 동일 Draft PR에서만 수정 후 재수용.

## 서버 Acceptance — 원래 최초 명령 (빌드에서 중단)

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
