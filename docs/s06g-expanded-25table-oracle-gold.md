# S-06-G — 25개 테이블 규모의 합성 Oracle Schema Gold 회귀

> 2026-10-19 · 기준 `main@33417ee`, S-06-F 머지/서버 Source 동기화 확인.
> **가상의 25개 Table 오프라인 Fixture**로, 실제 DEMIS DB·스키마 사본이나 기존 25-Table Oracle Mock의 실데이터를 대체하지 않는다.

## 1. 선택 이유

S-06-C/D/E는 Oracle Fake Dictionary 2개 테이블에 대해 수집/정규화/변경 Diff/
v2 `WARNING` Candidate/6개 검색 문서·FK 관계를 검증했고, S-06-F는 별도
일회용 PostgreSQL에서 `WARNING` 인덱싱의 `READY` 활성 검색 격리를 검증했다.
반면 여러 테이블·FK·인덱스를 한 번에 포함한 **25개 테이블 규모의
Inspector → Candidate → Data Discovery 파생문서** 결과는 회귀 기준이 없었다.

S-06-G는 `tests.u02_oracle_parity_runner.FakeEngine`의 메타데이터-only
`ALL_*` Fixture를 확장해 **2개 U-02-A 합성 테이블 + 23개 가상 테이블**을 검사한다.
기존 2개 테이블의 잘못된 복합 FK/UK Source 컬럼만 테스트 안에서 보완하고
프로덕션 Adapter/DB/승인 로직은 수정하지 않는다.

## 2. Fixture 및 Gold 조건

- 스키마 이름은 기존 테스트와 일치하는 `DEMIS_OWNER`; 실제 군 Oracle 스키마임을 뜻하지 않는다.
- Table 25, Column 50, PK 24, FK 24, Index 24, 복합 FK/UK/Index 포함.
- 새 테이블은 `TB_GOLD_00`~`TB_GOLD_22`의 **합성 이름**만 사용.
  `TB_GOLD_22` FK는 `REFERENCE_OWNER.TB_REFERENCE_ONLY`에 대한
  외부 Reference-only 메타데이터로, 조회·접근 권한을 부여하지 않는다.
- `OracleSchemaInspector.inspect`: Schema Bind + READ ONLY Transaction 1회 +
  Dictionary SELECT 정확히 6회, DB/Network 연결 없는 `FakeEngine`.
- 모든 Candidate ZIP은 `WARNING`이며 `activation_eligible=False`.
  실제 `READY` 발급, 승인된 Preflight, Catalog Import/Activation을 구현하지 않는다.
- 합성 `CatalogImportRevision`은 **Session에 저장되지 않은 in-memory 객체**로,
  `build_documents_for_revision`, `expand_relations`만 사용한다.

| 신규 단위 테스트 | 기대 회귀 조건 |
|---|---|
| 25-table 전체 수집·문서 | 25/50/24/24 Catalog metadata Count, **75개(TABLE 25 + COLUMN 50) 검색 문서**, Source/Revision/Fingerprint 일치, 외부 참조 Schema는 자가 Table 문서로 추가되지 않음 |
| Dictionary 행 순서 재정렬 | Diff 0, 후보 ZIP Byte/Fingerprint 동일, 75개 문서 내용/local Fingerprint 동일 |
| 1개 Table 주석 변경 | Diff `TABLE CHANGED` 1건, 변경 테이블과 2개 하위 COLUMN 문서 **3개만** local Fingerprint 변화 |
| 1개 Index 누락 | `INDEX REMOVED` 1건, 관련 TABLE 문서 local Fingerprint **1개만** 변화 |
| Source A/B 분리 | 동일 물리 스키마라도 Source별 ZIP·Revision Source Identity 다름; 물리 Fingerprint 및 정규화한 검색 문서 본문은 일치하되 provenance는 격리 |

**신규 테스트 5건**은 전부 DB를 사용하지 않는 Python 회귀다.
고정된 예상값은 이번 가상 Fixture의 결과이지 실제 DEMIS 25개 테이블
Inventory 또는 Oracle Mock 배포의 실측 건수가 아니다.

## 3. 보안·운영 경계

