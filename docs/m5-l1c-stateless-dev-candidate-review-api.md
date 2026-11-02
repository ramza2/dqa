# M5-L1C — 개발용 LLM 연결 후보 서버 검토 API (Stateless)

> Draft PR #169는 #168(M5-L1B)의 순수 서버 후보 검증기에 의존한다.
> **설정 편집, LLM 호출, 인증/기관 승인, DB 기록 기능이 아니다.**
> 사용자 로컬 컴퓨터의 테스트 환경에 실제 의료정보를 입력하지 않는다.

## 엔드포인트

`POST /api/v1/admin/integration-settings/llm-candidate/review`

- 개발/테스트 환경(`APP_ENV=development|test`) 전용. 프로덕션에서는 기능 자체가 비활성이다.
- `CONNECTION_PROFILE_MANAGE` 관리자 권한 필요. 개발용 `dev_headers`는 보안 주체가 아니며 실서비스에 사용할 수 없다.
- 기본 OFF: `DQA_DEV_LLM_CANDIDATE_REVIEW_ENABLED=false`.
- **별도** HTTPS 정확한 URL pin: `DQA_DEV_LLM_CANDIDATE_REVIEW_ALLOWED_BASE_URL`. L0 메타데이터 접속 시험 설정과 혼용하지 않는다.
- 핀 주소가 없는 경우 기능 자체를 차단. 유효하지 않거나 HTTP인 pin도 차단.
- 본문은 `application/json`, 최대 4 KiB. 중복 JSON 키/잘못된 JSON/예상하지 않은 필드를 거부한다.
- 입력 스키마는 `docs/m5-l1b-server-candidate-policy.md` 참조. `timeoutSeconds`는 **정수**로 전송한다.
- 응답은 안전 판정 코드와 불변 `false` 플래그뿐. URL/모델 ID/API 키/원문을 반사하지 않는다.

## 상태와 오류

| 조건 | 결과 |
| --- | --- |
| 관리 권한이 있는 개발환경 + 명시된 flag/HTTPS pin | 판정 코드 `200` |
| flag OFF, production, URL pin 부재/형식 오류 | `409 LLM_CANDIDATE_REVIEW_DISABLED` (인증 통과 후) |
| 로그인/권한 부족 | 기존 Auth 제공자에 따른 `401`/`403`/`503` |
| JSON이 아닌 Content-Type | `415 JSON_BODY_REQUIRED` |
| 최대 요청 크기 초과 | `413 CANDIDATE_BODY_TOO_LARGE` |
| JSON 문법/입력 구조 오류 | `200 INVALID_FIELDS` |

관리자 GET `/api/v1/admin/integration-settings`에는 boolean `llm.candidate_review_available`를 추가한다. URL, API Key, 인증 정보는 여전히 비공개다.

## Docker Compose 개발 오버레이

`docker-compose.onprem.dev.yml`에서만 다음 환경변수를 backend로 전달한다.

```dotenv
DQA_DEV_LLM_CANDIDATE_REVIEW_ENABLED=false
DQA_DEV_LLM_CANDIDATE_REVIEW_ALLOWED_BASE_URL=
```

유지보수자가 격리 개발환경에서 시험할 때 명시적으로 enable/pin을 지정한다.
`docker-compose.onprem.yml` 프로덕션 Compose는 해당 값을 전달하지 않으며,
`APP_ENV=production` + `DQA_AUTH_PROVIDER=disabled` 경계를 유지한다.

## 비허용 범위와 후속

1. **네트워크 호출 없음:** 제출 URL로의 DNS, HTTP/HTTPS 요청, LLM 생성/GET 모델 목록 없음.
2. **비밀 저장/DB/활성화 없음:** 환경변수 변경, 자격증명 조회, 감사/DB 기록, 런타임 provider 선택 없음.
3. **기관 정보 반출 없음:** 원문 질의, 결과 rows, 환자자료 입력/전송 금지.
4. 실제 **운영 설정 편집**에는 기관 승인 + 운영 IdP + 비밀저장소 + URL SSRF 방어 + 감사가 필요하다.
5. 다음 프론트엔드 연결은 PR #167과 #168을 병합 후 독립 변경으로 진행하며, 브라우저에 서버가 받은 후보나 URL을 저장하지 않는다.

M4 CPU-first/LLM-free Query Template 조회·Preview·Oracle Mock SELECT의 실행 자격에는 어떠한 변경도 없다.
