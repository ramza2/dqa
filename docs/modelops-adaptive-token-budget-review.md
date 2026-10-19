# DQA — ModelOps Adaptive Token Budgeting 적용 검토 및 최소 안전 개선

> 2026-10-19, 검토 기준 `ramza2/dqa@6ae26e8` (S-05-K 머지 후).
> ModelOps 계약 출처: `ramza2/ai-modelops/docs/api/08-gateway-model-capabilities.md`
> 및 `gateway/app/api/openai_routes.py`. 외부 Gateway 실시간 호출·응답 검증은 이 검토에서 수행하지 않았다.

## 1. 현재 DQA의 실제 LLM 호출 범위

DQA는 **LLM으로 임의 SQL을 생성하지 않는다**. 승인된 Query Template만 실행하고,
Structured Query Plan → SQL 변환은 `app/domain/query_compiler.py`의 결정적 컴파일러를 거친다.
LLM 관련 호출은 다음 두 경로뿐이다.

| 경로 | 파일 | LLM에 전달하는 입력 | 현재 제한 | 출력 상한 |
| --- | --- | --- | --- | --- |
| Query Template 추천 | `services/template_recommendation.py` | 승인·활성 호환 Template의 메타데이터와 매칭된 검색어. 원본 NL 요청/SQL 원문/쿼리 결과 행 제외 | 상위 최대 20 후보, 사용자 JSON 최대 12,000자, 초과 시 후보 순위순 축소, 최후 실패 차단 | `max_tokens=512` |
| 파라미터 추출 | `services/parameter_extraction.py` | 승인된 템플릿의 선언된 파라미터와 요청 텍스트. 원본 요청 전송은 기술·외부 승인 두 게이트 필요 | 요청 길이 최대 2,000자, 사용자 JSON 최대 12,000자, 초과 시 전송 전 실패 | `max_tokens=1024` |

쿼리 결과 행은 LLM 전송 금지. SQL 생성, 임상 환자 조회, LLM Tool Calling/Streaming 경로는 이 코드 범위에 없다.
`LLM_ENABLE_THINKING`은 `chat_template_kwargs.enable_thinking`으로 기존대로 전달되며,
별도의 `thinking_token_budget`은 현재 DQA 호출 코드에 없다.

## 2. 위험 및 이번에 필요한 최소 개선

- **Context Window 하드코딩:** 실제 프로바이더에 `context_window=8192`가 설정되어 있지는 않지만
  `schemas/recommendation.py`의 12,000자 제한 설명이 8192급 런타임을 가정한다.
  문자 예산은 Chat Template, 한국어 토큰 분할, Thinking, 메시지 오버헤드를 포함하지 않아 Context 적합성을 증명하지 못한다.
- **정확한 프롬프트 토큰 계측 미구현:** DQA는 서버와 동등한 Tokenizer의 `prompt_tokens` 사전 측정 경로가 없다.
  결과의 optional `usage.prompt_tokens`는 사후 지표일 뿐 사전 Budget 근거가 아니다.
- **출력 예약:** Phase별 고정 `max_tokens`(512/1024)가 이미 명시되어 있다.
  VERIFIED Context와 실측 Prompt Token을 함께 사용한 동적 재계산은 미구현이다.
- **`finish_reason=length` 오류:** 기존 LLM 어댑터는 JSON 스키마 검사 후 `length`를
  그대로 성공 결과에 포함했다. JSON이 우연히 완결되었더라도 생략·잘림 가능성이 있으므로
  **`LLM_PROVIDER_STRUCTURED_OUTPUT_INVALID`로 fail-closed**하도록 제한된 수정을 한다.
  기존 서비스의 Error Mapping이 유지되며 임의 SQL 실행 권한이나 자동 재요청을 추가하지 않는다.

## 3. ModelOps VERIFIED Capability 연동 — 별도 최소 후속 작업 조건

ModelOps 제공: `GET /v1/models/{alias}/capabilities`. 정상 검증 예시는
`status=VERIFIED`, 양의 정수 `context_window`, `source=CURRENT_CONTAINER_ARGV`,
`deployment_id`, `route_id`, `routing_version`, `observed_at`.
현재 Runtime 컨테이너의 명시적인 `--max-model-len`을 증거로 사용하며,
요청의 Chat+Completion 총 Context를 의미한다. Registry 값이나 모델 이름으로 추정하지 않는다.

