# U-01-R2 — 2026-10-22 체계과 협의 반영 및 DQA Oracle Mock 종단간 개발 계획

> 상태: **내부 개발 계획 초안 / 외부기관 승인 및 실 DEMIS 연결과 무관**  
> 기준: `main@6e3f135` (2026-10-19), 2026-10-22 의료정보체계과 협의 전사·메모.  
> 이 문서는 DQA의 **내부 선행 개발**을 위한 것이다. DQA를 컨소시엄 공식 아키텍처의 필수 제품, FHIR 제공사 구현 범위, DEMIS 운영사 계약 의무로 선언하지 않는다.


## 0. 기술 기준 및 M0 점검 (2026-10-23)

- 군 의료정보체계과 관리 DEMIS 관련 DB의 확인된 버전은 **Oracle 19c**(사용자 전달). **조회용 Standby/별도 복제 DB도 19c인지, 실제 Mock이 19c인지 아직 미확정**이며 19c 실기관 호환성 검증·접속 승인을 의미하지 않는다.
- 기존 개발 Oracle Mock은 `demis-oracle-test` / `FREEPDB1` 설정을 사용한다. 해당 Mock의 실제 버전은 별도 확인 필요.
- 현재 구현과 UI/권한/승인 체계 간 결손, 안전하게 개발할 순서, 환경별 차단조건은 [M0 정적 점검 결과](m0-oracle-mock-e2e-gap-audit-20261023.md)를 기준으로 한다.
- M0 정적 코드 점검은 완료했지만, 실제 Mock 컨테이너·포트·Credential·기존 Catalog 상태는 읽기 전용 서버 실측 전이므로 **M0 현장 재현성 검증은 미완료**이다.

## 1. 개발 목표 — 사용자가 UI에서 한 바퀴 돌릴 수 있는 Oracle Mock E2E

승인된 **가상 Oracle Sample/Mock**만을 사용하여 다음 6개 사용자 흐름을 끝까지 구현·검증한다.

1. **DB 대상 등록 및 연결 확인:** 개발 전용 Oracle Mock의 Connection Profile을 생성·검증·활성화하고 관리자 화면에서 연결 상태를 확인한다.
2. **DB 구조 자동 분석:** 승인된 개발용 스키마 한정 메타데이터 검사(Table, Column, Comment, PK/UK/FK, Index)를 실행하고 Snapshot을 저장한다.
3. **Catalog 생성·검토:** Snapshot·Diff·v2 Package 후보를 검토하고 명시적 **개발용 검증 정책**에 따라 실제 검색 가능한 READY Catalog로 연결한다.
4. **자연어 Query Template *초안* 작성:** “코드 그룹별 코드를 조회하는 템플릿을 만들어줘” 같은 요청과 선택된 Catalog의 **스키마 메타데이터만**으로 SQL SELECT 초안·파라미터 스키마·설명·제한을 만든다.
5. **Template 관리·승인:** 작성자에게 생성된 SQL과 근거 테이블/컬럼을 보여주고 수정/버전화, SQL 안전성 검사, 관리자 검토·승인·활성화를 수행한다.
6. **실행·결과 확인:** Query Assistant가 승인된 Template을 추천하고 파라미터를 검증한 후, 기존 Oracle Mock의 읽기 전용 SELECT로 제한된 조회 결과를 표와 감사 이력에서 확인한다.

**완료 기준:** 새 개발용 환경에서 사용자가 UI만으로 1~6을 연속 수행할 수 있고, API·통합 테스트가 실행/차단/재시도/복구 경계를 검증한다. 단, Secret 주입과 설치는 별도의 안전한 개발환경 설정으로 수행해도 된다. 외부 DB·실환자 데이터는 E2E에 절대 포함하지 않는다.

## 2. 현재 구현/누락 분리 (기존 API 재사용 우선)

| 흐름 | `main`에 구현된 기반 | 부족한 통합 기능 |
| --- | --- | --- |
| DB 등록/연결 | `/api/v1/connection-profiles` CRUD·diagnostics·live test API, React metadata-only 관리 화면; Oracle SELECT adapter | **개발 Mock 전용** 연결 테스트/명시적 enable UI; 선택 대상과 허용환경 표시; 비밀정보 화면 노출 금지 |
| 스키마 분석 | Oracle `ALL_*` metadata Inspector(단일 서버 설정 schema), Snapshot capture/history/diff/review; 운영 기본 차단 | UI 선택 Profile과 관리자 승인 Inspector Target의 안전한 identity/scope 바인딩; Mock용 분석/캡처 사용자 흐름 |
| Catalog | v2 import, immutable revision, READY-only activation, Inspector→`WARNING` 후보 빌더, Data Discovery | Snapshot 후보 검토→독립 검증→READY 단계가 불연속. **운영 승격 우회 금지**, 명시적 dev-only mock 수용 검증 또는 기존 승인된 Mock READY fixture와 대응 검증 |
| 자연어 템플릿 신규 작성 | 없음. 기존 추천 API는 **기존 APPROVED Template 중 추천**; 파라미터 추출은 별개 | 새 “자연어→Query Template DRAFT” 기능 및 관리자 작성 UI 필요 |
| Template 관리 | Create/update/version/review/approve/enable, SQL safety/preview/execute API | 작성·검토·승인·버전·활성화 전체 관리자 UX 연결 |
| 실제 결과 | Query Assistant, 승인 template execute, 제한된 read-only Oracle Adapter, 감사·MCP/REST 기본 경계 | 새 분석 스키마에서 생성한 **새 Template**의 Mock 데이터 실행 및 결과표·감사 연계 E2E |
| 운영 배포 | On-prem Docker/PostgreSQL/pgvector/Frontend; dev auth overlay 지원 | 최신 브랜치는 현재 실행 컨테이너에 미배포. 기존 운영 DQA가 아닌 **격리 개발 스택**에서만 통합 수용 |

