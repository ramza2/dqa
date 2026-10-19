# S-06-F — Import된 Oracle WARNING 후보의 활성 검색/Embedding 격리

> 기준: `main@b2fcd8a` (S-06-E GitHub Merge 및 PuTTY 소스 동기화 확인).
> **일회용 루프백 PostgreSQL 개발 검증**; 운영 DQA DB, 실 DEMIS/복제 EMR DB,
> 실제 의료데이터/임상 승인, 독립 DBA READY 발급 근거가 아니다.

## 1. 발견된 검증 Gap

- S-06-C/D는 Oracle Inspector Fake Dictionary → Snapshot → v2 `WARNING` 후보 및 변경 Diff를 검증했다.
- S-06-E는 **영속 저장 없이** v2 `WARNING` JSON → 6건의 TABLE/COLUMN 문서 및 FK 경로를 확인했다.
- S-06-A/B는 별도로 생성한 합성 `READY` ORM Revision으로 일회용 pgvector 기반 검색·문서·Embedding 경계를 검증했다.
- **빠진 E2E 경계:** *실제로 수집된 합성 Oracle WARNING ZIP*을 DQA의 **정식 Import 서비스**로 영속 저장하고, 문서·Embedding까지 생성했더라도 **활성 포인터와 검색은 오직 별도의 READY Revision만** 사용해야 한다.

S-06-F에서는 새 애플리케이션 엔드포인트·보안 정책을 구현하지 않고,
기존 Import / Active / Discovery 서비스를 결합하는 격리 회귀를 추가한다.

## 2. 신규 테스트 2건

1. **WARNING만 Import한 Source**
   - `build_catalog_v2_candidate(_inspect())`로 Oracle 합성 Inspector 기반 ZIP 생성,
     정식 `import_catalog_package_bytes`로 `WARNING` Revision 저장.
   - `rebuild_for_revision` → 정확히 **6건** 물리 문서, `StubEmbeddingProvider` → 6건 embedding 생성.
   - `activate_catalog_revision`은 `REVISION_NOT_ACTIVATABLE`로 거부.
   - Index/Embedding이 존재해도 `search_schema`는 활성 Revision 부재를
     `ACTIVE_REVISION_NOT_FOUND`로 실패 처리, 활성화 Event 0건.

2. **동일 Source의 기존 READY 포인터 보존**
   - **테스트 전용으로 별도 만들어진** READY ZIP(`TB_S06F_READY_ONLY`)을 Import·Activate 후,
     문서 2건 및 1024차원 Stub Embedding 생성.
   - 동일 Source에 다른 물리 식별자의 Oracle 합성 `WARNING` ZIP을 Import한 후
     문서 6건 및 Stub Embedding을 생성해도 WARNING의 활성화 시도는 409에 대응하는
     `REVISION_NOT_ACTIVATABLE` 경계에서 차단(본 시험은 HTTP가 아닌 Service Exception).
   - 활성 Source pointer/Fingerprint/Activation Event는 기존 READY 그대로.
     `list_tables`에는 오직 READY 테이블, `TB_VISIT` keyword query 결과 0,
     keyword·semantic·hybrid 검색도 **기존 READY Revision의 Source/Revision/Fingerprint**
     및 READY 문서 키만 반환한다. FK 관계 확장도 WARNING 테이블을 노출하지 않는다.
   - 여기의 READY는 **승인·독립 DBA Preflight에서 발급한 패키지가 아니라
     테스트 전용 Fixture**이다. 합성 READY 결과는 운영 활성화 권한을 만들지 않는다.

## 3. 범위·DB 안전 조건

- 신규 `backend/tests/test_s06f_disposable_warning_search_isolation.py`(2개 통합 회귀).
- 기존 `scripts/dqa-s06b-disposable-gold-check.sh`의 **pytest 파일 목록에 S-06-F를 1건 추가**.
  기존 S-06-A의 루프백/고정 DB명/계정/포트/빈 DB 확인/Compose 프로젝트 충돌 거부/
  Alembic-only 초기화, 종료 시 독립 Compose 정리 정책을 그대로 사용한다.
  새 runner·Compose/DB 포트를 복제하지 않는다.
- 임시 DB는 `127.0.0.1:55442`, `dqa_s06a_disposable` / `dqa_s06a_user`,
  Docker Compose 프로젝트 `dqa-s06a-disposable`. 동일한 기존 Compose
  프로젝트가 발견되면 **시작 및 삭제를 거부**한다. 실행 전 루프백 Docker context,
  `DOCKER_HOST` 미설정, 빈 전용 DB인지 재검증한다.
