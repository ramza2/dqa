# U-02-C-1 — Legacy Schema Analyzer → DQA 데이터 이관 인벤토리 및 Cutover Gate

> **2026-10-15 소스 코드 기준의 의사결정 초안. 운영 데이터 조회/수정·DB 이행·PoC 중단·기관 승인 없음.**
> 실행된 U-02-A/B 오프라인 검증과 달리 **실제 Legacy DB 테이블별 레코드 수, 볼륨, 운영 상태는 미확인**이다.
> 정확한 17개 ORM 테이블 분류는 기계 검증용 [JSON](u02-c-legacy-cutover-inventory.json) 참조.

## 1. 고정 기준 및 확인 증거

- Legacy: [`demis-schema-search-poc@c9b88f6f6d14dc2598765efbf6bb41b4771f9b25`](https://github.com/ramza2/demis-schema-search-poc/tree/c9b88f6f6d14dc2598765efbf6bb41b4771f9b25).
- DQA: `ramza2/dqa@ded1b320b69a8dc90e1b04d7c07670423fbb2e47` (PR #85까지 merge).
- 관련 기존 분석: [U-02 소스 Gap](u02-schema-analyzer-dqa-gap-analysis.md).
- 검증 근거: PR #82 (U-02-A Oracle Inspector 합성 parity), #83 (U-02-B-1 Fingerprint/후보 계약), #84 (U-02-B-2-A 실제 Legacy finalizer + 합성 Session ZIP), #85 (U-02-B-2-B **격리된 실제 PostgreSQL** Catalog ORM + 최종 ZIP/DOCX/2-run Diff/Preflight 생성 및 DQA 구조 검증).
- #85 서버 결과: **69 passed**, `DQA_U02B2B_ACCEPTANCE_PASS`. 모두 **합성 Fixture/Mock 기준**이며 실제 DEMIS 데이터 동등성/기관 승인과 별개다.

## 2. 물리적 데이터베이스 구조 차이

Legacy는 `CatalogSource.id` → `CatalogAnalysisRun.source_id` → `CatalogAnalysisSnapshot.run_id`와
`CatalogTable.id` → Column/Constraint/FK/Index/Category/Search Document/Embedding 관계를
**업서트되는 관계형 카탈로그**로 유지한다. 근거:
`backend/app/models/catalog.py`,
`catalog_history.py`, `catalog_category.py`, `catalog_validation.py` (고정 Legacy).

DQA는 **검증된 v2 Catalog Package의 불변** `catalog_import_revisions`와
`catalog_active_revisions`/activation events를 권한의 기준으로 삼는다.
`schema_snapshot_revisions`는 출처·이전 리비전·CAS·캡처 ID를 갖는
**별도의 append-only Inspector 이력**이므로 Legacy `run_id` 또는 `snapshot.id`와
교환 가능한 키가 아니다. 검색 자료는 `data_discovery_documents`와
`data_discovery_embeddings`로 재구축된다. 근거:
DQA `backend/app/models/{catalog_import,catalog_active,schema_snapshot_revision,data_discovery,data_discovery_embedding}.py`.

**결론:** Legacy 테이블 → DQA 테이블 직접 `INSERT`/`COPY`/ID 복원 금지.
분리된 소스 증빙 보존 → 승인된 v2 ZIP 생성/반출검사 → DQA validate/import(필요 시) →
독립 승인 및 명시적 activate → 활성 Revision 기반 인덱스 재생성 순서로 다룬다.

## 3. 17개 ORM 테이블 처분 분류

| 분류 | 개수 | 대상 | 최종 처분 |
|---|---:|---|---|
| **패키지 물리 메타데이터** | 8 | Table, Column, KeyConstraint/Column, Relation/Column, Index/Column | `tables/columns/relations/indexes.json`을 v2 검증해 immutable Import Revision에 저장; 원본 ID는 별도 crosswalk |
| **패키지 의미 메타데이터** | 2 | Category, TableCategory | `categories.json`의 분류·테이블 매핑 및 provenance를 검증해 보존; 임상 의미를 자동 생성하지 않음 |
| **이력 외부 보존** | 2 | AnalysisRun, AnalysisSnapshot | 모든 Run/Snapshot을 별도 승인 백업에 유지; 최신 Run/Snapshot의 v2 첨부만으로 과거 전체 이력 복원 불가 |
| **불신 Preflight 증거** | 1 | CatalogPreflightResult | 최신 v2 첨부 + 전체 Legacy 증빙 별도 보존. `READY`를 독립 DBA의 `VERIFIED`로 승격 금지 |
| **DQA로 재생성** | 3 | SearchDocument, EmbeddingRun, Embedding | 원본 검색문서/Vector/Embedding 작업 ID 이식 금지. 활성 Revision에 속한 문서·1024d 인덱스 재구축 및 coverage 측정 |
| **별도 재설정** | 1 | CatalogSource | Source 식별자·DB/schema만 crosswalk. DQA ConnectionProfile/Secret ref를 별도 DBA 승인으로 작성; Legacy host/암호문/계정 복사 금지 |

각 행의 **실제 모델명·테이블명·소스 파일·목표 DQA 테이블·수용 기준**은
`docs/u02-c-legacy-cutover-inventory.json`에 17건 전부 명시한다.

## 4. 근거/부가파일과 누락 위험

| 항목 | 현재 DQA 구현/간극 | 결정·수용 조건 |
|---|---|---|
| **원본 ZIP, DOCX, README, Diff MD** | Import 모델은 필수 11개 JSON·Manifest와 Managed Digest를 저장. 원본 ZIP 및 첨부 DOCX/MD의 바이트 전체 보관 필드는 확인되지 않음 | 이전 전 승인된 외부 보존 저장소·암호화/접근통제·체크섬·복원 테스트; Import DB를 유일한 백업으로 간주하지 않음 |
| **Fingerprint** | Legacy와 DQA의 계산 대상/정규화가 다름 (#83) | `(legacy.source_id, legacy.run_id, legacy_fp, dqa.import_revision_id, dqa_fp, algorithm_version)` 별도 교차표. 원시 SHA 일치 요구 금지 |
| **Category** | `categories.json`에 MANUAL/AUTO/IMPORT, confidence/note가 담길 수 있음 | DB/table natural key 일치, 수기 분류 출처와 변경 이력 보존, 의료 의미 자동 추론 금지 |
| **Preflight / READY** | DQA validator는 Legacy manifest `READY`에 `activation_eligible=true`를 반환할 수 있으며 DQA activate는 VALID+READY 여부를 확인함 | 실제 승인 이력 검증 이전 외부 Legacy READY 자동 활성화 금지. 신뢰한 외부 서명/발급자·범위·만료·철회·독립 DBA 확인 정책은 미구현/미승인 |
| **열 Default·Index SQL·연결 정보** | Legacy v2에 `default_value`, `index_definition`, 자유 텍스트가 들어갈 수 있음; 기존 DQA validator는 임의 민감 문자열을 완전히 제거하지 않음 | 인가된 Export 범위·비식별·민감정보 검사 후 ZIP 저장/전송, 필요 시 차단·필드 제외 별도 PR |
| **Search/Embedding** | DQA는 활성 Revision 및 model_key, document_fingerprint에 종속 | DQA 문서 재구축→BGE-M3 1024d embedding 재생성→Gold query top-k·문서 coverage 검사. 기존 pgvector 바이너리 직접 복사 금지 |
| **Target/UI/기타 DBMS** | Legacy Target CRUD, MySQL/MariaDB/Postgres Analyzer, Streamlit ERD/Report 등이 DQA와 동일하지 않음 | 군 DEMIS Oracle 범위와 필수 UI/보고서 정의 확정 전 자동 이관/제거 금지 |

## 5. 사전 Cutover 의사결정 및 정합성 절차 (실행하지 않음)

1. **G0 범위/승인:** 실제 대상 Source·스키마, 조회 계정, 유지기간, Legacy 데이터 보존/개인정보 포함 가능성, ERD·Report·Category 편집 필요 여부를 PM·DBA·보안·군과 확인. 운영 Credential 취급 방식 별도 승인.
2. **G1 원본 백업:** Legacy DB 전체의 일관성 있는 백업(읽기 검증 가능 시점·manifest·복원 리허설) 및 v2 최종 ZIP/DOCX/Diff를 별도 제한 저장소에 보존. 운영 DB/서비스 중지·삭제·스키마 변경 없음.
3. **G2 익명화 재고 조사:** 허가된 독립 **읽기 전용** 환경에서 Source별 테이블/컬럼/FK/Index/Category/Assignment/Run/Snapshot/Preflight/Search Doc/Embedding 개수를 **집계값만** 수집. 원본 PK·환자행·암호문·임의 SQL/벡터를 출력하거나 대화에 붙여넣지 않는다.
4. **G3 Source·Revision Crosswalk:** `legacy.source_id`→승인된 `DQA.source_name`/environment, `legacy.run_id`→원본 증빙 묶음, `DQA.catalog_import_revision_id`와 고정 ZIP SHA를 별도 매핑. Source name 충돌과 누락 Run을 차단. `snapshot_revision_id` 자동 조작 금지.
5. **G4 Validate-only→제한 Import:** 원본 패키지의 SHA/manifest/count/source/FK/Category를 비교하고 비밀/DDL default 값을 검사한 뒤 격리 DQA에서 validate-only. Import는 운영 승인 후 별도 수행. **READY 매니페스트만으로 Activation 불허**; WARNING/BLOCKED는 권한 기준 아님.
6. **G5 재인덱스/검색 동등성:** 활성화를 허가한 Revision에 대해서만 문서와 embedding을 재생성, 1024차원/모델 버전·문서 coverage·Gold 검색 품질 및 FK/Category 표시 비교.
7. **G6 명시적 Cutover/복구:** 출처별 승인/역할·감사/추적, Rollback/재활성화·백업복원 리허설 완료. **해당 기관의 서면 승인 전 Legacy 중단·삭제 금지.**

### 최소 인벤토리 리포트 형식 (아직 값 없음)

`source_name_pseudonym / schema_scope / run_success_count / run_failed_count /
snapshot_count / table_count / column_count / pk_uk_count / fk_count /
index_count / category_count / assignment_count / doc_count /
embedding_count / preflight_count / latest_run_at / backup_sha256 /
v2_archive_sha256 / policy_decision / acceptance_status`.

실제 DB 건수·민감 필드는 이 문서/JSON에 저장하지 않는다. 카탈로그/임상행 건수를
혼동하지 않으며 Patient 수나 DEMIS 전체 완전성은 이 단계로 판단하지 않는다.

## 6. 정적 검증

`backend/tests/test_u02c_cutover_inventory_contract.py`:
- JSON 전체 17개 분류 중복/누락, 정책상 금지 처분, 명시된 DQA 대상 테이블 유무 검사.
- `DQA_U02_LEGACY_ROOT` 설정 시 원본 SHA·Git blob 검증 후 Legacy ORM
  `__tablename__` AST에 대해 **정확히 17개 전체 coverage** 확인.
- Python 표준 라이브러리만 사용하며 대상 Legacy 앱 모듈 import, DB/API/Oracle 연결, 파일 쓰기 없음.

```bash
cd /tmp/dqa-pr86-review/backend
DQA_U02_LEGACY_ROOT=/tmp/dqa-u02-legacy-pr83.GsdyYQ \
  ~/dqa/.venv/bin/python -m pytest -q -rs \
    tests/test_u02c_cutover_inventory_contract.py
```

서버 실행 전 테스트 통과를 단정하지 않는다. 변경 범위는 문서·오프라인 테스트만;
U-02-C-2의 실제 허가된 Read-only DB 건수 조사, Run/Source 매핑 데이터/리허설
및 U-02-C-3 Cutover 승인정책 구현은 **별도 PR**이 필요하다.
