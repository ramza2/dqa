# Real DEMIS Onboarding & Acceptance Runbook

Operator checklist for a **separately authorized**, first-time real DEMIS
**read-only** connection and controlled acceptance. It does not grant site
access/DBA authority, certify the outcome, or change runtime behavior. Do
not execute production actions based on this template without institutional
approval and an approved IdentityProvider.

## 1. 목적 / 적용 범위

이 runbook은 다음을 위한 운영 절차다.

- 실제 DEMIS 환경에 DQA를 최초 연결하기 전 준비와 검증
- 운영/실증 전 acceptance 기록
- 개발용 Oracle mock 검증과 production readiness를 혼동하지 않기

적용 범위 (**현재 Read-only acceptance만**):

- **READY** 상태의 검증된 Catalog Package v2를 소비하는 DQA path
- 현재 구현된 Approved + Enabled Query Template **SELECT-only** 실행
- Read-only Connection Profile + explicit live probe + Production Readiness Report
- 실제 DEMIS Read 계정의 DBA 최소권한/인증/감사 등 외부 증빙

현재 구현과 목표 (혼동 금지):

| 영역 | 현재 구현 (개발 검증 범위) | 목표 통합 플랫폼 |
|--|--|--|
| 의료진 UI | DQA Query/Data Discovery 개발·운영 UI | **SNUH.AI 단일 의료진 UI** / DQA는 관리자 UI |
| Schema 수집 | 기존 PoC 서비스·Package Import 유지; DQA 내부 metadata-only Inspector/Snapshot 캡처 **코드 존재**, 기본 비활성·운영 연결 차단 | 승인된 DQA 내부 Inspector→검증된 Snapshot→Preflight→READY Import/Activation |
| Discovery | Catalog Explorer + Keyword/Semantic/Hybrid 및 Index Status; Snapshot 이력·diff/review·WARNING 후보는 격리 개발 검증 | 통합 Inspector→독립 승인→READY Revision→Discovery 재색인 파이프라인 |
| MCP | 내부 Streamable HTTP, Discovery/Query Tool 4종 + readiness; 기본 제한 | 승인된 FHIR/SNUH.AI 클라이언트 연계 MCP/REST |
| Read 실행 | Approved + Enabled Query Template / read-only Oracle Adapter | 동일 안전 경계, 승인된 업무별 Read Capability 추가 |
| Write 실행 | **없음**; 모든 기존 경로에서 금지 | 기관이 승인한 **별도 Controlled Insert** (기본 disabled) |
| 승인 감사 | DQA 조회 실행 감사 | SNUH.AI/공식 임상 승인 원본 + DQA 등록 실행 감사 분리 |

별도 `demis-schema-search-poc` 사이트는 DQA Inspector 코드 존재 여부와
관계없이 **실 DEMIS parity(G1) 및 기관이 서명한 운영 Cutover(G5)** 전까지
유지하는 Legacy 서비스/참조 기준선이다. 최종 배포 의존성은 아니지만 이
read-only onboarding 절차에 따라 PoC 서비스/DB/Volume을 중단·삭제하거나
실제 Catalog 데이터를 마이그레이션하지 않는다.

적용하지 않는 범위 (**이 문서로 인증하지 않음**):

- 기본 비활성 Inspector의 실제 DEMIS metadata 접속/DBA 수집 승인 및 별도 수집 Runbook
- Legacy 전체 Source·Run·Snapshot/ZIP·Category 실데이터 이관, G1/G5 Cutover/운영 복구 승인
- Dynamic Query 실행/MCP 외부 연계의 운영 인증·접근 수용
- **임상문서·진료 결과 INSERT와 쓰기 계정/승인 증빙/쓰기 결과 대사**
- arbitrary LLM Text-to-SQL 직접 실행
- production IdentityProvider 구현 및 DBA 권한의 자동 PASS 판정

**중요:** Oracle mock E2E 및 U-02 합성/격리 parity·백업 복원 시험 성공은
개발 증빙에 한정된다. 실제 DEMIS 접근, 운영 IdP/DBA 권한, 임상 데이터
사용, Legacy 서비스 종료 및 운영 복구 승인 증빙이 아니다.
[U-02 인수인계](u02-integration-acceptance-handoff.md)와
[미결정 승인 항목](u02-external-decision-register.md)의 G0/G1/G2/G5를
별도로 충족해야 한다.

