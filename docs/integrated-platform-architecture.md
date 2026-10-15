# Integrated DQA Platform Architecture

> **Target architecture rebaseline — 2026-10-13 (planning document, not deployment approval).**
> DQA is the single deployable **DEMIS Schema Intelligence, Data Access & MCP Tool Platform**.
> This target **supersedes the producer/consumer deployment boundary** in Phase 26-B:
> the former DEMIS Schema Analyzer PoC will not be a separately deployed production site
> once parity, migration and acceptance are complete. Existing code/runtime controls
> remain unchanged until reviewed implementation PRs are merged.
>
> **Status separation:** implemented != mock-verified != real DEMIS-approved.
> See [Roadmap](roadmap.md) and [Real DEMIS Onboarding](real-demis-onboarding.md).
> Root/backend `AGENTS.md`, `README.md` and parts of the existing runbook still
> describe a strictly read-only DQA and an independent Schema Analyzer.
> They must be aligned through reviewed PRs **before any write-path implementation**.
> This document alone does not loosen those existing prohibitions.

## 1. 목표 및 시스템 책임

- **DQA / 오픈링크시스템:** DEMIS 대상 스키마 수집·분석, 버전 Catalog,
  Data Discovery, 승인된 의료데이터 **조회**, 군 측에서 허용한 업무에 한정된
  **임상문서 초안/진료 결과 Insert**, 안전한 DEMIS Adapter, 공용 REST/MCP Tool,
  **승인증빙 자동 검증과 쓰기 실행 감사**, 관리자·운영자 포털.
  일반 의료진용 승인/반려 UI나 중복 HITL 엔진은 개발하지 않는다.
- **FHIR 서버 / 메디칼스탠다드:** DEMIS뿐 아니라 PACS 및 기타 의료시스템의
  데이터를 수집·매핑·표준화하여 FHIR R4 기반 의료정보를 SNUH.AI에 전달.
  DQA는 PACS 연계나 FHIR 변환/검증을 중복 구현하지 않는다.
- **SNUH.AI / 인프메딕스:** 의료 AI 및 Agent Workflow, 임상문서 초안 생성,
  **의료진 단일 통합 UI**에서 검토·수정·승인/반려와 승인 원본 이력 관리,
  승인 완료 문서의 DEMIS 등록 요청 및 결과 표시. 의료진에게 DQA의
  별도 승인 화면을 요구하지 않는다. SNUH.AI가 생성했다는 사실 또는
  SNUH.AI의 임의 `approved=true` 전달 자체는 DEMIS 쓰기 권한이 아니다.
- **군/병원/DEMIS 운영자:** 실제 데이터 접근 범위, 환자·Encounter 식별,
  임상 승인 주체 및 증빙, 쓰기 가능 대상/방식, 권한·운영 정책 승인.

DQA의 클라이언트는 특정 벤더로 고정하지 않는다. 승인된 FHIR 서비스,
SNUH.AI, 운영 포털 또는 기타 내부 서비스는 각자의 인증과 정책 하에
동일한 DQA 응용서비스를 호출할 수 있다. **"어느 쪽에서든"은 인증·인가가
완료된 클라이언트만**을 뜻하며, 누구나 임의 호출할 수 있음을 의미하지 않는다.

## 2. 최종 배포·연계 구성

