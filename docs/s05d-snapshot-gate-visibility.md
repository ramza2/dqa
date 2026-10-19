# S-05-D — Snapshot 필수 Gate 안내 (읽기 전용)

> 기준 `main@fb46fa1`, 2026-10-19. 이번 기능은 S-05 운영자가 기존 Snapshot review preview의 필수 후속 단계를 볼 수 있게 하는 **순수 Frontend** 변경이다. `DEC-08`의 전체 S-05 UI 범위 확정이나 외부 Preflight/READY/운영 승인으로 해석하지 않는다.

## 범위와 기존 API

- 기존 Data Discovery → Snapshot History → 상세 보기 화면에서 조회되는 `GET /api/v1/schema-inspector/snapshots/{revision_id}/review?source_name=...` 응답을 재사용한다. **추가 HTTP 호출 없음**.
- `required_gates`는 Backend `app.services.schema_snapshot_review.REQUIRED_GATES`의 5개 정해진 식별자를 보여준다:
  1. `MANUAL_CHANGE_REVIEW`: 변경 내용의 수동 검토
  2. `INDEPENDENT_PREFLIGHT`: 독립 DBA·보안 Preflight 증빙
  3. `EXPLICIT_CATALOG_IMPORT`: Catalog Package v2 명시적 Import
  4. `READY_ELIGIBILITY_VERIFICATION`: READY 적격성 별도 검증
  5. `MANUAL_ACTIVATION`: 적격 Catalog Revision 수동 활성화
- 이 목록은 **필요한 후속 절차**이지 각각의 수행/완료 여부를 나타내는 값이 아니다. 진행률, 승인 완료 버튼, 단계 PASS, 누가 승인했는지의 근거를 생성하지 않는다.
- 선택 Snapshot이 더는 최신이 아니면 `SUPERSEDED`와 최신 Revision 번호를 안내한다. 이전 Revision도 Diff 이력으로 조회 가능하지만 후속 실행 대상으로 승격시키지 않는다.
- 기존 `SnapshotCatalogContext`가 보여주는 활성 Catalog/Activation 이력은 독립적인 체계이며, 이 Gate 목록과 결합해 Snapshot 계보·READY 발급·DBA 승인 완료를 추론하지 않는다.

## Fail-closed 표시 계약

기존 `SchemaSnapshotHistory`의 Source/Revision/Fingerprint 응답 일치 검사에 더해 다음 계약을 확인한다:
- `preflight_status=NOT_VERIFIED`, `candidate_package_readiness=WARNING`, `activation_eligible=false`;
- `snapshot_verified=true` 및 `candidate_package_valid=true`는 **내부 보관 메타데이터·후보 포맷 검증만** 나타낸다;
- `is_latest`, `review_status`, `latest_revision_id` 간 일관성;
- `required_gates`는 정해진 5개로 구성되어야 하며 누락/중복/미확인 문자열이 있으면 거부한다. 미확인 Gate 원문은 출력하지 않는다.

응답 계약 불일치 시 **Preview/Gate 영역만** 오류로 표시하고 Snapshot 상세 Diff·기존 Catalog 조회는 숨기지 않는다. Preview 자체의 403/409/500도 기존 오류 분리 동작 유지. Source 전환/Revision 선택 이후 늦은 이전 응답은 기존 시퀀스 가드로 폐기한다.

**신규 버튼, 신규 권한, DB/Oracle/DEMIS 연결, Snapshot Capture, Review 기록, Preflight VERIFIED, Import, READY 변경, Catalog 활성화, 의료정보 조회/쓰기 기능은 전혀 없다.** `CATALOG_READ` Backend 권한을 그대로 따른다.

## 수정 파일

- `frontend/src/utils/snapshotReviewGates.ts`: 순수 Gate 목록/계약 검증
- `frontend/src/components/SnapshotReviewGates.tsx`: 미승인 안내 컴포넌트
- `frontend/src/components/SchemaSnapshotHistory.tsx`: 기존 Preview 영역에 통합
- `frontend/src/test/SnapshotReviewGates.test.tsx` 및 `SchemaSnapshotHistory.test.tsx`: 정상·stale·malformed·승격 변조/409·Source 격리 회귀
- `frontend/src/App.css`: 안내 패널 최소 스타일
- `frontend/src/components/DataDiscoveryIndexStatus.tsx` 및 `frontend/src/test/DataDiscovery.test.tsx`: 전체 Suite 검증 중 드러난 자동 refresh 경고 소실 최소 수정 및 회귀 증명

## 서버 Acceptance — 1차 Build 오류, 수정 후 재검증 대기