기존 Mock bootstrap은 `oracle_demis_mock`의 Connection Profile과 `demis.code-master.by-group` 승인 Template을 준비한다. 이것은 **기존 한 개 템플릿의 등록·승인** 시험이지 자연어 신규 작성이나 새로운 스키마의 전체 UI E2E가 아니다.

## 3. 2026-10-22 회의 반영: 외부 조건과 내부 Mock의 경계

| 구분 | 회의에서 확인/논의한 내용 | DQA 선행 개발 처리 |
| --- | --- | --- |
| 조회 원천 | DEMIS 운영 통합DB 직접 조회는 허용되지 않으며 기존 Standby 활용 가능성 또는 별도 복제 DB를 DBA/운영사와 검토. DBMS 버전/접속/복제 라이선스·비용 미확정 | Mock 대상만 연결. 운영 통합DB 자동 fallback 금지. 실제 소스는 DEC-10 후 결정 |
| 복제/정합성 | 12개 거점병원과 사령부 통합DB 동기화가 있고 정합성·중단·복제 주기 우려 | `source_name`, Snapshot 버전/시점, 데이터 갱신지연과 불일치 대응은 ICD/운영 검토 항목으로 유지 |
| 식별자 | 군번/주민번호는 중복 가능하며 DEMIS의 **고유 환자번호**를 중심으로 접근해야 함 | 실제 식별자명·Encounter 매핑은 가정하지 않음. Mock은 가상 식별자만 사용 |
| 인증/권한 | 기존 군 통합 SSO에 별도 체계로 가입하는 것보다 **DEMIS 주체계의 보조 시스템**으로 세션·권한정보를 연계하는 방향 논의. 병원/직군/진료과 접근 정책 필요 | DQA 독자적 군용 SSO 구현 금지. Mock dev_headers는 개발 전용; 실제 세션·위임/정책 결정은 DEC-03/05 |
| 화면·확정 | DEMIS 진료화면 연계, 의료진 선택에 따른 자동/수동 호출, 의료진 검토 뒤 기록 반영 논의 | DQA E2E 범위는 **read-only**. 임상 저장/DEMIS 쓰기는 DEC-09 및 별도 승인 전 구현·테스트 제외 |
| 컨소시엄 R&R | FHIR(메디칼스탠다드), 플랫폼/Agent(인프메딕스), DEMIS 연계(오픈링크) 실 ICD 협의 필요 | DQA를 전제한 외부 인터페이스 요구 금지. 내부 Mock 완료 후 채택 여부를 별도 결정 |

※ 위 내용은 회의에 근거한 **설계 입력과 후속검토 사항**으로서, 체계과 공식 서면 승인·명세를 대체하지 않는다. 특히 Standby 직접 조회 허가는 확정되지 않았다.

## 4. 개발 순서와 단계별 수용 기준 (작은 Draft PR)

### M0 — 안전한 현황 고정 및 Mock E2E 재현
- 기존 Oracle Mock fixture/컨테이너 식별, 기존 프로필·승인 Template·Catalog readiness를 **읽기 전용** 점검.
- `main` API/권한/검사 흐름의 중복 구현 여부를 확인한다. 재현 스크립트는 새 일회용 스택/DB를 대상으로만 구성.
- **Acceptance:** Oracle Mock과 빈 개발 DQA가 실제 환자정보 없이 준비되고, 실 DEMIS·운영 DQA/다른 프로젝트의 프로세스/볼륨 변경 0.

### M1 — Target 등록 및 연결 상태 UI
- `ConnectionProfilePortal` 재사용, 관리자에게 Mock DBMS/Source/environment, enabled 상태/연결 진단을 구분해 표시.
- `test-connection`/enable 액션은 **development + allowlisted Mock**에서만 노출, 서버에서 다시 강제. 운영 연결 대상 임의 테스트/활성화 불가.
- **Acceptance:** 신규 등록→명시적 테스트→활성화→실패 진단, 잘못된 secret/config/비관리자 거부; 인증정보·호스트 비밀 로그 유출 0.

