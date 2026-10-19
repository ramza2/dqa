# S-05-E — Catalog Import Revision 이력 조회 (읽기 전용)

> 2026-10-19, 기준 `main@156bad2` (S-05-D 병합 이후). **Frontend-only 운영 UI**.
> 외부 DEC-01/02/08/10, 독립 DBA Preflight, READY eligibility, 실 DEMIS 연결/승인은 미확정.

## 현재 공백 / 구현

S-05-A~D는 Snapshot History/Diff, 활성 Catalog/Activation Events, Connection Profile/Inspector 설정 대조, Snapshot 후속 Gate 안내를 제공한다. 하지만 **같은 Source의 immutable Catalog Package Import Revision 이력**은 보이지 않는다.

이번 단계는 기존 `GET /api/v1/catalog/imports?source_name=...&limit=10&offset=0` (CATALOG_READ)를 사용하여 최근 최대 10개 Import Revision의 **공개 메타데이터만** 표시한다.
- 표시: Import Revision ID, Imported at, Package Version, Package Readiness (READY/WARNING/BLOCKED), Validation 상태, Table/Column 수, 축약 Fingerprint.
- 현재 Active Catalog가 있고 동일 Source에서 Import Revision **ID + Fingerprint**가 모두 일치하는 경우에만 “현재 활성 포인터와 ID/Fingerprint 일치” 문구를 보여준다. 한 항목이라도 다르면 승인/계보/READY를 추론하지 않는다.
- Active Catalog 조회가 404/403/500이거나 아직 완료되지 않았어도 Import 이력은 별도 GET으로 독립적으로 조회한다.
- Snapshot ID, Import ID, Activation Event는 **서로 다른 이력 축**이며 동일 ID나 Fingerprint도 공식 생성 계보·DBA 승인 증빙이 아니다.
- `READY`는 **Package 자체의 준비 상태**이고 활성화 완료나 운영 허가는 아니다. `WARNING/BLOCKED`의 활성화 조작을 허용하지 않는다.

## 보안·변경경계

- 신규 API 없음; 기존 Backend route `GET /catalog/imports`만 호출 (source-filtered, limit=10).
- 사용자가 Source를 바꾸거나 화면에서 벗어날 때 이전 비동기 응답을 표시하지 않는다.
- 서버 응답에 다른 Source/중복 Import ID/위조 Readiness/잘못된 Fingerprint/목록 개수 초과 또는 비배열 반환이 있으면 목록 전체를 폐기하고 비공개 오류만 표시한다.
- 401/403/5xx도 빈 목록으로 오인하지 않고 구분하여 표시하며, 서버 상세 오류 메시지, DB Name, Archive/Manifest Digest, 비밀/SQL/Patient 데이터는 표로 출력하지 않는다.
- UI가 `POST /catalog/imports/{id}/activate`, `POST /catalog/packages/import`, Inspector Capture, Credential resolver, Query Core, DEMIS/Oracle 등에 접근하거나 Import/Activation 버튼을 추가하지 않는다.
- Backend, Alembic/DB, Server Settings, Docker/운영 구성 변경 없음. S-05-D Snapshot Gate 정책 유지.

## 변경 대상

- `frontend/src/types/catalog.ts`, `frontend/src/api/catalog.ts`: 기존 응답 계약을 타입으로 선언하고 조회 함수 추가.
- `frontend/src/components/CatalogImportHistory.tsx`: 읽기 전용 Import 목록.
- `frontend/src/components/SnapshotCatalogContext.tsx`: Snapshot/Active/Activation 하위에 독립 패널로 연결.
- `frontend/src/test/CatalogImportHistory.test.tsx`: 분리 Mock 검증(정상·공백·cross Source·중복/변조·권한/에러 sanitization·stale response·ID/FP 비교).
- `frontend/src/test/SnapshotCatalogContext.test.tsx`, `SchemaSnapshotHistory.test.tsx`: 연계 및 기존 화면 회귀 Mock.

## 서버 Acceptance — 최종 PASS (2026-10-19)

- 검증 코드 HEAD: `c916bec`, 별도 detached Worktree `/tmp/dqa-s05e-review`.
- `npm ci`: **PASS**, 설치·감사 패키지 259개 기준 **취약점 0건**.
- `npm run build`: **PASS** — TypeScript, Vite 6.4.3 production build (62 modules).
- `npm run lint`: **PASS**, ESLint 오류 없음.
- `npm test -- --run`: **12 Test Files / 100 Tests PASS** — 신규 CatalogImportHistory 7건, SnapshotCatalogContext 10건, SchemaSnapshotHistory 10건 및 전체 Frontend 회귀.
- `git diff --check 156bad2 HEAD`: **PASS**. 최종 마커 `DQA_S05E_REVIEW_PASS` 확인.
- 이 문서는 검증 이후 결과만 기록하는 후속 커밋이다. **실행된 애플리케이션·테스트 코드와 의존성은 해당 검증 HEAD 대비 변경하지 않았다.**
- GitHub Actions CI 및 실제 Docker 이미지 빌드·운영 재배포·실 DEMIS/Oracle 데이터 연결은 미실행. 이 테스트는 군/DBA 승인·인수 수용 증빙이 아니다.
- 독립적으로 명시 승인하기 전에는 `main` 병합 및 운영 배포를 진행하지 않는다.

## 서버 검증에 사용한 명령 (실행 완료)

로컬 운영 서비스, DEMIS/DB, 공유 frontend 의존성 설치 상태를 변경하지 않고 별도 Worktree에서만 실행:

```bash
cd ~/dqa && git fetch origin && \
git worktree add --detach /tmp/dqa-s05e-review \
  origin/feature/s05e-catalog-import-history-readonly && \
(
  cd /tmp/dqa-s05e-review/frontend && \
  npm ci && \
  npm run build && \
  npm run lint && \
  npm test -- --run
) && \
git -C /tmp/dqa-s05e-review diff --check 156bad2 HEAD && \
echo DQA_S05E_REVIEW_PASS
```

기준 Frontend 전체 92 tests/11 files; S-05-E 7개 테스트 및 기존 Snapshot Context 통합 회귀 1건 추가로 **예상 100 tests / 12 files**. 정적 빌드, ESLint, 모든 Vitest 및 whitespace PASS 필수. 신규 GitHub Actions CI 실행을 가정하지 않는다.

- 사용자 승인 없이 Draft→Ready 여부를 테스트 성공으로 오인하지 않는다.
- 별도 승인 전 GitHub `main` 머지, Docker 재빌드/서비스 배포, 운영 DB/DEMIS 연계 **금지**.
