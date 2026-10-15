# U-02-B-2-A — Legacy Final ZIP → DQA Validator 오프라인 호환성 검증

> 상태: 합성 데이터 테스트 구현, 서버 실행 및 acceptance **대기** (Draft PR).
> 이 PR은 U-02-B-2의 **첫 번째 한정 검증**이다. 실 Legacy Catalog DB의
> 실제 테이블을 이용한 finalizer E2E, DOCX 렌더링, Preflight/DBA 인증, 데이터 이행,
> Import/Activation은 아직 검증하지 않는다.

## 목적 및 고정 기준

- Legacy: \`ramza2/demis-schema-search-poc@c9b88f6f6d14dc2598765efbf6bb41b4771f9b25\`.
- DQA 기준: PR #83 squash merge \`4f04870\`.
- 원본 실행 함수: \`app.services.catalog_package.build_catalog_package\` 와
  \`app.services.catalog_package_finalizer.build_final_catalog_package\`.
- 대상 DQA 함수: \`app.services.catalog_package_validation.validate_catalog_package_bytes\`.
- Legacy subprocess는 \`PYTHONPATH=<pinned-legacy>/backend\`로 독립 실행.
  원본 Git 커밋 및 finalizer/writer/model Git blob을 확인한 뒤에만 실행.
- **실제 Legacy 원본 함수는 수정/복제/모사하지 않는다.** 오직 PostgreSQL/Oracle
  접근 대신 합성 ORM row 집합을 반환하는 read-only \`SyntheticLegacySession\`을 사용한다.

## 검증 범위

| 항목 | 자동 검증 |
|---|---|
| Legacy finalizer 실제 ZIP 생산 | 원본 v1 writer와 v2 finalizer를 실제 호출, ZIP 바이트를 프로세스 간 Base64 전달 |
| DQA Validator | ZIP 압축 해제 없이 실제 validator로 2.x, manifest, 파일 크기·SHA, 필수 11개 JSON, source/fingerprint/count 계약 검사 |
| 물리+의미 메타데이터 | 2 table, 5 column, 1 FK(복합 2열 매핑), 1 index, 복합 PK, Category 1·수동 Assignment 1 |
| 부가물 | Package README, diff 요약, report 파일 경로가 manifest에 포함되는지 검사 |
| 정보 노출 | 합성 host·user·credential marker가 ZIP 및 내용에 포함되지 않는지 확인 |
| 무결성 | Category JSON을 변조하고 기존 manifest를 유지하면 DQA가 \`CHECKSUM_MISMATCH\` 거부 |
| READY 의미 차이 | **Legacy의 합성 preflight READY**를 사용하면 DQA validator는 구조적으로 \`READY/activation_eligible=true\`를 반환할 수 있음을 확인. 이는 독립 DBA 검증 또는 임상 승인 **아님** |

## 명시적인 한계

- 합성 \`Session\`은 SQLAlchemy query를 실행하지 않고 미리 준비된 row만 반환한다.
  즉 DB 트랜잭션/SQL 필터/스키마 동기화/권한을 입증하지 않는다.
- \`catalog_report\`, \`catalog_validation_service.latest_preflight_result\`,
  \`schema_diff_service.compare_snapshot_payloads\`는 프로세스 내부 테스트 대체물이다.
  생성된 \`reports/fixture.docx\`의 바이트는 **실제 DOCX 문서가 아닌 테스트 표식**이다.
  report 렌더링, 실 Preflight, 두 번의 Snapshot 간 Diff 자체를 검증하지 않는다.
- \`CatalogAnalysisRun.schema_fingerprint\`는 synthetic 고정 값이며 Legacy 수집 결과로
  계산한 실제 Run fingerprint가 아니다. 실제 Schema/주석/DDL 동기화 검증은 별도다.
- DQA validator는 현재 Manifest의 \`READY\`를 \`activation_eligible\`로 투영한다.
  **외부 Legacy READY를 독립 DBA/기관 승인으로 신뢰하면 안 된다.**
  이 테스트는 ZIP 파싱과 차단 정책을 관찰할 뿐 실제 DQA Import/Activation API를
  호출하지 않는다. 운영 전 검증정책/서명증빙 승인 및 실패시 fail-closed가 필요하다.
- Legacy의 \`default_value\`/index SQL 반출 위험과 실제 DOCX·Category 재이관 안전성은
  별도 보안/수용 테스트를 통과해야 한다. 구조 검증 성공만으로 반출 안전 보증 불가.

## 서버 실행 (PR detached worktree / Legacy 별도 디렉터리)

서버의 기존 \`/tmp/dqa-u02-legacy-pr83.GsdyYQ\`가 고정 SHA를 가리키는지
테스트 fixture가 다시 확인한다. \`set -e\`를 대화형 SSH에서 사용하지 않는다.

\`\`\`bash
cd /tmp/dqa-pr84-review/backend
DQA_U02_LEGACY_ROOT=/tmp/dqa-u02-legacy-pr83.GsdyYQ \
  ~/dqa/.venv/bin/python -m pytest -q -rs \
    tests/test_u02b2_legacy_final_zip_validator.py \
    tests/test_u02b_catalog_v2_fingerprint_contract.py \
    tests/test_catalog_package_validation.py
\`\`\`

환경변수를 빼면 신규 테스트는 SKIP되므로 테스트 성공으로 간주하지 않는다.
서버에서 성공 로그와 \`git diff --check 4f04870 HEAD\`를 확인할 때까지
Draft 유지 / Merge 금지.

## 다음 acceptance (U-02-B-2-B / U-02-C)

분리된 일회용 **Legacy PostgreSQL Catalog DB**에서 실제 persist/snapshot/finalizer/
DOCX 및 2-run Diff를 생성하고 DQA Validator 검증 및 API **validate-only** 경로를
재확인한다. 실제 카테고리·키 제약·SQL default 및 부가물 안전성 점검,
Source/Run 이행 인벤토리, DB backup/restore/rollback 범위 결정은 후속으로 격리한다.
실 DEMIS 접근·임상 데이터 사용·운영 DB 변경·Catalog Activation은 제외한다.