~~~mermaid
flowchart TB
  S["SNUH.AI / Agent Workflow"]
  F["MedicalStandard FHIR Server<br/>DEMIS + PACS + 기타 시스템 표준화"]
  P["PACS / 기타 의료시스템"]
  W["DQA Web Portal"]
  T["DQA MCP Tool + internal REST boundary"]
  CORE["DQA Shared Application Core<br/>Identity / RBAC / Catalog / Safety<br/>Read / Write Policy / Audit"]
  INS["DQA Schema Inspector<br/>Oracle metadata only"]
  C["DQA Catalog / Discovery<br/>PostgreSQL + pgvector"]
  R["DEMIS Read-only Adapter<br/>separate SELECT account"]
  I["DEMIS Controlled Insert Adapter<br/>separate approved write account"]
  D["DEMIS Oracle"]
  M["ModelOps Gateway<br/>LLM / BGE-M3 (policy-gated)"]

  S <-->|"FHIR exchange / workflow"| F
  P -->|"PACS data"| F
  F <-->|"authorized MCP or REST"| T
  S -.->|"optional direct authenticated MCP"| T
  W --> CORE
  T --> CORE
  CORE <--> C
  CORE --> R
  CORE --> I
  INS -->|"approved metadata inspect"| D
  INS -->|"immutable Catalog revision"| C
  R -->|"parameter-bound SELECT"| D
  I -->|"approved scoped INSERT"| D
  CORE -.->|"approved AI data egress only"| M
~~~

**연계 배치 원칙**

1. 통상 의료데이터 제공 흐름은 `SNUH.AI ↔ FHIR ↔ DQA ↔ DEMIS`;
   PACS는 FHIR 서버의 별도 원천 경로다.
2. SNUH.AI가 DQA MCP를 직접 호출할 수도 있으나, FHIR 표준화가 필요한
   데이터를 우회해 임상 서비스에 그대로 사용하지 않도록 상위 Workflow 계약이 필요하다.
3. FHIR 측 MCP Client 지원 여부와 무관하게, 필요 시 내부 REST Adapter로
   동일한 DQA application service를 호출하도록 지원한다.
4. MCP Transport를 추가하더라도 조회/쓰기 검증·실행·감사 코드의
   별도 복제품을 만들지 않는다.
5. **현 구현 MCP는 loopback-only 정책, 생산환경 인증 부재, 실행 기능
   기본 비활성화** 상태다. 네트워크만 연결하여 외부에 노출하지 않는다.
   승인된 사설 ingress, 상호 신뢰된 서비스 인증 및 사용자 위임정책이
   구체화된 후 별도 구현·검증한다.
6. DQA의 배포 구성은 Frontend + Backend(Inspector/REST/MCP/Services) +
   DQA PostgreSQL(pgvector) 중심. 독립적인 `demis-schema-search-poc` 웹/
   Backend/Catalog DB는 최종 배포하지 않는다. 개발용 Oracle Mock은 별도
   검증 fixture이며 운영 의존성이 아니다.

## 3. Schema Analyzer 단일 플랫폼 이관

**논리적 책임은 분리하되, 최종 배포는 DQA 내부 모듈로 통합한다.**

| 책임 | 최종 DQA 모듈 | 현재/목표 |
|---|---|---|
| Target·검사 계정 정책/연결 테스트 | Schema Target / Inspector Admin | **이관 필요** |
| Oracle metadata introspection (table/column/PK/FK/index/comment) | Schema Inspector | **이관 필요** |
| Snapshot, schema fingerprint, diff | Schema Snapshot/Change Review | **이관 필요** |
| Catalog Package v2 검증/immutable import/READY activation | Catalog | **기 구현** |
| Catalog 탐색, 관계 확장, 의료용어 사전 | Data Discovery | **구현/Mock 검증** |
| Keyword, Semantic, Hybrid / document rebuild / embedding sync | Data Discovery | **구현/Mock 검증** |
| Read-only Query Template, preview, audit | Query Core | **구현, 실 DEMIS 미승인** |
| MCP Discovery, Template prepare/execute | MCP Adapter | **구현, 운영 노출 미승인** |

**권장 수집 파이프라인**

1. 권한이 제한된 **메타데이터 검사 전용 계정**으로 운영자 요청 또는 승인된
   예약 작업 시점에만 Oracle metadata inspect. 임상 데이터 행을 수집하지 않는다.
2. Target과 스키마 범위, 수집한 테이블/컬럼/키/관계/주석 및 제외 사유를
   기록하여 **Catalog Package v2 호환 Snapshot**을 생성한다.
