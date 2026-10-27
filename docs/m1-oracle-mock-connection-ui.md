# M1 — Oracle Mock DB Target 등록·읽기 전용 연결 검사·활성화 UI

> Status: Draft PR / **isolated code tests PASS**, live Oracle Mock UI acceptance **not executed**.  
> Baseline: `main@6e3f135`. **Synthetic Oracle Mock only**, not DEMIS Oracle 19c acceptance.

## Goal

DQA Connection Profiles portal에서 개발용 `demis-oracle-test:1521/FREEPDB1`
하나에 한하여 다음 작업을 순서대로 수행한다.

1. "Oracle Mock 대상 준비" (기존 프로필이면 고정 Target 규격 검증 후 반환, 없으면 비활성 프로필 생성).
2. "읽기 전용 연결 검사": **비활성 상태에서도** 일시적 `enabled=True` Snapshot에 한하여 서버가 읽기 전용 거래/`SELECT 1 FROM DUAL`을 시도. 영속 프로필 상태는 변경하지 않음.
3. 검사가 `SUCCEEDED/live_connection_tested/reachable/read_only` 모두 True일 때만 "연결 검사 후 활성화" 제공. 서버에서 **다시** live probe하여 성공해야 DB 프로필 `enabled=true` 저장.
4. 일반 Source/Environment/Profile은 기존 metadata-only 화면 유지. `/enable`, `/test-connection`을 UI에서 직접 호출하지 않음. DEMIS 운영 Source에 영향을 주지 않음.

## Strict opt-in and security

- New flag: `DQA_DEV_ORACLE_MOCK_ACTIONS_ENABLED=false` default.
- Server requires ALL: `APP_ENV=development/test`, `DQA_AUTH_PROVIDER=dev_headers`, flag=true, `CONNECTION_PROFILE_MANAGE` actor, exact Target values:
  - `source_name=oracle_demis_mock`, `environment=development`, `dbms_type=oracle`
  - `host=demis-oracle-test`, `port=1521`, `database_name=FREEPDB1`, `username=DEMIS_RO`, `credential_secret_ref=env:DEMIS_SECRET_ORACLE_PASSWORD`.
- New endpoints: `GET /api/v1/connection-profiles/oracle-mock-capability`, `POST /oracle-mock-profile`, `POST /{id}/oracle-mock-test`, `POST /{id}/oracle-mock-enable` (all below Connection Profile API prefix).
- Target fields checked **server-side** before resolving any credentials or live probes. Existing REST generic profile routes unchanged. No requests may override host/user/secret; single fixed Mock only.
- No credential/password displayed in UI or written to source code; host/username are existing non-secret metadata. Frontend masks the reference already returned in existing profile API.
- Probe/read-only success is **not** clinical data access authorization, DBA security confirmation, official replica-source acceptance, or Oracle 19c parity. No schema analysis, clinical Insert, migration, production deployment in this step.
- Current Oracle Mock image `container-registry.oracle.com/database/free:latest-lite` is not evidence of Oracle 19c. DEMIS core DB 19c is a separate externally reported fact.

## 2026-10-23 executed code checks (user terminal evidence)

`/tmp/dqa-m1-134-review` was created as a detached worktree at `9e157b0`. User reported:

| Command / evidence | Result |
| --- | --- |
| `~/dqa/.venv/bin/python -m pytest -q tests/test_m1_oracle_mock_actions.py` | **18 passed** (Starlette/TestClient deprecation warning, not failure) |
| `npm ci` | Dependencies installed; audit **1 high-severity vulnerability** (needs `npm audit` dependency identification prior to deployment) |
| `npm run build` | **PASS** (TypeScript `tsc -b` + Vite) |
| `npm run lint` | **PASS** |
| `npm test -- --run src/test/OracleMockActions.test.tsx src/test/ConnectionProfiles.test.tsx` | **12 passed** (6 + 6) |
| Final marker | `M1_CODE_REVIEW_PASS` |

These results establish only targeted application code checks, not current running Docker revision, actual Oracle Mock connectivity, profile persistence, or acceptance of future Oracle 19c. No CI run status should be inferred.

**Model-optional direction:** This M1 code does **not** need LLM/Embedding. For M2–M6, see [CPU-first / no-LLM architecture decision](https://github.com/ramza2/dqa/blob/docs/u01r2-oracle-mock-e2e-plan/docs/dqa-cpu-first-model-optional-architecture.md): keyword/manual baseline, approved CPU embeddings optional, generative SQL creation deferred. This does not change M1 PR scope.

## Existing service reuse

Reuses:
- `services.connection_profile.create_connection_profile`, `enable_connection_profile`;
- existing `ConnectionProfile` persistence and read-only Oracle Adapter `probe_readonly`;
- `ConnectionProfilePortal` metadata UI with additional independent `OracleMockActions` guarded component.
- New server config flag goes into `docker-compose.onprem.dev.yml` **only**; `DQA_DEV_FRONTEND_ROLES` can be set to `administrator` **only in an isolated dev project** to use manager UI. Default remains `query_operator`.

## Development test plan — no operational DQA or DEMIS

Run in a **detached temporary worktree**. Only use tests that do **not** call root `db_session`/`db_client` fixtures because those can TRUNCATE database tables.

~~~bash
cd ~/dqa
git fetch origin
git worktree add --detach /tmp/dqa-m1-review origin/feature/m1-oracle-mock-profile-ui
(
  cd /tmp/dqa-m1-review/backend
  ~/dqa/.venv/bin/python -m pytest -q tests/test_m1_oracle_mock_actions.py
)
(
  cd /tmp/dqa-m1-review/frontend
  npm ci
  npm run build
  npm run lint
  npm test -- --run src/test/OracleMockActions.test.tsx src/test/ConnectionProfiles.test.tsx
)
~~~

No Docker Compose, no `alembic upgrade`, no production `pytest`, no probes to current Mock or operational data in this test plan. Actual Mock connectivity/UI must later be tested in an independently configured Compose project/volume/port after explicit separate approval.

### Negative cases

- flag OFF, prod/staging, production auth → no tool visibility/calls;
- read-only mismatch or failed live probe → profile remains disabled;
- profile host/service/secret reference/source/environment changed → blocked before credentials;
- non-admin → 403 before probe;
- stale selection/response, duplicate clicks, ref/host/SQL error fields → no unauthorized enable or sensitive output;
- no automatic production/real DEMIS connection/activation.

### Acceptance limitation

GitHub commit and static review only until the above commands run. Test code presence ≠ test PASS. Old `dqa-onprem` frontend/backend continue unaffected until an explicitly approved, isolated development run.

## Later: MCPFlow inter-project combined testing

After M4 Web Oracle Mock data retrieval and M5 DQA MCP client E2E are complete, add **M6 MCPFlow ↔ DQA integration**:
- register DQA 5 existing MCP Tools as external tool server in MCPFlow only in approved isolated development network;
- pass clinical-context-free synthetic `source_name/template_id/version_id/parameters`; validate agent tool selection, `prepare_query`/read-only `execute_query`, permission denials, trace/audit comparison and errors;
- do not widen the current loopback MCP ingress solely for convenience. Design isolated gateway/transport and delegated actor authorization separately; **no real DEMIS, patient data or production MCPFlow project mutations**.
