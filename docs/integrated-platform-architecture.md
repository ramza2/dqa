# Integrated DQA Platform Architecture

> **2026-10-19 U-03 문서 정합화 (2026-10-15 군 협의 요청 반영):**
> 기존 2026-10-13 도식의 `DEMIS Oracle` 직접 Inspector·Read/Write
> 연결은 **옛 목표 가정**이다. 아래 도식의 **복제 EMR Read Source**와
> **공식 운영 원장 Write Interface**는 서로 분리된 *미승인 제안*으로
> 표시한다. 허용 DBMS·접속 방식·복제 주기/범위·계정/라이선스 책임은
> [U-01-R1 복제 EMR 검토](u01-replicated-emr-db-architecture-review.md)
> DEC-10/01, 쓰기는 별도 DEC-09/G4의 서면 결정 전까지 미확정이다.
> 어떤 점선도 현재 운영 연결이나 임상 접근 승인을 뜻하지 않는다.

> **Target architecture rebaseline — 2026-10-13 (planning document, not deployment approval).**
> DQA is the single deployable **DEMIS Schema Intelligence, Data Access & MCP Tool Platform**.
> This target **supersedes the producer/consumer deployment boundary** in Phase 26-B:
> the former DEMIS Schema Analyzer PoC will not be a separately deployed production site
> once parity, migration and acceptance are complete. Existing code/runtime controls
> remain unchanged until reviewed implementation PRs are merged.
>
> **Status separation:** implemented != mock-verified != real DEMIS-approved.
> See [Roadmap](roadmap.md) and [Real DEMIS Onboarding](real-demis-onboarding.md).
> Root/backend `AGENTS.md` and the real-DEMIS onboarding runbook
> **correctly preserve today's strictly read-only execution restrictions**.
> A future clinical-write capability and final retirement of the independent
> Analyzer require their own reviewed implementation/policy PRs and the
> applicable site approvals. This planning document does not loosen them.

## 1. 목표 및 시스템 책임

- **DQA / 오픈링크시스템:** DEMIS 대상 스키마 수집·분석, 버전 Catalog,
  Data Discovery, 승인된 의료데이터 **조회**, 군 측에서 허용한 업무에 한정된
  **임상문서 초안/진료 결과 Insert**, 안전한 DEMIS Adapter, 공용 REST/MCP Tool,
  인증·권한·감사·운영 포털.
- **FHIR 서버 / 메디칼스탠다드:** DEMIS뿐 아니라 PACS 및 기타 의료시스템의
  데이터를 수집·매핑·표준화하여 FHIR R4 기반 의료정보를 SNUH.AI에 전달.
  DQA는 PACS 연계나 FHIR 변환/검증을 중복 구현하지 않는다.
- **SNUH.AI / 인프메딕스:** 의료 AI 및 Agent Workflow, 임상문서 초안 생성,
  임상 승인 절차와 연계된 호출. SNUH.AI가 생성했다는 사실 자체는
  DEMIS 쓰기 권한 또는 임상의 승인 근거가 아니다.
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
  INS["DQA Schema Inspector<br/>Oracle metadata code, disabled"]
  C["DQA Catalog / Discovery<br/>PostgreSQL + pgvector"]
  R["DQA Read-only Adapter<br/>Oracle code exists; source pending"]
  I["Future Controlled Write Boundary<br/>not implemented"]
  D["Proposed replicated EMR read source<br/>DBMS/API/grants pending DEC-10/01"]
  SAVE["Proposed official operational EMR save interface<br/>undecided DEC-09/G4"]
  M["ModelOps Gateway<br/>LLM / BGE-M3 (policy-gated)"]

  S <-->|"FHIR exchange / workflow"| F
  P -->|"PACS data"| F
  F <-->|"authorized MCP or REST"| T
  S -.->|"optional direct authenticated MCP"| T
  W --> CORE
  T --> CORE
  CORE <--> C
  CORE --> R
  CORE -.-> I
  INS -.->|"authorized metadata only, if supported"| D
  INS -.->|"gated candidate/review to Catalog"| C
  R -.->|"approved read route and scope only"| D
  I -.->|"separately approved clinical write only"| SAVE
  CORE -.->|"approved AI data egress only"| M
~~~