3. 기존 Catalog validator를 재사용해 유효성·fingerprint·변경 Diff 검증.
   새 Revision은 **불변**으로 저장; 필요 시 검토/승인 후 READY만 활성화.
4. 활성화 이후 해당 Revision의 검색 문서 Rebuild와 BGE-M3 Embedding Sync를
   별도의 추적 가능한 작업으로 실행한다. 실패 시 이전 활성 Revision과
   서비스 가능한 인덱스 상태를 보존한다.
5. 기존 업로드형 Catalog Package 검증·Import는 오프라인/망분리 반입과
   긴급 복구 수단으로 계속 지원한다.
6. 실제 DEMIS로의 스키마 탐색은 허용된 Oracle data dictionary/view 범위와
   접근 권한을 군 측에서 승인해야 한다. **실행 시마다 실시간 크롤링하지 않는다.**

PoC 코드를 무조건 복제하지 않는다. Inspector와 snapshot builder의 검증된
알고리즘을 선별 이관하며 PoC Streamlit UI, 독립 DB, 암호화 자격정보 저장 방식,
Docker 토폴로지를 그대로 복사하지 않는다. DQA Connection Profile / secret
reference 경계와 Alembic-only 스키마 관리가 우선한다.
기존 PoC Gold Set 평가/검색 순위 비교는 regression evidence로 유지한다.

## 4. 공통 응용서비스 경계와 조회 Path

~~~text
Authenticated Web / MCP / internal REST
→ Verified service & end-user identity + patient/encounter scope + purpose
→ Active Catalog / approved logical resource mapping
→ Approved + Enabled Query Template (current safe path)
→ validated typed parameters / eligibility / SQL safety / preview
→ Read-only Oracle adapter (SELECT-only credentials + bounded query)
→ bounded, minimized source-data JSON
→ audit metadata / correlation
→ caller (FHIR standardizes if needed)
~~~

- 호출자가 SQL, DB 주소/자격정보, 임의 테이블명 또는 권한을 지정해
  실행 경로를 우회할 수 없다.
- 스키마/임상 의미 매핑은 실제 DEMIS와 군 측 승인 전 임의로 확정하지 않는다.
- Logical `Patient`, `Encounter`, `Diagnosis`, `Medication`, `LabResult`,
  `Procedure` 등의 필드는 현재 검증된 **mapping registry가 비어 있는 설계
  경계**다. 승인된 resource/field/relationship 매핑을 별도로 구축해야 한다.
- Structured Dynamic Query Plan(Phase 29)은 보완 경로다. 검증·Oracle SELECT
  compiler preview를 실제 실행 권한과 혼동하지 않는다.
- FHIR R4 변환/프로파일 적합성 검증은 FHIR 서버 담당이며 DQA는
  공통 JSON 조회 계약과 provenance/오류 메타데이터를 제공한다.

## 5. AI 임상문서·진료 결과의 승인된 DEMIS Insert (미구현 목표)

**요구 범위:** SNUH.AI가 생성한 의무기록 초안, 진료/진단보조 결과 등
군/병원이 허용한 문서·업무 유형을 임상의 승인 후 실제 DEMIS에
등록하는 기능. 기능 구현은 **대상 업무, 저장 필드, 최종/초안 상태,
의무기록 법적 책임과 승인 방식, DEMIS 공식 쓰기 인터페이스**가 확인된
이후에만 가능하다. 실제 DEMIS에 직접 INSERT가 허용된다고 가정하지 않는다.
기관에서 제공하는 **공식 저장 API/프로시저가 있다면 우선 검토**하고,
직접 DB Insert는 서면 승인된 경우에 한해 제한한다.

### 5.1 분리된 Write Boundary

