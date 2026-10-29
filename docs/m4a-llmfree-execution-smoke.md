# M4-A — LLM-free 승인 템플릿 조회 E2E 검증 체계 (2026-10-29)

## 목적
Gap Audit 이후, 기존 Query Execution 엔진을 재사용해 **LLM 없이**
`manual-templates → form → preview → execute → audit` 경로를
격리 환경에서 검증할 수 있게 한다.

## 재사용
- M3-A `GET /api/v1/query-executions/manual-templates`
- 기존 form / preview / execute / audit-events API
- `OracleReadOnlyDemisAdapter` 및 durable audit (앱 코드 변경 없음)
- 기존 `scripts/dqa-oracle-mock-smoke.sh` (LLM recommend 경로) **호환 유지**

## 추가물
| 경로 | 역할 |
|------|------|
| `backend/tests/test_m4a_llmfree_execution_contract.py` | 합성 시드 + Fake adapter API 계약 / 차단 경로 |
| `backend/tests/test_m4a_script_safety.py` | 하네스/스모크 스크립트 정적 안전 검사 (DB/네트워크 없음) |
| `scripts/m4a-test-isolated.sh` | 일회용 PostgreSQL + 계약/정적 테스트 + Mock TCP 별도 판정 |
| `scripts/dqa-m4a-llmfree-smoke.sh` | 허용된 개발용 Oracle Mock 대상 LLM-free HTTP Live E2E |

## 판정 레이블 (혼동 금지)
| 레이블 | 의미 | 출력 위치 |
|--------|------|-----------|
| `API_CONTRACT=PASS` / `M4A_API_CONTRACT_PASS` | Fake adapter 계약·정적 검사 통과 | 격리 하네스 |
| `ORACLE_MOCK_REACHABLE=yes` | allowlisted Mock TCP만 열림 | 격리 하네스 또는 smoke 시작 |
| `LIVE_E2E=NOT_RUN` | 격리 하네스는 Live E2E를 돌리지 않음 | 격리 하네스 (항상) |
| `LIVE_E2E=PASS` | manual→form→preview→execute→audit 전체 성공 | live smoke만 |
| `M4A_ORACLE_MOCK_BLOCKED` / exit `2` | Mock/허용 조건 불충족 — **PASS 아님** | 둘 다 |
| `M4A_ISOLATED_HARNESS_BLOCKED` / exit `2` | Docker/포트/인터프리터 등 격리 전제 실패 | 격리 하네스 |

**금지:** Oracle TCP reachable만으로 `M4A_REVIEW_PASS` 또는 `LIVE_E2E=PASS`를 출력하지 않는다.
격리 하네스의 `git diff --check` 실패는 무시하지 않는다 (`|| true` 금지).

## Live smoke 허용 조건 (전부 충족, 불확실하면 BLOCKED)
1. `DQA_M4A_ALLOW_LIVE_ORACLE_MOCK=1` 명시 opt-in
2. Mock 엔드포인트 **오직** `demis-oracle-test:1521` (allowlist; 그 외 BLOCKED)
3. Source `oracle_demis_mock`, environment `development`
4. `APP_ENV` = `development`|`test`, `DQA_AUTH_PROVIDER` = `dev_headers`
5. `DEMIS_SECRET_ORACLE_PASSWORD` 존재 (값은 절대 출력하지 않음)
6. host/port는 안전 charset 검증 후 `os.environ`으로만 Python에 전달 (셸/Python 삽입 금지)

실 DEMIS·운영 Oracle·비개발 인증 모드에서는 실행하지 않는다.

## 오류·출력 안전
- HTTP 오류 시 상태 코드만 보고하고 응답 본문을 출력하지 않는다.
- 실행 결과 행·환자 식별자·시크릿·감사 payload 값을 stdout/stderr에 넣지 않는다.
- audit는 `NAMES_ONLY` 및 값 미포함을 검증한다.

## 격리 규칙
- `tests/conftest.py`는 `localhost:5432/dqa`를 TRUNCATE한다.
- `m4a-test-isolated.sh`는 **포트 5432가 비어 있을 때만** tmpfs Docker
  PostgreSQL을 기동한다. 기존/공용/운영 DB가 점유 중이면
  `M4A_ISOLATED_HARNESS_BLOCKED`로 거부한다.
- 실 DEMIS, 운영 배포, Alembic, LLM, MCP 변경 없음.

## 차단 경로 (계약 테스트)
- 비인증/권한 없음
- 미승인(DRAFT) 템플릿 — manual 목록 제외 + preview 409
- Catalog fingerprint mismatch — manual 제외 + preview 409
- Adapter 실행 실패 — FAILED audit 기록, 비밀 미노출

## 실행 예
```bash
# 격리 계약 + 정적 안전 검사 (Docker + 빈 5432 필요)
# → API_CONTRACT / ORACLE_MOCK_REACHABLE / LIVE_E2E=NOT_RUN
bash scripts/m4a-test-isolated.sh

# 라이브 Mock HTTP smoke (명시 opt-in + 스택·시크릿·allowlisted Mock 필요)
DQA_M4A_ALLOW_LIVE_ORACLE_MOCK=1 \
  DEMIS_SECRET_ORACLE_PASSWORD=... \
  bash scripts/dqa-m4a-llmfree-smoke.sh
```
