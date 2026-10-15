# S-03-D — 일회성 PostgreSQL 트랜잭션 및 Revision 복구 격리 검증

> **2026-10-15 / 테스트 전용 Draft.** 실제 군 DEMIS·Oracle 연결 금지,
> 임상/개인 데이터 사용 금지. 기존 DQA 서비스 DB의 `db_session` 픽스처나
> Migration 명령을 직접 재사용하지 않는다.

## 전용 실행 환경

- `compose.s03d.disposable-pg.yaml`: `pgvector/pgvector:pg16`
  컨테이너 하나, 호스트 `127.0.0.1:55439`만 바인딩.
- Compose Project: **`dqa-s03d-disposable`**, 기존 DQA/ALZI/ModelOps
  프로젝트 및 볼륨과 이름/경로 분리.
- DB: **`dqa_s03d_disposable`**, USER: `dqa_s03d_user` (하드코딩된
  테스트 전용 계정/암호; 실제 비밀키를 재사용하지 않음).
- `/var/lib/postgresql/data`: **tmpfs** (512MiB), 파일/Named Volume 없음.
  컨테이너가 제거되면 테스트 데이터가 소멸하며 백업/영속성 시험이 아님.
- `scripts/dqa-s03d-disposable-pg-check.sh`: 기존 동일 Compose Project
  컨테이너가 있다면 즉시 실패, 원격 `DOCKER_HOST`/Docker Context 거부,
  DQA 연결 환경변수 강제 덮어쓰기, 임시 PostgreSQL 생성 후
  DB명·User·무테이블 확인 **이후에만** Alembic Head 적용.
  종료 또는 실패 시 전용 Project만 `compose down --remove-orphans`.
  **절대 `down -v`나 운영 DQA `docker compose`를 호출하지 않음.**
- 테스트 모듈은 `DQA_S03D_ISOLATED_PG=1`, `APP_ENV=test`,
  `127.0.0.1:55439`, 정확한 DB/User 및 Migration 테이블을 재검증.
  다른 DB에서는 실행하지 않고 중단한다.

**주의:** 포트 `55439`가 이미 사용 중이거나 같은 이름의 Compose
Project가 있으면 임의로 다른 DB에 접속하거나 프로젝트를 정리하지 말고
문제를 확인한 뒤 재시도한다. 실행 전 해당 서버가 실제 개발 GPU 서버인지
확인하고 **운영 호스트에서는 실행하지 않는다**.

## 검증 시나리오 (실 PostgreSQL, 합성 데이터)

| 항목 | 수용 조건 |
|---|---|
| Alembic 기반 독립 DB 구성 | 빈 전용 DB 확인 후 Migration; 운영 DB·볼륨 무접촉 |
| 실제 Snapshot Capture → v2 WARNING 후보 | DB Commit 후 Source/Revision 한정 생성 |
| 기존 READY 활성화 뒤 WARNING Import + 동일 ZIP 재등록 | Import 이력만 생성·중복 방지, Active Pointer/조회/Activation Event 불변 |
| WARNING Import의 활성화 요청 | `REVISION_NOT_ACTIVATABLE` 거부; 기존 READY 보존 |
| WARNING Import 도중 Commit 전 Rollback | 변경 Import 행 미지속; 기존 READY 조회/이력 유지; 이후 정상 재시도 가능 |
| 기존 READY A→READY B 활성화 시 이벤트 저장 오류 주입 | UPDATE Flush 이후 Exception·Rollback; 기존 A Pointer와 Event Count가 DB에서 그대로 유지 |
| 기존 READY 복원 | 명시적 API/service 동작으로만 A 다시 활성화; WARNING Revision 비활성 유지 |

기존 개발 단계 S-03-A/B/C는 FakeSession 및 Synthetic Repository를
중심으로 검증했다. 이번 테스트는 **실 SQLAlchemy+pgvector PostgreSQL**
트랜잭션에서 Insert/Flush/Rollback/Commit 및 활성 Pointer + Activation
Event 원자성을 확인한다. **전용 DB의 트랜잭션 검증**이지 운영 시스템의
HA/Backup/Restore, 전원 장애·네트워크 파티션, 실제 Oracle 메타데이터
검증은 아니다.

테스트 메서드는 `backend/tests/test_s03d_disposable_pg_transactions.py`.
기존 `backend/tests/conftest.py`의 `db_session` (실 DB 테이블 TRUNCATE)
또는 `db_client`를 **사용하지 않는다.** 각 시나리오는 고유 Source를
사용하고 DQA 레포의 마이그레이션과 운영 정책을 수정하지 않는다.

## PuTTY 서버 Acceptance (별도 임시 PostgreSQL 자동 종료)

**아직 실행·수용되지 않았다.** 서버에서 다음 명령만 실행한다:

```bash
cd ~/dqa && git fetch origin && \
git worktree add --detach /tmp/dqa-s03d-review \
  origin/test/s03d-disposable-pg-transaction-boundary && \
(
  cd /tmp/dqa-s03d-review && \
  bash scripts/dqa-s03d-disposable-pg-check.sh
) && \
git -C /tmp/dqa-s03d-review diff --check 549724a HEAD && \
echo "DQA_S03D_PG_REVIEW_PASS"
```

검증 성공 시 스크립트 내부에서 `DQA_S03D_DISPOSABLE_PG_PASS`, 상위
명령에서 `DQA_S03D_PG_REVIEW_PASS`가 출력된다. 실패하면 테스트 컨테이너만
내리는 정리 루틴이 동작한다. `pytest`만 별도로 실행하거나
`alembic upgrade head`를 기존 `~/dqa` 환경에서 실행하지 않는다.

## 남은 승인 및 리스크

1. 병합 전 서버에서 위 스크립트가 실제로 격리되는지, 새 DB에서
   테스트가 PASS하는지 확인해야 한다.
2. 향후 운영 승인용 DB 동시성·백업/복구·IdP 분리·배포/모니터링 테스트는
   이 임시 DB만으로 증명되지 않는다.
3. 실제 DEMIS ALL_* Metadata 가시성·독립 DBA Preflight 신뢰·
   Catalog READY 발급/수동 Activation 및 G0/G1/G5는 **별도 미승인**.
4. 본 PR은 **Compose/테스트/스크립트/문서만 추가**, 운영 API·서비스·DB
   Migration·실 DEMIS Connection Profile 변경 없음.
