# S-05-A — DQA Snapshot History 읽기 전용 운영 화면

> 개발 기준: `main@889197499d202506787a93ecc7861591ab26d846`,
> 2026-10-15. **개발 UI 추가는 군/DBA 운영 승인, 독립 Preflight,
> Catalog READY 전환 또는 Legacy Analyzer Cutover를 의미하지 않는다.**

## 1. 화면 경계

DQA Web의 **Data Discovery → Snapshot History** 탭에서 다음
정보를 이미 존재하는 `CATALOG_READ` 권한의 GET API로만 조회한다.

| 화면 | 기존 Backend API | 처리 |
|---|---|---|
| Source별 Snapshot 이력 | `GET /api/v1/schema-inspector/snapshots?source_name=...&limit=50&offset=...` | Source 직접 입력, 명시적 조회, 50건 단위 이전/다음, 기준 없음과 0건 구분 |
| 개별 Snapshot 상세·Diff | `GET /api/v1/schema-inspector/snapshots/{id}?source_name=...` | Source/Revision/Fingerprint 교차 확인, Object/변경유형/식별자/변경된 **필드명만** 표시 |
| Review preview | `GET /api/v1/schema-inspector/snapshots/{id}/review?source_name=...` | WARNING, `NOT_VERIFIED`, `activation_eligible=false`, 최신 여부 표시. 운영 승인으로 오인 금지 |
| Change review history | `GET /api/v1/schema-inspector/snapshots/{id}/reviews?source_name=...` | 관리자 이벤트 이력 조회 전용 (기록/승인/반려 POST 미제공) |

**중요:** Snapshot은 READY Catalog 활성화 이전에도 존재할 수
있으므로, `/catalog/active`에 등록된 Source만 목록에 보여주거나
활성 Catalog 부재를 Snapshot 부재로 해석하지 않는다.
Backend의 `CATALOG_READ` RBAC·Source 격리·응답 마스킹이 우선한다.
UI는 개발자가 입력한 Source명을 기존 조회 API에 전달할 뿐
새 Oracle Host/Query/Credential을 등록하거나 Inspector를 실행하지 않는다.

## 2. 동시성·실패 처리

- Source 변경, 새 페이지 조회, 컴포넌트 언마운트, 선택 Revision 변경 시
  순번 토큰을 무효화하여 **이전 비동기 응답의 재표시 방지**.
- 이력·상세·미리보기·이벤트 응답의 **Source/Revision/Fingerprint
  일치 여부**를 검사; 불일치 시 기존 UI에 반영하지 않음.
- Preview 409/403/500은 상세 Diff 조회 실패로 둔갑시키지 않는다.
  Preview 영역만 별도 오류 표시. HTTP 코드/오류 코드는 기존
  `CatalogApiError` 메시지로 표시.
- NO_BASELINE에서 `total_changes=null`은 0과 구분해
  “기준 없음”으로 보여준다. 0개 Snapshot / API 실패도 별도 표시.
- Table/Object 원문·Diff Before/After·Credential/SQL/임상 레코드 노출
  없음: 서버에서 제공하는 안전한 메타데이터 필드만 렌더.
- Snapshot 검토 미리보기 결과는 **독립 DBA 발급 증빙이 아니다**.
  `WARNING` 후보를 `READY`로 승격시키는 버튼/API 호출은 없다.

## 3. 구현 범위

- `frontend/src/types/schemaSnapshot.ts`: 기존 Pydantic 응답 계약 Mirror
- `frontend/src/api/schemaSnapshot.ts`: 신규 **GET 전용** API Client
- `frontend/src/components/SchemaSnapshotHistory.tsx`: 읽기 전용 운영 화면
- `frontend/src/components/DataDiscoveryPortal.tsx`: 네 번째 탭 노출
- `frontend/src/test/SchemaSnapshotHistory.test.tsx`: 정상·미리보기 409,
  리스트 Source 불일치·Stale Source/Detail 응답·NO_BASELINE·입력 검증 등

**이번 PR에 Backend/Migration/Oracle/DEMIS/Runtime/DB/LLM/FHIR/MCP
코드·설정 변경 없음.** 임상의 승인 UI, Snapshot 캡처, 수동 Review POST,
DBA Verified, Catalog Import/Activation, Target CRUD, ERD/Report/Category
편집은 범위 밖. 추후 S-05 세부 화면은 DEC-08 협의 후 분리한다.

## 4. 서버 Acceptance

서버 개발 환경은 필요한 npm 패키지를 Detached Worktree의
`frontend/node_modules`에 독립 설치한다. `~/dqa`의 현재
실행 중 컨테이너와 PostgreSQL에 접근하거나 `db_session` 통합
테스트를 실행하지 않는다.

```bash
cd ~/dqa && git fetch origin && \
git worktree add --detach /tmp/dqa-s05a-review \
  origin/feat/s05a-readonly-snapshot-history-portal && \
(
  cd /tmp/dqa-s05a-review/frontend && \
  npm ci --ignore-scripts --no-audit --no-fund && \
  npm run lint && \
  npm test -- --run src/test/SchemaSnapshotHistory.test.tsx && \
  npm run build
) && \
git -C /tmp/dqa-s05a-review diff --check 8891974 HEAD && \
echo "DQA_S05A_FRONTEND_REVIEW_PASS"
```

필수: 새 테스트 PASS, ESLint/TypeScript/Vite Build PASS,
Whitespace 검사 및 `DQA_S05A_FRONTEND_REVIEW_PASS`.

환경별 npm Registry/캐시 장애는 제품 검증 실패와 구분한다.
운영 웹 재배포·main Merge는 서버 Acceptance와 사용자 별도 승인 이후만.

## 5. 외부 의사결정

- `DEC-08`: Target/ERD/Report/Category/Preflight 등 운영 UI의 필수/
  선택 범위는 PM·PL·사용기관 합의 대기. 이번 Snapshot History 조회 화면은
  그 결정 이전에 가능한 최소 독립 단위일 뿐 전체 S-05 완료가 아니다.
- `DEC-01/02`: 군/DEMIS DBA Inspector Scope, 독립 Preflight 증빙
  인증·만료·철회 정책 미확정. `VERIFIED`/READY 발급 불가.
- `DEC-04/G1`: 실제 스키마·검색 동등성, Legacy 운영 종료는 미검증·미승인.
