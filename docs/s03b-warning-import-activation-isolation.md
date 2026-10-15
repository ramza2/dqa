# S-03-B — WARNING 후보 → 기존 Import/Activation 격리 검증

> **2026-10-15 / 합성 서비스·HTTP 테스트.** 이번 단계는 기존 Production
> Import/Activation API의 안전성 회귀 테스트 추가이며, 실제 DQA PostgreSQL
> 데이터나 DEMIS Oracle에 연결하지 않는다. **실기관 G0/G1/DBA 승인 아님.**

## 1. 현재 동작 계약

1. **S-03-A Snapshot 최신 버전 검증:** 저장한 Source/Revision의 본문, Diff,
   Fingerprint 정합성 확인 후 `WARNING` Catalog v2 후보 ZIP 생성.
2. **기존 Package v2 Validator:** ZIP/Manifest/File Digest/Source/Fingerprint를
   검증하되 결과는 `package_readiness=WARNING`, `activation_eligible=false`.
3. **기존 Import 경로:** `POST /api/v1/catalog/packages/import`는
   `WARNING` 후보를 **비활성 Import 이력으로만** 기록할 수 있다.
   같은 SHA-256 ZIP 재업로드는 동일한 Import Revision으로 deduplicate.
   **Import 자체는 Active Catalog Pointer/Activation Event를 갱신하지 않는다.**
4. **기존 Activation 경로:** `POST /api/v1/catalog/imports/{id}/activate`는
   `validation_status=VALID`이고 `package_readiness=READY`인
   Import Revision에 한해 활성화 가능. WARNING 요청에는
   `409 REVISION_NOT_ACTIVATABLE`을 반환한다.
5. **기존 조회 경로:** `GET /api/v1/catalog/active/{source}` 및
   `catalog_query.list_tables`는 이전의 READY 활성 Revision만 이용한다.
   WARNING의 Import 이력 존재와 무관하게 조회 결과/Revision 불변이다.

## 2. 이번 회귀 테스트

`backend/tests/test_s03b_warning_import_active_isolation.py`는
**실제 Validator, Import/Activation/Query 서비스, FastAPI 라우트**를
실행하지만 Repository와 SQLAlchemy Session만 **메모리 전용 FakeStore**로
치환한다. `backend/tests/conftest.py`의 `db_session` 픽스처는 기존
DQA DB 테스트용 테이블을 `TRUNCATE`하므로 여기에서 **절대 사용하지 않는다.**

| 시나리오 | 수용 조건 |
|---|---|
| 기존 READY 활성 + S-03-A WARNING ZIP Validate·Import | WARNING `valid=true`, Import `created=true`, `activation_eligible=false` |
| 동일 WARNING ZIP 재 Import | `created=false`, Import Revision 증가 없음 |
| WARNING 활성화 시도 | `409 REVISION_NOT_ACTIVATABLE`, 기존 Pointer/Event 불변 |
| WARNING Import 전후 Catalog 조회 | 이전 READY Source/Revision 및 Table 목록 유지 |
| 활성 Revision 없는 Source에 WARNING Import | Pointer/Event 생성하지 않음, 활성조회 404 |
| Import ZIP 손상 오류 | HTTP 400, 기존 READY Pointer·검색 결과·Event 그대로 |
| Snapshot 저장 이력 | S-03-A 내부 ZIP 생성·Import와 무관하게 불변 |

## 3. 운영 승인 경계

이번 테스트는 **실제 PostgreSQL 트랜잭션/동시성/복구**를 검증하지 않는다.
운영 적용 전에는 **DQA 서비스 DB와 물리적으로 분리된 독립 PostgreSQL**
에서의 통합 검증 및 DB 백업·복원 정책이 필요하다. 실 DQA DB에서
`db_session`/TRUNCATE 테스트를 실행하지 않는다.

운영 Inspector는 여전히 기본 비활성 및 Production 접근 차단 상태.
독립 DBA Preflight(현재 `NOT_VERIFIED`), READY 발급자 신뢰 검증과
Snapshot→READY 전환 경로는 **미구현/외부 승인 대기**다.
WARNING ZIP을 임의로 수정해 READY로 위조하거나 `CatalogImportRevision`
행을 직접 갱신하는 것은 승인된 전환 방안이 아니다.

## 4. 서버 Acceptance (비파괴 단위 테스트)

```bash
cd ~/dqa && git fetch origin && \
git worktree add --detach /tmp/dqa-s03b-review \
  origin/test/s03b-warning-import-active-pointer-isolation && \
(
  cd /tmp/dqa-s03b-review/backend && \
  ~/dqa/.venv/bin/python -m pytest -q -rs \
    tests/test_s03b_warning_import_active_isolation.py \
    tests/test_s03_snapshot_warning_candidate.py \
    tests/test_schema_snapshot_review.py \
    tests/test_catalog_package_validation.py
) && \
git -C /tmp/dqa-s03b-review diff --check 5edeac1 HEAD && \
echo "DQA_S03B_WARNING_IMPORT_ISOLATION_PASS"
```

**본 절차는 `db_client`, `db_session`, 기존 실 DB를 사용하지 않는다.**
합성 회귀 PASS는 DBA/군 운영 승인, 실 PostgreSQL 이관 수용 또는
Snapshot 후보 활성화 허가로 간주하지 않는다.
