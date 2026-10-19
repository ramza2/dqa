# S-05-G — Schema Snapshot Diff 집계 및 기준선 상태 표시 (읽기 전용)

> 2026-10-19. 기준 `main@02cc2c0` (S-05-F 병합 후).
> 이 단계는 저장된 Schema Snapshot의 **메타데이터 Diff 가시성 및 응답 정합성**만 개선한다.
> 운영 DEMIS/Oracle 접근, DBA Preflight VERIFIED, Catalog READY/Activation 및 임상 기록 승인은 포함하지 않는다.

## 구현 배경

기존 DQA Data Discovery → Snapshot History는 Diff 상세 항목과 `total_changes`만 보여준다.
그러나 이미 구현된 Backend GET `/api/v1/schema-inspector/snapshots/{revision_id}?source_name=...`는
`diff_counts`에 객체 유형별 Added/Removed/Changed 건수를 담고 있다.
이를 보여주어 어떤 물리 메타데이터가 변경됐는지 검토자가 빠르게 파악하도록 한다.

- COMPARED Snapshot에서 이전 Snapshot Revision 기준, 전체 변경 합계 및
  Table / Column / Primary Key / Unique Constraint / Foreign Key / Index 유형별 건수를 표시한다.
- 최초 Snapshot `NO_BASELINE`은 **비교할 이전 Snapshot 없음**으로 표시.
  이를 비교한 결과 변경 0건인 COMPARED와 구별한다.
- `diff_counts`, `total_changes`, `changes`의 합계·유형·세부 행 수 일치,
  각 Object ID 길이, Change type, Changed fields, 중복 Object Identity,
  미지원 Object Type, 안전하지 않은 숫자 등을 Frontend에서 검증한다.
  기존 Backend Source/Revision/Fingerprint 확인에 더해 이전 Revision ID와
  Diff Status/Total을 목록의 선택 Snapshot 정보와 대조한다.
- 실패 시 손상된 **Diff 영역만 fail-closed**. 별도 GET으로 가져오는 Review Preview,
  필수 Gate 안내, 변경 검토 저널, Catalog Import/Activation 조회를 숨기지 않는다.
- 개인정보/SQL/실제 DEMIS 행, before/after 원본 메타데이터, 자격증명 노출 없음.

## 보안 경계

- 기존 `GET /schema-inspector/snapshots/{id}` **재사용**. 신규 API·POST·승인 버튼 없음.
- 비승인 Catalog WARNING을 READY로 변경하거나 활성화/Import하지 않음.
- Backend/DB/Alembic/Docker/Oracle Adapter/권한 처리, ModelOps/LLM 호출 변경 없음.
- 정적 Frontend 집계/검증 로직이며 개발용 Synthetic/Mock 자료로만 테스트.
- `NO_BASELINE`과 0건이라는 숫자 비교는 실제 Oracle DBA 적격성/변경 없음 판정과 별개다.

## 변경 파일

- `frontend/src/utils/snapshotDiffOverview.ts` — 메타데이터 Diff 계약 검증과 집계 행 제공.
- `frontend/src/components/SchemaSnapshotHistory.tsx` — 기존 Diff에서 집계, 기준선, 오류 상태 렌더링.
- `frontend/src/test/SnapshotDiffOverview.test.ts` — 정상·다중 유형·변경 0·NO_BASELINE·합계 불일치·변조/중복 검증 6건.
- `frontend/src/test/SchemaSnapshotHistory.test.tsx` — 실제 Snapshot 화면에서 집계/NO_BASELINE/오류 격리 회귀 3건.
- 이 문서.

## 서버 Acceptance — 최종 PASS (2026-10-19)

- **검증 코드 HEAD: `a350f92`**, 독립 Detached Worktree `/tmp/dqa-s05g-review`, 비교 기준 `main@02cc2c0`.
- `npm ci`: **PASS** — 258개 패키지 설치, 259개 패키지 감사 결과 **취약점 0건**. `whatwg-encoding`/`eslint` deprecation warning은 비차단 안내.
- `npm run build`: **PASS** — TypeScript/Vite 6.4.3 production build, 64 modules transformed.
- `npm run lint`: **PASS** — ESLint 오류 없음.
- `npm test -- --run`: **14 files / 117 tests PASS** — 신규 SnapshotDiffOverview 6건, SchemaSnapshotHistory 15건 포함 전체 Frontend 회귀.
- `git diff --check 02cc2c0 HEAD`: **PASS**; 최종 마커 **`DQA_S05G_REVIEW_PASS`** 확인.
- 본 수용 결과 추가는 **문서 전용 후속 커밋**이며, 검증 당시 Frontend 기능·테스트 코드 및 의존성은 변경하지 않았다.
- GitHub Actions CI, 실제 Docker 운영 빌드/재배포, Oracle/DEMIS 접속 및 군·DBA 승인·실증은 이번 시험 범위가 아니다.
- 사용자 별도 승인 전 `main` 머지·운영 배포 금지.

## 서버 수용에 사용한 명령 (실행 완료)

현재 `main@02cc2c0` Frontend **13 files / 108 tests**에서
6개 순수 Helper + 3개 통합 테스트를 추가해 **14 files / 117 tests PASS**를 확인했다.
운영 서비스에 영향을 주지 않는 별도 Detached Worktree에서 확인:

```bash
cd ~/dqa && git fetch origin && \
git worktree add --detach /tmp/dqa-s05g-review \
  origin/feature/s05g-snapshot-diff-overview && \
(
  cd /tmp/dqa-s05g-review/frontend && \
  npm ci && \
  npm run build && \
  npm run lint && \
  npm test -- --run
) && \
git -C /tmp/dqa-s05g-review diff --check 02cc2c0 HEAD && \
echo DQA_S05G_REVIEW_PASS
```

- Build, Lint, Vitest 전체, Diff 검사 및 마지막 `DQA_S05G_REVIEW_PASS` 확인을 완료했다.
- 사용자 명시적 승인 전 GitHub `main` Merge, Docker 운영 재배포 및 DEMIS 실측 연결 금지.
- 외부 결정 `DEC-01/02/08/10`과 `G1/G5` 수용은 계속 별개이다.
