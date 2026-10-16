# P30-C — Data Discovery Source / Catalog Revision / Index Lifecycle ASGI 통합회귀

> 개발기준: `main@83df7b3`. **실행 전 Draft 수용 계약**. 실제 DEMIS, Oracle,
> 복제 EMR DB, ModelOps, LLM, 의료 데이터, 군·DBA 승인/운영배포와 무관하다.

## 1. 선정 배경 및 기존 시험과의 차이

- S-06-A/B는 합성 Catalog Gold Set 및 keyword/semantic/hybrid 검색·관계·품질 지표를 서비스 계층에서 검증했다.
- P30-A는 Web/MCP 공통 Query Execution 서비스를 무DB 테스트로, P30-B는
  격리 PostgreSQL + ASGI + Mock Oracle Query Audit를 검증했다.
- **P30-C**는 실제 `/api/v1/data-discovery/{source}/index-status`,
  `.../documents/rebuild`, `.../embeddings/sync`, `/search`의
  HTTP 경계를 통과해 **Source ↔ Active Revision ↔ Document/Embedding
  상태 일관성**을 검증한다. 기존 UI는 변경하지 않는다.
- 활성 Catalog를 구성하는 `READY` fixture는 **합성 과거 Import
  객체**이며 승인/DBA Preflight `VERIFIED` 근거가 아니다.

## 2. 격리·제한 (중요)

- 새 `compose.p30c.disposable-pg.yaml`에서 별도 Compose 프로젝트
  `dqa-p30c-disposable`, PostgreSQL/pgvector 16, 512MB `tmpfs`,
  `127.0.0.1:55448` (loopback)과 비생산 DB `dqa_p30c_disposable` 생성.
- 전용 runner는 **기존 프로젝트/Port가 존재하면 실패**, 로컬 Docker
  unix context, 새 컨테이너 Project Label/Port, 빈 DB, DB 사용자 확인 후
  Database COMMENT 마커 `DQA_P30C_DISPOSABLE_DB_V1`을 새 DB에 기록.
  이 확인 이후에만 격리 DB 대상으로 Alembic `upgrade head` 수행.
- 전용 pytest fixture는 매 테스트 전 DB Host/Port/Name/User/Password,
  P30-C 실행마커, DB COMMENT, 필요한 테이블 상태를 확인한다.
  **위험한 루트 `db_session` 또는 `db_client` fixture를 전혀 호출하지 않는다.**
  실제 DB `TRUNCATE`/DROP 실행 없음. 테스트는 각자 합성 Source·Revision
  객체를 새 DB에 추가한다.
- 임베딩 `StubEmbeddingProvider`는 SHA256 기반 결정적 **가짜 벡터**를
  메모리 계산만으로 반환한다. `EMBEDDING_BASE_URL`은
  `embedding.invalid` 메타데이터용이며 외부 연결하지 않는다
  (`create_embedding_provider`를 실제 앱 라우트에서 주입된 Stub으로 대체).
- PostgreSQL 자체는 Docker localhost 연결만 허용. DEMIS/Oracle
  연결, 외부 LLM/모델 호출, 데이터 업로드/수집, 운영 DB/Compose 접근 금지.
- 독립된 폴더 `backend/tests/p30c/`만 실행, 종료 뒤 전용 Container·Network
  제거 성공을 확인한 뒤에만 PASS 출력.

## 3. 신규 통합시나리오 (4건)

| ID | 입력/변화 | 서버 Acceptance |
|---|---|---|
| P30C-01 | Source A/B의 동일 Table Key + 각자 독점 객체, 두 Source 별 Rebuild/Sync | HTTP keyword/semantic/hybrid 3종 모두 Search Response Source/Revision/Fingerprint·각 Hit Identity 일치, 상대 Source 독점 객체 누출 없음. Index Status 두 Source 모두 READY |
| P30C-02 | Source A1 READY + Embedding READY, B1 유지 → Source A2 활성화 | A2 문서 0 시 검색 3종 409 DISCOVERY_INDEX_NOT_READY. A2 문서만 Rebuild 후 Keyword는 A2만 노출, Semantic/Hybrid는 409 EMBEDDING_NOT_READY. A2 Sync 후 모두 A2만 검색·READY, A1 옛 문서 보존, B1 영향 없음 |
| P30C-03 | 같은 현재 Revision 대상 Rebuild×2, Embedding Sync×2 | 두 번째 Rebuild에서도 처리 문서 수(upserted_count)=1, 삭제=0. Document ID·Key·Fingerprint·본문과 Embedding ID·Fingerprint 유지, 중복 row 생성 없음. 두 번째 Sync embedded=0/skipped=1, Status READY 및 상태 조회로 모델 `embed_*` 호출 없음 |
| P30C-04 | 무권한 사용자의 검색·상태 조회, Viewer의 관리 API 접근, 없는 Source | 무권한 CATALOG_READ 403, Viewer CATALOG_MANAGE 403 (읽기는 원래 허용), 없는 Source 404. 대기 인덱스가 저절로 생성되지 않음 |

**범위 한계:** HTTP TestClient는 ASGI 인프로세스 요청이며 실제 원격
브라우저 네트워크와 프론트엔드 경합/느린 응답을 시뮬레이션하지 않는다.
별도 `frontend/src/test/DataDiscovery.test.tsx`의 stale-response 가드와
혼동하지 않는다. 성능/Recall@k/실 임상 검색 품질도 측정하지 않는다.

## 4. 변경 파일

1. `compose.p30c.disposable-pg.yaml` — 완전 분리 PostgreSQL
2. `scripts/dqa-p30c-disposable-discovery-check.sh` — 검증 선행 및 종료 정리
3. `backend/tests/p30c/conftest.py` — DB identity/marker 검증 (TRUNCATE fixture 미사용)
4. `backend/tests/p30c/test_discovery_revision_asgi.py` — 4개 ASGI/DB 테스트
5. 이 문서

**제품 backend/app, frontend, API schema, Alembic revision, Config,
운영 Compose, Query Template/MCP 또는 Oracle Adapter 수정 없음.**

## 5. 서버 Acceptance — 아직 미실행

```bash
cd ~/dqa && \
git fetch origin && \
git worktree add --detach /tmp/dqa-p30c-review \
  origin/test/p30c-discovery-revision-asgi && \
(
  cd /tmp/dqa-p30c-review && \
  bash scripts/dqa-p30c-disposable-discovery-check.sh
) && \
git -C /tmp/dqa-p30c-review diff --check 83df7b3 HEAD && \
echo "DQA_P30C_REVIEW_PASS"
```

수용 예상: **4 tests passed, 0 failed**, 전용 Container/Network 제거 후
`DQA_P30C_DISCOVERY_ASGI_PASS`, `DQA_P30C_REVIEW_PASS`.
**서버 출력 전까지 통과를 주장하지 않는다.**

오류 시 기존 DQA 서버를 재시작하거나 DB 세팅을 바꾸지 않는다.
본 Draft PR 범위에서만 수정해 재검증한다. 사용자 별도 명시적
승인 전 main 머지·운영 재배포 금지.

## 6. 다음 계획

- P30-C 통과/머지 이후 **S-05-C1 Connection Profile 조회·상태 운영 UI**
  와 **S-05-C2 Inspector Target 관리 경계**를 단계적으로 검토한다.
- 10/15 의무사 주간회의 기준 운영 EMR 직접 연결은 불가, **별도 복제
  EMR DB 필수**. 단, DBMS·라이선스·네트워크 ACL·허가된 Scope 및 군
  보안 절차는 미확정. 실접속 여부를 개발자가 임의로 판단하지 않는다.
