# S-06-A — 합성 Gold Set 기반 Schema·관계·검색 정합성 1차

> **2026-10-15 / 개발망 및 격리 PostgreSQL 기준.** 실제 DEMIS와
> Oracle, 실환자/임상 데이터, Legacy 운영 DB, DQA 운영 PostgreSQL,
> 외부 LLM/Embedding Gateway를 사용하지 않는다.

## 1. 목표와 적용 기준

S-03-A~F는 내부 Snapshot→WARNING v2 후보, Import·Activation의
원자성 및 격리 PostgreSQL 재시작/Crash Recovery를 검증했다.
S-06-A에서는 **금표준 기대 결과를 코드에 명시**하여
Schema Diff·Catalog 검색의 회귀 경계를 검증한다.
[미완료 항목 정리](s03-post-recovery-gap-priority.md) 및
[U-02 기능 Gap](u02-schema-analyzer-dqa-gap-analysis.md) 기준
U02-01·06·09·12의 **합성 부분**에 한한다.

| 영역 | Fixture·Gold 판정 |
|---|---|
| Schema | 2-table Snapshot에 Table/Column Comment, 복합 PK·UK·FK, Index 순서 변경을 동시 적용; 기대 object key/changed_fields **7개**와 fingerprint 정합성 검사 |
| Schema 안정성 | 입력 DTO 나열 순서 변동은 동일 Fingerprint·Diff 0; default SQL/index SQL 민감한 원문 제외 |
| Package | 변경 Snapshot으로 만든 v2 `WARNING` ZIP이 Validator를 통과하고 DQA Diff Target Fingerprint 일치·Activation 불가 |
| Keyword | `TB_LAB_RESULT` (TABLE) 및 `GLUCOSE` (COLUMN) 합성 Gold Query의 키 포함 **Recall@5=1.0** |
| Relation | 복합 2-column FK 경로의 컬럼 순서, Source/Schema 구별 및 연관 테이블 탐색 |
| Semantic/Hybrid | **해시 기반 결정적 Stub 임베딩**(`1024d`)으로 모델 키/Revision·출처/활성 범위 검증. 실제 모델의 Top-k/정확도 평가 아님 |
| Revision 전환 | Source A READY A1→A2 교체 후 오래된 A1 검색 문서가 활성 조회로 유출되지 않음, A2 Embedding 미준비 시 검색 거부; Source B 불변 |

이 테스트의 `READY` 행은 **테스트 ORM Fixture**이며 내부
독립 Preflight·DBA 승인·실운영 패키지 발급이 아니다.

## 2. 전용 PostgreSQL 환경 (실 DB 접근 불가)

- `pgvector/pgvector:pg16`
- Compose Project: `dqa-s06a-disposable`
- DB/User: `dqa_s06a_disposable` / `dqa_s06a_user`
- Loopback Host Port: `127.0.0.1:55442`
- **tmpfs 전용**: 영구 볼륨 없음. 종료 시 전용 컨테이너·Network 제거.
- 기존 동명 Compose Project 컨테이너 존재 시 거부;
  `DOCKER_HOST`·비로컬 Docker Context 거부.
- 검사 스크립트에서 DQA DB 접속값을 테스트 전용으로 고정하고
  새 DB의 이름·User·빈 `public` 스키마 **확인 후에만** Alembic.
- 통합 테스트 파일은
  `DQA_S06A_ISOLATED_PG=1`과 Host/Port/DB/User를 추가 확인.
- 테스트는 `db_session`/`db_client` Fixture를 사용하지 않음
  (`db_session`은 실제 DQA DB에서 `TRUNCATE` 가능).
- 의료정보·Oracle/DEMIS 연결·실제 LLM Gateway 호출 없음.

## 3. 수용 및 해석

서버 수용 전 **미검증 Draft**. PuTTY 명령:

```bash
cd ~/dqa && git fetch origin && \
git worktree add --detach /tmp/dqa-s06a-review \
  origin/test/s06a-synthetic-gold-schema-search && \
(
  cd /tmp/dqa-s06a-review && \
  bash scripts/dqa-s06a-disposable-gold-check.sh
) && \
git -C /tmp/dqa-s06a-review diff --check c870aa7 HEAD && \
echo "DQA_S06A_GOLD_REVIEW_PASS"
```

- 테스트 출력 `S06A_SYNTHETIC_GOLD_METRICS`:
  Keyword Recall@5와 Stub Semantic/Hybrid 반환 건수. **개발 Fixture만의 수치**.
- 전용 DB 마이그레이션, Gold Schema/검색 pytest 모두 성공하고
  Cleanup한 뒤 `DQA_S06A_SYNTHETIC_GOLD_PASS`.
- 최종 Diff 확인 후 `DQA_S06A_GOLD_REVIEW_PASS`.
- 실패 시 테스트 수행 여부와 실패 출력 확인 후 **같은 PR에서**
  수정한다. 기존 DQA DB·DEMIS에서 테스트 재실행 금지.

## 4. 증명하지 않는 것 / 다음 작업

- Legacy PoC와 DQA의 **실제 모델 기반 검색 순위 동등성**,
  의료어휘 맥락 정확도, 운영 Golden Query 임상 정답률.
- 실제 Oracle Dictionary 전체 누락/제약 가시성, 승인 Schema Scope,
  실 DEMIS G1 parity, 운영 인덱스 성능·RPO/RTO.
- 의료 의미 Category 정책, S-05 운영 UI 범위, 독립 DBA Preflight/
  Positive `VERIFIED`와 `READY` 승격, 실제 임상 Insert.
- Phase 2 권장: Legacy 고정 Snapshot·Gold Query(관계·약어·전문용어)
  측정 정책을 DBA/의료 QA와 확정하고, 동일 Dataset/Model/Source/
  Revision 조건의 병렬 parity 평가. 미승인 중 운영 PoC 중단 금지.
