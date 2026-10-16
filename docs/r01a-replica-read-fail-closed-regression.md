# R-01-A — 복제 EMR 조회 경로 Fail-closed 계약 (합성·오프라인)

> 기준 `main@e94eb7f`; 2026-10-15.
> [U-01 복제 EMR 구성 검토](u01-replicated-emr-db-architecture-review.md)의
> **DEC-10 미확정 상태를 유지**한다. 본 단계는 개발 안전회귀,
> 기관의 복제 DB 연결 허가·DBA Preflight·실 EMR 접근 검증이 아니다.

## 목적과 결론 경계

- 기존 Oracle Read-only Adapter는 **하나의 Connection Profile**에 지정된
  물리 Host/Service만 사용한다. 합성 연결 실패·READ ONLY 트랜잭션
  거부 시 운영 EMR 등 **다른 DB로 자동 fallback/retry하지 않는지** 고정한다.
- `(source_name, environment)`를 정확히 매칭하는 Profile이 없거나,
  다른 Source/Environment가 반환되면 즉시 `CONNECTION_PROFILE_NOT_FOUND`
  에러를 반환하는 계약을 검증한다.
- 미지원 DBMS는 Profile에 참조된 Secret을 읽기 **전에** 차단한다.
  Oracle 접속 오류에는 호스트·계정·Credential이 노출되지 않도록 한다.
- Query Execute 서비스의 **Execution Audit STARTED→FAILED**,
  하나의 Profile만 Adapter Factory에 전달, 실행 실패 후 재시도 없음,
  Eligibility 부정 시 Credential/Adapter 호출 없음도 격리 검증한다.
- 추가 18 case 모두 **가상 Source/Host, Fake Resolver,
  주입형 연결 실패 및 메모리 Audit**만 사용한다. 실제 SQL 실행/DB 연결
  없음. 기존 Integration 테스트를 재실행하지 않으며 운영 DB는 사용하지 않는다.

## 중요: 아직 보장할 수 없는 내용

1. **운영 원장 Host 접근 정책/allowlist는 아직 구현·승인되지 않았다.**
   현행 관리자가 구성한 `Connection Profile.host`가 복제 DB라는
   독립 증빙이 없으므로, 이 테스트 성공으로 운영 원장 접근을
   원천적으로 불가능하다고 주장하지 않는다. 현재 확인 가능한 것은
   **실패 시 코드가 다른 Host로 자동 우회하지 않는 것**이다.
2. 복제 DB의 DBMS/Service/Schema/Replication 방식, Read 계정,
   Dictionary 접근권한, 장애·갱신 지연·자료 사용 목적 및
   **Oracle License**는 군·의료정보체계과/DBA 협의가 필요하다.
3. 임상문서 저장은 **별도 공식 운영 EMR Interface 승인과 Gate**
   (기존 DEC-09/G4)가 필요하다. 복제 DB 읽기 회귀 통과는
   INSERT/UPDATE/DELETE 또는 Controlled Write 권한을 부여하지 않는다.
4. Schema Inspector는 운영 기본비활성/차단, Snapshot WARNING
   후보는 승인된 READY가 아니다. 기존 `Source/Revision/Fingerprint`
   일치와 RBAC/감사 경계를 수정하지 않는다.

## 변경 범위

- `backend/tests/test_r01a_replica_read_safety.py` (신규): 테스트
  DB fixture 미사용; unregistered DBMS 5종, Oracle Read/Probe
  연결 단일시도 2종, READ ONLY 실패 1종, Profile Source/Env
  부정 3종, Caller Target 주입 거부 4종, 실행 Audit/No Retry 2종,
  Execution Eligibility 부정 1종, **합계 18개 parameterized case**.
- `scripts/dqa-r01a-offline-safety-check.sh` (신규): 정확히 이 테스트
  파일만 실행하는 가드형 Runner. `APP_ENV=test`로 설정하며
  Docker/DB 서비스 및 Oracle 대상 접근을 하지 않는다.
- `docs/r01a-replica-read-fail-closed-regression.md` (신규): 이 문서.

**Backend Runtime, API, DB Migration, Oracle Adapter, Container, Profile,
Query Template, Target, Credential, 운영 설정은 변경하지 않는다.**

## 서버 Acceptance — Detached Worktree

```bash
cd ~/dqa && \
git fetch origin && \
git worktree add --detach /tmp/dqa-r01a-review \
  origin/test/r01a-read-connection-fail-closed && \
(
  cd /tmp/dqa-r01a-review && \
  bash scripts/dqa-r01a-offline-safety-check.sh
) && \
git -C /tmp/dqa-r01a-review diff --check e94eb7f HEAD && \
echo "DQA_R01A_REVIEW_PASS"
```

Runner는 `~/dqa/.venv/bin/python`을 기본 사용한다
(변경이 필요한 경우 `DQA_R01A_PYTHON`에 **검증된 별도 venv 경로**만 지정).
기존 서버의 `docker compose` 서비스, PostgreSQL, Oracle/DEMIS
계정, 원장/복제 EMR 데이터베이스를 변경하거나 probe하지 않는다.

**PASS 조건:** 새 모듈 **18 passed**, `DQA_R01A_OFFLINE_SAFETY_PASS`,
`diff --check` PASS, `DQA_R01A_REVIEW_PASS`. 실패 시 동일
Draft PR만 수정하고 안전 테스트 재수행. Merge와 실서비스 재배포는
사용자의 명시적 승인 전 시행하지 않는다.

## 이후 진행 조건

- **P0:** 2026-10-22 의료정보체계과 협의에서 복제 DB(DBMS·원장 분리·
  조회 권한·시점/갱신·License)의 실제 규격을 수령한 후 G0/DEC-10
  Source/Target 정책 설계를 수립한다.
- **P1:** 승인된 복제 DB Source 식별·별도 Reader Credential·
  Query Template/Catalog 일치/Failover 금지 정책을 코드에 반영한
  신규 소규모 PR과 격리된 Mock E2E를 별도 계획한다.
- **미해제:** 승인된 별도 저장 경로/임상 승인 없이는
  Controlled Write 개발·실 DB 쓰기를 시작하지 않는다.
