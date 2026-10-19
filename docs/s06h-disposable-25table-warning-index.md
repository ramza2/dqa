# S-06-H — 25-table WARNING Catalog의 일회용 PostgreSQL 색인/검색 격리 검증

> 2026-10-19 · 기준 `main@03298c9` (S-06-G 머지 및 PuTTY Source 동기화 확인).
> **Synthetic-only, disposable loopback PostgreSQL**. DB 테스트 수용은 군/병원 DBA 또는 Legacy Parity 승인이 아니다.

## 목적과 기존 검증과의 차이

- S-06-G: Oracle Fake `ALL_*` Dictionary → 25 Table / 50 Column
  → v2 `WARNING` → 75 `SearchDocumentDraft` (**메모리**) 및 Diff.
- S-06-F: 오프라인 Oracle **2 Table** 후보를 일회용 PostgreSQL에
  Import하고 6개 문서·Stub Embedding을 저장해도 `READY` 검색은 보호됨.
- **S-06-H의 Gap:** 25개 테이블을 실제 DQA Catalog Import→75개 문서 저장
  →`pgvector(1024)` Stub Embedding 색인으로 연결하고, 재실행 중복 처리·
  Coverage/Revision Provenance/READY 검색 보호를 일회용 DB에서 검사.

새로운 운영 기능을 만들지 않는다. 현행 서비스의 크기/재실행/활성화
경계를 재사용·고정하는 **2개 통합 회귀 테스트**만 추가한다.

## 골드 수용 조건

| 시험 | 예상 결과 | 범위 제한 |
|---|---|---|
| **WARNING 25-table 재실행·색인** | Import 한 번→25T/50C/24FK/24IX → 75개 문서, 75개 Stub Vector. Coverage 처음 0/75 → 동기화 후 75/75; 동일 ZIP 재 Import는 같은 Revision으로 dedup, 재 rebuild 후 Embedding 재호출 **0건**/skip 75건 | Coverage `is_ready`는 *embedding 최신성* 상태이지 Catalog `READY` 승인 아님. CLI/Runtime/LLM 미사용 |
| **이미 활성화된 합성 READY 보호** | 별도 독립 합성 `READY` 패키지 2개 문서 활성화 → 같은 Source에 25-table `WARNING` 75개 문서+벡터 생성 및 Activation 거부 → Active Revision/Fingerprint·Activation Audit 그대로. `TB_GOLD_07` Keyword 결과 0; READY 대상 Keyword/Semantic/Hybrid는 READY 문서와 해당 Source/Revision만 반환. 관계 확장도 격리 | `READY`는 **테스트용 인위적 Fixture**, DBA 서명 증빙·Preflight 인증이 아님 |

테스트 주입점은 `tests.test_s06g_25table_oracle_gold._candidate/_inspect_25`,
기존 `S-06-F`의 인위적 `READY` ZIP 생성기,
`S-06-A`가 이미 구현한 제한된 일회용 DB Factory,
`StubEmbeddingProvider`이다. 어떤 실제 Oracle 접속/LLM/임상 데이터도 없다.

## 변경 파일 및 안전 기준

- `backend/tests/test_s06h_disposable_25table_warning_index.py`: 새 테스트 2건.
- `scripts/dqa-s06b-disposable-gold-check.sh`: 기존 테스트 파일 목록에
  **S-06-H 하나만 추가**. 루프백/고정 DB명·User·Port, Docker Context,
  기존 Compose 프로젝트 존재 거부, 빈 DB 확인, Alembic, EXIT cleanup 유지.
- 본 수용 문서만 추가. Production Backend/Frontend/API/Oracle Adapter,
  DB Migration/운영 데이터/Container, Catalog READY/Preflight/Activation
  정책, DEMIS/복제 EMR, MCP/Write, FHIR/SNUH.AI/KMed-AI, LLM/ModelOps 변경 없음.

일회용 DB는 `127.0.0.1:55442`, `dqa_s06a_disposable`,
`dqa_s06a_user`, Compose 프로젝트 `dqa-s06a-disposable`.
**실행할 때마다 새 tmpfs PostgreSQL**에 한해 Schema Migration 수행.
기존 프로젝트가 있으면 자동 채택/종료/볼륨 삭제 대신 **거부**.
테스트가 종료되면 해당 신규 프로젝트 Container와 Network만 정리.
`db_session/db_client` Fixture (운영 DB `TRUNCATE` 위험)는 사용하지 않는다.