- 기존 `OracleReadOnlyDemisAdapter`와 `QUERY_OPERATE` 권한을 쓰기에
  사용하지 않는다. 별도 `ControlledWriteAdapter`,
  `WRITE_PREPARE` / `WRITE_COMMIT` 권한, 전용 비밀 참조 및
  허용된 저장 Operation Registry가 필요하다.
- 클라이언트의 임의 SQL, 테이블/컬럼 지정, 범용 CRUD 또는
  LLM 생성 SQL을 실행하지 않는다. `MedicalRecordDraft`,
  `ClinicalDecisionRecord` 등의 **예시 operation 타입**만 업무 승인에 따라
  확정한다. 코드·테이블명과 payload 매핑을 미리 하드코딩하지 않는다.
- 사전 승인 operation별 허용 자원/필드, 길이/타입, 상태, 업무 코드,
  필수 환자/Encounter 결합, 작성자·임상 검토자, 중복 처리 정책을
  명시적으로 정의한다. 환자/Encounter 정합성은 서버 측 권한 있는
  조회/매핑으로 재검증한다.
- **HITL 승인·반려는 SNUH.AI 단일 의료진 UI/군이 인정한 상위
  임상 승인 Workflow의 책임**이다. 의료진은 문서를 검토·수정하고
  **1회 명시 승인**한다. DQA에 별도 승인 버튼·의료진 승인 대기함/
  승인 상태 원본을 중복 구현하지 않는다.
- DQA는 의료진을 다시 승인시키지 않지만 **승인 유효성을 기계적으로
  독립 검증**한다. 단순 `approved=true`, 임의 헤더, 전달받은 승인자
  문자열만으로 쓰기를 허용하지 않는다. 신뢰된 승인 시스템에
  승인 참조를 조회하거나, 승인 주체의 검증 가능한 서명 증빙을
  확인한다. **검증 가능한 승인증빙**에는 승인 주체·권한·시각,
  문서 ID·최종 버전/정규화 해시, 환자·Encounter, 업무 operation,
  정책/대상, 만료·취소·문서 수정 여부가 포함되어야 한다.
- **승인 원본과 의료진 수정·반려 이력은 SNUH.AI 또는 군 지정
  승인 시스템이 보유한다.** DQA에는 승인 원본을 복제하지 않고,
  승인 참조·검증 결과·operation·요청/실행 상태·DEMIS 결과 참조 등
  필요한 최소 감사 메타데이터만 보존한다. 두 감사는 request/approval/
  audit correlation ID로 연결한다. 승인증빙 원본 보관 여부는 군
  보안·감사 정책에 따르며 기본적으로 PHI 원문을 DQA에 적재하지 않는다.
- 읽기 계정은 SELECT만; Write Adapter는 승인 operation의 최소 저장
  대상만. 감사 DB와 의료 원장 DB의 일관성/재시도 시나리오를 별도 설계한다.

### 5.2 안전한 2단계 쓰기 흐름 (목표)

~~~mermaid
sequenceDiagram
  participant C as SNUH.AI/FHIR/Authorized Client
  participant A as SNUH.AI clinician UI / approved workflow
  participant D as DQA MCP / REST + Policy
  participant V as Trusted approval verifier
  participant X as DEMIS Controlled Write Adapter
  participant DB as DEMIS
  C->>D: prepare_write(operation, draft version, patient/encounter, request id)
  D->>D: schema / scope / allowlist / payload checks, no DB write
  D-->>C: PREPARED / BLOCKED + draft digest
  C->>A: clinician reviews, edits and approves exactly once
  A-->>C: approval reference bound to final approved digest
  C->>D: commit_write(preparation, approval ref, final approved payload, idempotency key)
  D->>D: authenticate service and operator context; revalidate request
  D->>V: trusted server-to-server approval lookup / signature verification
  V-->>D: verified approver + current status + exact document binding
  D->>D: reject mismatch/revocation; idempotency and audit precondition
  D->>X: execute approved mapped operation (bound values)
  X->>DB: site-approved insert operation / official storage API
  DB-->>X: committed result / DEMIS document reference
  X-->>D: sanitized outcome
  D-->>C: COMMITTED / REJECTED / RECONCILIATION_REQUIRED + audit id
  C-->>A: show result / request manual reconciliation if uncertain