DQA는 **기본 비활성·관리자 제한의 Oracle metadata-only Inspector와
append-only Snapshot 캡처/이력, diff/review, WARNING-only v2 후보** 코드를
보유한다. 다만 운영 연결은 코드상 차단되어 있으며 **군/DBA의 실제 DEMIS
Schema·계정 승인, 독립 Preflight 및 READY 전환, 운영 수용은 미완료**다.
Inspector는 허가 후에도 Oracle `ALL_*` dictionary metadata 조회만
수행하고 일반 업무 데이터 조회/쓰기 권한을 얻지 않는다. Snapshot은
READY Catalog에 대한 자동 실행 권한이 아니다.
LLM이 생성한 임의 SQL을 즉시 실행하는 기능은 금지된다.
**현재 Read 실행 경로**의 SQL은 APPROVED + ENABLED Query Template에서만
나오며, Structured Dynamic Query Plan의 실제 실행은 별도 승인·검증 전까지
preview-only로 제한한다. Read-only SQL 안전성, 인증, 감사 경계는
Schema Inspector/추후 Controlled Write 도입에도 완화되지 않는다.

**임상 Insert는 이 runbook의 Read-only acceptance와 별도이다.**
실제 저장 경로(공식 API/프로시저/허가된 제한적 INSERT), 대상 의무기록
유형/필드, 임상 승인 시스템의 검증 가능한 승인 증빙, 쓰기 계정/최소권한,
멱등성/불명확한 커밋 대사, 의료 QA·보안·병원/군의 서면 인수와
별도 Write Runbook/Gate가 확정되기 전에는 어떤 실제 DEMIS Insert도
허용하지 않는다. **이 문서의 SELECT-only 검증 통과로 Write 권한이
생기는 것은 아니다.**

## 2. 사전 선결조건

자동/내부 확인 가능 항목과 외부 승인 항목을 분리한다. DQA는 외부 항목을
자동으로 PASS로 추정하거나 readiness report에 완료 상태로 저장하지 않는다.

### 2.1 Repository / DQA 내부에서 확인 가능

| 항목 | 확인 수단 (예) |
|------|----------------|
| DQA PostgreSQL Alembic at head | `./scripts/dqa-migrate.sh`, readiness `MIGRATIONS_AT_HEAD` |
| Active Catalog Package == READY | Catalog activate API / readiness `ACTIVE_CATALOG` |
| approved + enabled + Catalog-compatible Query Template 존재 | template APIs / readiness `QUERY_TEMPLATE` |
| Connection Profile enabled + adapter config complete | profile APIs / readiness `CONNECTION_PROFILE` |
| concrete DEMIS adapter available | readiness `DEMIS_ADAPTER` (`oracle` registered) |
| SQL safety / timeout / row-limit 적용 | template SQL safety + execution path |
| durable audit path 동작 | execute → `audit_id` → audit lifecycle |

권장 사전 명령:

```bash
./scripts/dqa-migrate.sh
./scripts/dqa-up.sh
./scripts/dqa-readiness.sh --source-name <source> --environment <environment>
```

### 2.2 외부 / 운영 승인 필요

다음 항목은 DQA repository만으로 완료할 수 없다. readiness report에서
`ACTION_REQUIRED` / `BLOCKED`로 남거나, 운영 기록에서 별도 evidence가 필요하다.

- approved production IdentityProvider
- 실제 DEMIS endpoint / network route
- 실제 read-only account 발급
- DBA read-only privilege 검증
- risky function/package EXECUTE privilege 제한
- approved TLS termination
- secret storage 방식 승인
- audit retention 기간 정책
- backup storage / encryption 정책
- LLM data-egress 정책 (결과행 기본 거부 유지)

**DQA는 위 외부 항목을 자동 PASS로 추정하지 않는다.**

## 3. Catalog Package 온보딩

순서:

1. finalized real Catalog Package v2 확보 (`package_format=demis-catalog-package`)
2. validate (checksum / readiness / required fields)
3. import (immutable revision persist)
4. `package_readiness` 확인
5. **READY** revision만 activate
6. active `source_name` 확인
7. 기존 Query Template의 Catalog revision / fingerprint compatibility 확인

