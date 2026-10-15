# DQA S-03 개발 수용 현황 및 다음 우선순위 점검

> 기준일 2026-10-15 · 기준 `main@5f400c78dd5056dde8e666b3f474d0cdafa42c21`.
> **개발·합성/격리 환경 검증과 실제 DEMIS 운영 승인은 별개의 판단**이다.
> 본 문서는 현재 저장소 WBS/Gap/외부결정 레지스터에 기반한 작업
> 인계 메모이며, 운영 승인서·실기관 Cutover 자료가 아니다.

## 1. S-03-A~F 근거 및 판정

| 단계 | 병합 PR / Commit | 서버 수용 증빙 | 의미와 한계 |
|---|---|---|---|
| S-03-A | #93 / `5edeac1` | source-scoped Snapshot→v2 `WARNING` 후보·Validator 회귀 | 후보 생성은 승인/활성화가 아님 |
| S-03-B | #94 / `9516d5d` | 합성 Import/Activation/Query HTTP 회귀 전체 PASS | WARNING Import 후 이전 READY Pointer·조회 보존 |
| S-03-C | #95 / `549724a` | 합성 Revision 변경·Retry·Source 격리 **41 passed** | 운영 PostgreSQL rollback 보장은 아님 |
| S-03-D | #96 / `6839d0a` | 전용 PG Import Rollback·활성 Pointer/Event 원자성 **4 passed** | 운영 DB·DEMIS 접근 없는 일회성 DB |
| S-03-E | #97 / `0ca3e04` | 전용 PG 정상 재시작 전후 **2 passed**, 볼륨 정리 | Graceful restart, 운영 RPO/RTO 인증 아님 |
| S-03-F | #98 / `5f400c7` | 전용 PG SIGKILL/WAL 복구 전후 **2 passed**, 미커밋 변경 제거·볼륨 정리 | DB Crash Recovery, 전원장애·디스크손상·HA 증명 아님 |

**S-03 부분 판정:** `INTERNAL_WARNING_PIPELINE_VERIFIED`;
`READY_PROMOTION_NOT_APPROVED`; `REAL_DEMIS_PARITY_NOT_VERIFIED`.
코드상 Catalog Package v2 Import·immutable Revision·수동 READY-only
Activation이 존재하지만, DQA 내부 Snapshot→독립 Preflight→기관 승인
READY 패키지 발급 경로는 **미완료·외부 정책 대기**다. 따라서 WBS의
S-03을 전체 완료로 변경하지 않는다.

## 2. 기존 요구사항 대비 Gap (추가 개발 / 외부 결정 분리)

| 우선 | WBS/요구 | 확인된 기반 | 남은 작업 | 차단 |
|---|---|---|---|---|
| **P0 개발** | **S-06-A / U02-01·06·09·12** | U-02-A~B 합성 Oracle Inspector/Package parity, Snapshot Diff, Catalog/Discovery 검색 | **확장 합성 Gold Set**: 복합 PK/UK/FK·정렬/외부 FK·Comment/Index·Null/빈 값, 관계·검색 결과의 Source/Revision/Fingerprint 일관성, 결과/근거 누락 판정 | 실기관 완전성 판정은 DEC-04/G1 이후만 |
| **P0 협의** | U-04 / W-01 / DEC-03·09 | 통합 DQA↔FHIR↔SNUH.AI 역할 분리 설계 | 호출 주체, REST/MCP, Canonical JSON, Patient/Encounter, Trace/Error/Auth, DEMIS 공식 Insert 가능 여부 | 군/병원·컨소시엄 서면 결정 |
| **P1 협의** | S-01·02 / DEC-01 | Oracle metadata-only Inspector 코드·합성 권한/Dictionary fail-closed | 실제 Source/Schema allowlist, Dictionary grant·누락/제약 가시성 | 군·DEMIS DBA 승인 |
| **P1 협의** | S-04 / DEC-02 | Snapshot Diff·관리자 검토 이력, 비권위 Preflight Mock; Draft #77 | 독립 발급자/증빙 서명, 만료/철회, Snapshot binding, 재사용 차단 및 승인 권한 결정 | **#77 미병합** / G0; 임의 READY 승격 금지 |
| **P1 범위** | S-05 / U02-03·09·10·11·13, DEC-08 | DQA React Catalog Explorer / Schema Search / Index Status | 운영자의 Target·Snapshot/Diff·Preflight 상태/ERD·Report·Category 편집 중 필수 화면을 결정, 최소 UI 별도 PR | DEC-08; 범위 미확정 중 Legacy 화면 전면 복제 금지 |
| **P1 개발** | R-02~04 / S-06 | 승인 Query Template·SELECT-only Oracle Adapter·내부 MCP | 승인 Resource 매핑·Read-only Mock E2E·Gold Query 회귀 | 실 데이터/외부 MCP는 DEC-03·05/G2 승인 필요 |
| **P1 운영** | X-02·X-05 / DEC-04·06·07 | U-02-C 합성 Source/Run 인벤토리, 격리 PG 백업 복원, S-03-D~F DB 일관성 회귀 | 실제 이관 Crosswalk, 원본 ZIP/DOCX 보존, 운영 백업·복원/RPO·RTO, 인수 승인 | G1/G5 전 PoC 중단·데이터 복제/삭제 불가 |
| **승인 후** | W-02~07 | 별도 Controlled Write 아키텍처·안전 경계 문서 | 승인 증빙 검증·Registry·Prepare/Commit·감사·멱등·대사 등 | W-01/DEC-09·G0/G3/G4 전 **쓰기 구현·실행 금지** |

