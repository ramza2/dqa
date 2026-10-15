# S-06-B — Gold Query/관계 경계 확대 및 정량 회귀 검증

> 기준: `main@95f52f0`, 2026-10-15. **Synthetic metadata only.**
> 서버 실행 전 Draft. 이 검증은 실제 군 DEMIS Schema/Oracle dictionary,
> 임상 검색 품질, BGE-M3 유의미성 또는 기관 G1/G2 운영 승인을 인증하지 않는다.

## 목표

S-06-A는 2개 키워드 Gold Query·기본 복합 FK·활성 Revision 교체/검색
격리 및 Stub Semantic/Hybrid 경계를 확인했다. S-06-B는 동작을
중복 개발하지 않고 **Gold 판정셋과 관측 지표**를 확대한다.

| 항목 | 테스트 판정 | 범위/해석 |
|---|---|---|
| **Keyword 의료 용어** | 합성 Gold 5건(혈당·간수치·신기능·투약·퇴원요약), `Recall@5=1.0` | 의료 용어 확장 사전 기반. 실제 임상 질의 정확도 아님 |
| **정량 지표** | `Recall@k`, `Precision@k`, `MRR@k`, `nDCG@k` 산식·음성 케이스 자체 검증 | Binary/수동 Gold key 1개씩; 합성 재현성 평가 |
| **Exact identifier** | `DEMIS_OWNER.TB_LAB_RESULT`·`...GLUCOSE`가 각각 Top-1 | 같은 소스 안 `OTHER_OWNER` 동일명 충돌 분리 |
| **Expansion 게이트** | 5개 한국어 질의에서 `expand_terms=false`는 English-only 샘플 문서 비적중 | Dictionary에 물리 Table/Column ID 포함 금지 |
| **Cross-source provenance** | Source A/B가 같은 Table Key를 갖더라도 응답의 `source/revision/fingerprint`는 활성 소스만 반환 | 동일 키의 타 Source 행 누출 금지 |
| **Cross-schema FK** | 복합 FK ordinal이 입력 순서와 무관; 1-hop/inbound 경로 컬럼 Pair 보존 | Multi-schema 물리 metadata 추적 |
| **Cycle/other owner** | Cycle BFS 종료, 다른 Schema에서 이름이 같은 Table 미탐색 | 접근권한/DBA grant를 부여하는 기능 아님 |
| **Stub Semantic/Hybrid** | 결과 Document Key 중복 없음, Source/Revision/Model Key 일치, 반환 건수 기록 | 해시 기반 결정적 1024d 테스트. `Recall/Precision` 임상 품질 주장 금지 |

## 구현·운영 안전 경계

- `backend/tests/test_s06b_relation_gold.py`: DB 없는 합성 FK 그래프만
  검사. 복합 2-column FK/역방향/Schema 분리/Cycle/누락 Seed.
- `backend/tests/test_s06b_disposable_pg_gold_search.py`: 5개 한국어
  Gold Query에 대한 정량 점수, 2개 정확한 식별자 Top-1, Source 경계.
- `scripts/dqa-s06b-disposable-gold-check.sh`: **S-06-A 전용 Compose
  `compose.s06a.disposable-pg.yaml`을 재사용**. 기존 DQA DB는 사용하지
  않으며 독립 `dqa-s06a-disposable` Project를 생성한다.

Runner는 DB를 `127.0.0.1:55442` /
`dqa_s06a_disposable` / `dqa_s06a_user`로 고정한다.
기존 동명 Compose Project 발견 시 거부하고, `DOCKER_HOST` 및
비로컬 Docker Context 거부. 빈 테스트 DB 식별 확인 후에만 Alembic
적용한다. 기존 S-06-A의 DB Factory Guard(`DQA_S06A_ISOLATED_PG=1`,
DB Host/Port/Name/User 재확인)를 그대로 사용한다.

`db_session`/`db_client` 픽스처 **사용 금지**: 현재 기본 `db_session`
구현은 실제 DB를 `TRUNCATE`할 수 있다. 실제 DEMIS, Oracle,
운영 DQA Catalog/Embedding, 환자 기록/식별정보, ModelOps Gateway
호출 금지. 신규 실 운영 Endpoint/DB Migration/Frontend/Runtime
설정 변경 **없음**. 필요한 READY Revision은 별도 테스트 DB의
합성 ORM 행이며 독립 Preflight/READY 승인 근거가 아니다.

## 개발 서버 수용 명령 (미실행)

```bash
cd ~/dqa && git fetch origin && \
git worktree add --detach /tmp/dqa-s06b-review \
  origin/test/s06b-expanded-gold-query-relations && \
(
  cd /tmp/dqa-s06b-review && \
  bash scripts/dqa-s06b-disposable-gold-check.sh
) && \
git -C /tmp/dqa-s06b-review diff --check 95f52f0 HEAD && \
echo "DQA_S06B_GOLD_REVIEW_PASS"
```

기대 수용 표식:

- `S06B_SYNTHETIC_GOLD_METRICS`: 한국어 Query 5개 지표,
  Semantic/Hybrid Stub 반환 건수 (품질 점수 아님)
- `DQA_S06B_GOLD_PASS`: 관련 pytest 성공 및 **전용 Compose 정리 성공 이후**
- `DQA_S06B_GOLD_REVIEW_PASS`: Git diff whitespace 검사 이후

실패 시 새 PR의 테스트/문서만 수정해 재검증한다.
**사용자 명시적 Merge 승인 전 Draft 유지.**

## 다음 범위 (별도 협의)

- Legacy PoC와 DQA에 대해 **동일 Canonical Dataset/Index/Embedding
  Model Key/검색어/Top-k**를 사용한 검색 parity 및 Gold Set 확장.
- DB 구조 누락/외부 FK/Comment의 실제 DBA Dictionary 가시성은
  DEC-01/DEC-04 승인 뒤 실기관 검증.
- S-05 운영 UI 필수 항목 결정(DEC-08), 독립 Preflight
  서명·정책 결정(DEC-02/#77)은 이번 Test PR과 별도 처리.
