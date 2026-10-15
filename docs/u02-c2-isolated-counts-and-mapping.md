# U-02-C-2 — Legacy 데이터 건수 및 Source·Run 교차검증 (격리 PostgreSQL)

> **2026-10-15, Draft PR / 서버 실행 대기.** 운영 Legacy/DEMIS/DQA DB에 연결하지 않는다.
> 실제 Source/Run 이관 매핑을 수행하지 않고, **합성 카탈로그 집계·연계 정합성**만 검증한다.

## 1. 배경과 선행 작업

- 기준 `main=115c567` (U-02-C-1, PR #86), Legacy 고정 커밋:
  `c9b88f6f6d14dc2598765efbf6bb41b4771f9b25`.
- [U-02-C-1 처분계획](u02-c-cutover-plan.md)의 17개 Legacy ORM 테이블과
  `docs/u02-c-legacy-cutover-inventory.json`을 인벤토리 기준으로 사용한다.
- PR #85 U-02-B-2-B의 `scripts/u02b2b/Dockerfile` 최소 테스트 이미지를 재사용.
  원본 Legacy Checkout은 고정 Git HEAD와 6개 핵심 blob을 확인한 뒤
  **읽기 전용** 마운트한다.

## 2. 구현 및 경계

| 파일 | 역할 |
|---|---|
| `backend/tests/u02c2_inventory_core.py` | 모델 17개 **고정 allowlist**에서 Source별 `COUNT` SQL 생성. Table/Constraint/FK/Index/Category/SearchDoc/Embedding 자식 테이블은 적절한 Source 조인 적용 |
| `backend/tests/u02c2_legacy_pg_inventory_runner.py` | 독립 PostgreSQL에 원본 Legacy `_create_fixture` 2개 저장 후 테스트 전용 Category/Search/1024d Vector 추가. **별도 SELECT-only Role**을 생성하고 read-only Transaction에서만 Collector 실행 |
| `backend/tests/test_u02c2_inventory_readonly.py` | Source별 집계·Run→Snapshot 연결·분리, 사전 확인되지 않은 매핑의 NULL 유지, 악의/오류 연결 거부와 17개 파일 목록 확인 |
| `scripts/u02c2/compose.yaml` | `pgvector/pgvector:pg16`; 내부 네트워크 전용, **호스트 포트 0개**, 새로운 일회용 volume/project |
| `scripts/u02c2/run.sh` | Checkout/Blob 검사→일회용 Docker→집계→DQA pytest→Diff 검사→컨테이너/볼륨 폐기 |

### 읽기 전용 / 안전 제약

- **임시 DB 관리자 계정**으로 합성 Fixture와 제한된 Reader Role을 만든다.
  **Collector는 관리자 Session을 전달받지 않으며**, 신규
  `u02c2_reader`가 가진 `SELECT`만 사용한다. 일관된 `REPEATABLE READ` + 읽기 전용 Transaction 및
  `has_table_privilege(..., 'INSERT') = false`를 검사한다.
- 허가된 두 합성 Source ID만 내부 함수 매개변수로 사용한다.
  17개 집계 대상과 SQL join 경로는 하드코딩된 안전 목록이며, 사용자 제공 SQL이나
  연결문자열/임의 테이블명/API 인자는 받지 않는다.
- `max_sources=20`, `max_runs_per_source=1000`을 초과하면 **부분 성공이 아닌 실패**.
  중복 Run, Snapshot-Run 교차 Source, 존재하지 않는 Run, 한 Run의 다중 Snapshot,
  실패 Run에 붙은 Snapshot, Cross-Source Category Assignment를 차단한다.
- JSON 출력은 `SRC_001` 같은 **일회용 순서 별칭**, 17개 정수 건수,
  성공/실패 Run 수 및 Snapshot 유무만 포함한다.
  Source/Run 실제 ID·이름·원시 Fingerprint·접속정보·컬럼·환자행·Embedding Vector를
  내보내지 않는다. **이 별칭은 지속 가능한 이관 교차표가 아니다.**
- 출력의 DQA Source 이름, Import Revision ID, Snapshot Revision ID는 모두
  `null`; 승인/DBA 확인 전 실제 매핑 생성·Import·Activation 수행 금지.
- 외부 Legacy/실제 운영 DB의 **건수/품질을 이미 조사했다는 의미 아님**.
  Source ID는 Fixture 내부에서만 다루며 로그/문서에 저장하지 않는다.
- Run Snapshot이 일부 없는 상태는 발견 가능하지만, 단순 성공 Run만으로
  DQA 승인·이관 가능 판정을 내리지 않는다.
- 테스트 DB 데이터는 **합성 카탈로그 메타데이터뿐**이며
  의무기록, 실제 DEMIS/Oracle, 외부 인증·기관 승인과 무관하다.

## 3. 실행

기존 PR #86까지 반영한 서버 `main=115c567`, 원본 Legacy Checkout
`/tmp/dqa-u02-legacy-pr83.GsdyYQ`를 사용한다.

```bash
cd ~/dqa && \
git fetch origin && \
git worktree add --detach /tmp/dqa-pr87-review \
  origin/test/u02c2-isolated-inventory-crosswalk && \
bash /tmp/dqa-pr87-review/scripts/u02c2/run.sh
```

이 스크립트는 `set -e`를 대화형 PuTTY에서 실행하지 않는다.
성공 시 `DQA_U02C2_ACCEPTANCE_PASS` 출력.
실패 시 Docker 볼륨은 정리하고 **합성 출력 파일만 임시 디렉터리에 보관**한다.
결과 확인 전에 PASS를 단정하거나 자동으로 머지하지 않는다.

## 4. 이번 단계에서 증명하지 않는 것

- 실제 운영 Legacy의 Source/Run/Snapshot 개수, 과거 실패·누락 Run의 완전성.
- 승인된 Source alias→DQA `source_name`·`catalog_import_revision_id`
  교차표 작성, 운영 Catalog Import/Activation/Cutover.
- 실 DEMIS/Oracle 권한과 실 DB Metadata Inspector parity.
- 원본 ZIP/DOCX/실 Preflight 증빙의 지속 보관, 백업복구, 의료 데이터 보안 심사.
- 실제 Semantic/Embedding 검색 순위·임상 의미 동등성.

**후속 U-02-C-3**에서는 담당자 승인된 read-only 인벤토리 수집절차,
민감도/기관 승인·백업 확인, 출처별 실제 ID crosswalk 작성·복구 리허설 설계를
별도 PR에서 수용하도록 한다. 허가 없이 운영 DB에 집계기를 접속하지 않는다.