~~~

**Write safety requirements**

1. Prepare is **not** execution or approval. SNUH.AI UI에서 최종 문서
   검토·수정 후 의료진 승인은 **1회만** 받는다. 승인 후 문서가 바뀌면
   이전 승인 참조는 무효화하여 재검토한다.
   Commit 시 DQA는 임상의에게 재승인을 요구하지 않고 **신뢰된 승인
   서비스 조회 또는 서명 검증**으로 승인 상태·취소·만료·권한을 자동
   확인하며, Catalog revision/fingerprint, operation/payload digest,
   환자/Encounter, 요청자·대상·정책 버전을 다시 검증한다.
2. Exactly-once cannot be inferred from a transport retry. Require durable
   idempotency key scoped to client+operation+clinical target+payload, unique
   source-side business key when feasible, and explicit reconciliation of
   ambiguous timeout/network outcomes before any retry. No blind re-Insert.
3. Transaction boundaries, rollback and atomic audit outcome must be verified
   with the actual DEMIS integration interface. An uncertain commit is reported
   as `RECONCILIATION_REQUIRED`, not blindly retried or marked failed.
4. Write requests, payload text, generated medical findings and records must
   **not** be logged in application/audit traces. Persist only policy-approved
   minimal identifiers, digest/references, state, result code and timestamps,
   with access controls, retention and at-rest/in-transit protection.
5. No `UPDATE`, `DELETE`, `MERGE`, generic SQL, irreversible final sign-off or
   broad bulk write is implicitly allowed by the Insert requirement; each is
   a new scope requiring separate clinical/DBA/security approval.
6. Disable the Write feature by default in all environments. Development
   uses **synthetic fixtures only**; actual DEMIS Insert requires a distinct,
   time-bounded, explicitly signed site acceptance and rollback/reconciliation
   plan. A DB user with write grants is never shared with read-only operations.

## 6. MCP Tool 계약과 호출자 독립성

| Tool / interface | Current status | Contract / responsibility |
|---|---|---|
| `dqa.mcp_ready` | 구현 (internal) | MCP 상태 |
| `demis.search_schema` | 구현 (internal) | 승인 Catalog 스키마 검색 |
| `demis.describe_resource` | 구현 (internal) | 활성 물리 리소스/관계 설명 |
| `demis.prepare_query` | 구현 (internal) | Approved Template 조회 준비 |
| `demis.execute_query` | 구현, default disabled | 단기 opaque token으로 조회; 기존 TTL 중복 실행 가능, **쓰기용 재사용 금지** |
| `demis.prepare_write` | **계획** | SNUH.AI 단일 UI의 임상 승인 전후에 독립 호출 가능한 사전 검증, DQA 승인 UI 없음, no DB write |
| `demis.commit_write` | **계획** | **SNUH.AI 임상 승인 1회**의 원본 참조를 신뢰 검증·동일 문서 바인딩 후 제한된 Insert, 중복 승인 없음 |
| `demis.get_write_status` | **계획** | 미확정 상태 대사 및 실행 결과 조회 (임상 승인 상태 관리 기능 아님) |

Tool명과 입출력은 **제안안**이다. 최종 MCP schema, 의료업무 리소스명,
환자/Encounter 식별 계약 및 오류 코드·client capabilities는 FHIR/SNUH.AI/
군 측 연계 합의 후 동결한다. 기존 도구 이름과 동작은 변경하지 않고
호환성 정책을 수립한다. REST와 MCP는 단일 Policy/Execution/Audit 경계를 공유한다.

