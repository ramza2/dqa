# S-03-F — 전용 PostgreSQL 비정상 종료 및 WAL 복구 경계 검증

> **2026-10-15 / 개발 서버 전용·수용 검증 전 Draft.** 기존 DQA
> 운영·개발 DB, 실제 DEMIS/Oracle, 임상/개인정보에는 절대 접속하지 않는다.

## S-03-E와의 차이

S-03-E는 `docker compose restart`를 통한 정상 종료/재기동 후 커밋
지속성을 시험했다. S-03-F는 **전용 PostgreSQL 프로세스만 Docker
`SIGKILL`로 강제 종료**해 비정상 종료를 만든다. 이후 **동일 Docker
볼륨**을 가진 컨테이너를 다시 시작하고, PostgreSQL이 재시작한 상태에서
커밋/미커밋 경계를 확인한다.

본 시험은 **Crash Recovery의 DB 상태 정합성**을 확인하지만,
고의적인 디스크 손상, 강제 전원 차단, File System 장애,
fsync 오류, WAL 파일 유실, 백업 복원, HA 절체나 대규모 장애 복구는
시험하지 않는다. 운영 SLA/데이터 무손실 보장을 뜻하지 않는다.

## 격리 환경

| 항목 | S-03-F 전용 |
|---|---|
| Compose Project | `dqa-s03f-disposable` |
| DB Image | `pgvector/pgvector:pg16` |
| DB 이름 | `dqa_s03f_disposable` |
| Test User | `dqa_s03f_user` |
| Port | 호스트 `127.0.0.1:55441`만 노출 |
| Docker 볼륨 | `dqa-s03f-disposable_s03f_pgdata` |
| Test Guard | `APP_ENV=test`, `DQA_S03F_ISOLATED_PG=1`, 고정 Host/Port/DB/User |

- `scripts/dqa-s03f-disposable-pg-crash-check.sh`는 같은 Compose
  Project 또는 같은 Docker 볼륨이 이미 존재하면 **실행을 거부**한다.
- `DOCKER_HOST`와 비로컬 Docker Context를 거부한다.
- 테스트 전용 DB 자격증명만 사용하며 기존 DQA 서비스 DB 관련
  환경값을 **강제 덮어쓴다**.
- 새 DB의 식별자와 빈 `public` 스키마 확인 **후에만 Alembic Head 적용**.
- 테스트 모듈 자체도 DB 주소·User·DDL 존재 여부를 재확인한다.
- 운영 API, Backend Service, Migration, Frontend, Query Template,
  DEMIS Connection Profile의 변경 없음.
- `db_session`/`db_client` 픽스처 사용하지 않음
  (기존 `db_session`은 `TRUNCATE` 실행 가능).
- 초기 및 종료에는 **이 프로젝트의 Compose 서비스/볼륨만** 다룬다.
  정리 시 Docker Compose 소유권 Label을 확인한 정확한 Named Volume
  한 개만 제거하며, `down -v`, 전체 컨테이너 종료, 다른 볼륨 삭제 없음.

## 검증 순서 (서로 분리된 Python 프로세스)

1. **커밋된 기준 상태 생성**: Synthetic Schema Snapshot 1건 +
   Catalog v2 `READY` Import/명시적 활성화 +
   Snapshot에서 만들어진 `WARNING` Import. Active Pointer는
   READY A이며 Activation Event는 1건.
2. **미커밋 변경 송신**: 별도 Writer가 같은 Source에
   Snapshot 2 Capture, READY B Import 및 READY A→B
   Pointer 교체/Activation Event 추가를 실행.
   실제 PostgreSQL `FLUSH` 완료 후 **Commit하지 않고 대기**한다.
   Marker가 기록되고 Writer가 살아 있는지 확인한다.
3. **강제 종료**: Docker Compose Project/Service 소유권을
   확인한 뒤 **그 PostgreSQL 서비스만 SIGKILL**.
   이후 Writer 프로세스만 종료한다.
4. **같은 DB 재기동**: 동일 Named Volume으로 서비스를 재시작.
   `pg_control_system().system_identifier` 동일함과
   `pg_postmaster_start_time()` 변경을 검증한다.
5. **복구 결과**: 새 Python 프로세스/DB 세션에서 Snapshot은
   첫 커밋 1건만, Import는 READY A+WARNING 2건만,
   Active Pointer는 READY A, Event는 1건만 존재해야 한다.
   미커밋 Snapshot 2·READY B·Pointer 교체·Event가 남으면 실패.
6. **재사용·방어 검증**: 첫 Snapshot에서 WARNING ZIP 재생성
   시 SHA-256 동일; 재 Import 시 `created=false`;
   WARNING 활성화는 `REVISION_NOT_ACTIVATABLE`.
   이미 활성화된 READY A의 재활성화는 이벤트 증가 없음.
7. **정리**: 전용 Container/Network 종료 및 전용 Volume
   소유권 검증 후 삭제. 정상 정리 완료한 경우에만 PASS 출력.

**중요:** `READY A/B`는 독립 QA 환경에서만 만들어지는 테스트용
Fixture다. 운영에서 `WARNING`을 승격하거나 DBA 독립 Preflight를
우회하는 새로운 경로·권한을 추가하지 않는다. G0/G1/G5 검증과
실증기관 승인 절차는 여전히 별도다.

## 개발 서버 PuTTY Acceptance (아직 실행하지 않음)

```bash
cd ~/dqa && git fetch origin && \
git worktree add --detach /tmp/dqa-s03f-review \
  origin/test/s03f-disposable-pg-wal-crash-recovery && \
(
  cd /tmp/dqa-s03f-review && \
  bash scripts/dqa-s03f-disposable-pg-crash-check.sh
) && \
git -C /tmp/dqa-s03f-review diff --check 0ca3e04 HEAD && \
echo "DQA_S03F_PG_REVIEW_PASS"
```

**필수 수용 표식**
- `S03F_BASELINE_COMMITTED_PASS`
- `S03F_UNCOMMITTED_FLUSHED`
- `S03F_CRASH_RESTART_CONFIRMED`
- `S03F_RECOVERY_ASSERTIONS_PASS`
- `DQA_S03F_DISPOSABLE_WAL_RECOVERY_PASS` (리소스 정리 성공 후)
- `DQA_S03F_PG_REVIEW_PASS`

본 단계의 `SIGKILL`은 **테스트 Compose의 PostgreSQL 서비스 하나**에만
적용한다. 운영 환경·다른 Docker Compose Project에서 이 스크립트를
실행하지 않는다. 중간 실패 시 전용 리소스의 잔여 여부를 점검하되
공용 Docker 볼륨/컨테이너를 수동 일괄 정리하지 않는다.

서버 PASS 이전에는 수용 완료 주장 금지, 사용자 **명시적 Merge
승인 이전 PR 병합 금지**.