이 시험에서 `embedding_status_for_revision(...).is_ready`가 참이어도
`package_readiness='WARNING'`의 Activation은 계속 거부되어야 한다.
기관/DBA `G1/G2/G5`, 실제 25 Table Oracle Mock 접속, PoC↔DQA
같은 실 스키마/Model Key의 Parity, BGE-M3 실제 검색품질, 운영 Cutover는
여전히 **미검증 및 외부 의사결정 대기**. LLM 관련 PR #124 Draft 유지.

## PuTTY 서버 수용 결과 — PASS (2026-10-19)

- **검증 코드 및 Runner HEAD:** `930ba8f`, detached Worktree `/tmp/dqa-s06h-review`, 기준 `main@03298c9`.
- 격리 가상환경 생성 및 `pip install -e '.[dev]'`: **PASS**.
- `dqa-s06a-disposable` 루프백 PostgreSQL 컨테이너 **Healthy**, 전용 DB 안전 검증 및 Alembic `20261014_ss02`까지 Migration: **PASS**.
- `pytest -q -rs -s`: 로그의 `.....` + `.....`로 **10개 테스트 PASS / FAIL 0 / SKIP 0** 판정. `-q -s` 로그에 별도 건수 요약은 없으나 성공 마커와 종료 코드 0을 확인했다. 신규 S-06-H 2건 및 기존 S-06-B/F 회귀 포함.
- S-06-B의 합성 Gold 5개 질의(혈당/간수치/신기능/투약/퇴원요약): 각 `Recall@5=1.0`, `MRR@5=1.0`, `nDCG@5=1.0`, `Precision@5=0.2`; Stub Semantic/Hybrid 각 4건 조회 및 model_key 일치. **실 BGE-M3 또는 임상 검색품질 증빙이 아님**.
- 일회용 PostgreSQL Container **Stopped/Removed**, 전용 Network **Removed** 후 `DQA_S06B_GOLD_PASS`.
- `git diff --check 03298c9 HEAD` **PASS** 및 `DQA_S06H_REVIEW_PASS` 최종 마커 확인.
- `StarletteDeprecationWarning` 1건은 비차단.
- 후속 결과 기록 커밋은 **문서만 변경**하며, 이 서버에서 검증한 테스트/Runner 및 Production 코드·의존성을 변경하지 않는다.
- **실 DEMIS·복제 EMR·운영 PostgreSQL·독립 DBA Preflight/READY·G1/G2/G5·실의료 검색품질·GitHub CI·운영 Docker 배포는 검증 범위 밖이다.**
- LLM 관련 별도 PR #124는 Draft 보류 유지.

## PuTTY 서버 수용 명령 — 검증 당시 실행 내용

기존 `~/dqa`와 운영 DQA Docker·DB를 바꾸지 않으며 별도 worktree/venv를 쓴다.

```bash
cd ~/dqa && git fetch origin && \
git worktree add --detach /tmp/dqa-s06h-review \
  origin/test/s06h-disposable-25table-warning-index && \
(
  cd /tmp/dqa-s06h-review/backend && \
  python3 -m venv .venv && \
  .venv/bin/pip install -e '.[dev]' && \
  cd .. && \
  DQA_S06B_PYTHON=/tmp/dqa-s06h-review/backend/.venv/bin/python \
    bash scripts/dqa-s06b-disposable-gold-check.sh
) && \
git -C /tmp/dqa-s06h-review diff --check 03298c9 HEAD && \
echo DQA_S06H_REVIEW_PASS
```

성공 마커:
- `DQA_S06B_GOLD_PASS`: 기존 S-06-B/F + 신규 S-06-H Test 통과,
  전용 Compose Container/Network 정리 **후** 표시.
- `DQA_S06H_REVIEW_PASS`: Git whitespace 검사까지 통과 후 표시.
- 서버 로그에서 **10 PASS / 0 FAIL / 0 SKIP** 및 두 PASS 마커가 확인됐다.
  이 결과만으로 실제 DBA 또는 군 기관의 승인·운영 수용을 주장하지 않는다.

## 다음 의사결정 경계

S-06-A~H 합성/일회용 DB 경계가 통과해도,
**DEC-01/04/10**의 승인 Schema·실 Source 및 실제 Legacy→DQA
canonical 메타데이터/검색 Gold 기준이 없으면 G1을 완료 처리하지 않는다.
기관 협의 후 실접근이 승인되면 별도 승인·검토된 최소 권한·감사 검증을
착수해야 하며, 현재 PR에서 그 권한이나 연결을 생성하지 않는다.
**사용자 별도 명시 승인 전 `main` Merge/운영 배포 금지.**