FHIR가 DQA에 접근하는지, SNUH.AI가 직접 MCP를 호출하는지는 운영 흐름의
선택이며 DQA 서비스 로직에 종속되지 않는다. 다만 원천 데이터가 FHIR
표준을 요구하는 경우에는 FHIR 경로와 provenance를 보장해야 한다.

## 7. 인증, 환자 안전, 감사, 외부 전송

- Production `IdentityProvider`, 서비스 간 TLS/mTLS 또는 승인된 게이트웨이,
  권한 위임/claim 및 patient/encounter purpose-of-use mapping은 **미확정**.
  사설 network 접근만으로 인증을 대체하지 않는다.
- 실제 환자정보는 mock 테스트, Git/PR, stdout, LLM 프롬프트, 감사로그,
  평가 Gold Set에 넣지 않는다. ModelOps로의 clinical egress는 별도
  정책 승인 전 차단한다.
- **이원화된 감사 책임:** SNUH.AI/공식 승인 시스템은 문서 검토·수정·승인/
  반려·승인취소의 원본 이력을 관리한다. DQA는 승인증빙 **검증 사실**
  및 DEMIS 등록 실행·결과·미확정 대사를 관리한다. 두 시스템 간
  `approval_id`, `client_request_id`, `workflow_id`, `audit_id`로
  상관관계 추적하며 기록 원본을 중복 적재하지 않는다.
- DQA 감사 기준: 호출자 시스템·검증된 사용자, request/trace ID, workflow ID,
  operation type, source/revision, 정책·승인 reference 및 검증 상태,
  결과/row count, 상태·시간·오류 범주. 원문 결과행/초안 텍스트는
  기록하지 않는다.
- 변경 이력은 변조 방지와 최소 보관을 원칙으로 하며, 규정상 감사에
  필요한 인덱스/증빙 원문 위치만 정책에 따라 보안 저장한다.
- AI 임상 결과는 무조건적 저장 대상이 아니다. 의료진 검토, 진료 맥락,
  필수 의무기록 필드 검증 및 군 운영 승인 범위 내에서만 기록한다.

## 8. 단계별 전환과 운영 승인

1. **Baseline:** PoC Schema Analyzer와 DQA의 동일 Oracle Mock 스키마 결과
   (테이블/컬럼/PK/FK/Index/comment/fingerprint), 검색 Gold Set 및
   화면·운영 기능 차이를 정량 비교한다.
2. **DQA Inspector 이관:** Metadata collector + Catalog Snapshot/Package +
   diff/version + run status를 통합하고 독립 Analyzer의 임상 운영 의존성을 제거한다.
3. **Read API/MCP:** approved Query Template, external REST/MCP contract,
   FHIR/SNUH.AI interface, Oracle Mock read-only E2E 및 감사 등가성을 검증한다.
4. **Controlled Write:** 군/병원의 서면 쓰기 범위/승인/인터페이스 확정 후
   mock synthetic write E2E → site-limited clinical acceptance 순으로 진행한다.
   승인 지연 시 쓰기 기능을 **비활성 유지**하며 조회 기능까지 막지 않는다.
5. **Cutover:** Analyzer 외부 의존성 0, Catalog 동등성, 복구 검증,
   DQA 운영 인증·보안, FHIR/PACS 책임 명확화 후 기존 사이트를 중단한다.
   기존 서비스/데이터 Volume은 승인 전 삭제하지 않는다.

### Release gates

| Gate | 최소 합격 조건 | Authority |
|---|---|---|
| G0 Architecture | 역할 분담, 검사/조회/쓰기 경계, MCP 호출 경로 및 책임 승인 | 컨소시엄/PL |
| G1 Inspector | 동일 Mock 스키마 분석 parity, immutable Catalog, rebuild/sync 검증 | 개발/QA |
| G2 Read | 승인 조회 E2E, audit, RBAC/IdP, TLS, 실 DEMIS SELECT 권한 확인 | 군/병원/보안 |
| G3 Write mock | 승인증빙 위조/만료/취소, 중복/재시도/실패/롤백 포함 무해한 fixture 실증 | 의료 QA/보안 |
| G4 Real write | 대상 기록 유형/필드/공식 인터페이스/DBA grant/임상의 승인과 실증서 승인 | 군/병원/DEMIS 운영 |
| G5 Cutover | FHIR/SNUH.AI 통합검증, Analyzer parity, 복원/운영 수용 및 전환 승인 | 컨소시엄/운영 |

