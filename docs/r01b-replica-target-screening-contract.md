# R-01-B — 복제 EMR DB Source/Target 식별 정책 초안 (오프라인)

> 기준: `main@acea54a`, 2026-10-16.
> `DEC-10`(복제 EMR DB 승인 대상·DBMS·Oracle License·원본/복제 연결경계)
> 미확정 상태이므로 **연결 정책의 실제 적용을 허용하지 않는다.**

## 1. 문제 정의와 현재 경계

- R-01-A는 **한 Profile로 연결 실패 시 다른 Host/원본 DB로
  자동 우회하지 않는 행위**를 검증했다.
- 하지만 관리자가 `Connection Profile.host`에 **운영 원본 EMR**
  위치를 직접 입력하면, 현행 코드에는 기관 검증된 원본/복제 DB
  판별 체계가 없다. Host 이름에 `replica`가 포함됐다고 복제본이
  되는 것도 아니다.
- 이 차이는 **실제 허가된 복제 DB 식별/접근 허용 정책**이 필요함을
  보여준다. 이번 단계에서는 **적용 정책이 아니라 대조 모델만** 만든다.

## 2. R-01-B 범위

| 단계 | R-01-B 구현 | 권한/통신 |
|---|---|---|
| 프로필 입력 | 기존 `ConnectionProfileSnapshot` 읽기 전용 데이터 | 실제 Admin CRUD/Connection/Profile DB 호출 **없음** |
| 기준정보 | `SiteTargetExpectation` (검토용 인메모리 가상 Reference) | 기관 서면 승인·전자서명·인증된 issuer **없음** |
| 대상 정합성 | Profile ID/Source/Environment/DBMS/Host/Port/DB Service/Username **엄격한 동등 비교** | DNS, IP 조회, Alias/와일드카드 자동 보정 **없음** |
| 대상 구분 | 기준정보 Purpose가 `REPLICA_EMR_READ`일 때만 구조 비교. `OPERATING_EMR`·`UNKNOWN`은 즉시 거부 | 자기 신고한 Purpose **신뢰 불가**, 결과는 실행 권한 아님 |
| 결과 | `STRUCTURAL_MATCH_UNVERIFIED` 또는 Sanitized Blocked code | **모든 분기에서 `connection_authorized=False`** |
| 테스트 | 합성 Target/Host, 인메모리 정책 평가, R-01-A 회귀 | DB fixture, Oracle, DNS, 실제 DEMIS/EMR, Credential·SQL·MCP 없음 |

**핵심:** `SiteTargetExpectation`은 형식상 Site/DBA가 제시할
대상 식별 데이터의 잠정 초안이지만, **독립적으로 검증된 근거가
아니다**. 외부·요청자·관리자가 임의로 동일한 Record를 만들어
전달해도 절대 접속 허용을 의미하지 않는다.

### 2.1 의도적으로 하지 않는 것

- `Connection Profile`의 등록/Enable/Probe 동작 변경
- Query Execution Eligibility/Preview/Execute나 Schema Inspector와
  본 대조 모듈 연결, 운영 연결 차단/허용 Flag 신설
- Credential Secret Resolve, DNS 조회, Firewall 변경, 실복제 DB 연결
- 운영 EMR Host/IP/DBMS/Oracle License 값 저장, 실제 임상데이터 조회
- 서명된 Preflight/기관 승인·READY 발급과 연계, DQA Controlled Write

## 3. 상태 코드와 의사결정

| Status | 의미 | 실제 연결권한 |
|---|---|---|
| `SITE_RECORD_MISSING` | 기준정보 없음 | **없음** |
| `SITE_PURPOSE_NOT_REPLICA_READ` | 원본 운영 EMR 또는 미분류 표식 | **없음** |
| `PROFILE_DISABLED` | 프로필 비활성 | **없음** |
| `PROFILE_TARGET_INCOMPLETE` | 연결 Target 필수 필드 미입력 | **없음** |
| `TARGET_IDENTITY_MISMATCH` | 바인딩된 Profile/Source/Environment/물리 Target/계정이 정확하게 다름 | **없음** |
| `STRUCTURAL_MATCH_UNVERIFIED` | 문자열/정수 기반 8개 필드 **구조 일치에 불과** | **없음** |

