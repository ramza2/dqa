# DQA Development Roadmap

> **2026-10-13 통합 플랫폼 전환 WBS 초안** · 과제 전체 종료 기준 **2027-08-16**.
> 현재 배포 검증은 Oracle Mock/개발망 증빙이다. 실제 DEMIS 임상 사용,
> Insert 권한, 운영 IdP, SNUH.AI/FHIR 연계 승인은 확보되었다고 가정하지 않는다.
>
> 신규 목표와 단계별 acceptance는 아래 **Unified Platform WBS**가 우선한다.
> 그 아래 Phase 0–30 내용은 **기존 구현 이력 및 당시 로드맵**으로 보존한다.
> 특히 기존 Phase 26-B의 독립 Schema Analyzer 배포 경계와 'DQA read-only'
> 원칙은 **최종 제품 목표와 다르며**, 현재 코드/AGENTS의 엄격한 제한은
> 해당 변경 PR과 기관 승인 전까지 계속 유효하다.
>
> 상세 계약: [Integrated DQA Platform Architecture](integrated-platform-architecture.md).
> 기능 개발은 작은 Draft PR, 테스트, 사용자 명시적 Merge 승인으로 진행한다.

## Unified Platform WBS — DEMIS Schema Analyzer 통합 + 조회/승인 Insert + MCP

### A. 기준·범위·일정

- **최종 배포 단위:** DQA Web + Backend(Inspector/Catalog/Read/Controlled Write/MCP)
  + PostgreSQL/pgvector. 기존 `demis-schema-search-poc` 웹/Backend/Catalog DB
  운영 의존성은 Parity 및 데이터 이행을 거쳐 제거한다. PoC 저장소는 평가 근거로 보존.
- **연계 책임:** DQA는 DEMIS 접근 및 업무별 Tool/내부 API. 메디칼스탠다드는
  DEMIS/PACS 등 다원천 데이터를 FHIR R4로 표준화. 인프메딕스/SNUH.AI는
  Agent·Workflow 및 임상 검토 연계를 담당.
- **쓰기 범위:** 승인된 의무기록 초안과 진료/진단보조 결과의 대상별
  DEMIS Insert(공식 API 우선 검토). **기존 조회용 Oracle Adapter를 Write에 재사용 금지.**
  임의 SQL, 무승인 자동 확정, 포괄 UPDATE/DELETE/MERGE는 제외.
- **일정:** 아래 월 구간은 *계획 기준선(잠정)*이며 인력 투입량·일자별 착수일은
  확정 WBS가 아니다. 선결 군/DEMIS 접근 권한·FHIR ICD·임상 승인 정책에
  따라 재산정한다. 종료 목표는 2027-08-16.
- **역할:** PM, PMO, PL, SA, DBA, 백엔드, AI엔지니어, QA, 보안, 인프라.
  외부 기관은 '군/병원/DEMIS 운영', 'FHIR(메디칼스탠다드)',
  'SNUH.AI(인프메딕스)'로 표현. 모든 개발 완료의 운영 승인 대체 금지.
- **상태:** `검증완료(개발)` / `진행` / `계획` / `외부결정 대기`.
  **행의 일정·담당은 제안안**이며 계약상 업무분장 확정이 아니다.

### B. 단계별 WBS (상위 산출물 및 선후행)

