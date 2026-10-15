# U-02-B — Catalog Package v2 / Fingerprint 계약 비교 (오프라인)

> **단계:** U-02-B-1 (Fingerprint + DQA v2 후보 계약, Draft PR / 실행 검증 대기).
> 실제 Legacy **최종 ZIP을 생성해 DQA에 import**하는 통합 E2E는 **U-02-B-2 후속**이며,
> 이번 단계만으로 Package v2 전체 이관·호환·READY를 보증하지 않는다.

## 비교 고정 버전

- Legacy `ramza2/demis-schema-search-poc@c9b88f6f6d14dc2598765efbf6bb41b4771f9b25`.
  - `backend/app/services/catalog_writer.py::schema_snapshot_fingerprint`
  - `backend/app/services/fingerprint.py::fingerprint`
  - `backend/app/services/catalog_package_finalizer.py::build_final_catalog_package`
- DQA `ramza2/dqa@975990a04f596ea80e5ef572be03d8cf3803a20d`.
  - `backend/app/services/schema_catalog_candidate.py`의 `_physical_payload`, `_fingerprint`, `build_catalog_v2_candidate`
  - `backend/app/services/catalog_package_validation.py::validate_catalog_package_bytes`
  - `backend/app/adapters/catalog/limits.py::REQUIRED_RUNTIME_JSON_FILES`
- 기존 U-02-A [원본 수집기 동등성](u02-a-oracle-inspector-parity.md) 테스트의
  네트워크 없는 `FakeEngine` 및 `rich`/`changed_comment` 합성 Oracle dictionary 응답을 재사용.

## 확인된 계약 차이와 판정 원칙

| 항목 | Legacy Analyzer | DQA | 결론 |
|---|---|---|---|
| ZIP 포맷 | `demis-catalog-package` v2 finalizer, core v1 JSON을 유지하고 `analysis/`, `validation/`, `diff/`, `reports/` 추가 | v2 `WARNING` 후보 ZIP; 11개 필수 runtime JSON + validator | 공통 root JSON 구조 존재, **실 Legacy ZIP E2E 호환은 미검증** |
| Fingerprint 입력 | `schema_snapshot_fingerprint`에서 table, column name/type/null/default/comment, PK/UK/FK, index 요약 | 정렬한 physical DTO로 table, column length/precision/scale 등 추가 속성 포함. default SQL과 index definition 제외 | **해시가 같아야 한다는 조건 금지**. 개별 물리 메타데이터 매핑/버전 확인 |
| 컬럼 길이·정밀도 변화 | Legacy fingerprint 입력에 **포함되지 않음** | DQA physical fingerprint에는 포함 | 두 SHA 값이 다르게 변해도 버그로 판단하지 않음 |
| Oracle default SQL 변화 | Legacy DTO의 `default_value`가 지정되면 fingerprint에 포함. 기본 Oracle 수집기는 `DATA_DEFAULT`를 수집하지 않음 | Snapshot default 값을 **모두 None으로 정규화해 export/해시에서 제외** | 비밀·SQL default 반출 방지; 원본 collector 실제 결과와 합성 DTO 변형을 구분 |
| Index SQL 정의 변화 | Legacy fingerprint는 index name/unique/method/columns만 반영 | DQA physical은 `index_definition=None`으로 정규화 | SQL 본문을 동일성 판단 근거로 간주하지 않음 |
| 주석 변경 | fingerprint에 포함 | fingerprint에 포함 | 양쪽 변경 감지 동작 확인 |
| READY 판단 | `catalog_package_finalizer._package_readiness`: Success Run + Snapshot + persisted PoC Preflight `READY` 시 `READY` 가능 | Candidate는 무조건 `WARNING`, `activation_eligible=false` | **Legacy `READY`가 독립 DBA 증빙/자동 Catalog 활성화가 되지 않음** |
| Supplemental 자료 | `reports/*.docx`, `PACKAGE_README.md`, `diff/latest_summary.md` 등 포함 | DQA 후보에는 없고 11개 필수 JSON만 생성 | Supplemental 파일의 기능 동등/승계는 별도 판단 |

## 이번 PR의 실제 자동 검증

- `backend/tests/u02_package_contract_runner.py`: 별도 Python subprocess가 **원본의 실제** `schema_snapshot_fingerprint`를 호출. DQA는 자체 Candidate ZIP을 생성한 뒤 Validator를 호출한다. 두 구현의 코드를 테스트에서 복제하지 않는다.
- `backend/tests/test_u02b_catalog_v2_fingerprint_contract.py`:
  1. Legacy baseline Git SHA, Oracle collector/base, catalog_writer/fingerprint 원본 Git blob 일치 검사.
  2. `rich`, 주석, 길이, 정밀도, SQL default, index SQL 변형에 대해 양쪽 실제 해시 비교. **원시 hash 일치가 아님**.
  3. 길이/정밀도 변경: Legacy hash 불변, DQA hash 변경; default 변경: Legacy hash 변경, DQA hash 불변; 주석 변경은 모두 변경.
  4. DQA ZIP format/version/`WARNING`, `activation_eligible=false`, 11개 필수 JSON, manifest-managed 파일 크기·SHA-256, manifest/database/run/Snapshot fingerprint 상호 일치.
  5. default SQL/index definition sentinel의 ZIP JSON 반출 없음, Table/Column/복합 FK/Index/Count 구조 유지.
- 실제 DB/Oracle/HTTP/임상자료/키/암호/기존 PoC DB 사용 **없음**. 새로운 migration/운영 서비스/API 없음.

## 한계 및 U-02-B-2 Gate

**이번 단계에서 검증하지 않은 항목**:
Legacy 최종 ZIP을 원본 `build_final_catalog_package`로 **실제 생성**한 후
DQA validator가 받아들이는지, Legacy Categories와 semantic assignment,
Key Constraint, optional DOCX/Diff/Preflight 파일·metadata 버전, 소스·Run·
기본 Schema 매핑, Size/Checksum, Legacy 가공 단계의 데이터 누락/대체,
행 단위 객체 동등성, 실제 DB 데이터 이행 여부.

후속 U-02-B-2에서 **분리된 일회용 합성 Legacy Catalog DB**로 원본 finalizer를
실행하고 DQA validator와 비교한다. Legacy `READY`가 발생해도
**검증 통과는 Import/Activation 승인과 다르며**, 운영 Catalog pointer는 유지한다.
실제 DEMIS/군 DB 계정 및 DBA 승인 없이는 Production 증빙으로 사용하지 않는다.

## 실행

Legacy 고정 worktree `/tmp/dqa-u02-legacy-pinned`과 DQA PR detached
worktree를 준비한 뒤 다음처럼 실행한다.

```bash
DQA_U02_LEGACY_ROOT=/tmp/dqa-u02-legacy-pinned \
  ~/dqa/.venv/bin/python -m pytest -q -rs \
    tests/test_u02b_catalog_v2_fingerprint_contract.py \
    tests/test_schema_catalog_candidate.py
```

Legacy 환경변수를 지정하지 않으면 신규 비교 테스트는 `SKIP`된다.
그 상태를 동등성 PASS로 보고하면 안 된다.
