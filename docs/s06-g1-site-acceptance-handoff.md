# S-06-A~H 개발 검증 종합 및 G1 실기관 Parity 수용 준비

> 작성: 2026-10-19 · 기준 DQA `main@73d91b8` (PR #130 squash merge / 서버
> `~/dqa` Fast-forward 확인) · **문서 전용, G1 승인 전 준비자료**.
>
> **현재 판정:** `DEV_SYNTHETIC_BASELINE_VERIFIED` /
> `REAL_DEMIS_PARITY_NOT_VERIFIED` / `CUTOVER_NOT_APPROVED`.
> G0/G1/G2/G5, 독립 DBA Preflight/READY, 운영 DB 연결·진료 데이터 접근·Legacy 종료를
> 이 문서나 합성 회귀 통과로 승인한 것이 아니다.

## 1. 검증 완료 범위와 남은 차이

기준 근거: [U-02 인수인계](u02-integration-acceptance-handoff.md),
[외부 의사결정 DEC-01/04/10](u02-external-decision-register.md),
[복제 EMR DB 협의 Q01–Q09](u01-replicated-emr-db-architecture-review.md),
[Unified WBS S-06 / G1](roadmap.md).
각 단계의 pytest 수는 **테스트 선택·중복이 다른 개별 회차의 실행결과**다.
이를 합산하여 프로젝트의 총 통과 건수 또는 현장 인수율로 표시하지 않는다.