| WBS | 작업·내용 | 목표 구간 | 주 역할·협조 | 선행 / Gate | 산출물·완료 기준 | 상태 |
|---|---|---|---|---|---|---|
| U-01 | DQA 단일 플랫폼 아키텍처 및 책임분담 재정의 | 2026-10 | PL·SA / FHIR·SNUH.AI | 없음 / G0 | 논리·배포 구성, 조회/쓰기 경계 및 운영 책임 합의 | 진행 |
| U-02 | 기존 Analyzer→DQA 기능/코드/데이터 Gap 분석 | 2026-10~11 | PL·백엔드·DBA | U-01 | 이관/재사용/제외 목록 및 스키마 동등성 기준 | **진행 — 합성/격리 검증 기준선 완료, 운영 수용 대기** |
| U-03 | `AGENTS.md`·README·운영 Runbook 및 보안 규칙 정합화 | 2026-10~11 | PL·SA·보안 | U-01 / G0 | 기존 read-only 금지 규칙 변경은 승인 범위로만 분리·현행화 | **진행 — 현재 구현/최종 목표 문서 정합화, G0 외부승인 대기** |
| U-04 | DQA ↔ FHIR ↔ SNUH.AI ICD·호출 경로 확정 | 2026-11~12 | SA·PL / FHIR·SNUH.AI | U-01 / G0 | MCP vs REST, 공통 JSON, 환자/Encounter·trace·오류·소유권 계약 | 외부결정 대기 |
| S-01 | Schema Inspector Target 및 metadata credential 정책 | 2026-11 | SA·DBA·보안 | U-02, U-03 | 검사 계정과 조회/쓰기 계정 격리; 허용 스키마 범위 | **진행 — 합성 정책/Dictionary 거부 회귀 검증, G0·DBA 승인 대기** |
| S-02 | Oracle Schema Inspector·connection diagnostics 이관 | 2026-11~12 | 백엔드·DBA | S-01 | Table/Column/PK/UK/FK/Index/Comment 수집 테스트 | 계획 |
| S-03 | Snapshot·fingerprint·Catalog Package v2 생성·검증 연결 | 2026-12 | 백엔드·DBA | S-02 | 기존 immutable import/READY 활성화 경로 재사용 | 계획 |
| S-04 | 스키마 변경 Diff·검토·활성화 및 오류 복구 | 2026-12~2027-01 | 백엔드·QA | S-03 | 수동 승인·이전 Revision 보존·실패 시 rollback | 계획 |
| S-05 | DQA 포털 Target/Analyze/Revision 운영 UI | 2027-01 | 프론트엔드(백엔드)·PL | S-03, S-04 | 독립 Streamlit 없이 분석/상태/변경 확인 | 계획 |
| S-06 | Analyzer parity + 문서/Embedding 동기화 회귀 평가 | 2027-01~02 | QA·AI엔지니어·DBA | S-04, S-05 / G1 | 25-table Oracle Mock 기본 fixture 및 확장 테스트, Gold Set/검색 품질 확인 | 계획 |
| R-00 | 기존 Catalog/검색/Gateway/Frontend Mock 검증 기준선 고정 | 2026-10 | PL·QA | 기존 배포 / G0 | 231/231 embeddings READY, Keyword/Semantic/Hybrid 및 HTTP smoke evidence | 검증완료(개발) |
| R-01 | 실제 DEMIS 조회 Profile·권한·배포 네트워크 협의 | 2026-11~2027-01 | DBA·보안·인프라 / 군·DEMIS 운영 | U-04 | 최소 SELECT 권한, live probe, 리소스 접근 정책 문서 | 외부결정 대기 |
| R-02 | 승인 Query Template / 의료업무 logical resource 매핑 | 2026-12~2027-02 | SA·백엔드·의료 QA | S-03, U-04 | Patient/Encounter/Document 등 **승인된** resource·필드 매핑 | 계획 |
| R-03 | MCP/REST 공통 조회 API 및 서비스 인증 경계 강화 | 2027-01~03 | 백엔드·보안 / FHIR·SNUH.AI | U-04, R-02 | Web/MCP/REST 동일 Safety·Audit, 호출자·권한 및 오류 계약 | 계획 |
| R-04 | Oracle Mock 조회 E2E와 FHIR 조회 계약 연동 | 2027-02~03 | 백엔드·QA / FHIR | R-03 | 승인된 query preview/execute, 반환 JSON, 감사 연계 | 계획 |
| R-05 | Phase 29 Structured Dynamic Query 후속 범위 판단 | 2026-10~2027-03 | PL·SA·백엔드 | R-02 / 별도 승인 | 29-C preview-only 유지, 29-D 실제 실행은 별도 보안 Gate | 진행 |
| W-01 | DEMIS Insert 지원 방식·DBA grant·문서 유형 확인 | 2026-10~12 | PM·PL·SA·DBA / 군·병원 | U-01 | 공식 저장 API/직접 INSERT 허용 범위, 저장 위치/상태·지원불가 항목 서면 확인 | 외부결정 대기 |
| W-02 | 임상의 승인증빙·책임·취소/만료 정책 및 필드 계약 | 2026-12~2027-01 | SA·보안·의료 QA / 군·SNUH.AI·FHIR | W-01, U-04 / G0 | 검증 가능한 approval reference, source/payload digest, clinician identity, patient/Encounter | 외부결정 대기 |
| W-03 | Write Operation Registry·payload schema·RBAC·별도 계정 설계 | 2027-01~02 | SA·백엔드·DBA·보안 | W-01, W-02 | Allowlist, record draft 상태, `WRITE_PREPARE/COMMIT`, 기본 disabled | 계획(승인 후) |
| W-04 | `prepare_write` Tool/API: 임상컨텍스트·문서 정합성 검증 | 2027-02~03 | 백엔드·QA | W-03 | PREPARED/NEEDS_APPROVAL/BLOCKED, DB 쓰기 없음 | 계획(승인 후) |
| W-05 | 별도 ControlledWriteAdapter 및 최소권한 실행 | 2027-03~04 | 백엔드·DBA | W-03 / G3 준비 | 실제 지원 인터페이스에서만 bound insert; 트랜잭션·제한 테스트 | 계획(승인 후) |
| W-06 | `commit_write`·`get_write_status`·승인 재검증/멱등성 | 2027-03~05 | 백엔드·보안·QA | W-04, W-05 | 위조/만료 승인 차단, 중복·모호한 commit 처리, audit fail-closed | 계획(승인 후) |
| W-07 | Synthetic Oracle Mock 쓰기 E2E·장애/재시도·의료 QA | 2027-05~06 | QA·DBA·보안·의료 QA | W-06 / G3 | 승인 없는 쓰기 0, 멱등/재시도/권한/감사/대사 테스트 PASS | 계획(승인 후) |
| X-01 | FHIR/SNUH.AI 조회·승인 결과 처리 통합 시험 | 2027-04~06 | PL·백엔드·QA / FHIR·SNUH.AI | U-04, R-04 | 데이터 소유권/표준화 경계 유지, end-to-end trace·error mapping | 계획 |
| X-02 | 운영 인증·네트워크·비밀·감사·복구 하드닝 | 2027-04~07 | 보안·인프라·DBA·QA | R-01, W-06 / G2 | approved IdP, TLS, least privilege, 백업·복원, observability | 계획 |
| X-03 | 제한적 실 DEMIS 조회 실증 | 2027-06~07 | PL·QA·DBA / 군·DEMIS 운영 | R-04, X-02 / G2 | 비식별/최소 범위 SELECT, 감사 및 DBA evidence | 외부승인 필요 |
| X-04 | 제한적 실 DEMIS 임상문서 Insert 실증 | 2027-07~08 | PM·PL·QA·DBA·의료 QA / 군·병원·SNUH.AI | W-07, X-02 / **G4** | 서명 승인 범위 내 특정 문서, 중복/취소/대사 및 안전성 판정 | 외부승인 필요 |
| X-05 | Schema Analyzer 의존성 제거·배포/롤백 Cutover | 2027-07~08 | PMO·PL·인프라·QA | S-06, X-01, X-03 / G5 | 단일 DQA 운영, legacy 서비스 비활성, 데이터 보존/복구 승인 | 계획 |
| X-06 | 최종 운영 인수·실증 보고/산출물 정리 | **~2027-08-16** | PM·PMO·PL·QA | X-05, X-04 조건부 | 검증 결과서·미완료 대외 리스크/범위 명시·운영 매뉴얼 | 계획 |