모든 검사는 **순수 함수**이며 결과는 민감정보/Host/Username/Secret
값을 재출력하지 않는다. DNS Name이 같더라도 네트워크 ACL, DNS
재지정, 서비스 Alias 및 VIP가 운영 원장에 연결될 위험은 별도
인프라/DBA 실사와 Egress 제한이 필요하다.

## 4. 향후 실운영 게이트 구성 (미구현)

```text
기관 승인 DB/데이터 경계·License·인터페이스 확정 (DEC-10)
              ↓
기관 서명/신원 검증 가능한 승인 Target 증빙 취득
              ↓
Issuer Trust·서명·유효기간/철회·Scope·환경 검증 (별도 Gate)
              ↓
운영 EMR 직접 접근 금지 / Firewall·Network Egress Allowlist
              ↓
Connection Profile ID·Source/Env·타깃·Reader 계정 매칭
              ↓
Query Template·Catalog Revision/Fingerprint/Role/Audit Gate
              ↓
Read-only Adapter / approved replica EMR ONLY
```

위 도식은 **미래 설계 제안**이다. R-01-B 결과는 도식의
“기관 서명/신원 검증” 또는 “Network Egress Allowlist”를
대신하지 않는다. 승인·검증 이전에는 운영 Source를 변경하거나
Connection Profile을 연결·활성화하지 않는다.

## 5. 변경 파일 및 Acceptance

- `backend/app/services/replica_target_screening.py` — 신규 순수
  구조 비교 모듈, API/호출부에 **미연결**.
- `backend/tests/test_r01b_replica_target_screening.py` — Match라도
  연결허가 불가, missing/operating/unknown/disabled/incomplete,
  필드 불일치, Alias, Self-asserted expectation, Credential
  Reference rotation, DNS 미호출/비노출 등 **25 tests 예상**.
- `scripts/dqa-r01b-offline-target-policy-check.sh` — R-01-A
  18 tests + R-01-B 25 tests **합계 43건 예상**만 오프라인 실행.
- `docs/r01b-replica-target-screening-contract.md` — 이 문서.

서버 Detached Worktree Acceptance:

```bash
cd ~/dqa && \
git fetch origin && \
git worktree add --detach /tmp/dqa-r01b-review \
  origin/feat/r01b-offline-replica-target-screening && \
(
  cd /tmp/dqa-r01b-review && \
  bash scripts/dqa-r01b-offline-target-policy-check.sh
) && \
git -C /tmp/dqa-r01b-review diff --check acea54a HEAD && \
echo "DQA_R01B_REVIEW_PASS"
```

기존 `~/dqa/.venv/bin/python` 검증환경 사용(또는 검증된 별도
`DQA_R01B_PYTHON`). PostgreSQL/Oracle/FHIR/운영 Docker, 네트워크
및 환자 데이터에 접근하지 않음.

PASS: 43 tests 통과 및 두 표식
`DQA_R01B_OFFLINE_TARGET_POLICY_PASS`,
`DQA_R01B_REVIEW_PASS`. 실패 시 동일 PR에서만 수정한다.

## 6. 기관 협의 전제

`docs/u01-replicated-emr-db-architecture-review.md`의
**P0-Q01~Q04**(복제 DB 물리/논리 식별, DBMS·복제 방식·권한·
Oracle License) 확인 후 실제 허가 데이터를 근거로 승인 정책과
서명/철회·네트워크 적용 경계를 **별도 변경 PR**로 설계한다.
원장 쓰기는 별도 **DEC-09/G4**이며, 복제 DB Read Gate를
대체하지 않는다.

**본 Draft PR을 Merge해도 실 운영 Target 보호 정책은 자동 활성화되지 않는다.**