**도식의 점선은 미승인·미구현 연계 제안**이며, 실제 DEMIS/복제 DB
접속이나 Controlled Write 기능이 배포됐다는 뜻이 아니다. DQA에 구현된
Oracle 전용 Read/Metadata Adapter의 존재만으로 **DBMS가 아직 알려지지 않은
복제 DB에 연결 가능**하다고 판단하지 않는다.

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
→ Read-only Adapter (existing Oracle code; approved source/DBMS/route pending)
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
- **HITL 승인/반려 UI를 DQA에 중복 구축하지 않는다.** 승인 주체는 군이
  인정한 의료진/공식 상위 Workflow일 수 있으나, DQA는 단순
  `approved=true`, 임의 헤더, 임의 사용자 식별자를 근거로 수락하지 않는다.
  **검증 가능한 승인증빙**(승인 주체/권한·시간·문서 버전/해시·환자 및
  Encounter·정책 ID·만료/취소 상태와 서명/신뢰 검증 등)의 계약을
  협의하고 commit 직전에 재확인해야 한다.
- 읽기 계정은 SELECT만; Write Adapter는 승인 operation의 최소 저장
  대상만. 감사 DB와 의료 원장 DB의 일관성/재시도 시나리오를 별도 설계한다.

### 5.2 안전한 2단계 쓰기 흐름 (목표)

~~~mermaid
sequenceDiagram
  participant C as SNUH.AI/FHIR/Authorized Client
  participant A as Approved Clinical Workflow
  participant D as DQA Policy / MCP / REST
  participant X as DEMIS Controlled Write Adapter
  participant DB as DEMIS
  C->>D: prepare_write(operation, typed draft, patient/encounter, request id)
  D->>D: auth + scope + allowlist + payload validation + policy
  D-->>C: PREPARED / BLOCKED / NEEDS_APPROVAL + bindable draft digest
  C->>A: clinical review and explicit approval
  A-->>C: verifiable approval evidence bound to exact draft
  C->>D: commit_write(preparation reference, approval evidence, idempotency key)
  D->>D: reauthorize + verify approval / expiry / draft digest / target binding
  D->>D: dedup + durable audit precondition
  D->>X: execute approved mapped operation (bound values)
  X->>DB: approved transactional write or site-approved API
  DB-->>X: committed outcome / generated reference
  X-->>D: sanitized status
  D-->>C: COMMITTED / REJECTED / RECONCILIATION_REQUIRED + correlation id
~~~

**Write safety requirements**

1. Prepare is **not** execution; commit verifies approval and eligibility
   **again**, including Catalog revision/fingerprint, operation/payload digest,
   patient/Encounter, actor, target and policy version.
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
| `demis.prepare_write` | **계획** | 허용된 임상쓰기 operation 및 문서 버전 검증; no write |
| `demis.commit_write` | **계획** | 승인증빙·idempotency 검증 후 제한된 Insert |
| `demis.get_write_status` | **계획** | 미확정 상태 대사 및 요청 결과 조회 |

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
- 감사 기준: 호출자 시스템·검증된 사용자, request/trace ID, workflow ID,
  operation type, source/revision, 정책·승인 reference, 결과/row count,
  상태·시간·오류 범주. 원문 결과행/초안 텍스트는 기록하지 않는다.
- 변경 이력은 변조 방지와 최소 보관을 원칙으로 하며, 규정상 감사에
  필요한 인덱스/증빙 원문 위치만 정책에 따라 보안 저장한다.
- AI 임상 결과는 무조건적 저장 대상이 아니다. 의료진 검토, 진료 맥락,
  필수 의무기록 필드 검증 및 군 운영 승인 범위 내에서만 기록한다.

## 8. 단계별 전환과 운영 승인

1. **Baseline:** PoC Schema Analyzer와 DQA의 동일 Oracle Mock 스키마 결과
   (테이블/컬럼/PK/FK/Index/comment/fingerprint), 검색 Gold Set 및
   화면·운영 기능 차이를 정량 비교한다.
2. **DQA Inspector 이관:** 승인된 Read Source/Schema와 DBMS 계약 확인 후 Metadata collector + Catalog Snapshot/Package +
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
| G1 Inspector | Mock 합성 회귀는 선행 기준선. 실제 G1은 DBA 승인 Source/Schema·수집 시점에 대한 PoC↔DQA canonical metadata/검색 Gold 동등성 및 문서·Embedding/복구 경계의 기관 수용 | QA·DBA / 군 검수(승인 주체 확인 필요) |
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
  `real-demis-onboarding.md`의 **현행 read-only 금지/권한 규칙은 계속 유효**하다.
  별도 실기관 승인·설계 및 reviewed PR 없이 Oracle Read Adapter나 기존
  Query/MCP 경로에 임상 Write를 추가하지 않는다. 독립 Analyzer 종료도 G1/G5
  기관 수용 및 별도 전환 승인이 있을 때만 진행한다.

상세 개발 WBS, 선후행 관계 및 acceptance는 [Roadmap](roadmap.md)에 따른다.
