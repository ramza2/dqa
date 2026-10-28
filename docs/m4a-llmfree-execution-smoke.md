# M4-A — LLM-free 승인 템플릿 조회 E2E 검증 체계 (2026-10-28)

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
| `scripts/m4a-test-isolated.sh` | 일회용 PostgreSQL + 계약 테스트 + Oracle 준비 여부 판정 |
| `scripts/dqa-m4a-llmfree-smoke.sh` | 실행 중인 스택 대상 LLM-free HTTP smoke |

## Oracle Mock 판정
- 미준비(시크릿 없음 / TCP 불가 / 스택 없음): **`M4A_ORACLE_MOCK_BLOCKED`**
  또는 smoke exit code `2`. **PASS로 취급 금지**.
- 준비됨: smoke가 SELECT 결과 건수 + durable audit lifecycle + NAMES_ONLY를 검증.
  행 데이터·비밀번호는 출력하지 않음.

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
# 격리 계약 테스트 (Docker + 빈 5432 필요)
bash scripts/m4a-test-isolated.sh

# 라이브 Mock HTTP smoke (스택·시크릿·Mock TCP 필요)
DEMIS_SECRET_ORACLE_PASSWORD=... bash scripts/dqa-m4a-llmfree-smoke.sh
```
