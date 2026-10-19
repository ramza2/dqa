# S-06-E — 합성 Oracle v2 WARNING 후보 → Data Discovery 문서·FK 관계 연결

> 2026-10-19 · 기준 `main@5086ea2` (S-06-D merge + PuTTY 서버 소스 동기화).
> 합성 `ALL_*` Dictionary FakeEngine / DB 없는 테스트. **실 DEMIS/복제 EMR DB 또는 기관 G1 수용 증빙이 아님.**

## 확인할 실제 Gap

S-06-C/D는 Oracle Inspector → DQA Snapshot/변경 Diff → v2 `WARNING`
후보 구조와 Fingerprint를 검증했다. S-06-A/B는 별도로 구성된
Catalog Revision·문서를 대상으로 검색/관계/키워드 Gold Set을 검증했다.

두 경계를 연결하는 **실제 v2 후보 산출 JSON → Data Discovery 문서 Builder
및 FK 관계 탐색의 소비 계약**은 개별 단위 시험만으로는 보장되지 않는다.

이번 S-06-E에서는 기존 `_inspect/_candidate` Fixture로 생성한 v2 ZIP을
`validate_catalog_package_bytes`로 읽고, 포함된 `tables/columns/relations/
indexes/categories` JSON을 **Session 없는 임시 `CatalogImportRevision`
인스턴스**에 연결한다. 이 임시 객체는 실제 import/activate가 아니다.
`build_documents_for_revision` 및 `expand_relations` 순수 경로만 호출한다.

## Gold Acceptance — 신규 5개 DB-free 테스트

| 검증 범위 | 예상 Gold 결과 | 의미 / 한계 |
|---|---|---|
| 후보 → 문서 | 정확히 **2 TABLE + 4 COLUMN** 문서, 물리 key 중복 없음, `source/revision/fingerprint` 전부 동일; FK/Index 정보 보존 | `WARNING` 후보의 오프라인 형식 호환성. 실제 활성화/검색 DB 호출 아님 |
| FK 탐색 | `TB_VISIT → TB_PATIENT` outbound 및 inverse inbound의 2-column 매핑·ordinal 보존 | FK 참조는 자동 SELECT 권한을 부여하지 않음 |
| 주석 변경 | Table/Column 주석 2곳 변경 시 관련된 문서 5개의 local fingerprints만 변경. 영향을 받지 않는 문서 1개의 local fingerprint 유지 | 전체 Catalog fingerprint는 변경됨. 재인덱싱 대상 선정의 기초 정합성 |
| Oracle Dictionary 행 순서 변경 | 같은 후보의 문서 key/text/local fingerprints가 동일 | 불필요한 문서·Embedding 재생성 방지 기반 검사 |
| SQL Expression 제외 | Oracle column `default_value`·Index `index_definition` 민감 합성 문자열만 추가해도 산출 문서 내용 및 fingerprints 불변, 원문 포함 0건 | 모든 자유 텍스트 PHI 검사/발급자 신뢰 검증은 아님 |

**구분:** `SearchDocumentDraft` 생성만 확인한다. 실제 PostgreSQL
문서 upsert, `keyword_search`, `semantic/hybrid`, Embedding Gateway,
Active Revision 전환 및 검색 품질 `Recall@k` 측정은 기존 S-06-A/B의
별도 격리된 DB Fixture에서만 시험된다.
임시 `CatalogImportRevision(package_readiness='WARNING')`를
`READY`로 위조하거나 활성화하지 않는다.

## 변경·보안 경계

- `backend/tests/test_s06e_warning_candidate_discovery.py`: 새 테스트 5건.
- 이 문서만 변경. 기존 production Backend/Frontend, Alembic/DB,
  Oracle Adapter, LLM/ModelOps/KMed-AI, MCP, Catalog Import/Activation,
  승인·Preflight/임상 Write/실 DEMIS 연결/운영 Docker 코드 변경 없음.
- `tests/test_s06c_oracle_inspector_candidate_chain.py`의 합성
  `_inspect/_candidate`를 재사용하고 `db_session/db_client` 미사용.
- 외부 `DEC-01/02/04/08/10` 및 독립 DBA/군 G1/G2/G5 승인 대기 유지.
  실 DEMIS 스키마 가시성·복제 EMR DB 권한·현장 품질 평가와 별개다.
- LLM 관련 별도 Draft PR #124는 계속 보류.

## 서버 검증 — 최종 PASS (2026-10-19)

- 서버가 검증한 코드 HEAD **`4fa8072`**, detached Worktree `/tmp/dqa-s06e-review`, 기준 `main@5086ea2`.
- `python3 -m venv .venv`, `pip install -e '.[dev]'`: **PASS**, 격리된 의존성 설치.
- `python -m pytest -q -rs`: **32 passed / 0 failed / 0 skipped**.
  신규 S-06-E 5건과 S-06-D/C, Catalog Candidate, S-06-B DB 없는 관계 탐색 회귀 포함.
- `git diff --check 5086ea2 HEAD`: **PASS**, 최종 **`DQA_S06E_REVIEW_PASS`** 출력 확인.
- `StarletteDeprecationWarning` 1건은 비차단.
- 결과를 기록하는 이 후속 커밋은 **문서만 수정**한다.
  32건 PASS를 확인한 테스트 코드, 애플리케이션 코드 및 의존성은 변경하지 않았다.
- **실 DEMIS/복제 EMR DB, 운영 PostgreSQL 문서 upsert/검색, 독립 DBA Preflight,
  G1/G2/G5, READY 발급/Activation, GitHub CI 및 운영 Docker 배포는 검증 범위가 아니다.**
- **ModelOps Token Count P1-12는 참고사항으로만 유지**하며, DQA LLM 사용 여부/폐쇄망 제공자·KMed-AI 인터페이스 확정 전 Adaptive Budgeting 개발을 진행하지 않는다.
  기존 LLM Draft PR #124는 보류한다.

## 서버 검증 — 실행한 격리 Worktree 명령

기존 `~/dqa` Source/DB/Container 변경 없이 별도 Worktree만 생성.
`db_session/db_client`는 기존 DB에 `TRUNCATE`를 실행할 수 있으므로
여기서는 **DB 없는 합성 테스트만** 수행한다.

```bash
cd ~/dqa && git fetch origin && \
git worktree add --detach /tmp/dqa-s06e-review \
  origin/test/s06e-warning-candidate-discovery-parity && \
(
  cd /tmp/dqa-s06e-review/backend && \
  python3 -m venv .venv && \
  .venv/bin/pip install -e '.[dev]' && \
  .venv/bin/python -m pytest -q -rs \
    tests/test_s06e_warning_candidate_discovery.py \
    tests/test_s06d_synthetic_dictionary_drift.py \
    tests/test_s06c_oracle_inspector_candidate_chain.py \
    tests/test_schema_catalog_candidate.py \
    tests/test_s06b_relation_gold.py
) && \
git -C /tmp/dqa-s06e-review diff --check 5086ea2 HEAD && \
echo DQA_S06E_REVIEW_PASS
```

서버에서 32건 PASS/0 SKIP 및 최종 수용 마커를 확인했다. 합성 회귀 결과를 운영 승인으로 간주하지 않는다. GitHub CI와 실 DEMIS/DBA Preflight 검증,
운영 Docker 배포는 별도다. **명시 승인 전 `main` Merge/운영 배포 금지.**