### M2 — Schema Inspector Target → Snapshot → Catalog
- Connection Profile을 임의 URL/계정으로 Inspector에 직접 주입하지 않는다. 관리자 허용 Mock `source/schema`와 읽기 계정/metadata-only 계정의 일치 여부를 검증한다.
- 스키마 분석·Snapshot Capture·Diff·v2 WARNING Candidate를 UI에 연결.
- **개발용 승인된** Catalog fixture와 분석 대상의 Schema/fingerprint·source 일치를 검사해 승인 흐름의 테스트를 구성한다. `WARNING`을 자동 `READY`로 승격하거나 프로덕션 검증 정책을 우회하지 않는다.
- **Acceptance:** 자동 탐색 결과/Comment/FK 표시·Candidate 검토·revision 격리·재실행 멱등; 승인된 Mock READY Revision 활성화→검색 확인. 실기관 G1은 여전히 BLOCKED.

### M3 — 자연어 Query Template 신규 작성·관리 (핵심 신규 기능)
- 기존 `/query-recommendations`(추천)과 별도로 “템플릿 초안 생성”을 설계. 승인된 Catalog metadata와 사용자 요구만 프롬프트 입력으로 사용.
- 생성 결과는 **DRAFT** 제안(SELECT SQL, 이름/설명, target schema, typed parameters, 최대 row_limit/timeout, 참조한 catalog revision/source); **자동 실행·자동 승인·자동 enable 금지**.
- 기존 안전성 Validator + Catalog 대상 table/column allowlist + 파라미터 binding + 권한·버전·Catalog fingerprint 검사를 함께 적용. 사용자가 검토·편집 후 기존 리뷰/승인/활성화 API 재사용.
- LLM이 불가능한 컬럼·JOIN·권한을 추론하면 차단/수정 요구. 환자정보·실제 쿼리 결과·secret은 LLM 입력 금지.
- **Acceptance:** 정상 SELECT DRAFT → 수정/반려/승인/enable; INSERT/UPDATE/DELETE/MERGE, 여러 문장, 임의 table, SQL injection, 누락 컬럼, 과도한 행수/시간, stale Catalog에 대해 실행 차단.

### M4 — 자연어 조회→새 Template 실행 결과 통합 수용
- 생성·승인된 템플릿이 Query Assistant 검색 후보로 등장하고, 파라미터 입력/미리보기/Oracle Mock SELECT 실행→표형 결과를 표시한다.
- `template version`, `source/revision`, `row_limit`, `actor`, `trace_id`, 실행 성공/거부·오류코드를 최소 감사정보로 기록.
- **Acceptance:** 적어도 3종 **실제 Mock schema에 존재하는** 안전한 업무 질의를 검증; 예상 결과와 대조. 사용자 권한 없음, 프로필 OFF, catalog mismatch, DB 중단, timeout, 잘못된 파라미터, 중복 클릭 시 안전한 실패와 복구 확인.
- Frontend/API 통합 테스트 + 일회용 Oracle Mock/pgvector DB E2E 결과·스크린샷/로그 제출. 실제 DEMIS 접근 및 운영 Cutover는 별도 Gate.

## 5. 확정 범위 및 제외 범위

**포함:** 자체 개발 DQA의 UI/Backend/관리자 기능, Mock Oracle 전체 Schema 메타데이터와 합성 진료/코드 샘플 데이터, Catalog 검토/검색, 자연어 템플릿 **초안 작성**, 승인/버전, 안전한 SELECT 조회 결과 및 감사.

**제외:** 실제 DEMIS/Standby/복제 DB 접속, 운영 Secret·계정·스키마 변경, 실 환자정보, 실기관 DBA Preflight/READY 인정, 임의 SQL 자동실행, DEMIS Write-back, 군 인증 운영 배포, FHIR/SNUH.AI 계약상 연계 구현, 운영 Docker/볼륨 변경.

**PR 원칙:** 각 M1~M4를 작은 별도 Draft PR로 만들고 단위·통합 테스트 후 승인 요청. 운영 배포·DB Migration·PR Merge는 각각 별도 명시적 승인 후에만 진행. 기존 미병합 #66/#77/#124를 이번 계획에 자동 포함/변경하지 않는다.

## 6. 첫 개발 지시 범위

**가장 먼저 M0**: 저장소의 Oracle Mock 개발 fixture, `scripts/dqa-oracle-mock-bootstrap.sh`, `ConnectionProfilePortal`, Inspector Target config, Catalog fixture, Query Template API 및 Query Assistant 사이의 호출 경로를 점검하고 “일회용 개발 스택 E2E 준비/차단 목록”을 간단히 작성한다. 반드시 운영 DQA의 `dqa-onprem-*` 컨테이너·볼륨 및 실제 DEMIS 설정은 보존한다. 코드 수정은 근거가 확인된 **M1 전용** PR부터 시작한다.

## 7. 현장 전환의 별도 조건

DEC-10(조회 원천/복제 DB), DEC-01(메타데이터 접근 범위), DEC-04(G1 실제 동등성), DEC-03/05(연계 인증·권한), DEC-09(공식 기록 반영)는 각각 독립적인 외부 Gate이다. Oracle Mock E2E PASS는 이 Gate 또는 의료 QA·군 보안 승인을 통과한 증빙이 아니다.
