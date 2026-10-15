# U-02 — Legacy DEMIS Schema Analyzer → DQA 통합 Gap 분석 (소스 기준선)

> **상태:** 2026-10-14 코드 정적 비교 완료 / 동작 동등성·운영 수용 **미검증**.
> 이 문서는 최종 DEMIS 통합 범위·기관 승인이나 실스키마 분석이 아니다.
> **문서 전용 PR**이며 Backend/Frontend/DB/배포 동작을 변경하지 않는다.

> **2026-10-15 U-02-C 진행 현황:** 최초 작성 후 U-02-A (#82), U-02-B-1 (#83), U-02-B-2-A (#84), U-02-B-2-B (#85)의 **합성/격리 테스트가 main에 병합되어 검증됨**. 이는 실제 DEMIS parity·의료 운영 승인/전체 레거시 데이터 이관 검증을 의미하지 않는다. **U-02-C-1(전체 Legacy ORM 17개 대상 정적 분류/이관 계획)은 [별도 Cutover 문서](u02-c-cutover-plan.md)와 [기계 검증 인벤토리](u02-c-legacy-cutover-inventory.json)에서 관리한다.** 원본 U-02 기능별 Gap 표의 'parity 미검증' 등 표기는 *2026-10-14 분석 시점 상태*이다.

## 1. 비교 기준과 목표

| 대상 | 고정 기준선 | 분석 대상 |
|---|---|---|
| Legacy Analyzer | [`ramza2/demis-schema-search-poc@c9b88f6`](https://github.com/ramza2/demis-schema-search-poc/tree/c9b88f6f6d14dc2598765efbf6bb41b4771f9b25) (2026-09-21) | Streamlit·FastAPI, Target/Preflight, Schema Analyzer, Catalog Writer, v1/v2 Export, ERD/Report, Search/Embedding |
| DQA | [`ramza2/dqa@0d72e05`](https://github.com/ramza2/dqa/tree/0d72e051f47e8fce9974aaba76abf1f761e1dbbf) (2026-10-14) | Oracle metadata-only Inspector, append-only Snapshot, offline v2 `WARNING` candidate, 활성 Catalog, Data Discovery, Web |
| 목표 규격 | [DQA Unified Platform WBS](roadmap.md) / [통합 아키텍처](integrated-platform-architecture.md) | **최종 단일 DQA**, 기존 독립 Analyzer 런타임 의존성 제거, 권한·감사·READY 활성화 경계 유지 |

**판독 방법:** `기반 구현`은 DQA에 해당 코드/테스트가 존재함을 의미하고
동등성 확인과 운영 승인까지 완료했다는 뜻이 아니다.
`Gap`은 최종 단일화에 필요한 차이이고, `제외 후보`는 외부 협의 전
개발 확정 사항이 아니다. PoC의 기능·정책을 DQA와 동일하게 간주하지 않는다.

## 2. 기능별 Gap 매트릭스

| ID | Legacy Analyzer 근거/동작 | DQA 근거/현황 | 평가 | 다음 작업 / 수용조건 |
|---|---|---|---|---|
| U02-01 | `backend/app/analyzers/oracle.py`: Oracle `ALL_*` dictionary SELECT로 Table·Column·PK·UK·FK·Index·Comment 수집 | `backend/app/adapters/schema_inspector/oracle.py` 및 `schema_inspection.py`: Oracle Inspector 이관, `SET TRANSACTION READ ONLY`, 별도 검사 계정, dev/test 기본 비활성 | **기반 구현 / parity 미검증** | 동일 합성 Oracle fixture를 두 Analyzer로 검사해 객체 정체성·순서·컬럼 속성/주석·복합키/FK/인덱스 비교; metadata visibility·누락 처리 별도 확인 |
| U02-02 | `analyzers/factory.py`: PostgreSQL·MySQL·MariaDB·Oracle 지원 | `adapters/schema_inspector/oracle.py`: 현 Inspector Oracle 전용 | **범위 결정 필요** | DEMIS 통합 목적이 Oracle로 제한되면 타 DBMS Analyzer는 의도적 제외; PoC 다중 DBMS 기능 자동 이관 금지 |
| U02-03 | `services/target_service.py`, `api/targets.py`: Target CRUD, probe, schema listing, 여러 스키마 선택·분석, 암호화된 Credential/임시 입력 | `services/schema_inspection.py`: 운영자가 정한 하나의 Source·Schema/Secret ref만 검사. 읽기 Query용 Connection Profile은 별도 개념 | **설계 Gap (우선)** | Inspector Target 등록/목록/선택이 필요한지 확정; 임의 host·schema·password 입력/기존 암호문 DB 복제 금지. DBA 승인 allowlist·최소권한 설계 선행 |
| U02-04 | `services/preflight_service.py`, `api/preflight.py`: 대상 연결/스키마 가시성 및 Table/Column/Key/FK/Index별 검사를 수행해 PASS/WARNING/BLOCKED, 결과 저장 | `schema_snapshot_review.py`: 저장된 Snapshot 검증과 후보 호환성만 확인; `schema_preflight_contract.py`·`schema_preflight_snapshot.py`은 Mock/비권위 계약이며 항상 `NOT_VERIFIED` | **의미상 중대한 Gap (외부 정책 대기)** | 기존 PoC Preflight의 `READY`를 독립 DBA 증빙으로 승격 **금지**. 군/DEMIS 검증자·권한/범위·독립 증빙/만료 정책 확정 전 운영 `VERIFIED` 구현 금지 |
| U02-05 | `services/target_service.py` + `catalog_writer.py`: Run 기록, 여러 Schema 병합, Source별 Catalog upsert | `schema_snapshot_capture.py` + `schema_snapshot_history.py`: 단일 설정 Schema에서 명시적 수집, source-bound append-only Snapshot Revision·멱등/동시성 제어; Catalog pointer 변경 없음 | **구조적 차이 / 기반 구현** | Run↔Snapshot 이력, 실패·재시도, 다중 스키마, 소스 격리·삭제 의미 비교. PoC Catalog upsert·파괴적 Target 삭제를 DQA에 복제하지 않음 |
| U02-06 | `services/schema_diff_service.py`, `api/schema_diff.py`: 성공 Run baseline 캡처 및 run-to-run compare | `schema_snapshot_diff.py` + `schema_snapshot_review.py`: Snapshot Revision 기반 Diff와 무결성 검증, change-review 이벤트/Preflight 분리 | **부분 동등 / 의미 차이** | 기존 Run 번호/수동 baseline과 새 Revision 대응표, 무변경·복합 FK·주석 변화·missing object 판정 비교 |
| U02-07 | `services/catalog_package.py`: v1 package. `services/catalog_package_finalizer.py`: v2와 분석/스냅샷/Preflight/Diff/DOCX 근거 첨부; PoC 자체 readiness 산정 | `schema_catalog_candidate.py`: Snapshot→자체 validator를 통과한 v2 **`WARNING` 후보만**. `catalog_package_import.py` + 활성 Catalog는 별도 명시적 READY-only | **의도적 차단 (P0)** | v2 필드·manifest/count/category/relations/fingerprint/문서 파일 동등성 검사. 기관 정책 미정인 `READY` 자동 생성/승인·활성화 금지; 이관은 검증된 Import 및 명시적 활성화 경로만 |
| U02-08 | `catalog_writer.py`, `models/catalog.py`: 관계형 Catalog 변경 갱신 | `catalog_package_import.py` 및 active Catalog 서비스: immutable revision 중심 | **의도적 재설계** | PoC DB→DQA DB 테이블 직접 복사 금지. v2 export/validate/import/cross-check·원본 보존·rollback 설계 필요 |
| U02-09 | `api/erd.py`, `frontend/pages/3_ERD_Explorer.py`, `frontend/erd_component`: source-scoped ERD 노드/관계 UI | `api/routes/catalog_query.py` relations 조회와 `CatalogExplorer`/Table Detail 있음. 별도 ERD graph API/캔버스는 코드 목록에서 미확인 | **UI/표현 Gap** | S-05에서 활성 Revision 소속 FK만 표시하는 ERD UI 필요성 확정; 복합 FK 정렬·외부 참조·Source switch 시 stale guard 필수 |
| U02-10 | `api/catalog_report.py` + `services/catalog_report.py`: DB 분석 DOCX 생성/다운로드 | Catalog/Schema 조회 기능은 있으나 기존 양식 수준 DOCX 분석 보고 생성 API는 확인되지 않음 | **요구 판단 필요** | 보고서가 실증·인수 산출물인지 합의. 필요하면 승인된 활성 Catalog에서 비임상 메타데이터만 출력, 민감 default·연결정보·실행 SQL 제외 |
| U02-11 | `api/catalog.py`: Category CRUD 및 Table–Category 연결 수정 | `api/routes/catalog_query.py`: Category 조회; Data Discovery·인덱싱 제공. 동등한 Category CRUD는 해당 API에서 미확인 | **저작 기능 Gap 후보** | 수기 의미 분류 편집이 계약상 필요할 때만 Catalog immutable revision·감사·재색인 정책 설계; 원본 물리 사실과 추정 의미 구분 |
| U02-12 | `services/search/*`, `api/search.py`, Embedding 작업 | `services/data_discovery_search/*`, `api/routes/data_discovery.py`, `frontend/src/components/SchemaSearch.tsx`: Keyword/Semantic/Hybrid·Embedding 동기화 | **양쪽 구현 / 품질 parity 미검증** | 동일 Gold Query/활성 source/snapshot 기반 top-k, 정확성·출처·용어확장·Fingerprint·1024차원 호환성 비교. 벡터 DB 직접 이관 단정 금지 |
| U02-13 | Streamlit `frontend/target_dashboard.py`, `pages/1_...`~`6_...`: Target/Preflight/Table/ERD/Report/Diff/Package 운영 | React `CatalogExplorer`, `DataDiscoveryPortal`, `QueryAssistant` 중심; Inspector Target·Run·Preflight·Diff·Report 일체형 운영 화면은 미구현 또는 확인되지 않음 | **운영 UI Gap** | S-05: Source→Target→Read-only inspect→Snapshot 이력/Diff→Change-review/증빙 상태→분리된 Catalog Import/수동 활성화. Preview가 승인은 아님을 표시 |
| U02-14 | Legacy DB 내 `CatalogSource`, Run, Snapshot, Category, Search Documents/Embeddings 영속 데이터 | DQA Catalog Revision·Query Template·Data Discovery 등 별도 영속 스키마 | **데이터 이행 미검증** | Legacy 실데이터/볼륨 백업→레코드·개체 건수·연계 ID·Category/Embedding 품질·Read-only 검증→복원 리허설. 인덱스 재생성 가능성 평가. 사전 삭제 금지 |
| U02-15 | Legacy Analyzer의 별도 Backend/Streamlit 배포 | 최종 목표: DQA 단일 Backend/Web + PostgreSQL | **Cutover 미완료** | G1 parity, 검색 검증, 운영 인증/DBA 승인, Export/백업·복구, Rollback 성공 전 PoC 서비스/DB 중단 금지 |

## 3. 기술적 차이 및 주의사항

### 3.1 Fingerprint 비교는 규약별로 해야 함

Legacy의 `services/catalog_writer.py::schema_snapshot_fingerprint` 및
`services/fingerprint.py`와 DQA의
`services/schema_catalog_candidate.py::_physical_payload/_fingerprint`는
코드상 별개 경로다. **같은 스키마라도 SHA-256이 같을 것으로 가정하면 안 된다.**
DQA는 안전성 때문에 Oracle default SQL과 index_definition을 물리 payload에서
제외하며, Legacy의 컬럼 default·주석 등의 취급은 경로별로 다를 수 있다.

- 공통 비교용 canonical 구조는 `DB/schema + table/column + PK/UK/FK/index + comments`
  **실제 허용한 필드**로 규격화해야 한다.
- 원시 hash 동일성만으로 parity를 판정하지 말고 항목 단위 Diff 및
  양쪽 canonicalization version을 함께 보존해야 한다.
- 컬럼 타입·길이·정렬순서, FK 참조 대상이 스키마 범위 밖인 경우,
  dictionary view 가시성, expression index/unsupported object, 주석의
  null/empty 규칙을 Gold Fixture로 확인한다.
- 실제 Oracle과 연결된 검사 계정의 privilege completeness 및
  표준 범위는 군/DBA 서면 승인 전 검증됐다고 주장하지 않는다.

### 3.2 Legacy Preflight READY ≠ DQA Catalog READY

Legacy `catalog_package_finalizer.py::_package_readiness`는 성공 Run,
저장 Snapshot 및 persisted Preflight 상태를 사용해 `READY`를 산정한다.
이는 DQA가 요구하는 **독립적으로 인증된 DBA 증빙 + 수동 변경 검토 +
버전이 고정된 승인정책**과 같지 않다. Legacy ZIP을 단순히 `READY`로
포장하거나 DQA 내부에서 `WARNING`을 override하지 않는다.

S-04-C-2B-2A/B/C (PR #78~#80)는 테스트/내부 계약만 있고
외부 발급자 인증, 서명/철회 및 durable replay 검증은 아직 없다.
따라서 모든 내부 비교 성공도 `STRUCTURAL_MATCH_ONLY`이며
`NOT_VERIFIED`를 유지한다. 관련 미합의 정책은
[Draft PR #77](https://github.com/ramza2/dqa/pull/77)로 분리한다.

### 3.3 Target/접근 경계는 재설계 대상

Legacy Target CRUD는 다양한 DBMS와 사용자 지정 Host/Schema/Password를
관리한다. DQA의 Inspector는 승인된 단일 설정 Target 및 별도
`DEMIS_INSPECT_SECRET_` 계정으로 **개발망에서만** 실행한다.
DQA Read Query의 Connection Profile을 Inspector 권한과 혼용하거나
Legacy 저장 Credential/Catalog DB를 복사하지 않는다.
다중 Target·Schema가 반드시 필요한지는 U-01/U-04 및 DBA 정책의
후속 결정이다.

### 3.4 화면과 데이터 이행은 코드 동등성과 별도

DQA의 테이블·관계 조회는 ERD 사용자 경험을 보장하지 않으며,
Legacy DOCX 보고서는 기존 데이터 모델과 밀접하게 연결되어 있다.
레거시 테이블 ID, Source ID, Category 분류/검색 문서 연결의
새 Catalog Revision 대응 및 이행 후 재색인 검증이 필요하다.

## 4. 권장 구현 순서 (범위 협의 전 제안)

| 우선 | 후속 작업 | 선행 조건 / 검증 |
|---|---|---|
| **P0-1** | **U-02-A: Oracle Inspector metadata fixture parity harness** — Legacy와 DQA의 동일 synthetic Oracle 결과를 canonical field-level로 비교하는 오프라인 테스트 계획 및 실행 | 두 저장소 고정 SHA, Oracle Mock 전용 credential/DB 보호. 읽기 전용/운영 DB와 분리; 25-table fixture는 기준선 예시이지 전체 의료 DB의 완전성 증빙 아님 |
| **P0-2** | **U-02-B: Package v2 / Fingerprint contract parity** — Legacy 최종 package 검증, 공통 필드 목록·누락규칙·manifest compatibility 확인 | 현행 v2 validator 재사용; READY 자동 승격 금지, Category/관계/주석 보존·생략 필드 명시 |
| **P0-3** | **U-02-C: Cutover data inventory** — Target, Run, Snapshot, Category, Document/Embedding, Export의 이행/재생성/제외 결정표 | Source→Revision 매핑, 백업/복구, PoC DB 미수정 |
| **P1** | Inspector 운영 Target/Preflight 정책 결정 및 S-05 Portal 최소 UI | 군/DEMIS DBA 접근 허용 범위·검증 Identity/Target 관리 방식 |
| **P1** | ERD·DOCX Report·Category 편집의 필수/선택 범위 확정 | 실증기관/PM·PL 사용자 시나리오 확인 |
| **P1** | 검색 및 Embedding parity 자동 비교 | 동일 합성 자료/Gold Query, 같은 검색 범위·k·model/fingerprint 명시 |
| **G1 이후** | PoC 인프라 제거·단일 DQA Cutover | 메타데이터·검색 parity, 데이터 보존·복원, 실제 연계/권한 수용 및 운영 승인 |

**첫 개발 PR 권장 범위:** `U-02-A`의 parity 시험을
**문서/테스트 전용**, 고정 합성 fixture, DQA 운영 DB/Oracle 접근 없는
작은 Draft PR로 분리. PoC 원본 소스 복제·동적 패키지 설치·무자격한
실기관 연결은 금지한다.

## 5. 근거 코드 / 참조 (고정 커밋)

Legacy 기준선:
- [Oracle metadata collector](https://github.com/ramza2/demis-schema-search-poc/blob/c9b88f6f6d14dc2598765efbf6bb41b4771f9b25/backend/app/analyzers/oracle.py)
- [Target management](https://github.com/ramza2/demis-schema-search-poc/blob/c9b88f6f6d14dc2598765efbf6bb41b4771f9b25/backend/app/services/target_service.py)
- [Preflight](https://github.com/ramza2/demis-schema-search-poc/blob/c9b88f6f6d14dc2598765efbf6bb41b4771f9b25/backend/app/services/preflight_service.py)
- [Snapshot Diff](https://github.com/ramza2/demis-schema-search-poc/blob/c9b88f6f6d14dc2598765efbf6bb41b4771f9b25/backend/app/services/schema_diff_service.py)
- [Catalog v2 finalizer](https://github.com/ramza2/demis-schema-search-poc/blob/c9b88f6f6d14dc2598765efbf6bb41b4771f9b25/backend/app/services/catalog_package_finalizer.py)
- [ERD API](https://github.com/ramza2/demis-schema-search-poc/blob/c9b88f6f6d14dc2598765efbf6bb41b4771f9b25/backend/app/api/erd.py) / [DOCX report](https://github.com/ramza2/demis-schema-search-poc/blob/c9b88f6f6d14dc2598765efbf6bb41b4771f9b25/backend/app/services/catalog_report.py)

DQA 기준선:
- [Inspector](https://github.com/ramza2/dqa/blob/0d72e051f47e8fce9974aaba76abf1f761e1dbbf/backend/app/adapters/schema_inspector/oracle.py) / [read-only target binding](https://github.com/ramza2/dqa/blob/0d72e051f47e8fce9974aaba76abf1f761e1dbbf/backend/app/services/schema_inspection.py)
- [Immutable capture](https://github.com/ramza2/dqa/blob/0d72e051f47e8fce9974aaba76abf1f761e1dbbf/backend/app/services/schema_snapshot_history.py) / [Diff](https://github.com/ramza2/dqa/blob/0d72e051f47e8fce9974aaba76abf1f761e1dbbf/backend/app/services/schema_snapshot_diff.py)
- [v2 WARNING candidate](https://github.com/ramza2/dqa/blob/0d72e051f47e8fce9974aaba76abf1f761e1dbbf/backend/app/services/schema_catalog_candidate.py) / [Catalog import](https://github.com/ramza2/dqa/blob/0d72e051f47e8fce9974aaba76abf1f761e1dbbf/backend/app/services/catalog_package_import.py)
- [Preflight bridge](https://github.com/ramza2/dqa/blob/0d72e051f47e8fce9974aaba76abf1f761e1dbbf/backend/app/services/schema_preflight_snapshot.py) / [Data Discovery Search](https://github.com/ramza2/dqa/blob/0d72e051f47e8fce9974aaba76abf1f761e1dbbf/backend/app/services/data_discovery_search/service.py)

**미확인:** 두 시스템을 같은 실제 Oracle/Mock DB에 연결한 항목별 parity test,
Legacy 사용 DB 전체 데이터 이행량·스키마, 현행 사이트별 운영 용례,
실 DEMIS Inspector grant, PoC 중단 허가.
위 항목은 테스트/기관 확인 없이는 ‘동등’ 또는 ‘운영완료’로 처리하지 않는다.
