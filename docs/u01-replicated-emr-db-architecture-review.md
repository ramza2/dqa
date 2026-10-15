# U-01-R1 — 복제 EMR DB 기반 DQA 연계 아키텍처 협의 초안

> **작성 기준: 2026-10-15 주간회의 후속 요청, 개발 설계 초안.**
> '병원(국방의료정보체계) 운영 EMR이 아닌 **복제 EMR DB를 반영해 구성도를 재수립**'하는 요구를 해석한 **검토안**이다.
> 복제 DB의 실체·DBMS·동기화 방식·인허가·계약·지원 Interface·수신기관 역할은 아직 확인되지 않았다.
> 본 문서/그림은 실제 DEMIS 접근, 의료정보 조회, DBA 승인, Oracle 라이선스 충족 또는 운영 배포 허가가 아니다.

## 1. 기존 문서 대비 핵심 수정

- [기존 통합 플랫폼 목표 구조](integrated-platform-architecture.md)의 `DEMIS Oracle` 단일 원천에 직접 연결된 Inspector/Read/Controlled Insert 화살표는 **2026-10-15 회의 요청을 반영하지 않은 기존 목표 가정**이다.
- 신규 **제안**: 읽기는 군/병원이 제공하고 승인한 **복제 EMR DB(조회 전용)** 경계를 통해 수행한다. DQA는 복제 시스템 구축·운영·실데이터 복제를 당연히 맡는 것으로 보지 않는다.
- 복제 DB가 있다고 해서 **임상 결과의 최종 원장(운영 EMR)에 대한 쓰기**가 가능해지지 않는다. 별도의 **군 승인 공식 저장 API/프로시저/통합경로** 여부가 확인돼야 한다. 미결이면 실제 쓰기 기능은 `BLOCKED`.
- DQA의 `PostgreSQL + pgvector`는 Catalog/검색 문서/감사 등 **플랫폼 내부 저장소**이며, 복제 EMR DB나 원본 의무기록 DB와 **서로 다른 역할**이다.
- FHIR R4 변환·표준화 및 PACS/기타 데이터 소스는 **메디칼스탠다드**, 의료 AI·Agent Workflow·임상 승인 UI/절차는 **인프메딕스 SNUH.AI**의 협의 역할을 유지한다. 외부 계약 확정 전 호출형태(MCP/REST)는 선택사항이다.

## 2. TO-BE 후보: 읽기용 복제 DB + 승인된 쓰기 경로 분리

~~~mermaid
flowchart LR
  subgraph GOV["군 / 국방의료정보체계 운영영역 — 실제 배치 미확정"]
    EMR["운영 EMR / 원본 의료정보<br/>실제 진료·법적 기록의 원장"]
    REPL["복제 EMR DB<br/>DBMS·주기·Scope·위치 미확정"]
    SAVE["공식 EMR 저장 Interface<br/>존재/권한/형태 미확정"]
    EMR -.->|"기관 운영 복제 프로세스<br/>소유·방식·주기 협의 필요"| REPL
    SAVE -.->|"기관 허가된 저장 처리만"| EMR
  end

  subgraph OL["오픈링크 / DQA 영역 — 논리 구조"]
    INS["Schema Inspector<br/>승인 메타데이터만"]
    READ["Read-only DEMIS Adapter<br/>승인 Query Template / SELECT"]
    CORE["DQA Policy / Query / Audit<br/>REST·MCP 내부 서비스"]
    CAT["DQA Catalog / Discovery<br/>PostgreSQL + pgvector"]
    WRITE["Controlled Write 경계<br/>미구현·기본 차단"]
    INS --> CAT
    CAT <--> CORE
    CORE --> READ
    CORE -.-> WRITE
  end

  subgraph CON["컨소시엄 의료 AI"]
    FHIR["메디칼스탠다드 FHIR<br/>다중 원천 표준화"]
    PACS["PACS / 기타 시스템"]
    AI["인프메딕스 SNUH.AI<br/>의료 AI·임상 승인 Workflow"]
    PACS --> FHIR
    FHIR <--> AI
  end

  INS -->|"허용된 Dictionary/Metadata only"| REPL
  READ -->|"승인 계정·정형 조회"| REPL
  FHIR <-->|"인가된 REST 또는 MCP 조회"| CORE
  AI -.->|"선택적 인증된 호출<br/>별도 ICD 필요"| CORE
  WRITE -.->|"기관 공식 Interface 확정 후 별도 승인"| SAVE
~~~

