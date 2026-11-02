# M5-L1B — 서버 측 LLM 연결 후보 정책 검증

## 목적과 범위

M5-L1A 브라우저 메모리 초안(별도 Draft PR #167)에서 전달할 수 있는 **비신뢰 연결 후보**를 서버 측 순수 함수로 검증한다. 실제 연결을 설정하거나 테스트하는 기능이 아니다.

- 위치: `backend/app/services/llm_connection_candidate.py`
- 진입점: `assess_llm_connection_candidate(payload, allowed_base_urls=())`
- 실수로 권한을 열지 않도록 기본 URL 허용 목록은 **비어 있음(거부)**.
- 서버 설정/DB/시크릿 변경, 네트워크/DNS/HTTP 요청, 모델 추론, 임상 데이터 처리, 감사 로그 생성을 **하지 않음**.
- 이번 변경은 호출 가능한 HTTP API 또는 관리자 화면 저장 기능을 추가하지 않음.

## 입력

| 필드 | 허용값 | 의미 |
| --- | --- | --- |
| `name` | 1~100자의 비어 있지 않은 식별자 | 후보 표시명 |
| `environment` | `modelops` / `snuh_ai` / `self_hosted` / `other` | 어디에 배치된 모델인지 |
| `protocol` | `openai_compatible` / `custom_api` | 어떤 호출 규격인지 |
| `baseUrl` | 1~2048자, 정형 HTTPS URL | 후보 엔드포인트 |
| `modelId` | 1~200자의 모델 식별자 | 공급자 종속 모델명 |
| `timeoutSeconds` | 정수 1~300, 기본 60 | 후보 요청 시간제한 |

`environment`는 모델 공급/배치 형태이며 `protocol`과 독립적이다. 예를 들어 사내 ModelOps와 SNUH.AI는 각각 OpenAI-compatible 또는 향후 기관별 어댑터를 쓸 수 있다. 알 수 없는 추가 필드(특히 API 키, 프롬프트, 실행 허용 플래그)는 거부한다.

## 판정 코드

| 코드 | 의미 |
| --- | --- |
| `INVALID_FIELDS` | 필수 입력 또는 형식 오류/허용하지 않은 필드 |
| `INSECURE_ENDPOINT` | HTTPS가 아닌 URL |
| `INVALID_ENDPOINT` | 인증정보·query·fragment·제어문자·경로 혼동 등 URL 형식 위험 |
| `UNSUPPORTED_ADAPTER` | 지정 프로토콜용 어댑터 미구현 |
| `ENDPOINT_NOT_ALLOWLISTED` | 운영자가 지정한 URL의 정확한 일치가 없음 |
| `POLICY_REVIEW_REQUIRED` | URL 형식/허용 목록은 맞지만 운영 정책 심사가 필요 |

모든 응답은 판정 코드와 `false`인 보안 상태 플래그만 포함한다. 제출한 호스트, 모델 ID, 개인정보, 키 또는 URL은 반환하지 않는다. `POLICY_REVIEW_REQUIRED`도 사용/접속 허용이 **아니다**.

## 이후 활성화 단계의 선결 조건

1. 운영 관리자 IdP/역할 인증과 CSRF 대응 등 신뢰할 수 있는 쓰기 권한 확인. `dev_headers`는 불가.
2. 시크릿 저장소, 변경 승인/이력 및 감사 로그.
3. 대상 기관의 네트워크·데이터 반출 승인 및 URL/호스트 허용 정책. 실 호출 시에는 DNS 재바인딩, 내부 IP 접근, 리다이렉트, 프록시 등을 별도 방어.
4. 제공자별 어댑터 구현 및 모의/비임상 데이터로 검증.
5. CPU 기반 LLM-free 템플릿 검색/Preview/Oracle Mock SELECT 경로는 항상 독립적으로 유지.

이 단계는 기존 `llm_connection_probe`의 개발용 **허용된 메타데이터 GET** 범위를 확대하지 않는다. 연결 테스트 프로브 또는 활성 런타임에 후보를 자동으로 전달하면 안 된다.