주의:

- mock schema / table / source 이름을 production 상수로 하드코딩하지 말 것
- Catalog activation은 Connection Profile을 자동 생성·변경하지 않음
- WARNING / BLOCKED package는 query execution용으로 activate하지 않음

## 4. Production authentication

현재 production Compose 계약:

- `APP_ENV=production`
- `DQA_AUTH_PROVIDER=disabled`

이 상태에서 protected API가 fail closed되는 것이 정상이다.

승인된 production IdP가 정해지기 전:

- `dev_headers`를 production에서 사용 금지
- production Compose를 override하여 development auth를 켜지 말 것
- 임의 JWT / OIDC / SSO 구현 금지

향후 approved IdP가 결정되면 **별도 implementation PR**로만 진행한다.
이 runbook은 IdP를 구현하거나 provider type을 추가하지 않는다.

## 5. Real Connection Profile 등록

필요 정보 (값은 이 문서에 기입하지 말 것):

- `source_name` (active Catalog와 일치)
- `environment`
- `dbms_type` (현재 production-selectable concrete adapter: `oracle`)
- `host`
- `port`
- service / database name
- `username`
- `credential_secret_ref` (secret store / env reference only)

규칙:

- Connection Profile에 password / token / DSN 등 secret value 저장 금지
- reference만 저장 (`credential_secret_ref`)
- Catalog activation과 profile 변경은 독립
- 생성 후 `enabled=true` 및 configuration diagnostics 확인
  (`GET .../diagnostics`는 configuration-only; secret resolve / socket connect 없음)

실제 endpoint, account, credential 값은 runbook·ticket·PR에 붙여 넣지 말 것.

## 6. Explicit live connection test

Phase 25-A endpoint (administrator / `CONNECTION_PROFILE_MANAGE` only):

```http
POST /api/v1/connection-profiles/{profile_id}/test-connection
```

자동 실행되지 않는다. readiness report도 이 probe를 호출하지 않는다.

### 성공이 증명하는 것

- credential resolve 성공
- network / database connect 성공
- read-only transaction 설정 가능 (`SET TRANSACTION READ ONLY`)
- 최소 read probe 성공 (`SELECT 1 FROM DUAL`)

### 성공이 증명하지 않는 것

- 계정에 write privilege가 전혀 없음
- risky EXECUTE privilege가 없음
- 운영 정책(TLS / IdP / retention / backup) 전체 승인 완료
- production readiness overall READY

따라서 live probe 성공만으로 production READY 판정하지 말 것.
probe 결과는 현재 설계상 DB에 persist되지 않는다.

## 7. DBA privilege verification

DQA 밖, DBA / 보안 운영과 별도로 확인한다. DQA readiness의
`EXTERNAL_READONLY_PRIVILEGE`는 항상 `ACTION_REQUIRED`이며 자동 PASS되지 않는다.

### Acceptance checklist (최소)

- [ ] INSERT 권한 없음
- [ ] UPDATE 권한 없음
- [ ] DELETE 권한 없음
- [ ] MERGE 권한 없음
- [ ] CREATE / ALTER / DROP 권한 없음
- [ ] GRANT 권한 없음
- [ ] write-capable stored procedure / package EXECUTE 제한
- [ ] required SELECT 대상만 부여
- [ ] read-only transaction 동작 확인

확정되지 않은 Oracle system catalog query나 site-specific DBA SQL을
이 문서에 임의로 고정하지 않는다. 아래 evidence 필드에 DBA 측 참조만 기록한다.

| 필드 | 값 (실제 secret/SQL 붙여넣기 금지) |
|------|-------------------------------------|
| DBA evidence / reference | |
| Verified by (role) | |
| Verification date | |
| Notes | |

## 8. Production Readiness Report

```bash
./scripts/dqa-readiness.sh \
  --source-name <source> \
  --environment <environment>
```

`/health/ready`(DQA PostgreSQL reachable)와 역할이 다르다. readiness report는
metadata/config inspection이며 DEMIS credential resolve / socket probe를
수행하지 않는다.

### 상태 의미

