# P30-B — 격리 PostgreSQL + 합성 Oracle Adapter Web/MCP ASGI 통합수용

> 기준: PR #109 (`test/p30a-web-mcp-offline-parity@5a6adf9`) 위에 쌓는 Draft PR.
> P30-A 92/92 서버 테스트는 검증됨. **P30-B 신규 서버 검증은 아직 미실행**.
> DEC-10 복제 EMR DB 실연결·DBA 승인·운영 전환과 분리한다.

## 1. 목적과 P30-A 대비 추가된 증빙

- P30-A: Web route 함수와 MCP application facade가 한 Query Execution
  서비스를 재사용하는지 오프라인 합성 검증 (HTTP/MCP ASGI, SQL DB 접근 없음).
- **P30-B**: TestClient를 통한 실제 `POST /api/v1/query-executions/execute`
  와 MCP JSON-RPC `POST /mcp/` (`demis.prepare_query` /
  `demis.execute_query`) 호출. 독립 Alembic PostgreSQL에 READY v2
  Catalog, 승인/활성화된 Template, 합성 읽기 전용 Profile, 실제
  `QueryAuditEvent`를 저장하고 독립 세션으로 재조회한다.
- **Oracle은 실DB가 아님**: `FakeReadOnlyDemisAdapter`만 테스트용
  의존성 주입하며, `oracle_demis_mock` Source 이름도 합성 fixture.
  Oracle listener/DEMIS/운영/복제 EMR DB와 실제 연결 없음.

## 2. 실제 테스트 시나리오

| ID | 시나리오 | 예상 체크 |
|---|---|---|
| P30B-01 | Web Execute와 MCP Prepare→Execute | 동일 Source/Template/Revision/Profile, Row limit=1 및 Truncated, timeout=8, 응답 일치(별도 감사ID 제외). 두 요청 각각 PostgreSQL에 4개 감사 이벤트 commit |
| P30B-02 | Prepare 뒤 Profile Disable | Web 409, MCP 사전 Eligibility 차단. Fake Oracle 미호출. Web `QUERY_REQUEST STARTED/DENIED` 기록, MCP 사전거부는 Execute 감사 없음 |
| P30B-03 | QUERY_OPERATE 없는 Viewer | 양쪽 403, 감사·Fake Oracle 조회 없음 |
| P30B-04 | Synthetic Timeout | Web 504/MCP ToolError, 양쪽 `QUERY_EXECUTION FAILED` 및 `TIMEOUT` 범주가 PostgreSQL에 영속. SQL/Secret/Host 비노출 |

각 테스트는 **기존 단일 서비스를 변경하지 않고** 제품 REST/MCP HTTP
라우터, Auth/RBAC, Token 발급/검증·재검증, SQL safety/Eligibility,
Audit commit, FakeReadOnlyDemisAdapter를 통과한다.

## 3. 강제 격리 및 파괴적 fixture 주의

기존 `backend/tests/conftest.py`의 `db_session`는 테스트 시작 때
`TRUNCATE ... RESTART IDENTITY CASCADE`를 실행한다. **일반 DQA DB
또는 `pytest backend/tests/...` 직접 호출 금지.**

새 `scripts/dqa-p30b-disposable-asgi-check.sh`는 다음 순서로만 실행한다.

1. 로컬 Unix Docker Context / 기존 Compose project `dqa-p30b-disposable`
   없음 / 고유 포트 `127.0.0.1:55447` 확인 (기존 DQA Compose와 별도).
2. `compose.p30b.disposable-pg.yaml`: `pgvector/pgvector:pg16`;
   `dqa_p30b_disposable`/`dqa_p30b_user` 등 고정 테스트 전용
   접속정보, Loopback Port, 512MB `tmpfs`, 영구 볼륨 없음.
3. Compose 컨테이너 ID, project label, Docker published Port 비교.
   독립 프로세스로 DB명·접속 사용자·기존 테이블 0개 확인 후 PostgreSQL
   DB COMMENT `DQA_P30B_DISPOSABLE_DB_V1` 마커 설정.
4. 확인된 DB에만 Alembic Upgrade Head.
   `backend/tests/p30b/conftest.py`는 테스트마다 DB 이름/사용자/Port/
   인증변수와 **DB COMMENT 마커**를 재검증한 뒤에만 기존
   `db_session` fixture가 실행되게 한다.
5. `backend/tests/p30b/test_web_mcp_isolated_asgi.py` 4개 합성 ASGI
   테스트만 수행. `pytest` 종료 후 전용 Compose Project를 자동 종료.
6. 최종 PASS 표식은 DB 정리 이후에만 출력. **실패 시 자동 머지 금지.**

**제한 사항:** 컨테이너 스냅샷/환경 변수를 악의적으로 변경하는 특권 사용자를
보호하는 보안 경계는 아니다. 현장 접근 허가·실서비스 IdP/정책,
RPO/RTO·복제 지연·Oracle read-only 권한·Clinical/FHIR 데이터 등
실 운영 항목은 여전히 검증하지 않는다.

## 4. 변경 파일 (신규 5개)

- `compose.p30b.disposable-pg.yaml` — 독립 Compose
- `backend/tests/p30b/conftest.py` — root fixture의 위험 DB 대상 강제 제어
- `backend/tests/p30b/test_web_mcp_isolated_asgi.py` — 4가지 ASGI/DB 통합 시나리오
- `scripts/dqa-p30b-disposable-asgi-check.sh` — 생명주기/사전점검/DB 격리/정리
- `docs/p30b-disposable-web-mcp-asgi-acceptance.md` — 이 문서

변경 없음: `backend/app/` 제품 코드, `frontend/`, 영구 migration
Revision, 운영 Compose/DQA DB, Oracle/Demis Runtime, Preflight/READY 정책.

## 5. 서버 Acceptance (미실행)

이 PR의 기준 브랜치는 **PR #109의 feature branch**이며, #109 자체는
Ready for review이지만 **미머지** 상태다. 먼저 #109를 머지한 뒤 P30-B의
base를 `main`으로 변경하거나, P30-B를 후속 PR로 리뷰할 수 있다.

```bash
cd ~/dqa && \
git fetch origin && \
git worktree add --detach /tmp/dqa-p30b-review \
  origin/test/p30b-disposable-pg-web-mcp-asgi && \
(
  cd /tmp/dqa-p30b-review && \
  bash scripts/dqa-p30b-disposable-asgi-check.sh
) && \
git -C /tmp/dqa-p30b-review diff --check 5a6adf9 HEAD && \
echo "DQA_P30B_REVIEW_PASS"
```

**예상:** 새 4 tests passed와 `DQA_P30B_ISOLATED_ASGI_PASS`,
`DQA_P30B_REVIEW_PASS`. 실제 서버 검증 결과가 확인되기 전 PASS
주장하지 않는다. P30-A 92건은 기검증 결과이며 이 실행에서 다시 수행하지
않는다 (테스트 DB 초기화 fixture의 범위 제어 목적).

### 정리/금지

- `docker compose -f docker-compose*.yml up` 또는 운영 서비스 restart 금지
- 영구 Volume 삭제, 운영 DB 마이그레이션/Truncate, 실 환자 정보/실 Oracle 사용 금지
- 원본 운영 EMR 직접 연결, 복제 Target 자동 허가, Controlled Write 금지
- 테스트 실패 시 **같은 Draft PR**에서만 수정, 서버 검증 반복
- **사용자 명시적 요청 이전 PR #109 및 본 PR 머지 금지**
