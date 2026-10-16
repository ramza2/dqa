# P30-A — Web/MCP 조회 실행·감사 동등성 무DB 통합 회귀

> 기준 `main@93f151e` · Phase 30-A (내부 개발 합성 테스트).
> 실제 DEMIS, 군/DBA 접근 승인, 운영복제 EMR, PostgreSQL 영속 Audit, HTTP/MCP ASGI
> 전송 E2E 또는 Oracle 실연결을 검증하지 않는다.

## 1. 선정 사유

- [Phase 30 Roadmap](roadmap.md): Web/MCP 동등성, 보안·Adversarial, Oracle Mock
  통합수용이 후속 과제로 명시되어 있다.
- [U-02 통합 인수 문서](u02-integration-acceptance-handoff.md):
  실제 DEMIS, FHIR/SNUH.AI 외부 ICD, 운영 Cutover는 여전히 외부 의사결정 대상이다.
- 기존 Web `POST /api/v1/query-executions/execute`와 MCP
  `demis.execute_query`는 둘 다 `app.services.query_execution.execute_query`
  를 재사용하는 설계. 실제로 분리된 구현/감사가 생기지 않도록 경계 회귀 추가가 유용하다.
- **중요 테스트 안전 주의:** 기존 `backend/tests/conftest.py`의 `db_session`
  fixture는 실제 지정 DB의 여러 테이블에 `TRUNCATE ... CASCADE`를 수행한다.
  따라서 이 단계는 해당 fixture와 기존 DB 기반 테스트를 **전혀 호출하지 않고**,
  운영 DQA DB에 영향을 주지 않는 순수 합성 테스트로 분리했다.

## 2. 이번 작업 범위

| 시나리오 | Web API 함수 경계 | MCP Facade 경계 | 일관성/차이 |
|---|---|---|---|
| 승인 Template 기반 정상 SELECT | 실제 QueryExecution Service 호출 | 실제 AES-GCM 발급·검증된 짧은 수명 Token → eligibility 재검증 → **같은 서비스** | 바인딩 Target·Row Limit·Timeout·조회 Row 및 Audit 4단계 계약 동등 |
| DEMIS Adapter 타임아웃 | HTTP 504 sanitized error | MCP ToolError sanitized error | `QUERY_EXECUTION FAILED`, 동일 TIMEOUT category, DB 정보·SQL·Secret 비노출 |
| 감사기록 장애 | HTTP 503 | MCP ToolError | `QUERY_EXECUTION STARTED` 기록 실패 시 **Credential Resolver 및 Adapter 미호출** |
| Catalog 변경 | HTTP 409 + Request DENIED 감사 | MCP Token 사전 재검증 후 ToolError 및 **실행 단계 진입 전 거부** | 결괏값/실제 DB 조회 모두 없음. MCP 사전 단계 거부는 별도 실행 감사 이벤트 없음 (의도된 차이) |

- 테스트가 검증하는 것은 **기존 코드의 실제 두 애플리케이션 진입점**을 통한 공유
  서비스 호출이며, 별도 모방용 Query Core를 만들지 않는다.
- 요청/결과값은 `synthetic_*`, `.invalid`와 가상 환자키 등 **합성값**.
- `FakeReadOnlyDemisAdapter`는 테스트에서만 주입; Production Adapter Factory,
  실제 Credential Resolver, LLM, Oracle Socket, PostgreSQL 접속 금지.
- 감사 이벤트는 메모리 콜렉터로만 확인한다. **Durable PostgreSQL Audit
  commit/rollback/재기동 복구는 이 단계에서 검증하지 않는다.**
- 기존 R-01-A/B/C/D 합성 회귀도 함께 실행하되 DEC-10 제한은 변경하지 않는다.

## 3. 변경 파일

- `backend/tests/test_p30a_web_mcp_offline_execution_parity.py`:
  총 4개 테스트. 실제 QueryExecution 서비스 및 Token 암호화를 유지하면서
  Web/MCP Entry 차이와 Fail-closed 검증.
- `scripts/dqa-p30a-offline-web-mcp-parity-check.sh`:
  위 4개와 기존 R-01-A~D 88개, **총 92개 예상** (서버 검증 전 미확정).
- 이 문서. 기존 `backend/app/`, API, Frontend, DB/Alembic, Docker, `.env`
  변경 **0개**.

## 4. 서버 Acceptance (미실행)

```bash
cd ~/dqa && \
git fetch origin && \
git worktree add --detach /tmp/dqa-p30a-review \
  origin/test/p30a-web-mcp-offline-parity && \
(
  cd /tmp/dqa-p30a-review && \
  bash scripts/dqa-p30a-offline-web-mcp-parity-check.sh
) && \
git -C /tmp/dqa-p30a-review diff --check 93f151e HEAD && \
echo "DQA_P30A_REVIEW_PASS"
```

**예상:** 92 tests passed 및 두 표식
`DQA_P30A_OFFLINE_PARITY_PASS`, `DQA_P30A_REVIEW_PASS`.
이는 아직 실행 전 기대치이며 실제 테스트 결과로만 통과를 선언한다.
경고·실패 시 본 Draft PR에서 필요한 부분만 수정 후 재검증.

## 5. 완료 후 후속 (별도 PR, 승인 범위 주의)

1. **P30-B — 격리 DB 기반 Web/MCP/Oracle Mock ASGI 통합시험**:
   기존 서버의 DQA/PostgreSQL 테스트 fixture를 그대로 호출하는 대신,
   오직 **일회성 Compose 프로젝트 + 빈 테스트 DB + 고정 루프백 포트**
   를 검증 후 마이그레이션·실행한다. 승인 템플릿/토큰/감사영속화,
   Source 변경 시 조회 및 실행 거부, Web/MCP 실제 전송 동등성을 검증.
2. **P30-C — Data Discovery Revision/Source 경계 회귀**:
   검색 모드별 동일 Gold Fixture 결과, Index 상태 및 stale 응답 오염 방지.
3. 군·의료정보체계과의 실제 복제 DB 구성·라이선스·접근 승인 결정(DEC-10) 전에는
   실제 Target 연결 기능, 운영 EMR 우회, 임상데이터 처리 추가 금지.

P30-A 자체는 운영접근 승인, Cutover, 외부 ICD, Schema READY·Preflight, Controlled Write
검증에 영향을 주지 않는다. **Draft PR만 제출하며 사용자 승인 전 병합 금지**.