- 변경 파일: `backend/tests/test_s06g_25table_oracle_gold.py` 및 본 문서.
- 기존 Production Python, Frontend/API, DB/Alembic, Oracle Connection Profile,
  Credential/Target/실 DEMIS·복제 EMR, Catalog Import/READY/Activation, MCP,
  임상 Write, KMed-AI·SNUH.AI·FHIR, LLM/ModelOps, Docker/환경변수 설정 **수정 없음**.
- 기존 DB를 `TRUNCATE`할 수 있는 `db_session/db_client` Fixture 사용 금지.
- S-06-A/B의 일회용 PostgreSQL Search Quality/Stub Vector 측정과
  병원/군 측 실제 PoC↔DQA Parity 승인은 별개의 Gate.
- `DEC-01/02/04/10` 및 G0/G1/G2/G5는 외부 결정·서면 증빙을 기다리는 상태.
  실제 Oracle Schema 접근 권한, Index 누락 원인, DBA 승인/Legacy 종료를
  이 합성 회귀 결과만으로 판정하지 않는다.
- 별도 LLM Draft PR #124는 미머지/보류 유지.

## 4. PuTTY 서버 검증 — PASS (2026-10-19)

- **실제 검증한 코드 HEAD:** `b373a1e` · `/tmp/dqa-s06g-review` detached Worktree · 기준 `main@33417ee`.
- `python3 -m venv .venv` 및 `pip install -e '.[dev]'`: **PASS**, Worktree 전용 Python 환경 생성.
- `python -m pytest -q -rs`: **33 passed / 0 failed / 0 skipped**, 신규 S-06-G 5건 및 S-06-E/D/C·Catalog 후보 회귀 포함. `................................. [100%]` 성공 점 33개와 종료 코드 0 확인.
- `git diff --check 33417ee HEAD`: **PASS**. 최종 `DQA_S06G_REVIEW_PASS` 마커 확인.
- `StarletteDeprecationWarning` 1건은 비차단.
- 결과 기록을 위한 후속 커밋은 **문서만 변경**하며, 서버 검증을 통과한 Test/Production 코드 및 의존성을 변경하지 않는다.
- **실 DEMIS·기존 Oracle Mock 25개 테이블의 실제 DB 검증, Independent DBA Preflight/READY, G1/G2/G5, 실 검색품질·임상정보, CI 및 운영 Docker 배포 증빙이 아니다.**
- LLM 관련 PR #124는 여전히 Draft로 보류한다.

## 5. PuTTY 서버 검증 — 실행한 격리 Worktree 명령

**운영 DQA Postgres/Oracle/Docker 미접근.** 독립 Worktree와 해당
Worktree 전용 venv로 아래 DB 없는 테스트 파일만 실행한다.

```bash
cd ~/dqa && git fetch origin && \
git worktree add --detach /tmp/dqa-s06g-review \
  origin/test/s06g-expanded-25table-oracle-gold && \
(
  cd /tmp/dqa-s06g-review/backend && \
  python3 -m venv .venv && \
  .venv/bin/pip install -e '.[dev]' && \
  .venv/bin/python -m pytest -q -rs \
    tests/test_s06g_25table_oracle_gold.py \
    tests/test_s06e_warning_candidate_discovery.py \
    tests/test_s06d_synthetic_dictionary_drift.py \
    tests/test_s06c_oracle_inspector_candidate_chain.py \
    tests/test_schema_catalog_candidate.py
) && \
git -C /tmp/dqa-s06g-review diff --check 33417ee HEAD && \
echo DQA_S06G_REVIEW_PASS
```

**주의:** S-06-F는 일회용 PostgreSQL이 필요한 통합 테스트이므로
이번 S-06-G의 DB-free 테스트 명령에는 포함하지 않는다.
S-06-F의 8건 PASS는 별도 2026-10-19 서버 수용 기록으로 유지한다.

서버 로그에서 **33 PASS / 0 SKIP** 및 `DQA_S06G_REVIEW_PASS`가 확인됐다. 해당 결과는 합성 개발 회귀 수용에 한정하며, 운영 기관의 승인 또는 실제 DB Parity로 해석하지 않는다. **사용자 명시 승인 전 `main` 머지 금지.**