**도식 범위 제한**: 점선은 **제안/미확정 경로**, 실선도 제품 간 실배포 연결을 인증하지 않는다. 방화벽 Zone, 물리 서버 수, DBMS/Oracle 제품·License, 네트워크 속도, FHIR 내부 구현은 실제 증빙을 받아 확정한다. 운영 EMR과 복제 DB 사이의 동기화 수단을 DQA가 자동 관리하거나 원장 데이터에 직접 접근하는 구조로 해석하면 안 된다.

### 2.1 조회/검색 Path (서면 승인 이전 미가동)

1. 군 담당기관이 복제 EMR DB의 **원본 시스템/복제 타깃/허용 데이터 스키마/DBMS/갱신 계약**을 확인하고 접근정책을 승인한다.
2. DQA가 내부 연결 프로필에 **승인된 물리 Read Source**를 바인딩하고, 별도의 최소권한 읽기 Credential을 참조한다. `source_name`, Catalog Revision, Connection Profile과 복제 대상의 대응은 명시적 수용 항목이다.
3. Inspector는 별도 허가된 검사 계정과 Metadata 범위로만 `Snapshot → Diff → WARNING Candidate`까지 수집/검토할 수 있다. **운영 Inspector는 현재 비활성·연결 금지**이며 독립 DBA Preflight/READY 정책 미확정.
4. 기존 Catalog validator/Import는 변경하지 않는다. **독립 증빙과 승인 조건 없이 신규 Snapshot을 READY로 승격하거나 활성화하지 않는다.**
5. 실제 조회는 승인된 템플릿/파라미터/권한/환자-Encounter Scope/감사 검사를 통과할 때만 복제 DB에 제한된 Read-only SELECT로 수행하며, 반영 시각·데이터 지연의 표시 정책을 별도 정한다.
6. FHIR 서버가 의료 자원을 표준화하고 SNUH.AI로 전달한다. PACS 별도 경로의 실제 원천은 컨소시엄·군에서 확인한다.

### 2.2 쓰기/승인 Path — 조회용 복제 DB에서 분리

- SNUH.AI 임상 초안·승인 Workflow가 작성물을 생성하더라도 DB 저장 권한이 생기는 것은 아니다.
- 복제 DB가 조회만 허용하는 환경에서는 **복제 DB에 INSERT/UPDATE/DELETE를 수행하지 않는다.**
- 기관이 제공하는 **공식 EMR 저장 API/승인된 중계시스템/허용된 프로시저** 등을 우선 협의한다. 정식 제공/허용 여부는 확인되지 않았다.
- Controlled Write는 [기존 목표 아키텍처 §5](integrated-platform-architecture.md)에 기술된 분리 권한·감사·멱등성·임상 승인/책임 요건을 충족하고 **DEC-09/G4**가 해제된 경우에만 별도 설계·검증한다.
- **인증된 조회 대상의 DBMS가 Oracle인지 여부는 별도 쓰기 Interface/DBMS를 결정하지 않는다.**

## 3. AS-IS / TO-BE 정리용 문구 (확정 전 제안)

| 구분 | AS-IS — 현재 확인된 사실과 미확인 사항 구분 | TO-BE — 목표/확인 필요 |
|---|---|---|
| 의료정보 원천 | 회의에서 병원 운영 EMR 직접 접근이 아닌 복제 EMR DB 기반으로 변경 요청. 현행 복제 토폴로지·운영실적은 아직 자료 없음 | 운영 EMR과 복제 EMR DB를 논리·보안 경계로 분리하고 조회 경로를 승인된 복제본으로 한정 |
| DQA 기술 | 개발망 Oracle Mock, `OracleReadOnlyDemisAdapter`, metadata-only Inspector, Catalog/Template/pgvector 구현. 실 DEMIS 연결 승인·검증 없음 | 승인된 복제 원천에 한해 Source/Schema/Query Template/Read 권한 및 Audit 매핑, Provenance/갱신 지연 식별 |
| 진료정보 표준화 | 메디칼스탠다드 FHIR·PACS·기타 시스템 담당 분리 (실 ICD 미확정) | FHIR R4 변환·환자/Encounter/trace/오류 계약 기반으로 SNUH.AI와 통합 |
| AI 활용 | SNUH.AI·임상 승인/의무기록 생성의 목표 및 역할은 정의되어 있으나 기관 수용 미확정 | 임상 안전성과 승인된 업무만 진행. 공식 저장 Interface·임상 승인·대사 체계 없으면 Write 차단 |
| 운영 신뢰 | 실제 현장 전원·네트워크·Oracle License·권한·DBA Scope 미확인 | 실측값/공식 문서 기반으로 인프라 용량 및 DB·라이선스 구조 확정 후 변경 관리 |