## 3. 권장 다음 작업 — S-06-A 1차 Draft PR

**다음 구현은 운영 코드 수정 없이 합성 회귀 테스트·Gold Fixture·
평가 결과 정의에 한정하는 것이 적절하다.**

1. Legacy 고정 기준과 DQA의 기존 U-02-A/B 비교 하네스 재사용;
   두 Fingerprint의 **원시 SHA 동일성 가정 금지**.
2. Table/Column/PK/UK/FK/Index/Comment 정규화 항목 및
   순서·외부 참조·누락 처리 테스트를 확장한다.
3. 활성 Catalog와 **분리된 최신 Snapshot의 권위 경계**를 유지하고
   Source/Revision/Fingerprint 불일치 결과가 검색/관계 조회에
   반영되지 않는지 검증한다.
4. 검색 Gold Query는 Keyword/Semantic/Hybrid를 **같은 Index,
   Model Key, Revision과 평가 조건**에서 비교하되, Legacy 원본 모델과
   DQA 모델/정규화가 다르면 순위 동일성을 전제하지 않는다.
5. `Coverage/Recall@k`, 누락·오탐과 근거 출처를 기록한다.
   **실 DEMIS parity/G1 승인 판정은 하지 않는다.**
6. DB 통합 시험이 필요하면 별도 일회성 PG 컨테이너와
   비파괴 절차만 사용; 현재 `db_session` 픽스처는 `TRUNCATE`
   위험이 있어 활성 DQA DB에서 호출 금지.

**비범위:** S-05 UI 일괄 구현, Positive 독립 Preflight/READY,
새 production IdentityProvider, 직접 DEMIS 조회·Insert, 외부 MCP
노출, Legacy PoC 운영 종료.

## 4. 외부 결정·운영 인수 현황

[의사결정 레지스터](u02-external-decision-register.md)의
**DEC-01~09는 확인된 승인 자료가 없으므로 PENDING/미승인 상태를
유지**한다. 특히 #66(SNUH.AI 단일 임상 승인 UI 설명),
#77(독립 Preflight 증빙 계약)은 **Draft·미병합** 상태다.
개발용 `READY` Fixture와 기존 Oracle Mock PASS는 독립 DBA 서명·
승인된 의료기록 저장 방식의 증거가 아니다.

**실행 권장 순서:** S-06-A 합성 Gold 회귀 → S-05 필수 범위
DEC-08 협의 → 승인된 최소 UI → DEC-01/02/03/09 확정에 따른
S-02/S-04/R-02/W-01 후속 PR. 동시에 G1/G2/G5 운영 검증 계획은
별도 관리한다.

참조:
- [Unified WBS / Gate](roadmap.md)
- [U-02 Gap 기준선](u02-schema-analyzer-dqa-gap-analysis.md)
- [U-02 검증 인수인계](u02-integration-acceptance-handoff.md)
- [U-02 외부 결정 레지스터](u02-external-decision-register.md)
- [통합 아키텍처](integrated-platform-architecture.md)