| 단계·근거 | 내부에서 확인된 내용 | 서버 수용 기록 | G1까지 여전히 부족한 근거 |
|---|---|---|---|
| [S-06-A](s06a-synthetic-schema-search-gold.md) | 합성 Schema Diff / 복합 FK·Index·Package 후보, 별도 일회용 PostgreSQL 검색과 Active Revision·Embedding 보호 | 개별 문서·로그 참조; 이번 종합에서 신규 실측값을 만들지 않음 | 실제 승인 Schema의 Diff·검색 의미적 타당성 |
| [S-06-B](s06b-expanded-gold-query-relations.md) | 합성 Gold Query 정량 산식, Exact Top-1, 의료용어 확장, Source 격리 및 Stub 1024d Semantic/Hybrid | S-06-H 검증에서 기존 S-06-B 포함 10 PASS; 5개 합성 질의 `Recall@5=MRR@5=nDCG@5=1.0`, `Precision@5=0.2` | 실 승인 Dataset·실 모델의 품질/임계치. Stub 점수와 혼동 금지 |
| [S-06-C #125](s06c-inspector-to-candidate-gold.md) | 2 Table Oracle Fake Dictionary → Inspector Snapshot/Diff → v2 `WARNING` | **31 PASS / 5 SKIP**, 이때 Legacy 비교 경로 SKIP을 PASS로 간주 불가 | 실제 Legacy Oracle Dictionary 및 PoC/DQA 비교 |
| [S-06-D #126](s06d-synthetic-dictionary-drift-guards.md) | Index 누락, 외부 복합 FK drift, 민감 SQL 제외, 비정상 Index 거부 | **35 PASS / 0 SKIP** | 실제 Dictionary grant 누락과 실 DDL 변화의 DBA 판별 |
| [S-06-E #127](s06e-warning-candidate-discovery-contract.md) | 2 Table `WARNING` 후보 → 메모리 검색 문서 6건과 FK 경로·Fingerprint | **32 PASS / 0 SKIP** | 실 인덱스/문서·검색 실측 |
| [S-06-F #128](s06f-warning-index-active-search-isolation.md) | 2 Table `WARNING` 정식 Import 및 문서/Stub Embedding 저장 후 Active READY 검색 격리 | **8 PASS / 0 SKIP**, 일회용 PG 정리 완료 | 실제 DBA 발급 READY/사이트 Active 사용 승인 |
| [S-06-G #129](s06g-expanded-25table-oracle-gold.md) | 가상 25 Table/50 Column/24 FK/24 Index → 75개 메모리 문서, 행순서·Drift·Source 격리 | **33 PASS / 0 SKIP** | **25개는 실제 DEMIS 스키마 건수도 기존 Oracle Mock 인스턴스의 실측도 아님** |
| [S-06-H #130](s06h-disposable-25table-warning-index.md) | 같은 가상 25 Table 후보의 Import → 75개 문서/Stub Vector, 재실행 멱등, 기존 READY 검색 보호 | **10 PASS / 0 SKIP**, 일회용 PG·네트워크 정리 완료 | 실제 복제 EMR DB·PoC 동등성, 실 Embedding 모델/검색 품질 |

S-06-F/H의 합성 `READY`는 테스트 Fixture일 뿐 독립 DBA 증빙/승인
결과가 아니다. `embedding_coverage.is_ready`는 1024d Stub 벡터 최신성,
Catalog `package_readiness=READY` 발급 권한과 무관하다. DQA 자체 생성
`WARNING` 후보는 승인 전 활성화하지 않는다. S-06 관련 Merge #125~#130은
GitHub `main` 소스 반영이며 운영 Docker 배포·실기관 현장 검증이 아니다.

## 2. 선행 결정: 무엇을 먼저 받아야 하는가

| 우선/결정 | 군·DBA·협력기관에 확인할 항목 | 서면/보안경로로 받을 최소 산출물 | 미확정이면 |
|---|---|---|---|
| **P0 / DEC-10** | 원본 운영 EMR 또는 복제 EMR DB 중 **공식 조회 원천**이 무엇인가? 복제본 DBMS/버전/Edition, 제공·운영 주체, 동기화·지연·범위, 데이터 소유권, Oracle/복제 옵션 라이선스 책임은? | 승인 원천·복제 토폴로지, DBMS/운영 책임·복제 계약, 라이선스 확인, 데이터 범위/장애 처리 정책. 기존 [Q01/Q02/Q04/Q09](u01-replicated-emr-db-architecture-review.md) 참조 | DQA Oracle Adapter의 운영 대상/Schema, 실 검증 비교군을 결정하지 않음 |
| **P0 / DEC-01** | 누가 어떤 계정/망에서 어느 **Source·Schema·View·Dictionary**를 검사할 수 있는가? 원본과 복제본의 ALL_* 가시성과 외부 FK는 동일한가? 계정 역할·권한·반출 허용 범위는? | DBA가 확인한 Source/Schema allowlist, Metadata-only grant/읽기 전용 제약, 네트워크·보안 승인 문서. [Q03/Q06](u01-replicated-emr-db-architecture-review.md) | 실 DB 접속·Inspector Target 추가/교체·원시 메타데이터 수집 금지 |
| **P0 / DEC-04** | PoC와 DQA 비교 **대상 Source/Schema/시점**, Table/View·Column·PK/UK·복합 FK·Index·Comment의 canonical 규칙과 허용 누락/차이는? Gold Query 표본·정답 키·Top-k 품질 임계치 및 검증 책임자는? | Versioned field/Normalization 정의서, Baseline Snapshot·예외/누락 사유, 시험 시나리오·검수자·판정 임계치·승인서 | `REAL_DEMIS_PARITY_NOT_VERIFIED`, G1 `BLOCKED`, Legacy 종료 금지 |
| **별개 / DEC-02** | 독립 Preflight/READY 발급자·검증 시점·서명·만료·철회·재사용 정책 | 신뢰된 발급·검증 정책 및 감사 계약(미확정, #77 Draft) | 합성 `WARNING`의 `VERIFIED` 또는 `READY` 자동 승격·실 활성화 금지 |
| **별개 / DEC-05·09·G2/G4** | 실 환자 데이터 조회와 의료기록 저장 공식 Interface/권한의 별도 승인 여부 | G2 조회 최소권한/IdP/TLS·감사, G4 승인된 저장 Operation/임상 책임 | G1 메타데이터 검증을 진료정보 조회/쓰기 권한으로 확대 불가 |

**특별 확인:** 복제 EMR DB가 **Oracle이 아닐 수도 있다**. DBMS·허용 접속
방식(API 중계 포함)이 결정되기 전 DQA의 Oracle Inspector를 그대로 실
복제 DB에 사용할 수 있다고 전제하지 않는다. 복제본 장애 시 원본 운영 EMR
자동 우회는 금지한다. 운영 원장 Write는 별도 DEC-09/G4 경계다.

## 3. G1 실제 비교 실행 전 'Go / No-go' 체크리스트 (현재 모두 PENDING)

아래 각 항목은 **군/운영/DBA가 권한과 범위를 서면 허가한 뒤에만**
실제 환경에서 수행한다. 사전 협의 단계에서는 문서 검토만 한다.

| 순서 | 증빙·사전 확인 (값은 기밀 저장소만) | 검증책임/관계자(제안) | 현재 |
|---|---|---|---|
| G1-01 | 승인된 Read/Inspector Source, Target DBMS, Schema/계정 Allowlist와 최소권한/망 정책이 같은 대상에 묶였는가 | DBA·보안 / 의료정보체계과 | PENDING |
| G1-02 | Legacy PoC 기준과 DQA 기준의 원천·추출 시점·Snapshot identity/Fingerprint 정규화 기준이 기록됐는가 | DBA·QA·PL | PENDING |
| G1-03 | 동일 Scope의 TABLE/VIEW·COLUMN 타입/NULL/정밀도/Comment, PK/UK, 복합 FK 매핑·외부 Schema, INDEX별 개수·순서를 비교할 Gold 기준이 승인됐는가 | DBA·QA | PENDING |
| G1-04 | Dictionary에 보이지 않는 객체, 복제되지 않은 View/Index, 변경 중 DDL, 원본↔복제 지연을 '결측/정책제외/정상차이/오류'로 판정하는 규칙이 있는가 | DBA·운영사 | PENDING |
| G1-05 | Canonical Diff에서 변경 0/다름의 기대 결과, 허용 편차/예외 사유, 수용 기준 임계치·재검증 절차를 승인했는가 | QA·DBA·PL | PENDING |
| G1-06 | 동일 승인 Catalog/모델/Version·Source·Revision 조건의 검색 Gold Query(실데이터 필요 여부와 비식별 기준 포함), Recall@k/Precision@k/MRR@k/nDCG@k 임계치가 합의됐는가 | QA·DBA / 의료 QA·업무 담당 | PENDING |
| G1-07 | 변경 시 문서/Fingerprint/Embedding Coverage 및 Active READY-only·Source 격리, 오류 시 기존 상태 보존을 어떻게 현장 시험할지 승인됐는가 | QA·PL·DBA | PENDING |
| G1-08 | 수집·비교 결과의 반출/보관/열람·감사·가명처리/마스킹 정책, 보안 위치·검토자·승인번호가 확인됐는가 | 보안·DBA·군 담당 | PENDING |
| G1-09 | 차이 목록과 예외를 처리할 책임자, 검증 후 정리/재검증 시점, 기관 G1 판정 서명 절차가 확정됐는가 | 군 검수자 / QA·PL·DBA | PENDING |

- **금지:** 위 항목 미충족 상태의 DQA Production Connection Profile/Secret 수정,
  실 Oracle/DEMIS/복제 DB 접근, 데이터 Dictionary crawl, 환자 SELECT,
  비승인 Dynamic SQL, 임상 Write, 기존 활성 포인터 변경, PoC 서비스 종료.
- **수행 방식 제안:** 권한 문서 승인 → 허용 범위·비식별 자료 수령
  → 동일 Scope의 Legacy/DQA 출력물 offline canonical 비교
  → 민감 필드/원시 SQL 없는 구조적 Diff와 Gold 결과/결측 사유
  → QA·DBA·군 검수자 판정. 실제 DB 접속 필요성은 별도 승인 후 재검토.
- **소프트웨어 DB보안:** 현장 DB암호화·DB접근통제·서버보안 장비가 있다면
  제품명뿐 아니라 해당 정책의 적용 구간, 검사 계정 허용 범위, 감사/접속 차단
  책임자를 DBA/보안 담당에게 별도 확인한다. 제품 설치 사실만으로
  검사 접근권한 또는 정책 충족을 추정하지 않는다.

## 4. 현장 인수 증빙 등록 형식 — 빈 양식

> **값을 임의 기입하지 않는다.** 증빙 ID/Checksum은 기관 승인 보관소의
> 식별자로만 연결하고, GitHub·ChatGPT·일반 메일에는 IP/DSN/비밀/라이선스번호,
> 원본 의료정보, 환자 ID, 원시 SQL/default/index 정의, 원본 벡터 등을 반출하지 않는다.

| 기록 항목 | 현재 |
|---|---|
| `decision_id` / 연결 Gate / 승인 문서 번호·버전·유효기간 | PENDING |
| 발급/검증 기관과 **실제** 승인자·담당역할 | PENDING |
| 원본/복제 Source 식별 참조와 DBMS/Version·허용 Schema | PENDING |
| Inspector/Read 계정 구분 및 metadata visibility 확인 참조 | PENDING |
| Legacy PoC Snapshot·DQA Snapshot의 승인 시점/Scope 및 Canonical 규칙 버전 | PENDING |
| 비교 항목별 총 건수·결측·예외·수정/재실행 결과의 **비민감** 요약 | PENDING |
| Gold Query Set 버전/라벨 정책/Top-k/임계치/결과/반례 | PENDING |
| 민감정보 통제/내부 보안 보관소 참조 및 Evidence SHA-256 | PENDING |
| 군/병원·DBA·QA의 종합 판정 및 허가된 **다음** 작업 | **BLOCKED / NOT_APPROVED** |

## 5. 후속 협의와 개발 우선순위

- **1차: 2026-10-22 의료정보체계과 협의 준비** — 현재
  [복제 DB 검토서 §5](u01-replicated-emr-db-architecture-review.md)의
  Q01–Q04/Q06/Q09를 DEC-10·01·04에 연결해 질문, 담당역할,
  회신 문서/버전/권한 승인 경로를 확인한다. 이 회의는 일정 *요청/준비*
  상태로, 개최·결정 완료를 주장하지 않는다.
- **2차: 문서 수령 후** — DEC-10/01/04 근거가 확보된 경우에 한해
  실제 Metadata 비교 범위/방식의 승인을 요청하고 미수용 항목을
  Risk Register에 남긴다. 승인 전 연결·실행 없음.
- **3차: G1 수용 이후 별도** — 운영 포털 S-05 범위(DEC-08),
  Preflight 발급/READY(DEC-02), G2 실조회(DEC-05), FHIR/SNUH.AI ICD,
  G5 원본 이관/백업/Legacy 종료(DEC-06/07)는 각각 별도 승인으로 진행.
- **LLM 관련 Draft PR #124** 및 독립 Preflight 정책 Draft #77은
  현재 Gate를 통과했다고 가정하여 병합·수정하지 않는다.

**개발 다음 작업:** 권한과 판정 기준이 들어오기 전에는 S-06-A~H 합성
검증을 G1 완료로 승격하거나 신규 운영 통합 코드를 임의 확장하지 않는다.
기관 질문 회신과 승인된 수용기준을 이 문서에 연결하는 작은 문서 PR을
우선하고, 실제 원천 접근/배포는 항상 별도 명시 승인 후 진행한다.