*운영 기간/완료 Gate는 군 실증기관·컨소시엄 협의에 따라 변경될 수 있다.
의료 QA는 각 기관 전문인력 협조 역할이며 DQA 개발 역할을 임의 확대하지 않는다.*

> **U-02 검증 증빙 현행화 (2026-10-15):** Legacy Inspector·v2 Package/Fingerprint·17개 ORM 이관 분류·합성 Source/Run 및 격리 PostgreSQL 백업/복구 시험은 [#82–#88 검증 결과](u02-integration-acceptance-handoff.md)로 병합 완료. 이는 **개발·합성환경 기준선**이며 **실 DEMIS Schema/권한/Preflight 승인·데이터 이관·운영 Cutover 완료가 아니다.** 남은 외부 결정은 [U-02 승인/차단 레지스터](u02-external-decision-register.md) 참조. 원본 Analyzer 중단은 G1·G5 수용 후 별도 서면 승인까지 금지한다.

### C. Gate / 의사결정 및 선후행 요약

| Gate | 결정 항목 / 검증 책임 | 통과 전 금지 |
|---|---|---|
| G0 — architecture | 컨소시엄과 군의 인터페이스/데이터 책임, 승인 주체·업무 범위 확정 | 운영 임상 쓰기 설계 확정·인터페이스 임의 고정 |
| G1 — Inspector parity | PoC와 동일 스키마 Snapshot/관계/Fingerprint 비교, 인덱스/검색 테스트 | 기존 Analyzer 사이트 운영 종료 |
| G2 — real read | 운영 IdP·권한·최소 SELECT DBA 검증, 감사, 암호화, 실 DEMIS 조회 수용 | 실 환자 조회 및 외부 MCP 노출 |
| G3 — write mock | 기관이 승인한 write 계약에 맞춘 synthetic fixture의 승인/멱등/오류 복구 | 실 DEMIS Write 활성화 |
| G4 — real write | 군/병원·DEMIS 운영자의 공식 저장방식·필드·권한·임상 승인·실증 시나리오 **서면 승인** | 실제 의무기록/진료 결과 Insert |
| G5 — cutover | DQA 기능 동등성, FHIR/SNUH.AI, 백업·복원, 감사를 포함한 인수 승인 | 독립 Analyzer 운영 중단/볼륨 삭제 |

**Critical path (조건부):** U-01 → U-04/W-01 → W-02 → W-03 →
W-04/W-05 → W-06 → W-07 → G4 → X-04 → X-06.
FHIR ICD나 실제 DEMIS 승인 지연 시 임상 Insert는 `BLOCKED`로 남기고
기존 조회 기능과 스키마 통합 검증의 진행을 독립적으로 관리한다.

### D. 구현 단위 / PR 분리 원칙

각 행은 1개 이상의 작은 PR로 분해한다. 권장 단계:
1. **Documentation & governance:** 현재 2종 문서 → root/backend `AGENTS.md`,
   README, 실제 DEMIS Runbook·권한 정책의 **승인된** 정합화.
2. **Inspector:** Oracle metadata driver → Snapshot/Package → Diff/activation →
   DQA 운영 UI → parity tests. DB Migration과 secrets handling은 개별 PR.
3. **Read integration:** 승인된 logical mapping/Template → REST/MCP contract →
   mock E2E → 생산 인증/병원 검증. 기존 4종 MCP Tool의 backwards compatibility 유지.
4. **Write:** 범위 확정/승인 증빙 계약 → policy & registry → prepare-only →
   adapter → commit/idempotency/status → synthetic E2E → 승인된 실 DEMIS 수용.
   **조회 토큰을 쓰기 토큰으로 재사용하지 않는다.**
5. **Cutover:** Analyzer 데이터·스키마 동등성, 검색 품질, 연결 운영,
   복구 리허설 후 명시적인 운영 승인 하에 서비스 종료.

Phase 29-C Oracle SELECT compiler는 **preview-only** 진행 이력으로 유지.
Phase 29-D의 실행 연계는 읽기 전용 안전 Gate부터 분리 검토한다.
새 임상 Write 기능과 Dynamic Query 기능은 하나의 PR로 섞지 않는다.
과거 동작을 임의 변경하거나 이전 DB Volume을 삭제하지 않는다.

### E. 테스트·수용 기준 (자동·수동 구분)

- **Schema:** Source 및 Revision 격리, 최소 권한, Oracle metadata parity
  (테이블/컬럼/PK/FK/Index/Comment), 변경 탐지와 Catalog READY-only activation,
  구축 실패 시 이전 상태 보존.
- **Search:** keyword/semantic/hybrid, relation/medical expansion,
  `vector(1024)` 호환, model_key 및 fingerprint 일치, Golden Query 근거,
  검색/인덱스 stale guards.
- **Read/MCP:** Template compatibility, payload validation, principal RBAC,
  token expiry/actor/catalog/profile revalidation, row-limit/timeouts,
  audit fail-closed, FHIR 계약과 Web/MCP 결과 일관성.
- **Clinical Write:** 서버 승인 증빙 검증(원본 문서 해시·환자·Encounter·
  version·승인자·유효기간/취소), 권한 분리, operation whitelist,
  중복/타임아웃/부분실패/미확정 commit 대사, 응급 중단·복구, 의료 QA 안전성 판정.
- **Security:** production/dev_header 혼용 방지, 운영 IdP, 사설 ingress,
  TLS, DB 최소 권한, PHI/초안·SQL·비밀값 로그·Git·AI 반출 차단,
  감사 retention/backup/restore.
- **Integration:** FHIR가 PACS/기타 시스템을 표준화하는 책임 유지,
  DQA는 DEMIS 데이터 접근까지만 담당, 직·간접 MCP 호출 양쪽에서
  동일 접근정책이 강제되는지 확인.

### F. 외부 협조 요청·위험 등록부

| 우선도 | 외부 협조/위험 | 필요 결정 / 대응 |
|---|---|---|
| P0 | DEMIS 공식 Insert 가능 여부 | 쓰기 API/프로시저/DB 직접 Insert 허용 여부, 업무별 테이블·상태·DBA 권한 및 책임 주체를 군/DEMIS 운영자와 합의. **미승인이면 실행 금지** |
| P0 | 임상의 승인 증빙 | SNUH.AI 임상 Workflow 승인 주체, 검증 가능한 토큰/참조/해시, 취소/만료/사후 변경 정책 확정 |
| P0 | 운영 Identity & patient scope | 서비스 인증, 의료진 권한, 환자/Encounter 조회·기록 권한과 최소 데이터 반환 정책 |
| P0 | FHIR/SNUH.AI 호출 계약 | FHIR는 DEMIS/PACS/기타 표준화; 누가 DQA MCP/REST 호출하는지, Canonical JSON, 오류·idempotency·trace 표준 합의 |
| P1 | 실제 DEMIS 스키마 접근 | Dictionary view/검사 계정 및 SELECT 범위 승인, 최종 Schema·의무기록 쓰기 대상 분석 |
| P1 | DQA 저장/데이터 운영 | 백업 암호화·복원, 보관기간, 임상/쓰기 감사, 장애 시 원장 대사 |
| P1 | PoC 종료 위험 | Catalog 수집·변경/검색 parity 미달 시 기존 Analyzer 운영 유지 및 롤백 |

**Baseline evidence / remaining blockers (2026-10-13):**
DQA Oracle Mock Catalog 25 tables; Data Discovery 231 documents +
231 embeddings (READY); Keyword/Semantic/Hybrid in Web and API PASS;
Backend↔ModelOps Gateway PASS; frontend/backend/pgvector runtime PASS.
**이번 세션 Oracle Mock의 DEMIS_RO 비밀번호 인증 및 실제 SQL은 SKIP**,
실 DEMIS 접근·계정 권한, 운영 IdP, FHIR/SNUH.AI E2E, 의료용 Insert는
미검증/승인 전이다. 별도 과거 mock 기록이 있어도 실 DEMIS 수용 근거가 아니다.

---

## Historical implementation phases (Phase 0–30; retained for traceability)

## Phase 0 - Bootstrap

### PR 1 - Project bootstrap
Scope:
- AGENTS.md
- Cursor Rules
- architecture/security/contract documents
- directory skeleton
- environment placeholder

No business feature implementation.

## Phase 1 - Catalog foundation

### PR 2 - Backend application skeleton
Scope:
- FastAPI application
- settings
- PostgreSQL connection
- health endpoint
- pytest baseline
- Docker development skeleton

### PR 3 - Catalog Package v2 validation
Scope:
- safe ZIP reader
- manifest parser
- version validation
- checksum validation
- required JSON validation
- zip-slip / duplicate-entry / zip-bomb defenses
- tamper tests

No activation yet.

### PR 4 - Catalog import persistence
Scope:
- immutable package import revision
- archive SHA-256 / manifest SHA-256
- normalized import metadata
- package validation status
- import history API

### PR 5 - Active Catalog management
Scope:
- READY-only activation policy
- WARNING/BLOCKED inspection behavior
- active revision per source
- activation audit

## Phase 2 - Catalog exploration

### PR 6 - Catalog query APIs
Scope:
- tables
- columns
- relations
- indexes
- categories
- filters/search

### PR 7 - Catalog Explorer frontend
Scope:
- active package status
- table/column explorer
- relationship view
- package revision visibility

## Phase 3 - Query Template management

### PR 8 - Query Template registry
Scope:
- template + version model
- parameter schema
- draft CRUD
- Catalog compatibility metadata

### PR 9 - Approval workflow
Scope:
- IN_REVIEW / APPROVED / REJECTED
- enable/disable
- immutable approved version behavior
- approval audit fields

### PR 10 - SQL safety validator
Scope:
- one statement
- SELECT / WITH ... SELECT allow rules
- reject FOR UPDATE / SELECT INTO
- parser/tokenizer
- forbidden construct rejection
- declared parameter validation
- focused adversarial tests

No live DEMIS execution yet.

## Phase 4 - Recommendation

### PR 11 - LLM provider abstraction
Scope:
- OpenAI-compatible client interface
- structured response model
- timeout/error handling
- provider test doubles
- no query-result data egress

### PR 12 - Template retrieval/recommendation
Scope:
- candidate retrieval
- LLM ranking
- confidence/clarification
- no execution

### PR 13 - Parameter extraction
Scope:
- structured extraction
- deterministic type/constraint validation
- clarification workflow

## Phase 5 - Production execution prerequisites

### PR 14 - Authentication / RBAC foundation
Scope:
- authenticated actor abstraction
- roles/permissions foundation
- template author/approver/operator/auditor authorization points
- test/dev identity provider abstraction

### PR 15 - Connection Profile management
Status: implemented (foundation)
Scope:
- source/environment -> live DEMIS target binding
- non-secret connection metadata
- secret-reference boundary
- enable/disable
- sanitized connection diagnostics
- no live query execution yet
- administrator-only `CONNECTION_PROFILE_MANAGE` API protection
- Alembic migration for `connection_profiles`

### PR 16 - Audit foundation
Status: implemented (foundation)
Scope:
- request/execution audit model
- active Catalog revision/fingerprint
- template/version
- actor
- sensitive parameter logging policy (`NAMES_ONLY`)
- no full result-set logging by default
- append-only `query_audit_events` + `AUDIT_READ` list/get API
- Alembic revision after `connection_profiles` (`20260929_cp01`)
- not yet wired into recommendation / extraction / execution paths

## Phase 6 - Read-only execution

### PR 17 - DEMIS read-only adapter
Status: foundation contracts landed; Oracle thin-mode concrete adapter added
in a follow-up PR (`feat/oracle-readonly-adapter`).
Scope:
- DBMS-neutral adapter interface (`diagnostics`, `execute_readonly`)
- credential resolver protocol
- production `EnvironmentCredentialResolver` (`env:` + dedicated prefix boundary)
- Connection Profile snapshot eligibility (enabled + target metadata + credential ref)
- production factory fail-closed for unsupported DBMS; no DQA PG fallback
- test/fake adapter only (never production-selectable)
- read-only session/transaction / timeout / bound parameters / row limit contract
- sanitized connection diagnostics (`live_connection_tested=false` until probed)
- least-privilege assumptions documented

### PR 17c - Oracle read-only concrete adapter
Status: landed (`OracleReadOnlyDemisAdapter`, python-oracledb thin mode).
Scope:
- register `oracle` in the production concrete adapter factory
- bound SQL + parameters; `SET TRANSACTION READ ONLY` before SELECT
- call timeout; row_limit+1 truncation; rollback/close cleanup
- sanitized CONNECTION_FAILED / TIMEOUT / EXECUTION_FAILED mapping
- no Instant Client / thick mode; development-only Oracle mock network wiring is provided by `docker-compose.onprem.oracle-mock.yml`
- fake/test/mock/memory remain non-selectable

### PR 17b - Environment credential resolver
Status: landed on top of adapter foundation / preview.
Scope:
- `EnvironmentCredentialResolver` for `env:<NAME>` only
- `DQA_DEMIS_CREDENTIAL_ENV_PREFIX` allowlist boundary (default `DEMIS_SECRET_`)
- `create_credential_resolver(settings)` factory
- no DEMIS driver / connection / execute API
- Connection Profile and preview still store/check references only (no resolve)

### PR 18 - Execution preview and eligibility gate
Status: landed (`POST /api/v1/query-executions/preview`).
Scope:
- complete production execution eligibility gate (reusable service)
- executable eligibility checks (template/catalog/SQL/params/profile)
- preview API (`QUERY_OPERATE`); Oracle is production-selectable while unsupported DBMS/profile paths fail closed
- failure categories for preview/eligibility

### PR 18b - Query execution service + durable audit
Status: orchestration landed (`POST /api/v1/query-executions/execute`).
Scope:
- explicit user execution action (`QUERY_OPERATE`)
- re-run eligibility independently of preview
- durable audit writer (independent commit; fail closed on AUDIT_UNAVAILABLE)
- QUERY_REQUEST / QUERY_EXECUTION lifecycle (STARTED|SUCCEEDED|DENIED|FAILED)
- adapter factory + credential resolver wiring; normalized result response
- Oracle concrete adapter is selectable; unsupported DBMS, invalid profile, and unavailable credential paths remain fail closed
- fake adapter only via Python test DI (never HTTP/config/env selectable)
- result rows never persisted/logged/LLM-egressed

### PR 18c - Execution form metadata
Status: landed (`GET /api/v1/query-executions/form`).
Scope:
- QUERY_OPERATE-safe parameter + environment projection for Query Assistant
- no TEMPLATE_READ / CONNECTION_PROFILE_MANAGE grant
- no credentials / DEMIS / SQL execution / LLM / audit writes
- enabled environments only; incomplete → CONNECTION_PROFILE_INCOMPLETE;
  no concrete adapter → DEMIS_ADAPTER_UNAVAILABLE

### PR 19 - Query Assistant frontend
Status: landed (`feat/query-assistant-frontend`).
Scope:
- in-app Query Assistant / Catalog Explorer navigation (default: Assistant)
- natural-language recommendation → form metadata → optional AI extraction
- parameter confirmation, execution preview, explicit execute, result + audit_id
- Oracle mock development integration exercises preview/execute end to end
- production use remains blocked until production IdP and real DEMIS access/privilege validation are complete

## Phase 7 - Operations

### PR 20 - Internal/on-premise deployment
Status: foundation landed (`feat/onprem-deployment`).
Scope:
- frontend multi-stage production image (Node build → nginx SPA; `/api` proxy)
- production/on-prem Compose (`docker-compose.onprem.yml`)
- explicit LAN IP / frontend port binding; backend + DB not LAN-published
- internal-only DQA DB (no host ports; internal Compose network)
- production `APP_ENV=production` + `DQA_AUTH_PROVIDER=disabled` (fail closed)
- optional `docker-compose.onprem.dev.yml` for development/LAN `dev_headers` only
- `.env.onprem.example` + gitignored real `.env.onprem`; required DB password
- Alembic migrate workflow (`alembic upgrade head` via migrate profile/scripts)
- health/readiness (`/health`, `/health/ready`; frontend HTTP healthcheck)
- operational scripts: up / status / logs / down / migrate
- optional Traefik override only if an external-access requirement exists (not added)
- outstanding blockers documented: production IdP + real DEMIS endpoint/account/network/privilege validation

### PR 20b - Catalog RBAC hardening
Status: landed (`feat/catalog-rbac-hardening`).
Scope:
- `CATALOG_READ` / `CATALOG_MANAGE` permissions
- role mapping: read for viewer/author/approver/operator/auditor; manage admin-only
- protect active Catalog / query / import history / activation history reads
- protect package validate / import / activate management paths
- `query_operator` retains Catalog read for Query Assistant source discovery
- not part of this PR: production IdP, DEMIS adapter implementation, frontend redesign, or rate limiting

### PR 21 - Runtime security hardening (Phase 1)
Status: landed (`feat/runtime-security-hardening`).
Scope:
- nginx outer body-size limits (2m general; 55m Catalog validate/import)
- proxy/client timeout boundaries (backend query timeouts remain authoritative)
- CSP / Permissions-Policy / cache hygiene / `server_tokens off`
- production FastAPI `/docs` `/redoc` `/openapi.json` disabled
- error-sanitization regressions for representative secret markers
- request-field bound review for high-risk JSON endpoints
- on-prem checker no longer pip-installs dependencies
- rate limiting deferred pending traffic/concurrency requirements
- HSTS deferred to approved TLS termination
- not part of this PR: production IdP, DEMIS driver implementation, or frontend redesign

### PR 22 - DQA DB backup / restore + audit retention foundations
Status: landed (GitHub PR #28, `feat/db-backup-audit-retention`).
Scope:
- operator `dqa-backup.sh` (`pg_dump -Fc` via `dqa-db`, SHA-256 sidecar, `DQA_BACKUP_DIR`)
- fail-closed `dqa-restore.sh` (explicit `RESTORE` token, checksum, refuse while app up)
- dry-run `dqa-backup-list.sh` (no automatic backup deletion)
- audit retention policy document (append-only; duration not hardcoded; no auto purge)
- read-only `dqa-audit-retention-status.sh` (oldest/newest/count only)
- static regression checks for backup/restore safety boundaries
- no production IdP / real DEMIS connectivity / public audit DELETE API

### Oracle integration follow-ups
Status: landed (development/mock validation complete).

Landed follow-up work:
- GitHub PR #31: production-selectable `OracleReadOnlyDemisAdapter` using python-oracledb thin mode
- GitHub PR #32: local DEMIS Catalog Package ZIP excluded from Git
- GitHub PR #33: development-only Oracle mock Compose/network overlay with secret injection boundary
- GitHub PR #34: Oracle mock E2E smoke (`recommendation -> parameter extraction -> preview -> execute -> audit`)
- GitHub PR #35: security smoke for parameter validation, execution/audit RBAC, and `NAMES_ONLY` audit redaction
- GitHub PR #36: idempotent, fail-closed Oracle mock metadata bootstrap
- GitHub PR #37: isolated fresh-bootstrap contract test covering create -> review -> approve -> enable and repeat execution

Current boundary:
- Oracle mock integration is validated only for development/LAN testing
- no real DEMIS clinical data is used by these fixtures
- production remains fail closed until an approved IdP is configured
- real DEMIS endpoint, read-only account, network path, finalized Catalog Package, and database privilege validation remain external prerequisites

### PR 23 - Hardening (follow-up)
Status: repository-internal hardening complete; policy/site-dependent items deferred.

Implemented:
- operational error handling expansion
  - public DEMIS adapter errors use allowlisted codes + static sanitized messages
  - Recommendation/Parameter Extraction public errors use shared allowlisted
    contracts; unknown typed errors normalize to generic internal-error codes
  - Connection Profile, Catalog, Query Template, Audit, and execution typed
    errors use reviewed public contracts with fail-closed unknown-code handling
- security regression suite growth
  - recommendation LLM call-site egress denial regression
  - cross-cutting API role/permission matrix across representative protected routes
  - static route guard rejects direct typed-exception passthrough into public errors
- RBAC refinement across representative protected API surfaces
- data-egress policy enforcement
  - central fail-closed payload-class policy landed in GitHub PR #39
  - raw parameter-extraction request requires technical opt-in + explicit runtime approval assertion
  - query-result-row egress remains denied for all current LLM purposes
  - recommendation metadata egress is explicitly checked at the LLM call site
- public runtime/documentation state synchronized with the production-selectable
  Oracle read-only adapter and audited execution path

Deferred until policy/site inputs are confirmed:
- rate/size policy tuning based on internal concurrency / traffic requirements
- approved purge tooling after retention policy confirmation
- backup encryption after site key-management approval

### PR 24-A - Alembic historical schema adoption
Status: completed (merged via `hardening/alembic-historical-schema-adoption`).
Scope:
- Alembic revision `20261007_hist01` after `20260929_audit01`
- adopt create_all-era tables into Alembic ownership without data loss:
  `catalog_import_revisions`, `catalog_active_revisions`,
  `catalog_activation_events`, `query_templates`, `query_template_versions`,
  `query_template_review_events`
- fresh DB: `alembic upgrade head` creates full DQA schema
- legacy DB: existing tables are adopted only when schema-compatible
  (columns/PK/uniques/indexes/FKs); incompatible schemas fail closed
  (no stamp/ALTER/repair); compatible create_all rows preserved
- downgrade is non-destructive (revision pointer only)

### PR 24-B - Alembic-only schema lifecycle
Status: completed (merged via `hardening/alembic-only-schema-lifecycle`).
Scope:
- remove runtime `Base.metadata.create_all` / `init_db_schema` completely
- backend startup read-only Alembic head validation (fail closed; no schema mutation)
- shared checker: `app.adapters.db.migration_head` (+ CLI `alembic/check_at_head.py`)
- test DB fixtures bootstrap via `alembic upgrade head` only
- no new Alembic revision; head remains `20261007_hist01`
- authoritative workflow remains migrate then up (no auto-migrate)

### PR 25-A - Explicit Connection Profile live DEMIS probe
Status: completed (merged via `feat/live-demis-connection-probe`).
Scope:
- `POST /api/v1/connection-profiles/{profile_id}/test-connection` (administrator only)
- GET diagnostics remain configuration-only (no credential resolve / socket connect)
- production credential resolver + DEMIS adapter factory + Oracle `probe_readonly()`
- sanitized bounded failure categories; no probe result persistence
- no execution eligibility gate changes; no new Alembic revision

### PR 25-B - Production Readiness Report
Status: completed (merged via `feat/production-readiness-report`).
Scope:
- read-only operator preflight (`./scripts/dqa-readiness.sh --source-name ... --environment ...`)
- checks: migrations, auth provider, active Catalog, eligible Query Templates,
  Connection Profile, DEMIS adapter registration, live connectivity ACTION_REQUIRED,
  external read-only privilege ACTION_REQUIRED
- never resolves DEMIS credentials, never opens DEMIS sockets, never mutates schema/data
- distinct from `/health/ready` (DQA PostgreSQL reachability only)
- no HTTP readiness API in this PR; no new Alembic revision

### PR 26-A - Real DEMIS onboarding & acceptance runbook
Status: completed (merged via `docs/real-demis-onboarding-runbook`).
Scope:
- real DEMIS onboarding sequence
- automated vs external prerequisites
- explicit live probe interpretation
- DBA privilege verification checklist
- first controlled-query acceptance
- stop/rollback criteria
- acceptance record template
- no runtime behavior changes

### PR 26-B - Integrated DQA platform architecture rebaseline
Status: completed (merged via `docs/integrated-dqa-platform-architecture`).
Scope:
- redefine DQA as DEMIS Data Access & Query Platform
- SNUH.AI Agent Workflow → MCP → DQA → DEMIS target architecture
- integrate proven Schema Search PoC capabilities into DQA Data Discovery
- human Web Portal + MCP clients share one Safety/Execution/Audit Core
- define Approved Template path vs Structured Dynamic Query Plan path
- define Schema Analyzer / DQA bounded-context boundary
- define MCP tool surface at architecture level
- rebaseline subsequent implementation roadmap
- no runtime implementation in this PR

Authoritative target doc: `docs/integrated-platform-architecture.md`.

## Rebaselined implementation sequence (after 26-B)

Dependency order is fixed. Names may be refined; do not invert phases.

### Phase 27 - Data Discovery integration

- **PR 27-A — Data Discovery domain/contracts**
  Status: completed (merged via `feat/data-discovery-domain-contracts`).
  Catalog-derived search documents; source/revision scope; logical/physical
  identity; embedding model metadata; no UI; no search engine/API.
- **PR 27-B — Schema search engine integration**
  Status: completed (merged via `feat/data-discovery-search-engine`).
  Keyword / semantic / hybrid search; terminology + relation expansion;
  revision-scoped embedding lifecycle; no HTTP API / React UI yet.
- **PR 27-C — Data Discovery React Portal**
  Status: completed (merged via `feat/data-discovery-react-portal`).
  Schema Search, Schema Explorer, relation view, embedding/index status.

### Phase 28 - MCP integration

- **PR 28-A — MCP server foundation**
  Status: completed (merged via `feat/mcp-server-foundation`).
  Transport, tool registration, auth/ingress hardening; no Discovery/Query tools.
- **PR 28-B — Discovery MCP tools**
  Status: completed (merged via `feat/mcp-discovery-tools`).
  `demis.search_schema`, `demis.describe_resource` (CATALOG_READ; active Catalog only).
- **PR 28-C — Template query MCP path**
  Status: completed (merged via `feat/mcp-template-query`).
  `demis.prepare_query`, `demis.execute_query` reusing Approved Template
  execution core (shared safety/audit; opaque AES-GCM tokens; no parallel path).

### Phase 29 - Structured Dynamic Query

- **PR 29-A — Semantic Resource Model**
  Status: completed (merged via `feat/semantic-resource-model`).
  Logical resource/field/relationship contracts; deterministic validation
  against one Active Catalog revision; injectable empty-by-default registry.
  See [semantic-resource-mapping.md](semantic-resource-mapping.md).
  No SQL compiler, Dynamic Query execution, MCP tools, UI, or migrations.
- **PR 29-B — Structured Query Plan contract + validation**
  Status: completed (merged via `feat/structured-query-plan`).
  Strict StructuredQueryPlan contracts; deterministic validation against
  Active Catalog + Semantic Resource mapping; immutable validation-only
  logical plan (not executable authority).
  See [structured-query-plan.md](structured-query-plan.md).
  No SQL compiler, Dynamic Query execution, MCP/API/UI, or migrations.
- **PR 29-C — Deterministic query compiler**
  Status: in progress (`feat/deterministic-query-compiler`).
  Oracle SELECT compiler from server-revalidated StructuredQueryPlan;
  named binds; Catalog FK joins; preview-only output (`approved=false`,
  `executable=false`). See [deterministic-query-compiler.md](deterministic-query-compiler.md).
  No DEMIS execution, MCP/API/UI, approval workflow, or migrations.
- **PR 29-D — Dynamic Query execution integration**
  Shared eligibility/safety/audit core for MCP + Web.

### Phase 30 - Integrated acceptance / hardening

- Web/MCP equivalence tests
- Data Discovery regression vs former Schema Search PoC evidence
- security / adversarial tests
- Oracle mock E2E
- SNUH.AI integration acceptance (when interface exists)
- real DEMIS remains external acceptance
  ([real-demis-onboarding.md](real-demis-onboarding.md))

## Exit criteria before real DEMIS use

- Catalog Package import validated against a real finalized package
- only READY Catalog revisions can be execution-active
- approved template workflow operational
- unsafe SQL rejection demonstrated
- authentication/RBAC enabled
- explicit Connection Profile bound to the active source/environment
- read-only DB privilege verified externally
- risky function/package EXECUTE privileges constrained
- timeout/row cap verified
- audit persistence enabled
- secrets not logged
- full result rows not sent to LLM by default
- deployment health checks pass
