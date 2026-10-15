# U-02-A — Oracle Inspector 원본/이관본 합성 Fixture 동등성 테스트

> **상태:** 구현 완료, 로컬 테스트 실행/수용 **대기** (Draft PR).
> 독립 DEMIS 조회, Oracle Mock DB 연결, 임상 데이터/기관 승인과는 관계없다.

## 비교 대상 (고정 커밋)

- 원본: [`ramza2/demis-schema-search-poc@c9b88f6`](https://github.com/ramza2/demis-schema-search-poc/tree/c9b88f6f6d14dc2598765efbf6bb41b4771f9b25), `backend/app/analyzers/oracle.py` 및 `base.py`.
- 대상: DQA `b5b3c08`에서 분기, `backend/app/adapters/schema_inspector/oracle.py` 및 `base.py`.
- 독립 실행: `backend/tests/u02_oracle_parity_runner.py`는 외부 DB 드라이버를 생성하지 않는 합성 `FakeEngine`만 사용. `backend/tests/test_u02_oracle_inspector_parity.py`가 각각을 별도 Python subprocess (`PYTHONPATH` 격리)로 import/실행.
- 원본 Checkout은 **정확한 commit SHA + Oracle collector/base 파일의 Git blob SHA**를 검증하여 오염된 working-tree를 판정에서 배제. DQA/PoC 소스를 복사하거나 `sys.modules`를 공유하지 않는다.

## 수용 항목

| ID | Fixture/조건 | 기대 결과 |
|---|---|---|
| PA-01 | `rich` 합성 Oracle `ALL_*` dictionary 응답 | 2개 Table, Column 타입·길이·정밀도·nullability·comment, PK/UK, 복합 FK/Index, target Schema를 양 collector에서 수집한 `dataclasses.asdict` 전체 비교 |
| PA-02 | `empty` response | 모든 수집 목록 empty, source/target identity 유지. 실제 DB 빈 Schema 허용정책의 수용을 의미하지 않음 |
| PA-03 | `changed_comment` | Table/Column 주석 변경 결과를 양 collector에서 동일하게 인식 |
| PA-04 | `rich`와 `changed_comment` 대조 | 검사기가 실제 메타데이터 변경을 구분하고 FK는 보존 |
| PA-05 | 의도적 구현 차이 | Legacy: 0 read-only transaction; DQA: inspect와 schema list 각각 `SET TRANSACTION READ ONLY`. Legacy `list_schemas`의 연결 종료 뒤 mapping 소비 오류, DQA 수정 확인 |
| PA-06 | 보안 경계 | FakeEngine에 `SELECT ALL_*` 외 요청, 미바인딩 Schema, 연결 외 Cursor 접근 차단. 실제 DB 접근 경로/계정 설정/비밀정보 없음 |

**해석:** 동일한 합성 결과의 Snapshot 동등성은 제한된 fixture에 대한
컬렉터 변환 동등성만 입증한다. Oracle dictionary permission,
숨겨진 외부 FK/제약, expression index/LOB, 동시 DDL, Oracle 버전별
차이, 다양한 스키마 객체 및 **실 DEMIS 접근/인증**은 증명되지 않았다.
Legacy의 `list_schemas` mapping 수명 문제는 의도적 DQA 수정으로서
똑같아야 할 동작이 아니며 별도 판정한다.
기존 PoC fingerprint와 DQA fingerprint/Package v2는 **U-02-B**에서 따로 비교한다.

## 재현 및 오프라인 실행 조건

1. 원본 저장소를 기존 구동 인스턴스와 **별도** 디렉터리에 가져와
   `c9b88f6f6d14dc2598765efbf6bb41b4771f9b25`로 checkout한다.
   기존 PoC Docker·DB·파일을 변경하지 않는다.
2. PR 테스트용 DQA detached worktree에서 환경변수
   `DQA_U02_LEGACY_ROOT`를 **원본 git root**로 지정하고
   DQA의 기존 `.venv`에서 실행한다.

```bash
DQA_U02_LEGACY_ROOT=/tmp/dqa-u02-legacy-src \
  ~/dqa/.venv/bin/python -m pytest -q \
  tests/test_u02_oracle_inspector_parity.py \
  tests/test_schema_inspector_oracle.py
```

- 원본 경로 환경변수 미설정 시 신규 테스트는 `SKIP`한다.
  **이 경우 U-02-A가 통과했다고 보고하면 안 된다.**
  명시적 Acceptance 실행 시 환경변수 및 checkout/blob 검증을 필수화한다.
- DQA 자체 Inspector 회귀 테스트도 함께 실행.
- Legacy 저장소 root를 `PYTHONPATH`로 사용하지 말고 해당 `backend`
  하위만 subprocess에 지정한다. 경로 외 두 프로세스의 Python 환경은 동일.
- 성공 후 다음 단계는 U-02-B Package v2/Fingerprint contract 비교이며
  기관 정책 이전 `READY`/Preflight `VERIFIED` 구현을 추가하지 않는다.

## 범위 외

DB migration, production backend/frontend 변경, API, 실제 Oracle/DEMIS,
기존 Oracle Mock 컨테이너, 연결 Profile/Credential, Catalog Import/Active,
임상 데이터, 실제 병원 승인, Legacy 코드의 자동 변경·이관 없음.