- 임상 본문/환자 식별자 없음. 기존 DQA DB, 실 Oracle/DEMIS, 실제 BGE-M3/LLM/ModelOps,
  Backend/Frontend Runtime, 신규 DB migration/계정 권한, Catalog 승인·READY 발급,
  MCP/쓰기·외부 FHIR/KMed-AI 연결, 운영 Docker 배포 **변경/접근 없음**.
- 기존 `db_session`/`db_client`는 서버 DB를 `TRUNCATE`할 수 있어
  **절대 사용하지 않는다**.
- LLM 관련 별도 Draft PR #124는 유지/보류한다.
- 본 검증은 사이트 `G1/G2/G5`, 실 복제 EMR DB의 Registry/권한/신뢰 계약,
  PoC cutover 또는 운영 검색·임상 안전성 인증으로 사용하지 않는다.

## 4. PuTTY 서버 Acceptance — PASS (2026-10-19)

- **검증한 테스트/Runner HEAD:** `ff1c641`; detached Worktree `/tmp/dqa-s06f-review`; 기준 `main@b2fcd8a`.
- `python3 -m venv .venv` 및 `pip install -e '.[dev]'`: **PASS**.
- S-06-B 기존 disposable PostgreSQL project `dqa-s06a-disposable` 생성 및 healthy 확인, 빈 DB 가드 통과 후 Alembic `20261014_ss02`까지 이행: **PASS**.
- `python -m pytest -q -rs -s`: 출력 `.....` + `...` → **8 passed / 0 failed / 0 skipped**. 신규 S-06-F 2건 포함. Pytest는 `-q` 방식으로 별도 합계 문자열을 출력하지 않았지만 성공 dot 8개와 exit 0을 확인했다.
- S-06-B 합성 Gold 5개 질의(`혈당/간수치/신기능/투약/퇴원요약`)는 `Recall@5=1.0`, `MRR@5=1.0`, `nDCG@5=1.0`, `Precision@5=0.2`를 출력했다. Semantic/Hybrid Stub은 각각 4개 결과, model_key 일치. **실 BGE-M3·임상 품질 지표가 아니다.**
- 테스트용 PostgreSQL 컨테이너 및 Compose 네트워크 **Stopped/Removed** 확인 후 `DQA_S06B_GOLD_PASS` 출력.
- `git diff --check b2fcd8a HEAD` **PASS** 및 최종 `DQA_S06F_REVIEW_PASS` 확인.
- `StarletteDeprecationWarning` 1건은 비차단.
- 본 기록을 추가하는 후속 커밋은 **문서만 변경**하며, 검증한 Test/Runner/운영 코드는 그대로 유지한다.
- **실 DEMIS/복제 EMR DB, 운영 PostgreSQL, 기관 DBA Preflight·READY 승인, G1/G2/G5, 외부 LLM/Embedding, 실제 임상 검색 품질, GitHub Actions CI 또는 운영 Docker 배포는 이번 수용 대상이 아니다.**

## 5. PuTTY 서버 Acceptance — 격리 Worktree 실행 명령

```bash
cd ~/dqa && git fetch origin && \
git worktree add --detach /tmp/dqa-s06f-review \
  origin/test/s06f-warning-index-active-search-isolation && \
(
  cd /tmp/dqa-s06f-review/backend && \
  python3 -m venv .venv && \
  .venv/bin/pip install -e '.[dev]' && \
  cd .. && \
  DQA_S06B_PYTHON=/tmp/dqa-s06f-review/backend/.venv/bin/python \
    bash scripts/dqa-s06b-disposable-gold-check.sh
) && \
git -C /tmp/dqa-s06f-review diff --check b2fcd8a HEAD && \
echo DQA_S06F_REVIEW_PASS
```

수용 표식 `DQA_S06B_GOLD_PASS`와 `DQA_S06F_REVIEW_PASS`가 모두 서버 로그에서 확인됐다. 검사 완료 사실은 운영 DBA/Gate 승인으로 해석하지 않는다.

**운영/공유 Docker Compose 재배포나 서비스 컨테이너 재시작 명령을 실행하지 않는다.**
일회용 PostgreSQL은 임시 테스트를 위한 별도 Compose 프로젝트로만 사용된다.
서버 검증 전 PASS 또는 CI 완료 주장은 하지 않는다.
**사용자 명시 승인 전 PR 머지·운영 배포 금지.**
