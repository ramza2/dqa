# S-03-E — 분리 PostgreSQL 재시작 후 Snapshot·Catalog Revision 정합성

> **2026-10-15 / 개발 서버 전용 검증, 운영 환경 실행 금지.**
> 실제 DEMIS/Oracle, 임상 데이터, 기존 DQA PostgreSQL에 접근하지 않는다.

## 왜 S-03-D tmpfs를 재사용하지 않는가?

S-03-D는 *단일 컨테이너 실행 중 트랜잭션 롤백·원자성*을 확인하며,
저장은 `tmpfs`에 위치한다. `tmpfs`는 컨테이너가 중지되면 데이터가
사라질 수 있으므로 **PostgreSQL 컨테이너 재시작 후 지속성 시험에
사용할 수 없다.** S-03-E는 일회성 전용 Docker **Named Volume**을
사용해 정상 컨테이너 재시작 중에만 데이터를 보존한다.

| 설정 | S-03-E 전용 값 |
|---|---|
| Compose Project | `dqa-s03e-disposable` |
| Service | `disposable-pg` |
| Image | `pgvector/pgvector:pg16` |
| Host Bind | `127.0.0.1:55440` (외부 공개 없음) |
| Test DB/User | `dqa_s03e_disposable` / `dqa_s03e_user` |
| Docker Volume | `dqa-s03e-disposable_s03e_pgdata` |
| Guard | `DQA_S03E_ISOLATED_PG=1`, `APP_ENV=test`, DB Host/Port/Name/User 정확 일치 |

**격리/정리:** 기존 동일 Compose Project **또는 Volume이 발견되면
실행 거부**. 다른 Docker Context/`DOCKER_HOST` 접속 금지.
Fresh DB의 빈 `public` 스키마와 DB명·계정 검증 **후에만** Alembic
Head를 적용한다. 기존 DQA Compose/YAML, API, Storage, Migration,
`db_session`(TRUNCATE 포함)은 호출하지 않는다.

종료 시 **해당 Project만** `docker compose down --remove-orphans`로
종료하고, 정확한 Volume의 Compose 소유권 레이블을 확인해
**해당 Volume 한 개만** `docker volume rm`으로 삭제한다.
`docker compose down -v`와 다른 Volume 정리 명령은 사용하지 않는다.
실패 시 해당 리소스의 정리 실패를 보고하며, 수동으로 내용을 확인한다.

## 재시작 전·후 2-Phase 검증

`backend/tests/test_s03e_disposable_pg_restart.py`의 테스트 2개를
서로 다른 Python 프로세스로 실행한다.

### 1단계 — 커밋 후 상태 기록

- Synthetic Oracle 메타데이터 `SchemaSnapshotRevision` 1건 Capture·Commit
  (`NO_BASELINE`).
- 같은 Source에 Fixture Catalog Package v2 `READY` Import·명시적 활성화.
- Snapshot에서 생성한 v2 `WARNING` 후보를 Import·Commit.
  `READY` Pointer는 그대로, Activation Event 1건.
- 별도 Source에 `WARNING` Import를 Flush하되 명시적 Rollback으로 취소.
  재시작 후 해당 Import 기록이 없어야 한다.
- Source별 Active Revision, Table Query, Snapshot/Import/Activation 이력 확인.

### 컨테이너 재시작

- `docker compose --project-name dqa-s03e-disposable ... restart disposable-pg`.
- 서비스 Healthcheck 통과.
- 실제 `SELECT pg_postmaster_start_time()` 값의 **변화 확인**.
- Named Volume은 컨테이너 중지 및 재시작 동안 유지.

### 2단계 — 별도 프로세스 재조회

- 커밋된 Snapshot 1건, READY+WARNING Import 2건 지속 확인.
- 활성 READY Revision과 기존 테이블 검색 결과 유지, 감사 이벤트 1건 유지.
- Rollback했던 다른 Source의 Import는 없음.
- 저장된 Snapshot으로 WARNING ZIP 재생성 → 기존 Archive SHA-256 일치.
- 같은 WARNING Import 재요청 → `created=false`/기존 Revision 재사용.
- WARNING 활성화 시도 → `REVISION_NOT_ACTIVATABLE`; Pointer/Event 불변.

**검증 한계:** `compose restart`는 정상 재시작이며 강제 Kill,
PostgreSQL WAL crash recovery, Volume 손상, 장애 전원 차단,
HA/백업·복구·운영 Restart 순서를 시험하지 않는다. 사전 Rollback은
별도 명시적 트랜잭션 Rollback이지 불완전 종료 트랜잭션 검증이 아니다.
군 DBA G0/G1/G5, 독립 Preflight, Catalog READY 발급/실증 승인도
여전히 외부 정책·증적을 요구한다.

## 개발 서버 PuTTY 수용 명령 (아직 미실행)

```bash
cd ~/dqa && git fetch origin && \
git worktree add --detach /tmp/dqa-s03e-review \
  origin/test/s03e-disposable-pg-restart-consistency && \
(
  cd /tmp/dqa-s03e-review && \
  bash scripts/dqa-s03e-disposable-pg-restart-check.sh
) && \
git -C /tmp/dqa-s03e-review diff --check 6839d0a HEAD && \
echo "DQA_S03E_PG_REVIEW_PASS"
```

내부 출력 표식: `S03E_BEFORE_RESTART_PASS`,
`S03E_AFTER_RESTART_PASS`, **`DQA_S03E_DISPOSABLE_RESTART_PASS`**
(전용 컨테이너·Volume 정리 완료 후 출력).
상위 표식: `DQA_S03E_PG_REVIEW_PASS`.

기존 DQA DB에서 직접 Alembic 또는 `pytest -m integration` 실행 금지.
테스트가 중단된 경우 전용 Project·Volume 잔여물 확인 후 정리 절차를
검토해야 하며, 검증 완료로 처리하지 않는다.