- 2026-10-19 최초 서버 수용 시 `npm ci` 성공(258 packages, vulnerabilities 0), `npm run build` TypeScript 단계에서 **TS18048 3건**으로 중단. `npm run lint`, Vitest 및 최종 PASS 마커는 **미실행**.
- 문제: `Number.isSafeInteger(preview.revision_id)` 검사만으로 `Partial<SnapshotReviewPreview>`의 선택적 숫자 필드를 TypeScript가 좁히지 못함.
- 수정: `frontend/src/utils/snapshotReviewGates.ts`에서 두 Revision ID의 타입을 `typeof ... === "number"`로 명시 검증 후 범위 비교. Invalid/undefined 입력을 계속 fail-closed 처리.
- 이후 테스트 성공 전 기능 검증 완료 또는 PR Ready를 주장하지 않는다.

## 서버 Acceptance 2차 결과 및 원인 분석 (2026-10-19)

- 재검증 기준 `b7c0d73`: `npm run build` PASS, `npm run lint` PASS, Vitest **91 PASS / 1 FAIL (92건)**. S-05-D 신규/변경 테스트 14건 모두 통과.
- 실패: 기존 `DataDiscovery.test.tsx`의 `ignores sync response when revision snapshot no longer matches`에서 `index-stale-warning` 검색 실패.
- 원인: `DataDiscoveryIndexStatus.rejectStaleActionOnCurrentSource`가 revision mismatch 경고를 설정한 뒤 `refreshSources`를 호출하고, 이어지는 `loadStatus`가 `setStaleWarning(null)`으로 경고를 즉시 지우는 상태 갱신 순서. **비동기 타이밍에 따라 경고가 사용자에게 표시되지 않는 기존 UX 결함**으로 확인.
- 수정: 자동 상태 갱신에서만 경고 제거를 하지 않음. `onSelect` 및 신규 Rebuild/Sync 작업 시작에서는 기존처럼 경고 초기화. `DataDiscovery.test.tsx`는 자동 index status 재조회 후에도 경고가 유지되는지 회귀 검사.
- 범위 예외: 본 S-05-D 기능과 직접 관계없는 UI 회귀이지만, 전체 Suite를 통과하지 못하게 하는 기존 경고 동작 결함이어서 **두 파일의 최소 변경을 같은 PR에 명시적으로 포함**. Backend/DB/DEMIS 변경 없음.
- **최종 PASS 대기**. 새 수정 HEAD에서 전체 Vitest 92건과 Build/Lint를 다시 실행하기 전 머지/배포 금지.

## 서버 재검증 (기존 worktree 재사용)

```bash
cd ~/dqa && git fetch origin && \
git -C /tmp/dqa-s05d-review switch --detach \
  origin/feature/s05d-snapshot-gate-visibility && \
(
  cd /tmp/dqa-s05d-review/frontend && \
  npm run build && npm run lint && npm test -- --run
) && \
git -C /tmp/dqa-s05d-review diff --check fb46fa1 HEAD && \
echo DQA_S05D_REVIEW_PASS
```

최초 검증에서 `npm ci`가 정상 완료되었고 `package.json` / `package-lock.json`은 변경하지 않았으므로 동일 worktree의 설치된 `node_modules`를 재사용한다.

## 원래 검증 (첫 시도, Build 단계에서 중단)

기존 운영 Docker/DB/DEMIS에 영향 없는 별도 worktree에서 Frontend 검증:

```bash
cd ~/dqa && git fetch origin && \
git worktree add --detach /tmp/dqa-s05d-review \
  origin/feature/s05d-snapshot-gate-visibility && \
(
  cd /tmp/dqa-s05d-review/frontend && \
  npm ci && \
  npm run build && \
  npm run lint && \
  npm test -- --run
) && \
git -C /tmp/dqa-s05d-review diff --check fb46fa1 HEAD && \
echo DQA_S05D_REVIEW_PASS
```

- S-05-D 변경 전 Frontend 10개 파일 86건을 기준으로 이번 PR 전체 **11개 파일 92건**; 신규 Test와 회귀 PASS, ESLint/TypeScript/Vite Build, Diff PASS 필수.
- `DQA_S05D_REVIEW_PASS` 출력 전 완료/수용 주장 금지. `npm ci` 취약점 경고가 재출현하면 별도 분석하며 `npm audit fix --force` 금지.
- 사용자 별도 승인 전 GitHub main Merge/서비스 재배포 금지. 실제 군·DBA DEC-01/02/08/10 및 G1/G5는 여전히 대기.
