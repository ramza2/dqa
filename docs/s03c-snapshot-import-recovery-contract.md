# S-03-C — Snapshot/Import Revision 변경·재시도·복구 경계 (합성)

> **2026-10-15 / 테스트 전용.** 기존 운영 서비스와 HTTP 계약의
> Source/Revision 격리 검증. Oracle·실 DEMIS·실 DQA PostgreSQL이나 임상
> 데이터를 사용하지 않는다. DBA·군 G0/G1/G5 승인 근거가 아니다.

## 범위

기존 기능만 결합한다.

- 저장된 최신 Source Snapshot → Integrity Review → Catalog v2
  `WARNING` ZIP (S-03-A).
- ZIP Validate/Import, 해시 기반 Import 중복 방지 및
  `READY + VALID`만 허용하는 활성화 (S-03-B).
- Source별 Active Catalog Revision Pointer, append-only Activation Event,
  Catalog Query의 **기존 활성 Revision** 조회.

## 이번 회귀 시험

| 상황 | 예상 결과 |
|---|---|
| Snapshot 1의 WARNING ZIP을 Import한 뒤 변경 Snapshot 2 Capture | Snapshot 1 재생성은 `SNAPSHOT_CANDIDATE_SUPERSEDED`; Snapshot 2에서 새로운 Fingerprint/ZIP 생성 |
| 두 개의 WARNING ZIP을 Import·중복 재시도 | 각 Import Revision을 보존, 동일 ZIP 재시도는 새 행 없음 |
| 위 WARN 후보를 활성화 시도 | 각각 HTTP 409, 기존 READY Pointer·조회 Table·Activation Event 불변 |
| Import Repository가 **저장 전에** 예외 발생 | 실패 처리 후 메모리 Store와 Active 상태 불변; 정상 재시도 1회 생성 + 동일 ZIP 재시도 중복 방지 |
| 동일 Snapshot Capture Request ID로 동일 Payload 재전송 | Snapshot 이력 증가 없음; 달라진 Payload로 같은 ID 재사용하면 `CAPTURE_REQUEST_REUSED` |
| 다른 Source가 활성화된 상태에서 WARNING Import | 다른 Source Active Pointer/조회 결과/이력 불변; WARNING Source는 자동 활성화 없음 |
| READY A→READY B가 활성화된 상태에서 WARNING Import | 명시적 요청으로만 이전 READY A를 다시 활성화 가능, WARNING은 계속 비활성 |

**주의:** Import 실패 주입은 Repository `add` **진입 전에** 발생시킨
메모리 예외다. 이를 PostgreSQL 트랜잭션 Rollback 검증으로 표현하거나,
Activation Event 추가 도중 오류가 날 때의 DB 원자성까지 확인했다고
해석해서는 안 된다. 본 단계의 이전 READY 재활성화도 **명시적 운영자
호출의 동작 계약**이지, 자동 복구·운영 실행 권한이 아니다.

Snapshot 단위의 DB append-only 제약·Hash Collision·Transaction Lock,
Catalog 실제 PostgreSQL Atomic Commit 및 서비스 장애 후 Restart/Recovery
검증은 별도 **물리적으로 격리된 비파괴 테스트 DB**에서 승인을 받은
후에만 수행한다. 운영 `db_session` 픽스처는 Catalog 테이블을
`TRUNCATE`하므로, 이번 검증에 절대 포함하지 않는다.

## 보안 및 승인 경계

- Metadata Inspector는 Production 연결 차단·기본 비활성.
- `WARNING` 후보는 **DBA 독립 Preflight NOT_VERIFIED**, READY 발급
  또는 Catalog 활성화 대상이 아니다.
- Source/Schema Grant 범위·임상 데이터 Read·DBA 승인 및
  Legacy PoC 종료(G1/G5)는 별도의 외부 결정을 기다린다.
- 이번 PR은 **테스트 및 문서만 변경**하고 새 REST endpoint, Migration,
  DB Import/Activation 자동화, Secret 저장/노출을 추가하지 않는다.

## PuTTY 서버 Acceptance (비파괴 / 아직 미실행)

```bash
cd ~/dqa && git fetch origin && \
git worktree add --detach /tmp/dqa-s03c-review \
  origin/test/s03c-snapshot-import-recovery-contract && \
(
  cd /tmp/dqa-s03c-review/backend && \
  ~/dqa/.venv/bin/python -m pytest -q -rs \
    tests/test_s03c_snapshot_import_recovery.py \
    tests/test_s03b_warning_import_active_isolation.py \
    tests/test_s03_snapshot_warning_candidate.py \
    tests/test_schema_snapshot_history.py
) && \
git -C /tmp/dqa-s03c-review diff --check 9516d5d HEAD && \
echo "DQA_S03C_RECOVERY_CONTRACT_PASS"
```

합성 수용 통과는 **서버 재검증 후에만 표시**한다. 실제 DB 복구나
오라클 접근/임상 QA·실기관 준비 완료와는 별개다.
