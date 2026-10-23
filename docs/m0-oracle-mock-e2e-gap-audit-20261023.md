# M0 — Oracle Mock E2E 정적 점검 및 개발 착수 판정 (2026-10-23)

> 기준: `main@6e3f135`. GitHub 소스·설정·테스트의 **정적 점검** 결과이다. 사용자 서버의 실제 컨테이너, Oracle 접속, DB 내용, 네트워크, 포트, 환경변수 및 테스트 실행 결과는 이 단계에서 **새로 확인하지 않았다**. `dqa-onprem-*`, `demis-oracle-test` 등 운영/기존 테스트 스택은 변경하지 않았다.

## 0. 추가로 알려진 사실과 미확정 사항

- 2026-10-23 사용자 전달: 의료정보체계과가 관리하는 **기존 DEMIS 관련 DB 버전은 Oracle Database 19c**.
- **구별 필요:** 기존 개발 Mock 구성의 서비스 이름은 `FREEPDB1`, 호스트 식별자는 `demis-oracle-test`. 이것만으로 Mock의 Oracle DBMS 버전을 **19c라고 단정할 수 없다**. 실 DBMS 버전, Edition, 권한, 기존 Standby/향후 조회 복제 DB의 DBMS/버전과 운영 가능 여부는 별도 확인.
- `oracle+oracledb` Thin 및 `ALL_*` Dictionary Inspector는 현재 코드 기반으로 존재하지만, **Oracle 19c 환경에서의 실연결/계정 권한/메타데이터 결과**는 검증되지 않았다.
- 10월 22일 협의 전사/메모의 Standby DB, 복제 DB, 세션, 환자번호 이슈는 **설계 제약/질문**이지 연결이나 권한 승인 근거가 아니다.

## 1. 소스 기반 확인표

| 사용자 흐름 | 재사용 가능한 실제 코드 | M0에서 확인한 부족한 연결 |
| --- | --- | --- |
| 대상 등록 | `backend/app/api/routes/connection_profiles.py`: CREATE/LIST/GET/PATCH/ENABLE/DISABLE, configuration diagnostics, **명시적** test-connection API. `frontend/src/components/ConnectionProfilePortal.tsx`은 등록·수정·비활성 지원 | UI API client `frontend/src/api/connectionProfiles.ts`에 **enable/test-connection 호출 자체가 없음**. 화면은 live probe를 하지 않도록 의도적으로 구현됨 |
| DB 연결 | `backend/app/adapters/demis/oracle.py` 읽기 전용 Adapter와 `test_connection_profile_live_connection` | Oracle Mock E2E 안전 대상 식별 및 개발 전용 UI 실행 가드/검증 부재. 연결 성공과 데이터/메타데이터 권한은 별개 |
| 구조 분석 | `schema_inspection.py` `OracleSchemaInspector`(Table/Column/Comment/PK/UK/FK/Index) 및 `schema_snapshot_capture.py` | Inspector의 Target은 API Profile이 아니라 `DQA_SCHEMA_INSPECTOR_*` 서버 설정 **단일 허용 스키마**. 별도 `DEMIS_INSPECT_SECRET_*` 자격증명을 요구. `ConnectionProfilePortal`의 Target Review는 오프라인 설정 대조만 수행 |
| Catalog | Snapshot history/diff/review, `schema_catalog_candidate.py`, v2 Import/활성 READY-only 기능 | 자동 수집 결과는 **WARNING 후보**. 실제/개발 환경의 검증된 READY 수용·Import·Activation까지 단일 UI 흐름 없음; 정책 확정 없이 WARNING 자동 READY 승격 금지 |
| 자연어 Query Template 신규 작성 | Query Template CREATE/UPDATE/VERSION/SUBMIT/APPROVE/ENABLE 백엔드 API | **자연어→신규 SQL SELECT DRAFT 생성기 및 관리자용 Template UI 없음**. 기존 `recommendations.py`는 승인된 기존 템플릿 **추천** 전용. 환자 데이터 없이 Catalog metadata만 사용하도록 신규 안전성 설계 필요 |
| 조회 결과 확인 | `QueryAssistant.tsx`, `query_executions.py`, Oracle Adapter, 감사 | 사전 승인된 템플릿의 추천→파라미터→preview→execute 흐름은 있음. **사용자가 새로 만든 템플릿으로 처음부터 끝까지 Mock 데이터 결과를 보는 UI E2E**는 별도 시험 필요 |
| 기존 Mock 경로 | `docker-compose.onprem.oracle-mock.yml`, `scripts/dqa-oracle-mock-bootstrap.sh`, `scripts/dqa-oracle-mock-smoke.sh`, security smoke | Bootstrap은 `oracle_demis_mock` Profile + `demis.code-master.by-group` 템플릿 1종을 등록·승인한다. 신규 자연어 Template 작성·Catalog 생성은 시험하지 않음. Oracle Mock overlay는 **기존 외부 Docker network** `demis-schema-search-poc_demis-net` 필요 |
| 브라우저 권한 | `docker-compose.onprem.dev.yml` 개발용 `dev_headers`, QueryAssistant 사용 가능 | 기본 Vite UI `VITE_DQA_DEV_ROLES=query_operator`; Connection Profile 관리 API는 `CONNECTION_PROFILE_MANAGE` 요구하므로 **기본 브라우저 세션으로 관리자 UI E2E 불가**. 프로덕션 auth 비활성/Fail-closed를 변경해서 해결하지 말 것 |