1. **이후 실제 대량 입력/Context 초과가 관측된 추천·파라미터 추출 경로에만** 선택적으로 적용.
   기존 12,000자 상한 및 사전 보안·데이터 반출 게이트는 그대로 둔다.
2. 요청/Phase 직전 VERIFIED 결과를 읽고 `deployment_id`·`routing_version` 변화 시 다시
   조회·재계산. UNKNOWN, null, 503, 오래된 응답은 **추정 Context로 대체하지 않고 차단/축소**.
3. Gateway Alias와 **동일 serving runtime/tokenizer의 Chat 템플릿·Thinking 설정을 반영한
   사전 Prompt Token 계측 경로**를 확인한 후에만 토큰 기반 계산을 활성화한다.
   현재 ModelOps 문서에는 Gateway의 공개 `/tokenize` 계약이 없다. 내부 upstream
   `/tokenize`를 DQA에서 직접 우회 호출하거나 글자수÷상수 같은 근사치를
   검증된 실측값인 것처럼 취급하지 않는다.
4. 안전 예산: `prompt_tokens + phase_output_tokens + template/thinking_safety_margin <= context_window`.
   추천·추출 출력 예약 비율은 각 결과 스키마를 기준으로 독립 결정. 공간 부족 시
   추천은 가장 낮은 후보부터 축소, 추출은 값/파라미터를 임의 삭제하지 않고 명시적 거부.
5. `finish_reason=length`는 현재 PR의 차단 정책을 유지.
   임의 출력 증대/자동 재생성은 승인·출처/중복 호출을 검토한 후 별도로 결정한다.
6. Gateway Route 교체가 Capability 확인과 Completion 전송 사이에서 발생할 수 있어,
   재조회만으로 요청 처리 Route를 원자적으로 고정했다고 주장하지 않는다.
   추후 Gateway의 Route/Deployment pinning 계약 여부를 검증해야 한다.

## 4. 이번 PR 범위 / 수용 조건

- 변경: `backend/app/adapters/llm/openai_compatible.py`,
  `backend/tests/test_llm_provider.py`, 이 문서.
- 동작: `finish_reason=length`에서 **완결된 유효 JSON / 미완결 JSON 모두 오류**.
  `finish_reason=stop` 및 기존 Usage, Thinking, HTTP/timeout, 구조화 응답 처리 유지.
- 변경 없음: 공용 ModelOps Runtime/GPU, Gateway 배포/설정, DQA 환경변수, DB/Alembic,
  Query Template 정책, SQL 안전성, DEMIS 접근, PHI 반출, MCP, 임상 쓰기, Frontend, Docker.
- 테스트는 **서버 별도 Worktree에서 pytest**로 수용한다. 서버 PASS 이전에는 테스트 완료 주장 금지.

### 서버 수용 명령 (실행 대기)

```bash
cd ~/dqa && git fetch origin && \
git worktree add --detach /tmp/dqa-modelops-llm-review \
  origin/fix/llm-length-finish-reason-guard && \
(
  cd /tmp/dqa-modelops-llm-review/backend && \
  python3 -m venv .venv && \
  .venv/bin/pip install -e '.[dev]' && \
  .venv/bin/python -m pytest -q \
    tests/test_llm_provider.py \
    tests/test_template_recommendation.py \
    tests/test_parameter_extraction.py \
    tests/test_llm_egress_policy.py
) && \
git -C /tmp/dqa-modelops-llm-review diff --check 6ae26e8 HEAD && \
echo DQA_LLM_LENGTH_REVIEW_PASS
```

개발 서버 패키지 설치가 제한되는 경우 이 명령을 강제로 반복하지 말고 기존 Backend 개발용 venv에서
동일 테스트만 수행하며, Worktree의 운영/실 DEMIS 데이터는 접근하지 않는다.

사용자 명시 승인 전 `main` Merge/운영 배포 금지.