| Status | 의미 |
|--------|------|
| `PASS` | 해당 technical check 통과 |
| `BLOCKED` | 실 DEMIS 진행 전 해결 필요 (예: migration mismatch, no READY Catalog, no production IdP) |
| `ACTION_REQUIRED` | 외부 조치/수동 확인 필요; DQA가 자동 완료하지 않음 |

특히:

- `LIVE_CONNECTIVITY`는 Phase 25-B에서 **항상** `ACTION_REQUIRED`
  (explicit administrator probe는 별도; 결과 persistence 없음)
- `EXTERNAL_READONLY_PRIVILEGE`도 **항상** `ACTION_REQUIRED`
- overall `NOT_READY`는 application defect를 자동으로 의미하지 않음
  (미해결 외부 선결조건이 남아 있으면 정상적으로 NOT_READY일 수 있음)

exit code: `0` = overall READY only; `1` = NOT_READY / inspection failure.

## 9. 최초 실제 Query acceptance

실 DEMIS 최초 실행은 한 번에 광범위하게 하지 말 것.

권장 순서:

1. 사전 승인된 저위험 Query Template 선택
2. 비식별 / 코드성 또는 최소 위험 조회 우선
3. execution preview
4. template `row_limit` / `timeout` 확인
5. explicit execute
6. result `row_count` 확인 (결과행 내용 문서화·로그·LLM 전송 금지)
7. `audit_id` 확인
8. audit lifecycle 확인

### 합격 조건

- template / Catalog / profile binding 정상
- SQL safety PASS
- parameter validation PASS
- execution timeout 범위 내
- row limit 적용
- result rows 미영속
- LLM result-row egress 없음
- `QUERY_REQUEST` STARTED / SUCCEEDED
- `QUERY_EXECUTION` STARTED / SUCCEEDED
- audit parameter logging policy `NAMES_ONLY`

실제 환자식별자·임상 값을 문서 예제·ticket·PR에 넣지 말 것.

## 10. Stop / rollback criteria

다음이 발생하면 실 DEMIS query를 즉시 중단한다.

- Catalog mismatch / non-READY activation attempt
- unexpected write privilege 또는 write-capable EXECUTE 발견
- audit persistence failure
- credential / DSN / secret leakage 의심
- unauthorized actor access
- TLS 미적용 상태에서 민감정보 반환
- unexpected result-row LLM egress
- timeout / row-limit 정책 위반
- production IdP 미설정 상태에서 protected API 우회 시도

중단 시 조치:

1. Connection Profile disable
2. 추가 execute 중지
3. 관련 audit / evidence 보존 (결과행 원문 복제·외부 공유 금지)
4. 원인 분석 후 이 runbook의 해당 단계부터 재검증

DEMIS에 대한 DB rollback SQL, privilege 변경 SQL, 임의 DDL/DML은
이 runbook에서 작성·실행하지 않는다.

## 11. Acceptance record template

실제 사람 이름, 계정, URL, credential, DSN, SQL, 환자 데이터를 기입하지 말 것.
Evidence Reference에는 ticket ID / 내부 문서 ID 등 non-secret 참조만 사용한다.

| 항목 | 상태 | 검증일 | 검증 주체/역할 | Evidence Reference | 비고 |
|------|------|--------|----------------|-------------------|------|
| Production IdP | PENDING | | | | |
| Catalog READY | PENDING | | | | |
| Connection Profile | PENDING | | | | |
| Live Probe | PENDING | | | | |
| DBA Read-only Privilege | PENDING | | | | |
| Risky EXECUTE Restriction | PENDING | | | | |
| TLS | PENDING | | | | |
| Audit | PENDING | | | | |
| Backup/Retention | PENDING | | | | |
| First Controlled Query | PENDING | | | | |

## 12. Development / mock evidence

현재까지 repository / 개발 환경에서 검증된 Oracle mock 흐름 (development only):

- source: `oracle_demis_mock` (mock; production 상수 아님)
- explicit live connection probe PASS
- recommendation PASS
- parameter extraction PASS
- execution preview PASS
- read-only execution PASS (`row_count=3` in mock smoke)
- audit lifecycle PASS
- 전체 Oracle mock E2E smoke PASS

이 결과는:

- production evidence가 아님
- real DEMIS privilege 검증이 아님
- approved production IdP 검증이 아님
- Production Readiness overall READY를 의미하지 않음
