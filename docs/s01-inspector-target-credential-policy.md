# S-01 — Schema Inspector Target·Metadata Credential 정책 보강 (개발 검증)

> **2026-10-15 / Synthetic·test-only**. 미리 설정된 Oracle Inspector Target의
> 형식 및 Credential namespace 충돌 검사 단계다. **기관 승인·대상 Host 진위·
> 실제 Oracle grant/Role·방화벽/TLS 수용을 대신하지 않는다.**
> [U-02 외부 의사결정 DEC-01/02](u02-external-decision-register.md)와
> [실 DEMIS Read-only 운영 Runbook](real-demis-onboarding.md)을 참고한다.

## 1. 현재 코드의 보안 경계 (유지)

- `backend/app/services/schema_inspection.py`는 운영자 설정값
  `DQA_SCHEMA_INSPECTOR_*`의 Source/Schema/Host/Port/Service/Username/
  `env:` Credential 참조만 사용한다. 요청 Body가 Target/SQL을 바꾸지 못한다.
- `DQA_SCHEMA_INSPECTOR_ENABLED=false` 기본값, `APP_ENV=development/test`
  에서만 검사 경로 가능. `production/staging`은 연결 전 `INSPECTOR_ENV_NOT_ALLOWED`.
- HTTP `/api/v1/schema-inspector/inspect`는 관리자
  `CATALOG_MANAGE` 권한이 필요하며 응답은 수집 건수 중심이다.
- Inspector는 Oracle `ALL_*` 사전 메타데이터만 READ ONLY 트랜잭션에서
  읽는다. 임상·업무 행 조회, 사용자 SQL, DML/DDL, 자동 Catalog 활성화는 불가.
- Inspector 전용 `DEMIS_INSPECT_SECRET_*`와 Query Connection Profile 기본
  `DEMIS_SECRET_*`을 분리한다. 기존 Read Query Adapter의 SELECT-only,
  Query Template 승인/안전성 검사 및 DQA Catalog의 명시적 READY-only
  활성화 정책은 변경하지 않는다.

## 2. 본 PR 변경 계약

| 항목 | 이전 | 추가 Fail-closed 검사 |
|---|---|---|
| Host | 단순 URI 예약문자 검사 | 순수 IP(v4/v6) 또는 DNS label/길이의 문법검증. URL/DSN/공백/제어문자/label 오류 차단 |
| Oracle Service | URI 일부 문자 제한 | 255자 이하 영숫자 시작, 이후 영숫자·`_`·`-`·`.`만 허용. 인라인 URI·SQL/공백 차단 |
| Username | 공백/빈 문자열 검사 | Oracle 식별자 문법 검사 및 `SYS`·`SYSTEM` 등 시스템 계정 차단 |
| Inspector Secret Ref | Inspector 접두사 문자열 포함 확인 | `^env:DEMIS_INSPECT_SECRET_[A-Z0-9_]+$` 정확한 일치. URL/다른 Scheme/공백/개행 차단 |
| Query Secret Prefix | 별개 설정값, Inspector와 중복 가능 | 설정된 `DQA_DEMIS_CREDENTIAL_ENV_PREFIX`가 Inspector namespace를 포함하거나 포함되는 경우 연결 전 차단 |
| 실패 처리 | 숨겨진 Oracle 오류와 공통 응답 | 안전한 동일 `INSPECTOR_NOT_CONFIGURED` 코드 유지, Secret Resolver/Engine 생성 **전** 거부 |

**중요:** DNS 문법 검사·계정명 검사만으로 기관이 승인한 실제 대상인지
확인할 수 없다. DNS spoofing, Host/Schema allowlist 운영 승인, 실제
Oracle 사용자 grant/시스템 Role·Proxy 권한 및 동일 실체 계정의 별칭 여부는
DBA/보안 승인 증빙이 필요하다. 이름/Prefix가 다르더라도 계정 권한이
분리됐다고 단정할 수 없다.

## 3. 운영 필수 외부 승인 (현재 `PENDING`)

| Gate | 요청 주체(제안) | 필요한 증빙 | 통과 전 금지 |
|---|---|---|---|
| **G0/DEC-01** | PL·SA·군/DEMIS DBA·보안 | 실 운영 Host/Port/Service·Schema·Source allowlist와 인가된 메타데이터 전용 사용자/권한 증빙 | 실 DEMIS Inspector 접근 |
| **G0/DEC-02** | 군/DEMIS DBA·보안 | 승인된 증빙 발급자/검증·서명/철회 정책, Preflight 신뢰 경계 | Inspector `VERIFIED`, 독립 READY 발급 |
| **G1** | QA·DBA·군 | 동일 실 스키마 Snapshot·주석·FK/Index parity, 검색/문서 품질/가시성 검증 | PoC Analyzer 운영 종료 |
| **G2** | 군/병원/운영 보안 | 실제 Read Query 계정의 **별도** 최소 SELECT grant/운영 IdP·TLS·감사 | 실환자 조회/외부 MCP |
| **G5** | PMO·인프라·군 | 이력·백업·복구·운영 인수/롤백 서면 승인 | Legacy DB/서비스/Volume 삭제 및 DQA Cutover |

이 문서는 실제 Credential 값, DSN, 서버 내부 IP, 사용자명·계정증빙 원문을
GitHub/로그/대화에 기재하는 양식이 아니다. 운영 승인 시에는 제한된
기관 문서관리 시스템의 비밀 없는 증빙 참조 ID만 기록한다.

## 4. Acceptance (서버에서 실행 전 완료 주장 금지)

```bash
cd ~/dqa && git fetch origin && \
git worktree add --detach /tmp/dqa-s01-review \
  origin/test/s01-inspector-target-credential-policy && \
(
  cd /tmp/dqa-s01-review/backend && \
  ~/dqa/.venv/bin/python -m pytest -q -rs \
    tests/test_s01_inspector_target_policy.py \
    tests/test_schema_inspector_admin.py \
    tests/test_schema_snapshot_capture.py
) && \
git -C /tmp/dqa-s01-review diff --check 691d065 HEAD && \
echo "DQA_S01_TARGET_POLICY_PASS"
```

수용 조건: 유효한 합성 Target은 내부 Target 객체까지만 구성,
유효하지 않은 설정은 Secret 조회 및 Oracle Engine 생성 이전 거부,
기본 비활성·운영 차단·Admin 권한 회귀 유지. 실제 Oracle 연결/DB migration/
임상 데이터 테스트·Credential 출력 없음.

## 5. 다음 단계

실기관 Target allowlist, Metadata 계정·Grant 정책, 독립 Preflight 발급자
증빙이 승인된 후에만 **S-01 운영 수용**을 완료로 표시한다.
S-02/S-03 이후 작업도 Inspector 생산환경 활성화·Catalog 자동 READY
승격과 별개의 PR 및 기관 Gate를 요구한다.