**현재 사실 상태 (2026-10-13):** 개발 Oracle Mock Catalog 25 tables,
Data Discovery documents/embeddings 231/231 READY, Keyword/Semantic/Hybrid,
Gateway LLM/Embedding, DQA Frontend→Backend→PostgreSQL 통합 확인.
Oracle Mock의 이번 세션 **계정 인증/실제 SELECT는 미검증**이며,
실 DEMIS 연결·DBA 권한·임상 Insert·운영용 IdP·SNUH.AI/FHIR E2E는
검증되지 않았다. 과거 별도 Mock evidence가 있더라도 실제 DEMIS
운영 승인으로 간주하지 않는다.

## 9. 구현 범위 제외 / 결정 필요 사항

- DQA 내부 FHIR R4 mapper/validator 또는 PACS 직접 연계 — **제외**.
- 승인되지 않은 자유 SQL, 임의 DML/DDL, 자동 임상 승인 — **금지**.
- DEMIS 직접 DB 쓰기 가능성, 환자/Encounter 링크, 저장 대상,
  공식 interface, 승인증빙 신뢰 및 원장 중복 방지 — **외부 결정 대기**.
- 어떤 클라이언트가 MCP를 호출할지, FHIR REST 변환 책임, 의료 오류
  코드/성능·감사정보 최소집합 — **연계 ICD 협의 필요**.
- `AGENTS.md`, `backend/AGENTS.md`, `README.md` 및
  `real-demis-onboarding.md`의 기존 'read-only consumer' 규칙은
  실행 코드 관점에서 **계속 유효**하다. 첫 코드 구현 이전에
  새로운 승인된 Write/Inspector 경계로 일관되게 현행화해야 한다.

상세 개발 WBS, 선후행 관계 및 acceptance는 [Roadmap](roadmap.md)에 따른다.

## 10. 단일 UI 운영 포털 책임(추가 합의)

| SNUH.AI 의료진 통합 UI | DQA 운영·관리자 UI |
|---|---|
| 환자/Encounter 진료 컨텍스트 확인, 의무기록 초안 검토·수정 | DEMIS 연결 프로필 및 Schema Inspector/Catalog 운영 |
| 임상의 승인/반려/취소 및 의료진 검토 이력 | Query Template·Write Operation 승인된 정의/버전·연계 설정 |
| 승인된 기록 DEMIS 등록 요청, 실패/결과 표시 | 서비스 연결·MCP Tool 가용성·역할/권한·검증 실패·실행 감사 |
| 미확정 등록 상태 안내, 재처리 요청 | 미확정 Commit 결과 대사/운영 장애 처리(자동 재삽입 금지) |

- 최종 사용자는 원칙적으로 **SNUH.AI UI 하나만** 사용한다. DQA는
  관리자/DBA/보안 담당자의 시스템 설정·검증·감사용 UI를 제공한다.
- DQA에서 의료진에게 중복 승인 화면, 환자별 임상 검토 화면,
  독자적인 HITL 처리 엔진을 제공하지 않는다. 다만 **업무별 저장
  Operation 정책/배포 변경 승인**은 임상문서 승인과 별개의 관리자
  통제이므로 DQA 관리자 기능 범위에 포함될 수 있다.
- DQA의 승인 검증 실패는 SNUH.AI에 적절한 상태로 반환하지만 DQA가
  임상 승인 상태를 직접 수정하거나 승인자로 행세하지 않는다.
