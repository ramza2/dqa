# S-06-D — Oracle Dictionary 변경·누락 및 민감 SQL 메타데이터 회귀

> 2026-10-19, `main@f832af0` (S-06-C 병합 및 서버 소스 동기화).
> **합성 Oracle Dictionary FakeEngine / 오프라인 DB 미사용 테스트**.
> 실제 운영 복제 EMR DB, Oracle DBA Dictionary grant, 군 G1 수용 근거가 아니다.

## 배경 및 목적

S-06-C에서 Synthetic Oracle `ALL_*` 조회 결과 → DQA `SchemaSnapshot` →
Diff → v2 Catalog `WARNING` 후보 Fingerprint 일치 및 주석/정렬 처리 동작을 확인했다.

S-06-D에서는 구조 변경/Dictionary 미가시성을 구분 없이 정상으로 간주하는
위험을 막기 위해 **기존 S-06-C 검사 DTO를 재사용**하여 다음 4가지 경계를 검증한다.

| 테스트 | 검증할 기준 | 한계 |
|---|---|---|
| Dictionary Index 감소 | 기존 Index 1건 미조회 → `INDEX REMOVED` 정확히 1건, Diff·v2 후보 Fingerprint 변경, 후보 `WARNING`·Activation 불가 | 실제 DDL 삭제인지 Dictionary SELECT grant 부족인지는 별도 DBA가 판단 |
| 외부 Schema의 복합 FK 변경 | 참조 Schema·2번째 컬럼 쌍 변경 → FK `CHANGED` 1건, 변경 필드 `columns/target_schema`, v2 후보 Fingerprint 일치 | 타 Schema 조회 권한이나 환자 데이터 접근을 허용하지 않음 |
| SQL Expression 비반출 | Oracle default SQL / index definition 텍스트만 바뀌면 Diff 0, 후보 ZIP 바이트·SHA 안정, 원문 흔적 없음 | 임의 주석/보관정보의 전면 민감성 검사로 간주하지 않음 |
| 잘못된 복합 Index | 중복 `ordinal_position`을 가진 Index는 Diff 일치/동등으로 간주하지 않고 `ValueError` | v2 Builder 단독 정책 또는 실 Dictionary 무결성 전반 검증은 별도 |

**중요:** 부적절한 Dictionary 가시성은 정상적인 Schema DDL 변경과 표면상 동일하게
보일 수 있다. 개발 합성 회귀는 어느 원인인지 판별할 수 없다. 사이트 검증에서는
DBA 승인된 `Source/Schema/Account/권한 범위`와 Baseline, 읽기 전용 Dictionary
조회 기록으로 원인을 독립 판정해야 한다. Index 누락은 자동 복구하거나 무단 승인하지 않는다.

## 변경 범위 및 불변식

- `backend/tests/test_s06d_synthetic_dictionary_drift.py`: 테스트 4건.
- 이 문서만 추가. 기존 S-06-C `_inspect/_candidate` Fixture 재사용.
- API/Runtime/DB/Alembic/ModelOps/KMed-AI/LLM/Oracle driver/인증·권한/보안 설정,
  Snapshot/Preflight/Review, Catalog Import·Activation, MCP, 환자 조회·임상 Write
  및 운영 Docker 설정 변경 없음.
- `WARNING` 후보는 실제 `READY` 인증, 독립 DBA Preflight `VERIFIED`,
  G1/G2/G5 Cutover 승인이 아니다.
- 실제 Legacy Analyzer 5개 SKIP 케이스를 미확인 PASS로 간주하지 않는다.
- LLM 관련 Draft #124는 보류 상태 그대로 유지한다.

## 서버 Acceptance — 미실행

실제 DEMIS/기존 DQA DB·Docker와 무관한 **detached Worktree + DB 미사용 pytest**:

```bash
cd ~/dqa && git fetch origin && \
git worktree add --detach /tmp/dqa-s06d-review \
  origin/test/s06d-synthetic-dictionary-drift-guards && \
(
  cd /tmp/dqa-s06d-review/backend && \
  python3 -m venv .venv && \
  .venv/bin/pip install -e '.[dev]' && \
  .venv/bin/python -m pytest -q -rs \
    tests/test_s06d_synthetic_dictionary_drift.py \
    tests/test_s06c_oracle_inspector_candidate_chain.py \
    tests/test_schema_snapshot_diff.py \
    tests/test_schema_catalog_candidate.py
) && \
git -C /tmp/dqa-s06d-review diff --check f832af0 HEAD && \
echo DQA_S06D_REVIEW_PASS
```

DB-backed `db_session`/`db_client` 사용 금지. 해당 Fixture는
설정에 따라 기존 DQA DB에 `TRUNCATE`를 실행할 수 있다.
검증 로그에서 실제 PASS/SKIP 수와 최종 수용 마커를 확인할 때까지
완료를 주장하지 않는다.

GitHub Actions CI/운영 Docker/실 DEMIS/기관 승인과 서버 합성 pytest는 별개.
**사용자 별도 명시 승인 전 `main` Merge 또는 운영 배포 금지.**