## 2. 개발 전 안전 조건 (Blocking)

1. **운영 DQA와 완전히 격리:** 새 Compose project name, 신규 DQA PostgreSQL volume, 별도 Frontend bind port를 사용한다. 기존 `dqa-onprem` DB/볼륨·컨테이너에 새 Migration/pytest/bootstrap을 실행하지 않는다.
2. **Mock allowlist:** 개발 관리자 UI의 “연결 테스트/활성화”는 백엔드에서 `APP_ENV=development/test`, `source_name=oracle_demis_mock`, `environment=development`, 사전 승인한 Mock target identity(host/service) 등을 **독립 재검증**해야 한다. 단순 Frontend 표시 제한은 보안 경계가 아니다.
3. **분리된 Credential:** SELECT 전용 Credential과 metadata Inspector Credential은 현재와 같이 별도 접두사/최소권한. 관리 UI에 원시 암호·DSN 출력/입력 금지.
4. **DB/인증 분리:** dev_headers 관리자 역할은 별도 **격리 개발 스택**에서만 허용. 기존 프로덕션 `APP_ENV=production`, `DQA_AUTH_PROVIDER=disabled` 실패 차단 동작 보존.
5. **Catalog 권한:** `WARNING` Candidate는 자체적으로 검색 활성화 불가. Mock 전용 검증된 READY Catalog fixture / 정책을 독립적으로 마련하며 실기관 G1 증빙이라고 주장하지 않는다.
6. **불특정 SQL 금지:** LLM 출력을 실행 API에 직접 공급하지 않는다. 신규 초안은 admin 검토·SQL AST/Template·대상 스키마·파라미터 바인딩·버전/권한 경계를 통과해야 실행 가능하다.
7. **테스트 오염 금지:** 운영 DQA의 `backend/tests/conftest.py` 중 DB 세션 TRUNCATE fixture가 사용될 수 있으므로 프로젝트 DB 전역 `pytest` 금지. 오프라인 단위 테스트와 일회용 DB runner만 사용.

## 3. 다음 작업 우선순위 및 수용 기준

### M0-A. 개발 Mock 재현성 점검 (서버 읽기 전용 조사 — 별도 수행)
- Docker network/Mock service 실제 존재, Oracle Mock 버전, 활성 Mock Catalog source/revision, Query Template/readiness, 개발용 접속 Credential **설정 여부만** 확인 (값 출력 금지).
- 현재 DQA 소스 최신 main과 기존 운영 컨테이너 버전 차이를 기록한다.
- 외부 Oracle/DEMIS 연결 시도 없음. Mock이 19c가 아니면 **19c 버전 차이 회귀**는 별도 일회용 fixture/테스트로 보완한다.

### M1. 개발 Mock 관리자 Profile 연결 UI (첫 코드 PR)
- **Backend**: Production/일반 Source에서 새 개발 Mock-only UI 호출이 실행될 수 없게 추가 정책 확인; 기존 API의 독립적인 운영 관리자 권한은 임의로 완화하지 않는다.
- **Frontend**: 명시적 Mock 대상만 “연결 상태 확인/활성화” 제공; 실패·성공과 configuration-only diagnostics를 구분; 이중 클릭/선택 변경/stale 응답/네트워크 장애 대응.
- **테스트**: 개발 허용 Mock만 요청/승인 흐름, 일반/운영 target/비관리자 거부, Credential 비노출, real connection 무단 실행 0을 Mock HTTP/오프라인 테스트로 확인.
- **완료 조건**: 별도 관리자 개발 UI에서 Mock 등록→명시적 테스트→enable 및 실패 처리. 운영 프로필은 기존 수준 이상으로 제한.

### M2. Inspector → Snapshot → Catalog 관리 UI
- 개발용 Inspector는 **서버 승인 대상 한 개**로 제한한 채 Mock Profile identity 대조. Snapshot→WARNING candidate, 검토/승인 Fixture→READY 활성화까지.
- 승인 정책·증빙 미확정시 실기관 READY/Preflight 단계는 독립 금지.

### M3. 자연어→새 Query Template DRAFT 및 관리자 검토
- 새 Endpoint/UI, 안전성 검증, 검토·승인·버전과 연동. 기존 추천 기능은 변경 최소화.

### M4. 조회 결과 E2E
- 새 승인 템플릿 사용, 안전한 SELECT와 읽기전용 Mock 결과·감사 기록, 불일치/실패/재시도·인증 거부 테스트.

## 4. M0 판정

**STATIC_SOURCE_REVIEW_COMPLETE / LIVE_MOCK_INVENTORY_PENDING / ORACLE_19C_SITE_COMPATIBILITY_NOT_VERIFIED**.

M0 정적 점검만으로 DQA 운영 컨테이너·Oracle Mock 연결/등록/분석/조회 또는 M1~M4 종단간 동작이 검증되었다고 표기하지 않는다. M1 개발 착수는 **기존 운영 환경과 격리된 feature branch**에서 진행하며 PR Merge·서버 기동·DB 변경은 각각 별도 승인 후 수행한다.
