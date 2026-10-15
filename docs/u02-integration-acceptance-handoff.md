# U-02 — Schema Analyzer → DQA 통합 개발 검증 결과 및 운영 전환 인수인계

> **작성 기준: 2026-10-15 / DQA `main@838b63425c9fa7aa2af9824931d6b86439d722f5`**.
> **종합 판정: `DEV_SYNTHETIC_BASELINE_VERIFIED` / `REAL_DEMIS_PARITY_NOT_VERIFIED` /
> `CUTOVER_NOT_APPROVED`.** 본 문서는 *검증된 결과와 미검증 항목을 구분하는 보고서*이며,
> 인프라 변경·데이터 이전·외부 접근 허가·운영 인수 서류가 아니다.

## 1. 범위와 기준선

- Legacy 원본: [`ramza2/demis-schema-search-poc@c9b88f6f6d14dc2598765efbf6bb41b4771f9b25`](https://github.com/ramza2/demis-schema-search-poc/tree/c9b88f6f6d14dc2598765efbf6bb41b4771f9b25). 기존 PoC는 **운영 전환 승인 전까지 별도 유지**하며 원본 DB/Streamlit을 DQA로 그대로 복제하지 않는다.
- DQA: `ramza2/dqa@838b63425c9fa7aa2af9824931d6b86439d722f5` (PR #88까지 merge).
- 본 프로젝트의 최종 목표: **DQA 단일 배포**, 승인된 read-only DEMIS 조회, 표준 FHIR/SNUH.AI 경계 및 별도 승인 범위의 향후 Controlled Write. 구현 여부와 운영 승인을 혼동하지 않는다.
- [기존 U-02 기능별 원본 Gap 매트릭스](u02-schema-analyzer-dqa-gap-analysis.md)는 2026-10-14 정적 분석 **시점 스냅샷**이다. 그 안의 “parity 미검증” 표기를 소급 변경하는 대신 이번 증빙 레지스터로 후속 검증 상태를 추적한다.

## 2. 병합된 개발·격리 시험 증빙

| 단계 | Merge PR / SHA | 관측된 증빙 | **증명하지 않는 것** |
|---|---|---|---|
| **U-02-A** | [#82](https://github.com/ramza2/dqa/pull/82) / `975990a` | 고정 Legacy Oracle Inspector와 DQA Inspector를 **합성 Oracle Dictionary FakeEngine** 및 별도 subprocess로 비교. 컬럼·키·관계/주석·정렬 등 정규화 차이를 검사 | 실제 DEMIS Oracle Dictionary 접근·전체 실스키마 가시성 |
| **U-02-B-1** | [#83](https://github.com/ramza2/dqa/pull/83) / `4f04870` | Legacy/DQA Fingerprint 정규화 차이 및 DQA v2 `WARNING` 후보 계약 검사 | 원시 SHA가 같다는 주장, 실제 READY 승인 |
| **U-02-B-2-A** | [#84](https://github.com/ramza2/dqa/pull/84) / `93f7a64` | 실제 Legacy finalizer로 합성 Session의 v2 ZIP 생성·DQA validator 구조 검증, READY/WARNING/BLOCKED 구분 | 운영 DB·실패 없는 현장 수용, 실제 DQA Import/Activation |
| **U-02-B-2-B** | [#85](https://github.com/ramza2/dqa/pull/85) / `ded1b32` | 분리된 PostgreSQL+pgvector에서 원본 Legacy ORM과 2회 Run/Diff/Preflight/DOCX를 사용한 최종 ZIP 검증. 서버 `69 passed`, `DQA_U02B2B_ACCEPTANCE_PASS` | 운영 데이터·실 DEMIS/DBA Preflight |
| **U-02-C-1** | [#86](https://github.com/ramza2/dqa/pull/86) / `115c567` | 원본 **17개 ORM 테이블** 처분 분류, Source/Run/Snapshot·Category/Embedding·자격증명 이관 규칙. 서버 `4 passed`, `DQA_U02C_INVENTORY_PASS` | 운영 Legacy 테이블 건수와 실제 Source ID 매핑 |
| **U-02-C-2** | [#87](https://github.com/ramza2/dqa/pull/87) / `060d2ff` | 격리 PostgreSQL의 합성 Source 2개, 17개 테이블 집계, 별도 **SELECT-only Reader**와 Run→Snapshot 연결 검사. 서버 `15 passed`, `DQA_U02C2_ACCEPTANCE_PASS` | 실제 Source/Run 이관·승인 |
| **U-02-C-3** | [#88](https://github.com/ramza2/dqa/pull/88) / `838b634` | 합성 Catalog DB `pg_dump -Fc`→별도 DB `pg_restore`, 원본/복구 건수·행 Digest·Manifest SHA-256 검증. 서버 `32 passed`, `DQA_U02C3_ACCEPTANCE_PASS` | **운영** 백업/복구·RTO/RPO·실 데이터 정합성·Rollback 허가 |

**증빙 범위 주의:** 위 시험은 서로 다른 범위의 합성/격리 테스트이다. 통과 수 합산은 통합 인수 기준이 아니며, 운영 DB에 적용된 인프라/권한/배포 상태를 나타내지 않는다. #88은 테스트용 restore DB만 사용했고 실 DQA Catalog Revision을 생성하거나 활성 포인터를 바꾸지 않았다.

## 3. 기능별 현 상태: 기반 구현과 최종 통합의 차이

| 기능 영역 | 지금 코드에 존재하는 것 | 운영 전환 전 남은 작업 / 판단 | 연결 요구 |
|---|---|---|---|
| Oracle Inspector | 승인된 설정에 묶이는 DQA metadata-only Inspector·합성 동등성 시험 | DBA 승인 Source/Schema, Data Dictionary grant/가시성, 실제 Oracle 포함·누락 항목 동등성 | S-01·S-02 / G0·G1 |
| Snapshot·Diff | DQA append-only Revision, Source 격리, 변경 비교·검토 기반 | Legacy 전체 Run/실 Snapshot 복원 정책, 복합 FK/인덱스 변화·운영 조회 범위 검증 | S-03·S-04 / G1 |
| v2 Catalog | 외부 Package validator, immutable Import, READY-only 수동 활성화, DQA 내부 `WARNING` 후보 | 신뢰된 Preflight·수동 변경 검토·실제 `READY` 발급자/권한/만료/철회·활성화 연결 정책 | S-03·S-04 / G0·G1 |
| 독립 Preflight | 내부 구조 계약/Mock, `NOT_VERIFIED` 경계; [독립 증빙 정책 제안 #77](https://github.com/ramza2/dqa/pull/77)은 **Draft 미병합** | 군/DBA가 인정하는 독립 발급자, 지점·시점·권한·재사용 차단·검증 범위 확정 전 운영 `VERIFIED` 금지 | S-01·S-04 / G0·G1 |
| 데이터 이관 | 17 ORM 테이블 처분표, Source/Run 연결 집계, **합성** DB 백업·복원 검증 | 실제 Legacy 데이터 규모·백업/전체 이력·ZIP/DOCX 보존, `source_id`→`source_name`→Import Revision Crosswalk, 복구 계획 | X-05 / G5 |
| 검색·Embedding | Data Discovery Keyword/Semantic/Hybrid, 활성 Revision 기준 문서/1024d 벡터 관리 | Legacy/DQA 동일 Gold Query·rebuild/coverage·의미분류 provenance·복합관계 시나리오 parity | S-06 / G1 |
| UI·보고서 | Catalog/Source 탐색 및 Data Discovery React UI | PoC의 Target CRUD/Preflight/ERD/DOCX/Category 편집 필요 기능 결정 후 권한·감사·출처 경계를 지키는 최소 UI | S-05 / G0·G1 |
| DEMIS 조회·외부 연계 | 조회용 승인 Query Template, 읽기 전용 Adapter, 내부 MCP 기반 | 군 조회권한·IdP/네트워크·실행 감사; FHIR·SNUH.AI 공통 ICD와 외부 호출자 인증 | U-04·R-01~04 / G0·G2 |
| 의료 쓰기 | **아직 허가된 Write 실행 경로 없음**. DQA SELECT-only 원칙 유효 | 공식 저장 API/Insert 허용 여부, 필드·상태·임상의 서명 승인, 별도 Write 계정·재검증·멱등·감사 설계 | W-01~07 / G0·G3·G4 |

현재 내부 Mock/테스트 증빙은 “기반 구현” 판단에만 사용한다. 기능별 잔여 Gap의 원문 ID U02-01~15와 상세 수용조건은 [초기 Gap 분석](u02-schema-analyzer-dqa-gap-analysis.md) 및 [17개 데이터 처분표](u02-c-legacy-cutover-inventory.json) 참고.

## 4. 현재 결정되지 않은 외부 의사결정

별도 [대외 의사결정 레지스터](u02-external-decision-register.md)에 요청 주체·필요 증빙·차단사항을 분리했다. 모두 **미승인/미검증**으로 취급한다.

- **G0 (권한/책임 경계):** Inspector Target/Secret과 조회·쓰기 계정 분리, DEMIS Schema 범위, FHIR/SNUH.AI ICD, 증빙 검증 책임.
- **G1 (실 스키마 동등성):** DBA 승인 Schema Scope의 실제 Oracle Metadata와 PoC/DQA 비교, 복합 FK·주석·누락/가시성, 검색/ERD/문서 회귀.
- **G2 (실 조회):** IdP, 네트워크/TLS, 최소 SELECT 권한, Query Template/감사 로그/비식별 범위 승인.
- **G5 (Cutover):** 실제 데이터 인벤토리와 Category/검색/Embedding 보존, 원본 ZIP/DOCX, 암호화 백업·복구·감사, 독립 Analyzer 중단 및 복구 책임을 서면 승인.
- **W-01/G4 (추후 쓰기):** 공식 기록 저장 API/별도 Insert 허용 범위 및 임상 승인/보안 정책 확정 전 실제 DEMIS Write 불가.

## 5. 최종 수용/No-go 원칙

- **지금 판정:** `DEV_SYNTHETIC_BASELINE_VERIFIED`, `REAL_DEMIS_PARITY_NOT_VERIFIED`, `CUTOVER_NOT_APPROVED`. 이것은 후속 개발 계획의 입력으로는 충분하지만 현장 운영 승인이 아니다.
- 실제 소스/실환자 데이터 조회, 비승인 SQL 실행, 인증·암호문/연결정보 무단 이행, Legacy DB 직접 테이블 복제 및 Streamlit 운영 종료 금지.
- Legacy `READY` 패키지가 DQA validator에서 structurally eligible이어도 **독립 DBA/기관 승인 완료를 뜻하지 않는다**. 외부 Preflight/승인 Gate를 우회하거나 DQA 내부 `WARNING`을 자동 `READY`로 승격하지 않는다.
- Snapshot은 **Execution Authority 아님**; 검증된 READY Import Revision의 **명시적 활성화**와 감사가 권위의 근거다.
- Controlled Write는 별도의 승인·설계·테스트·보안 PR에서만 진행한다. 기존 읽기 Adapter/계정을 쓰기로 전용하지 않는다.
- **G5 미통과 중에는** PoC 서비스/DB/백업 볼륨 중단·삭제 및 단일 DQA 운영 전환 금지.

## 6. 인수인계 후 권장 실행 순서 (개발 PR과 승인 업무 분리)

1. **U-03/G0 문서 정합화:** 최종 아키텍처와 현재 read-only 금지를 동시에 표시하고, root/backend `AGENTS.md`·README·Runbook의 과거 별도 서비스 표현을 *승인된 범위에서만* 수정. **코드/권한 변경 없이 분리 PR**.
2. **S-01, U-04 외부 정책 확정:** 군/DBA·보안·FHIR·SNUH.AI의 Source/Schema/Preflight 발급·ICD 승인 책임을 문서화. 정책 미승인 중 Positive `VERIFIED` 구현 금지.
3. **S-03/S-04/S-05 최소 기능:** 승인된 범위의 Snapshot→v2→Review/Import/수동 활성화·운영 UI를 작고 독립적인 PR로 구현. 기존 Validator·Read safety 유지.
4. **S-06 회귀 자동화:** 확장 합성 Gold Fixture와 문서·검색·Category parity, stale Source/revision UI safety. 필요 시 별도 격리 DB 테스트.
5. **G1/G2/G5 현장 단계:** 접근 허가 후 실제 DBA 증빙 확보, 범위 확인, 백업/복원·ID 매핑·FHIR E2E/검색품질·롤백 리허설, 기관 서면 수용. **허가 전 실행하지 않음**.

### 참고 문서

- [원본 기능별 Gap 분석](u02-schema-analyzer-dqa-gap-analysis.md)
- [U-02-C-1 이관 표/단계별 Gate](u02-c-cutover-plan.md)
- [U-02-C-2 격리 Read-only 데이터 조사](u02-c2-isolated-counts-and-mapping.md)
- [U-02-C-3 PostgreSQL 복구 리허설](u02-c3-backup-restore-rehearsal.md)
- [통합 플랫폼 아키텍처](integrated-platform-architecture.md) / [WBS 및 Gate](roadmap.md)
