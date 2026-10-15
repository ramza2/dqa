# U-02-C-3 — 격리 Legacy Catalog 백업·복구 리허설과 Cutover Gate

> **상태: Draft / 서버 Acceptance 미실행.** 합성 Legacy Catalog PostgreSQL에 한정한다.
> 실제 DEMIS/의료데이터/운영 Legacy DB/DQA 운영 DB 접근이나 데이터 이관, 활성화, rollback 실행은 금지한다.

## 1. 기준 및 목적

- DQA `main@060d2ff` (U-02-C-2, PR #87).
- Legacy `ramza2/demis-schema-search-poc@c9b88f6f6d14dc2598765efbf6bb41b4771f9b25` (고정 Git blob 확인).
- [U-02-C-1 이관 계획](u02-c-cutover-plan.md): 17개 Legacy Catalog 테이블 전수 구분, 원본 ZIP/DOCX·Run/Snapshot/Category·백업/rollback 보존 규칙.
- [U-02-C-2 읽기 전용 인벤토리](u02-c2-isolated-counts-and-mapping.md):
  Source 두 개, Run/Snapshot 정합성, 일회성 별칭·집계값만 출력, 실제 Source→DQA ID 매핑 미확정.
- 목적: **논리적 원본 데이터 일관성 확인 + 물리적 PostgreSQL 백업본 실제 복구 가능성**을 자동 검사하고,
  단순 원본 ZIP/Preflight READY로 운영 cutover 및 활성화 승인을 주지 않는 Gate를 유지한다.

## 2. 테스트 단계

1. 유일한 Compose 프로젝트 `dqa-u02c3-PID` 및 `pgvector/pgvector:pg16` 초기화.
   내부 `isolated` 네트워크, **호스트에 공개된 DB/API 포트 없음**.
   실제 Legacy/DEMIS/DQA DB의 URL·password 사용 금지.
2. Legacy 원본 `_create_fixture`로 **합성 Source 2개 + 각각 Run 2/Snapshot 2** 및
   하나의 수기 Category/Assignment, Search Doc/1024d Vector 등 생성.
   U-02-C-2의 **독립 SELECT-only** 역할로 17개 원본 테이블 건수 조회.
   원본 finalizer로 실제 `Legacy Catalog Package v2 READY` ZIP 생성
   (READY는 어디까지나 합성 Preflight이며 DBA/기관 승인 아님).
3. 테스트 DB `u02b2b_catalog`를 PostgreSQL 고유 `pg_dump -Fc --no-owner --no-acl`
   로 **개인 임시 디렉터리**에 백업. `pg_restore --list` 및 SHA-256 무결성 기록.
4. 같은 일회용 PostgreSQL 컨테이너에 **다른 새 데이터베이스**
   `u02c3_restore`를 만들고 `pg_restore --exit-on-error --no-owner --no-acl`.
   원본 데이터베이스를 덮어쓰거나 삭제하지 않는다.
5. 복구 DB에 SELECT-only Role을 재허가하고, 소스/복구 DB의 독립
   `REPEATABLE READ, READ ONLY` 트랜잭션으로 동일 Source·Run·Snapshot 연결,
   모든 17개 테이블 건수, 원본 전체 행의 순서 고정 digest 및 `catalog_meta`
   비교. 원본 평문/식별자/벡터/실제 Snapshot JSON을 결과 파일에 출력하지 않음.
6. `backend/tests/u02c3_backup_gate.py`가 4개 정해진 증빙 파일
   (원본 DB custom dump, v2 ZIP, 집계 JSON, 복구 검증 JSON)의 바이트 크기와
   SHA-256을 묶은 `rehearsal_manifest.json`을 생성/재검증.
   바이트 변조/증빙 불일치/승인값 위조는 fail-closed.
7. DQA의 **기존 v2 Validator**로 실제 Legacy ZIP 파싱/검증만 수행하며
   Import/Activation/MCP/DEMIS 연계는 호출하지 않는다.
8. `docker compose down -v`로 일회용 DB/네트워크/볼륨 제거.
   성공 시 임시 증빙 파일도 삭제, 실패 시 **합성 증빙만** 로컬 /tmp에 보존.

## 3. 보안·승인 차단

- 백업 파일은 PostgreSQL catalog 전체를 포함하므로
  **합성 환경에서는 가짜 접속표식/가짜 계정 메타데이터까지 포함**할 수 있다.
  실제 환경에서 이 스크립트·기본 암호를 그대로 사용하거나 백업을 대화에 첨부하면 안 된다.
- 백업 원본/복구본의 행 해시는 테스트 컨테이너 안에서만 비교하며 JSON에는
  `original_inventory_equal`, `row_digest_equal` 등의 Bool 값만 저장.
  **같은 덤프를 자기 자신과 비교하는 검사는 부족하므로 실제 원본과 별도 복원 DB를 대조한다.**
- 증빙 Manifest의 `cutover_allowed=false`, `rollback_authorized=false`,
  `approved_by=null`, `source_to_dqa_mapping=UNRESOLVED_PENDING_APPROVAL`는 고정된다.
  U-02-C-3의 통과는 **테스트 DB에서 복원 성공**을 의미하며 운영 rollback 또는
  Catalog 활성화 근거가 아니다.
- DQA Validator가 Legacy ZIP `READY`를 보고 `activation_eligible=true`를
  반환할 수 있지만, 이는 구조 검증 결과이며 독립 검증자의
  인증·서명/철회·승인 기록을 입증하지 않는다.
- 운영 Source/Run ID 매핑, 실제 Legacy 볼륨 크기, 개인정보/기록 보존 요구,
  실기관 백업 승인, DQA Catalog 활성화/되돌리기 절차는 이 단계에서 미완료다.
- 실제 cutover 전에 원본 운영 DB 백업의 보존·암호화·복구 리허설,
  동일 데이터 일관성, DQA 별도 연결 자격증명/승인, 원본 ZIP/DOCX 보존,
  임상·보안·DBA 승인 및 롤백 시점 정의가 필요하다.

## 4. 테스트 명령

```bash
cd ~/dqa && \
git fetch origin && \
git worktree add --detach /tmp/dqa-pr88-review \
  origin/test/u02c3-isolated-backup-restore-rehearsal && \
bash /tmp/dqa-pr88-review/scripts/u02c3/run.sh
```

성공 표식: `DQA_U02C3_ACCEPTANCE_PASS`.
`pg_dump`, `pg_restore`, 원본/복구 해시, 정책 불변조건과 pytest가 모두
통과해야 출력된다. **서버 실행 결과 확인 전 완료/승인을 선언하지 않는다.**

## 5. 후속 범위 — U-02-C-4 / U-03 Gate

- 운영 서버 실제 연결 이전 **기관 승인 절차/접근 역할/백업 암호화·보존정책** 확정.
- 허가된 DBA의 read-only Legacy 실데이터 건수 조사 계획 및 개인정보 최소화.
- 승인된 Source/Run/Import Revision ID Crosswalk 정의, 충돌·중복·유실 방지.
- DQA 권위 있는 활성 Revision 복구/재활성화 리허설은 **별도 격리 DQA DB**가 있어야 검증 가능.
- 검색/임베딩 재생성 및 Gold Query 품질검증 후 Legacy PoC 중단 가능 여부 판단.
