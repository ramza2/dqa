# Real DEMIS Onboarding & Acceptance Runbook

Authoritative operator procedure for first-time real DEMIS linkage and
controlled acceptance. This document does **not** change runtime behavior.

## 1. 목적 / 적용 범위

이 runbook은 다음을 위한 운영 절차다.

- 실제 DEMIS 환경에 DQA를 최초 연결하기 전 준비와 검증
- 운영/실증 전 acceptance 기록
- 개발용 Oracle mock 검증과 production readiness를 혼동하지 않기

적용 범위:

- finalized Catalog Package v2를 소비하는 DQA consumer path
- approved + enabled Query Template 기반 read-only 실행
- Connection Profile + explicit live probe + Production Readiness Report

적용하지 않는 범위:

- DEMIS Schema Analyzer crawling / metadata inspection
- arbitrary LLM Text-to-SQL 실행
- production IdentityProvider 구현 (별도 승인 PR)
- DBA privilege의 자동 PASS 판정

**중요:** Oracle mock E2E 성공은 development evidence일 뿐이다. real DEMIS
production readiness, production IdP readiness, 또는 DBA privilege acceptance를
의미하지 않는다.

DQA는 schema crawler가 아니며, LLM이 생성한 임의 SQL을 즉시 실행하는
시스템이 아니다. 실행 가능한 SQL은 APPROVED + ENABLED Query Template에서만
온다.

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
