# U-02-B-2-B — Legacy 실제 Catalog PostgreSQL 최종화 + DQA v2 검증

> **상태:** 전용 격리 환경 테스트 구현. 서버 통합 실행 및 수용 대기 (Draft PR).
> 개발/운영 DQA, 독립 Legacy 운영 DB, DEMIS/Oracle, 임상데이터 사용 없음.

## 고정 기준 / 원본 경계

- DQA base: `93f7a64f9ab513dbab403f6cdcd35951f4e7291a` (PR #84).
- Legacy original: `ramza2/demis-schema-search-poc@c9b88f6f6d14dc2598765efbf6bb41b4771f9b25`.
- 원본 소스와 기존 통합 Fixture: `build_catalog_package`, `build_final_catalog_package`,
  `tests.test_catalog_package_finalization._create_fixture / _cleanup`, 보고서 생성기, Diff/Preflight 서비스.
- SHA 및 Git blob 확인 후 원본 checkout을 **읽기 전용 마운트**한다.
- 원본을 DQA 앱에 직접 import하지 않고 Docker runner에서 원본 기능 실행,
  생성된 ZIP에 대해 DQA 실제 `validate_catalog_package_bytes` 수행.

## 독립 실행 구성

- `scripts/u02b2b/compose.yaml`: 유일한 Compose project name (PID 포함).
  `pgvector/pgvector:pg16`, Legacy **원본 초기화 SQL**, 새 DB `u02b2b_catalog`,
  Compose 내부 DNS `catalog-db`만 사용. **host ports: 없음**, `internal: true` 네트워크.
- `scripts/u02b2b/Dockerfile`: torch/embedding 제외한 최소 Python 런타임 + 원본 DB/report 의존성.
- `backend/tests/u02b2b_legacy_pg_runner.py`: Legacy 실제 ORM Session,
  원본 기존 Fixture 기반 **2 SUCCESS Run, 2 Snapshot, DB Preflight 1**,
  합성 Category/Assignment 추가. `READY/WARNING/BLOCKED` 각각 원본 finalizer로 ZIP 생성,
  실제 python-docx 렌더링 결과의 DOCX 구조 검사와 Schema Diff 검사.
- `backend/tests/test_u02b2b_legacy_pg_finalizer.py`: 별도 DQA 프로세스에서
  validator, manifest/digest/count, 보조 ZIP/DOCX, Category, preflight redaction,
  변조 차단, 상태별 활성화 가능 플래그 비교.
- `scripts/u02b2b/run.sh`: 구성 확인→일회용 DB/runner→DQA 회귀 테스트→
  `git diff --check`→항상 `docker compose down -v`.
  성공 시 합성 ZIP 삭제; 실패 시 분석용 합성 ZIP만 /tmp에 유지한다.

## 서버에서 수동 실행

PR 브랜치 detached worktree를 별도 생성한 후, 기존 Legacy pinned checkout을 이용한다.

```bash
cd ~/dqa && git fetch origin && \
git worktree add --detach /tmp/dqa-pr85-review \
  origin/test/u02b2b-isolated-legacy-pg-finalizer

# run.sh는 서브프로세스이므로 실패해도 PuTTY 셸을 종료하지 않음
bash /tmp/dqa-pr85-review/scripts/u02b2b/run.sh
```

첫 실행 시 Docker 이미지 pull/빌드로 시간이 걸릴 수 있다. 필요한 테스트 DB는 전용
Compose 프로젝트와 볼륨에만 생성하고 호스트 PostgreSQL 포트를 사용하지 않는다.

성공 조건: `DQA_U02B2B_ACCEPTANCE_PASS`; 실패/skip은 acceptance가 아니다.
서버에서 직접 실행하기 전 PASS를 선언할 수 없다.

## 중요 정책 / 해석 한계

1. **실제 PostgreSQL DB의 Legacy Catalog 저장/조회와 DOCX 생성/2-run Diff 코드**를
   검증하되, Schema 수집은 합성 메타데이터 fixture다.
   실제 DEMIS 연결/기관 승인/의료데이터/Oracle metadata 조회와 무관하다.
2. DB Preflight JSON은 원본 Fixture가 저장한 **합성 READY/WARNING/BLOCKED** 증빙이며,
   물리적 Oracle 연결과 기관/DBA 검증을 수행하지 않았다.
3. DQA validator의 `activation_eligible=true`는 현재 구조상 manifest READY를 투영한
   결과다. 이 테스트에서는 DQA import 및 activate API를 **호출하지 않는다**.
   Legacy READY만으로 실 운영 Catalog 활성화/조회 권한을 부여하지 않는다.
4. 테스트 대상 Category는 **수동 합성 분류**이며, 실제 인덱싱/의미 판정/임상자문이 아니다.
5. 원본 코드의 일반 `default_value`, `index_definition`, 자유 텍스트 및 DOCX 내
   민감정보 방출 위험은 추가 egress 검토가 필요하다. 이번 테스트는 알려진 가짜
   host/user/credential marker 누출만 검출한다. 운영 외부 반출 안전성을 보증하지 않는다.
6. 모든 DB/ZIP은 통합 테스트 전용이며 의료 정보, 운영 credential 사용 금지.
   테스트 DB는 컨테이너/볼륨 제거로 완전 폐기한다.
7. `main`/운영 서비스/실제 Legacy PoC 소스 코드 수정 없음.

## 이후 U-02-C

- Legacy→DQA의 Source/Run/Category/어플리케이션 이행 인벤토리,
  Fingerprint 알고리즘 차이와 Legacy Category 의미 동등성, Oracle Mock 실제 조회
  테스트를 별도 PR/Acceptance 단계로 수행.
- 기관 협의 전 Read-only DEMIS 권한만 유지, 실제 승인 전 Controlled Write는 범위 밖.
