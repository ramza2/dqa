# R-01-D — 복제 EMR DB 운영 접근통제 적용 전 선결조건·회의 수용 기준

> 2026-10-16 초안 · 기준 `main@c95907e` · **DEC-10 미결 / 운영 접근 승인 아님**
>
> 대상: 2026-10-22 의무사·의료정보체계과 협의 준비. 실제 답변·승인·실측 없이
> 모든 정책/접속/전환 Gate는 **NOT_READY**.
> 본 문서는 실제 군/DBA 승인서, 접속자격, Oracle License 확인서가 아니다.

## 1. 현재 구현과 차단 범위

- **R-01-A**: 합성 경로에서 read-only, 단일 Target 실패 시 원본 DB 자동 Fallback
  없음, Source/Environment 격리 및 Fail-closed 행위 회귀.
- **R-01-B**: `SiteTargetExpectation` ↔ `ConnectionProfileSnapshot`
  8개 필드 문자열/숫자 동등 비교. `STRUCTURAL_MATCH_UNVERIFIED`는 **허가 아님**.
- **R-01-C**: 입력 증빙의 형식·타깃·발급 시각·유효 기간·자기 기재 철회 표시 검토.
  `CLAIMS_MATCH_UNTRUSTED`는 **issuer 진위/서명/철회 증명 아님**.
- **R-01-D**: 운영 적용 전 자료/책임/검증 기준과 **비인가 정책 모듈의 런타임
  무연결 상태를 AST 기준으로 회귀 확인**. 별도 허가 게이트나 Connection
  Profile 변경 기능을 **만들지 않는다**.
- **중요 위험**: 현재 실제 DEMIS Query/Connection 실행 경로는 R-01-B/C를
  의도적으로 호출하지 않는다. 따라서 **운영 Host를 복제본으로 판별·차단해
  주는 기능 자체가 아직 없다**. 구조 비교 테스트 성공을 안전한 실접속 보장으로
  주장해서는 안 된다. 승인 전 운영 EMR/복제 DB 양쪽 실제 접속·조회 금지.

## 2. 기관 요청용 선결자료 체크리스트 (전부 미확정)

| Gate ID | 확인자료/수용 기준 | 요청·확인 주체(제안) | 근거 질의 | 미충족 시 |
|---|---|---|---|---|
| R01D-G01 | **운영 EMR과 복제 EMR DB 식별/논리·물리 분리** 도식, 소유주/운영주체, DBMS·Version·Edition 확정 | 군 의료정보체계과·DBA·운영사 | P0-Q01 | Source/Target/Adapter 운영 설정 금지 |
| R01D-G02 | 복제 전송 방식·갱신 주기·허용 지연·대상 Table/View·일관성/누락/삭제 정책 | DBA·DEMIS 운영사 | P0-Q02 | 실증 데이터 최신성 주장·업무 사용 금지 |
| R01D-G03 | 접속 형태(DB 직접/중계 API), 최소 SELECT/Dictionary 계정, 환자/Encounter 허용 Scope·감사·Credential 관리 | 군 보안·DBA·의료정보체계과 | P0-Q03, P0-Q06 | Socket/SELECT/Inspector 접근 금지 |
| R01D-G04 | Source/Environment/Profile/DBMS/Service/Account별 승인 Binding + **승인자·문서/버전 확인** (실주소·계정명은 승인 보안 경로로만) | 의료정보체계과·DBA·PL | P0-Q01, P0-Q03 | 실 Target 등록·변경·Enable 금지 |
| R01D-G05 | 증빙 발행자 권한과 검증키 배포/회전·철회/만료·서명 알고리즘, 증빙 Scope·Replay 정책, 독립 정책/운영 승인 | 군 보안·DBA·운영사 | DEC-10 연계 후속 | 증빙 기반 허가 판정/Read Gate 연동 금지 |
| R01D-G06 | 실제 IP/VIP/DNS/Service Alias/방화벽 Outbound ACL, **운영 원본 EMR 직접 접근 차단** 테스트 승인 및 인프라 담당 확인 | 군 보안·통신·인프라 | P0-Q03 | 네트워크 기반 운영 연결 승인 금지 |
| R01D-G07 | 복제 DB/Oracle 옵션·고가용성·라이선스 범위와 계약/조달 주체 및 추가비용 근거 | 군·계약·DBA·벤더 | P0-Q04 | DBMS/서버·라이선스 사용/비용 확정 금지 |
| R01D-G08 | 복제본 장애·전환·지연·복구 RPO/RTO, 마지막 반영 시각 및 fail-closed 표시/차단 기준 | DBA·운영사·의료 QA | P1-Q09 | 장애/지연 시 의료 조회 실사용 금지 |
| R01D-G09 | FHIR 변환·환자/Encounter Correlation·호출자 권한·Trace·품질 책임과 기관별 인터페이스 문서 | 메디칼스탠다드·인프메딕스·PL·군 | P1-Q07 | 외부 E2E 수용·데이터 전달 승인 금지 |
| R01D-G10 | 군 현장 서버실·UPS·전력·냉각·랙·망 실측 및 장비 반입·보안절차 승인 | 군 시설·인프라·보안 | P1-Q08 | 설치/운영 배치 확정 금지 |