AS-IS 표의 개발 상태와 군 의료 현장의 운영상황을 동일하게 취급하지 않는다. 군/병원 및 상급종합병원의 구체적 업무 현황·도입효과 비교는 각 기관의 확인 자료를 받아 별도로 보강한다.

## 4. 현재 DQA 코드 영향 분석 (확인된 구현 기준)

| 영역 | 현재 구현 | 복제 DB 적용 시 결정/수정 필요 |
|---|---|---|
| `backend/app/adapters/demis/factory.py` | 등록된 실제 read Adapter는 **Oracle만**; 미지원 DBMS는 Credential 접근 전에 거부 | **복제 DB DBMS 확인 우선**. Oracle이면 기존 Adapter 재활용 가능한지 계약/망/권한 시험. 타 DBMS이면 새 Adapter·쿼리 Dialect·타입·오류/Timeout·Read-only 제어 별도 개발 필요 |
| `backend/app/adapters/demis/oracle.py` | `python-oracledb` thin의 read-only 트랜잭션 기반 | DB 서비스 정보, driver/network, fetch/timeout, 계정 SELECT 권한·복제 일관성 운영 검증 필요. **Oracle thin 사용 가능 ≠ 서버/복제 Oracle License 승인** |
| `backend/app/adapters/schema_inspector/oracle.py` | Oracle `ALL_*` dictionary metadata만 수집 | 복제 대상의 Dictionary/테이블·FK·Index·Comment 노출 범위 확인. 보이지 않는 메타데이터를 임의 가공하지 말 것 |
| `Connection Profile` | Source/Environment와 물리 DB target, Secret Ref 분리. 테스트 Connection은 명시적 관리자 동작 | 운영 Source 변경을 조용히 덮어쓰지 말고 새 Target 식별/승인·Template/Catalog 양립성 검토 및 감사 필요 |
| `Catalog/Snapshot/Data Discovery` | Snapshot/Import Revision/active pointer는 분리, Fingerprint/검색은 Revision 기반 | 복제 Schema와 기존 운영/Mock Catalog 동등성을 **가정하지 않음**. 승인된 Source scope별 Gold Diff, Reader/Inspector source 일치 검증 후 사용 |
| `Query Template/Read Audit` | 승인 템플릿과 정해진 파라미터, SQL 안전성, 조회 감사 | 복제 지연·시점/민감 필드·환자/Encounter 범위/최소행수·기간·비식별 규칙 반영. 복제본 장애 시 **원본 운영 EMR 자동 우회 금지** |
| `Controlled Write` | 기존 목표 문서의 **미구현/기본 차단** 기능 | 복제 DB에 쓰지 않음. 공식 원장 저장 Interface 및 기관별 승인·통합수용을 별도 Gate로 분리 |
| `DQA PostgreSQL/pgvector` | Catalog/Embedding/감사 저장용 별도 DB | 복제 EMR 원장 역할/임상 데이터 이관 대상으로 혼동 금지 |

## 5. 의료정보체계과 협의 질의서 (2026-10-22 회의 준비용)

> 실무자에게 단순히 “ERD와 DB 정보를 주세요”라고 요청하지 않고 아래 질문별로
> **답변자 역할 + 필요한 증빙 형태 + 미답변 시 개발 제약**을 함께 명시한다.
> 호스트 IP, 계정, 비밀번호, 실환자정보, 라이선스 번호 등의 원문은 이메일·GitHub PR에 첨부하지 않고 승인된 보안 경로를 사용한다.

