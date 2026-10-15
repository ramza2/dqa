# U-02 — 대외 의사결정 및 실기관 Cutover 차단 레지스터

> **2026-10-15 기준 / 상태: 결재·승인 미확인.** 본 표의 책임자는 **요청/협의 역할**이며
> 실제 기관의 결재권자·권한을 지정하거나 서명 승인으로 간주하지 않는다.
> [통합 검증 결과·기능별 현황](u02-integration-acceptance-handoff.md) 참조.

## 1. 의사결정 요청 목록

| ID / Gate | 요청할 결정 | 주관·협의 대상(제안 역할) | 확보할 문서/증빙 | 결정 전 제한 | 상태 |
|---|---|---|---|---|---|
| **DEC-01 / G0·S-01** | 운영 Oracle Inspector의 승인 Source, Host 접근범위, Schema 목록/표준 Naming, Metadata Dictionary 가시성 | PL·SA·DBA / 군·DEMIS 운영·보안 | 승인 대상 Source/Schema allowlist, 직접 검사 계정·grant(조회/쓰기와 분리), 네트워크 허용표 | 실 DEMIS Inspector 연결·새 Target 임의 등록 불허 | **미확정** |
| **DEC-02 / G0·S-04** | 독립 Preflight 증빙 발급자·서명·범위·검증 시점·만료·철회·Replay 및 예외 승인 정책 | SA·DBA·보안·QA / 군·DEMIS 운영 | issuer 신원/키 보관, Snapshot/Fingerprint/Source binding, 증빙 유효기간, 감사·철회/중복 체크 계약 | 임의 `VERIFIED`/Catalog READY 승격·자동 Activation 금지 | **미확정 (#77 Draft)** |
| **DEC-03 / G0·U-04** | DEMIS↔FHIR↔SNUH.AI 역할/소유권·MCP vs REST·공통 JSON·환자/Encounter/trace·오류/인증 ICD | PL·SA / 메디칼스탠다드·인프메딕스·군 | 버전·소유 기관·승인자 명시 ICD, 필드 매핑/인증·오류코드·재시도/감사 계약 | 외부 시스템 임의연계 및 임상 결과 표시 확정 금지 | **미확정** |
| **DEC-04 / G1·S-06** | PoC↔DQA 실제 Metadata 동등성 기준·허용한 누락·복합 FK·주석/Index·검색 품질 임계치 | QA·DBA·PL / 군 DEMIS 검증자 | 승인 Schema Scope, canonical field Diff, 누락 설명, Gold Query Top-k·Coverage 결과 및 판정자 | Legacy Analyzer 종료 불가 | **미검증** |
| **DEC-05 / G2·R-01/X-02** | 실제 DEMIS 조회/운영 인증·최소 SELECT·TLS·감사·로그 마스킹/보존 정책 | DBA·보안·인프라 / 군·병원 | 권한 승인표, 안전성 검증, 운영 IdP/네트워크 경로·감사/복구 계획 및 검수 | 실환자 조회·외부 MCP 노출 금지 | **미승인** |
| **DEC-06 / G5·X-05** | Legacy DB·Schema/Run/Snapshot/Category·검색자료·원본 ZIP/DOCX 보존·백업 범위 | PMO·PL·DBA·인프라·보안 / 군 운영 | 보존기간/반출/암호화 정책, Source→Import Revision 실매핑, Export/검수 건수, 백업 sha/복구 기록 | 실제 DB Copy/Export/운영 Cutover 금지 | **미승인** |
| **DEC-07 / G5·X-05** | 서비스 전환·구서비스 중단·운영 Rollback 책임자/판단시점·RPO/RTO·의사소통 | PM·PMO·PL·QA·인프라 / 군·컨소시엄 | 전환 승인서, 장애 대응/롤백 Runbook, 체크포인트·복구 리허설 판정, 중단 승인 | PoC 컨테이너·DB/볼륨 삭제 및 DQA 단독 운영 전환 금지 | **미승인** |
| **DEC-08 / G0·S-05** | 별도 Legacy ERD/Report/Category 편집/Target/Preflight UI 기능의 필수·선택·제외 범위 | PM·PL·사용기관 / QA·프론트엔드 | 필수 화면별 사용자 시나리오/권한, 의료데이터 표시·다운로드 허용범위, 인수조건 | UI 범위 임의 축소/전면 복제 금지 | **미확정** |
| **DEC-09 / W-01/G4** | 실제 DEMIS 임상의무기록 저장 경로(공식 API 우선) 및 허용 Operation·필드·상태·임상 승인 방식 | PM·PL·SA·DBA·의료 QA / 군·병원·DEMIS·SNUH.AI | 지원 Operation 계약, 저장 대상/상태, 최소권한, 승인 증빙·책임/취소·대사 정책 | **실 DEMIS Insert 및 Controlled Write 활성화 금지** | **미승인, U-02와 독립 Gate** |

| **DEC-10 / G0·R-01(제안)** | **복제 EMR DB를 공식 조회 원천으로 채택할지**, 원본↔복제 위치·DBMS/Version·데이터 범위·동기화/허용 지연·Read/Dictionary 권한·장애/복구 책임, Oracle Database/복제 옵션 라이선스·비용·소유를 누구 명의로 승인할지 | PL·SA·DBA·보안·인프라·계약 / 군·의료정보체계과·DEMIS/EMR 운영사 | 복제 DB 구성도·Replication 계약/SLA·Data Scope·승인 Read Source/Schema·License 확인서·전력/망 실측 확인표 및 역할별 서면 답변 ([협의 질의 Q01–Q09](u01-replicated-emr-db-architecture-review.md)) | **운영 EMR 직접 연결 금지**, 복제 DB 연결/계정 발급·실조회·Inspector Target 확정·기존 Catalog Source 전환 금지. 임상 Write는 별도 **DEC-09** 유지 | **회의 요청 수령, 상세 미확정/미승인** |

**중요:** “미확정”은 협의/기획 단계의 현 상태이며 거절 판정이 아니다.
그 밖의 법률·정보보호·병원 내부 절차는 관계기관의 별도 승인 양식에 따른다.
이 표에 날짜·이름을 임의 기입하거나 시험 통과를 기관 승인으로 대체하지 않는다.

## 2. 후속 구현/검증 백로그와 차단 해제 조건

| 순서 | 개발 업무 | 가능한 선행 작업(허가 없이도 안전한 범위) | 금지된 후속·승인 선결 |
|---|---|---|---|
| **1: U-03** | 아키텍처·README·AGENTS·Runbook 정합화 | 현재 read-only 동작과 미래 목표를 **현행/예정**으로 구분한 문서 정리 | 승인되지 않은 규칙 완화·임상 Write 설정 변경 금지 |
| **2: S-01·S-04** | Inspector Target/독립 Preflight 증빙 프로토콜 | 합성 allowlist/Mock 부정·철회·만료·Stale 테스트, #77 초안 검토 | DEC-01/02 미결 시 실기관 접속, positive VERIFIED, READY promotion 금지 |
| **3: S-03~S-05** | Snapshot→Catalog v2→수동 Review/Import/Activation, React 최소 운영 UI | 순수 함수·합성 Snapshot/Mock, 접근권한·stale response 보호 | DEC-08 화면 계약·독립 READY 정책을 가정한 무단 활성화 불가 |
| **4: S-06** | Oracle parity·Data Discovery/Embedding/ERD Gold regression | 확대 합성 Schema·용어 매핑/출처 품질 측정 | DEC-04 없이 실 DEMIS 동등성 완료 표시 금지 |
| **5: R-01~04/X-01~03** | FHIR/SNUH.AI 및 실 DEMIS read-only 통합 | ICD 제안, Mock E2E와 보안 위협분석 | DEC-01/03/05 없이 실제 연계/실환자 조회 금지 |
| **6: X-05** | Source/Run 실매핑·백업/복구·전환 | 독립 복구 테스트 방식 설계 및 Synthetic staging dry-run | DEC-04~07 및 G5 승인 전 운영 Copy/Cutover/삭제 금지 |

## 3. 증빙 수령 및 서면 승인 기록 양식 (미작성)

> 아래는 **기입 템플릿**이다. 현재 모든 항목 `PENDING`; 사용자/도구의
> 합성 테스트 보고서는 실제 발급 기관의 승인자료가 아니다.

| 항목 | 기입 내용 |
|---|---|
| Decision ID | `DEC-__` |
| 대상 Source/DB/환경·Schema Scope | `PENDING` — 비밀/서버 접속정보 원문은 문서에 기재하지 않음 |
| 발급 기관·담당 역할 및 승인번호 | `PENDING` |
| 승인 문서명·버전·최종 승인일 | `PENDING` |
| 근거 파일 SHA-256·보존 위치 참조 | `PENDING` — 접근 제한된 내부 문서관리 위치 |
| 예외·유효기간·철회 조건 | `PENDING` |
| 확인자/검토자·승인자 | `PENDING` |
| Gate 판정·승인된 작업범위 | `BLOCKED / NOT_APPROVED` |
| 후속 확인·재평가 시점 | `PENDING` |

## 4. 위험관리 및 원복원칙

1. **증빙 독립성:** Legacy `READY`, DQA 구조 Validator `activation_eligible`,
   synthetic restore PASS, 내부 Review 모두 기관/DBA 서명 증빙과 별개다.
2. **권위 분리:** Snapshot 저장 ≠ Catalog 실행 권한. 승인된 v2 Import Revision을
   **명시적 READY+VALID 검사·권한·감사** 후 활성화하며 이전 활성 Revision을 보존한다.
3. **문서·원본 보존:** DQA JSON 기반 Import만으로 Legacy ZIP/DOCX·모든 Run/Snapshot
   이력 원본 바이트를 재생성할 수 있다고 가정하지 않는다.
4. **DB 복구:** U-02-C-3 시험은 일회용 DB 안에서만 원본/복구 row digest를 비교했다.
   현장 RPO/RTO/재난복구 설계·암호화·운영 복구 승인·롤백 수행은 아직 없다.
5. **민감 데이터:** 임상/식별정보, Credential/DSN, 원시 SQL/default/index 정의,
   원시 Embedding·출처 ID를 GitHub PR·로그·대화에 반출하지 않는다.
6. **전환 원칙:** G5 미승인 동안은 Legacy 서비스를 유지하고, DQA 활성 포인터·
   DEMIS 계정·데이터를 수정하는 migration 또는 cutover 명령을 배포하지 않는다.