모든 항목은 **회의 시 질문/증빙 요청용 제안**, 사실 확인·승인된 결과가 아님.
회의 후 각 Gate의 `PENDING / EVIDENCE_RECEIVED / VERIFIED / BLOCKED`
상태는 **실제 검증자와 증빙 버전을 별도 관리**할 것. 공개 저장소에는
담당자 개인 연락처, 실 DB 주소·망도, 계정, 환자 데이터, 서명키,
라이선스 번호/계약 원문을 기록하지 않는다.

### 2.1 독립적으로 유지할 결정

- **DEC-02**: 독립 DBA Preflight/READY 발행·신뢰·Replay 계약.
  *Catalog READY/activation* 관련이며 R-01-C의 증빙 검토와 동일하지 않음.
- **DEC-09**: SNUH.AI/군 승인 기반 운영 EMR 의무기록 반영 공식 경로와
  Controlled Write. 복제 DB read 승인이 write 권한을 부여하지 않는다.
- **DEC-10**: 복제 DB를 실조회 원천으로 승인할지와 운영 책임/권한/라이선스.
  **이번 R-01-D로 어느 결정도 승인/해제되지 않는다.**

## 3. 10월 22일 회의 진행/인수 질문

1. **DB 실체** — DQA가 접속할 대상이 현재 실재하는 별도 복제 DB인지,
   신규 구축 예정인지, 아니면 중계 API인지? 누구의 시스템/책임인가?
2. **승인 Reader** — 직접 DB 조회 허가 여부, 보안 Zone, Schema/Field/행 수준
   Scope와 별도 읽기 계정·권한 문서 제공 가능한가?
3. **운영 원본 차단** — DNS/VIP/Service Alias 포함 원본 원장으로 가는
   경로를 네트워크 계층에서도 완전히 차단할 계획/증빙이 있는가?
4. **데이터 최신성** — 복제 변경 지연·누락·장애 시 조회 화면/Workflow를
   어떻게 정지하거나 stale로 표시할 것인가?
5. **비용/일정** — 복제 DB 구축, 서버·DBMS/복제 옵션 라이선스,
   방화벽 변경·계정 발급, 연계개발 비용을 어느 기관이 부담하는가?
6. **추후 근거** — 기관의 승인 문서·검증 담당자·증빙 전달 보안 채널과
   검증키/철회 관리 주체는 무엇인가?

답변이 부족한 경우 대안을 추측하지 말고 각 Gate를 `PENDING`
또는 `BLOCKED`로 유지한다. 사용자/관리자가 입력한 ‘승인 완료’ 표시만으로
`VERIFIED`를 설정하지 않는다.

## 4. 미확정 상태 개발/운영 금지 및 후속 이행

**이번 PR에서는 시행하지 않음:**
- 운영 Read 실행 경로에 R-01-B/C Policy Hook 추가 및 Authz Boolean 변경
- Connection Profile/Adapter/Inspector/Query/REST/MCP Route, DB 스키마,
  Migration, 설정/Container, Secret, 승인 Target, ACTIVE Catalog 수정
- 전담부대/병원 실데이터 또는 실 DEMIS·Oracle 접속/쿼리/Schema 수집
- Mock→실 DEMIS 전환, 새 현장용 Host/IP·Password 또는 서명키 반입
- 임상 Record Insert/Update 및 신규 Write API (DEC-09 별개)

**DEC-10 답변 확보 후 별도 PR과 수용 절차:**
1. 군 보안 경로로 공식 승인 문서/증빙 수령·기관 검증.
2. 검증키와 독립 Revocation + Target 식별/네트워크 ACL 설계 승인.
3. 승인된 Replica만 연결 가능하게 하는 운영 경계 **별도 검토 구현**.
4. 계획된 성능/안전성 시험과 감사로그, 장애 fail-closed, 재승인/회수 시험.
5. 군 인수 전에는 운영 배포·실환자 데이터 접근 금지.

## 5. 오프라인 Architecture Guard

`backend/tests/test_r01d_offline_policy_isolation.py`는 현재
`backend/app/**/*.py`에 대해 AST Import/ImportFrom/정적 Importlib
호출을 확인한다. R-01-B와 R-01-C 두 오프라인 모듈끼리의 의존은 허용하지만,
나머지 운영 모듈이 해당 모듈을 import하면 테스트가 실패한다.

**한계:** 이는 코드 검토용 정적 회귀 테스트이며 문자열 조립 기반
동적 로딩·런타임 설정 및 실제 네트워크 차단을 완전하게 검증하지 못한다.
따라서 **보안 인증 또는 운영 Read 허가 판단의 근거로 사용 금지**.

변경 파일 **3개**: 이 문서, 테스트, 서버용 스크립트. `backend/app/` 제품
코드 변경 없음.

### 서버 수용 검증 (테스트 실시 전)

```bash
cd ~/dqa && \
git fetch origin && \
git worktree add --detach /tmp/dqa-r01d-review \
  origin/test/r01d-site-gate-readiness-isolation && \
(
  cd /tmp/dqa-r01d-review && \
  bash scripts/dqa-r01d-offline-isolation-check.sh
) && \
git -C /tmp/dqa-r01d-review diff --check c95907e HEAD && \
echo "DQA_R01D_REVIEW_PASS"
```

예상: A(18) + B(25) + C(35) + D(10) = **88 tests**, `DQA_R01D_OFFLINE_ISOLATION_PASS`,
`DQA_R01D_REVIEW_PASS`. 실제 서버 결과를 받기 전까지 PASS 주장 금지.
PR은 **Draft**, 명시적 승인 전 자동 Merge 금지.