| 우선 | 명확한 질문 | 요청 산출물 / 답변 주체 제안 | 미확정 시 제한 |
|---|---|---|---|
| **P0-Q01** | 이번 과제의 **복제 EMR DB**는 어떤 시스템이 제공/운영하며 운영 EMR과 물리·논리적으로 어떻게 분리됩니까? 복제 대상 DBMS·Version·Edition은 무엇입니까? | 원본/복제 식별표·망/논리 토폴로지, **의료정보체계과·DBA** | Adapter/Topology 단정 금지 |
| **P0-Q02** | 복제 방식(동기/비동기/CDC/배치), 주기/허용 지연, 장애 시 마지막 정상시각, 복제 대상 테이블·View·누락 항목·정합성/삭제 반영 계약은 무엇입니까? | 복제 운영 기준 및 CDC/운영 정책, **DBA/운영사** | 진료 시점 최신 데이터 보장 표현 금지 |
| **P0-Q03** | DQA/컨소시엄이 직접 복제 DB에 접속 가능합니까, 아니면 API/중계 서비스만 허용됩니까? 허용 망, 인증 방식, 계정 수, SELECT·Dictionary 권한, 환자·Encounter 범위는 무엇입니까? | 승인 경로/네트워크/최소권한·사전 검증 문서, **보안/DBA/의료정보체계과** | 실제 Socket/SELECT/Inspector 실행 불가 |
| **P0-Q04** | 복제 환경 구축·사용으로 필요한 **Oracle Database 및 복제/대기/고가용성 옵션 라이선스**의 소유·계약 범위·추가 비용·운영 책임을 누가 확인합니까? | 기관·벤더 간 검토 결과/근거 문서, **라이선스 담당/DBA/계약 담당** | 비용·운영 적법성 확정 금지 |
| **P0-Q05** | SNUH.AI의 승인된 의무기록 초안/진료결과를 **운영 EMR 원장**에 저장하는 공식 Interface(API/중계/프로시저)가 있습니까? 지원 문서 유형·필드·상태·임상 승인 증빙은 무엇입니까? | 지원 API/업무 Operation·승인 정책 ICD, **병원/의료정보체계과/EMR 운영사** | Controlled Write BLOCKED; 복제 DB DML 금지 |
| **P0-Q06** | 환자·진료접수·Encounter·진료과·검체·영상 참조에 필요한 테이블/뷰·주키/참조키/코드체계·민감 필드와 조회 허용 기간은 어디까지입니까? | 승인 Schema/Logical field/Code map, **DBA/의료 QA/업무 담당** | Query Template/통합 FHIR ICD 확정 불가 |
| **P1-Q07** | DQA/FHIR/SNUH.AI 간 데이터 Source of Truth, 변환 담당, 책임 소유자, 환자/Encounter correlation, Error/Trace·TTL·재시도 계약은 무엇입니까? | 버전관리된 ICD/R&R, **메디칼스탠다드·인프메딕스·의료정보체계과** | 외부 MCP/REST E2E 수용 불가 |
| **P1-Q08** | 서버실 총 공급전력(kW/kVA)·현재 사용량·비상전원/UPS 용량·삼상전원 형식·분기차단기·랙/냉각/망속도·망구획/방화벽 실측/승인 값은 무엇입니까? | **2026-10-15 현장실측표**와 시설/망 담당 서명 또는 확인, **인프라/시설/통신 담당** | 장비 수용·용량/배치 확정 불가 |
| **P1-Q09** | 복제 DB의 백업·복구 책임과 장애시 전환/복원 우선순위는? 복제 지연 및 중단 시 의료업무에서 어떤 조회 결과를 표시/차단해야 합니까? | RPO/RTO·장애 대응·복제 stale 데이터 표시 정책, **운영/병원/의료 QA** | 운영 Readiness/G5 확정 불가 |

질의 일자는 면담 예정일이며, 답변 수령·승인 여부는 아직 모두 **PENDING**이다.
실무자별 실제 요청·회신을 추적할 때는 질문 ID를 변경하지 않고 요청일, 답변일,
증빙 문서/버전·승인자를 별도 등록한다.

## 6. 일정·협의 기록 및 결정 Gate

- **10/20(화)**: IITP 제출자료 수신처에 의무사령부 담당자 포함 요청 — 제출/발송 완료 여부 미확인.
- **10/22(목) 오전 정책과 / 15:00 의료정보체계과 협의 요청**: 회의 시간 최종 확정 및 오전/오후 참석 가능 여부 조정 필요.
- **10/28(수)**: 국방부 추진점검 전, 복제 DB 아키텍처/AS-IS·TO-BE/현장실측 및 인프메딕스 R&R·지분율 변경 현황을 승인된 형태로 정리. 구체적인 수치·계약은 이 문서에서 추정하지 않는다.
- 다음 Gate: **DEC-10(제안)** 복제 EMR DB 원천·DBMS·복제계약·접근 및 Oracle License → 기존 **DEC-01/04/05** Inspector/검색/실조회. **DEC-09** 원장 쓰기 Interface/임상 승인과 분리. **DEC-08** 운영 Portal 요구범위는 별도.

### 개발 중 준수사항

1. 이번 논의만으로 Connection Profile host/port/secret, Query Template의 물리 Table, Inspector Target, ACTIVE Catalog를 수정하지 않는다.
2. 실제 DEMIS/복제 DB에 접근·스키마 Crawl·환자 조회·쓰기 테스트를 실행하지 않는다. 현재 Fake/Oracle Mock 개발 검증 경로 유지.
3. 기존 Legacy Analyzer/PoC, DQA Catalog/DB/Volume은 기관 수용 및 G5 Cutover 전 중단·삭제하지 않는다.
4. 본 **문서 PR은 Draft**이며, 군/의료정보체계과의 협의 결과를 기존 목표 아키텍처와 WBS에 최종 반영하는 후속 단계를 별도 진행한다.
