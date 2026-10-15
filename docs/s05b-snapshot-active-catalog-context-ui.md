# S-05-B — Snapshot / Active Catalog 상태 연계 (읽기 전용)

> 기준 `main@189c146`, 2026-10-15. **DQA Frontend 범위**만.
> 개발 화면을 독립 Preflight·군/DBA 승인 또는 운영배포 완료로 해석하지 않는다.

## 1. 운영 목표

현재 S-05-A의 Data Discovery → Snapshot History 화면은
`SchemaSnapshotRevision` (캡처된 메타데이터 역사)만 보여준다.
S-05-B에서는 운영자가 **같은 Source 이름을 기준으로** 현재 활성
`CatalogImportRevision`과 Activation 이벤트도 **별개의 축**에서 확인한다.

| 영역 | 기존 GET API | 처리 |
|---|---|---|
| Snapshot | `/api/v1/schema-inspector/snapshots` 및 `/{id}` | 기존 S-05-A 유지 |
| Current Active Catalog | `GET /api/v1/catalog/active/{source_name}` | Active Source, Catalog **Import Revision**, Package v2 / `READY`, 활성화 시각, Full Fingerprint의 축약 표시 |
| Catalog Activation Event | `GET /api/v1/catalog/activations?source_name=...&limit=10&offset=0` | 최근 10개, 이전/활성화된 **Catalog Import Revision**, 이벤트 시각 |
| 현재/선택 Snapshot 비교 | API 신규 호출 없음 | `schema_fingerprint` **문자열 일치/불일치만 표시**, 승인·패키지 계보의 근거로 절대 이용하지 않음 |

### 반드시 지켜야 할 구분

1. **Snapshot Revision ID ≠ Catalog Import Revision ID.**
   숫자가 같아도 같은 도메인 Entity나 FK를 의미하지 않는다.
2. Fingerprint가 같아도 그 Snapshot이 해당 Import를
   생성/승인/활성화했다는 것을 **추론하지 않는다**.
   동일 Scope/Normalization/변환 방식과 승인된 Provenance가
   독립적으로 확인되어야 실제 계보를 선언할 수 있다.
3. Snapshot만 존재하고 Active Catalog가 없는 Source는 정상.
   `GET /catalog/active/{source_name}` **404는 ‘활성 없음’**으로
   표시하되, 403/500은 인증·서비스 오류로 분리한다.
4. `CatalogActivations`은 이전 활성 포인터를 보여주는
   메타데이터 이벤트 조회일 뿐, 다른 시스템의 임상 승인·DBA
   Preflight `VERIFIED` 또는 Snapshot Change Review가 아니다.

## 2. 보안·상태 무결성

- **GET 전용**; `CATALOG_READ`는 Backend에서 계속 강제된다.
- Source 변경/재조회/페이지 변경 시 이전 조회 컴포넌트를
  언마운트하여 이전 비동기 응답을 무시한다. Active 및 Activation
  응답 모두 요청 Source 일치 검증; 불일치면 결과를 폐기한다.
- Snapshot 조회 자체가 실패(403/500/Source 오류)하면
  연계 패널은 렌더링하지 않는다.
- 한쪽 조회(Active / Activation History)가 실패해도 상대편의
  유효한 결과 또는 Snapshot Detail/Diff를 숨기지 않는다.
- Snapshot 선택 시 선택 Revision의 Fingerprint, 아니면 첫
  페이지 최신 Snapshot의 Fingerprint와 Active Catalog를 비교한다.
  2페이지 이상 선택이 없으면 비교하지 않는다.
- **READ-only UI**: Snapshot Review POST, Capture, Import,
  Activate, Preflight 검증 실행, Credential 노출,
  Oracle/DEMIS 접근, 임상기록 조회·쓰기, LLM/VLM 호출 없음.
- Backend API/DDL/Alembic/Docker/실행 중 서비스 설정 **변경 없음**.
  현재 프론트엔드 테스트 Mock의 Catalog 이벤트는 합성 값이다.

## 3. 검증

새 `SnapshotCatalogContext` 컴포넌트와 기존 S-05-A 테스트를
단독 및 회귀 실행한다. 별도 Detached Worktree에서만 npm 의존성
설치·Lint·Vitest·Vite 빌드 수행.

```bash
cd ~/dqa && git fetch origin && \
git worktree add --detach /tmp/dqa-s05b-review \
  origin/feat/s05b-snapshot-active-catalog-context && \
(
  cd /tmp/dqa-s05b-review/frontend && \
  npm ci --ignore-scripts --no-audit --no-fund && \
  npm run lint && \
  npm test -- --run src/test/SchemaSnapshotHistory.test.tsx src/test/SnapshotCatalogContext.test.tsx && \
  npm run build
) && \
git -C /tmp/dqa-s05b-review diff --check 189c146 HEAD && \
echo "DQA_S05B_FRONTEND_REVIEW_PASS"
```

- 수용 예상: S-05-A 8개 회귀 + S-05-B 9개 신규 테스트,
  ESLint/TypeScript/Vite Build PASS, whitespace PASS.
- 404/403/503, 서로 다른 Source의 응답, Source 변경 중 늦은 응답,
  서로 같은 Revision 번호와 Fingerprint 일치/불일치,
  이벤트 별도 오류 및 Snapshot 조회 상태를 검증한다.
- 테스트 성공은 **Frontend Mock API 계약의 수용 결과**에 한정.
  운영 PostgreSQL, Oracle, DEMIS, 실제 IAM/RBAC, Site Acceptance,
  군기관 DEC-01/02/04/08/운영 승인과는 별개다.

실패 시 **동일 Draft PR에서만 수정 후 재검증**한다.
머지/Frontend 컨테이너 재배포는 사용자 승인 전 시행하지 않는다.

## 4. 후속 검토

S-05-C는 DEC-08에 따라 필요 화면(Target/ERD/Report/Category/Preflight)
범위를 결정한 뒤 진행한다. 승인 주체가 다른
실 DEMIS Query·FHIR·임상 Controlled Write와 연동하지 않는다.
