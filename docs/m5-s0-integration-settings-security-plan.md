# M5-S0 — 관리자 연계 설정 현황과 서비스 인증 설계 (2026-10-30)

> 개발용 설계/구현 착수 기록. 실제 군/DEMIS/FHIR/SNUH.AI 네트워크, IdP, 계약, 권한의 운영 승인을 뜻하지 않는다.
> **핵심 조회 경로는 CPU-first / LLM-free**이며 승인된 수동 Query Template + 결정적 SELECT 검증으로 계속 작동해야 한다.

## 1. 단계별 개발 범위

| 단계 | 작업 | 이번 PR | 후속 구현의 필수 승인/조건 |
| --- | --- | --- | --- |
| M5-S0 | 관리자 전용 LLM·서비스 인증 **상태 조회** UI 및 GET API. URL/비밀값 무노출, 기본 차단 | 코드 포함 | 개발 인증에서만 확인. 운영 로그인은 미구현 |
| M5-S1A | 외부 서비스 클라이언트 **등록·정책 초안·폐기·감사** API/DB (항상 DRAFT/REVOKED, **인증 불가**) | 코드 포함, 격리 PostgreSQL 회귀 22개 통과 | M5-S1B 및 M5-S2 이전에는 권한 적용 금지 |
| M5-S1B | 관리자 전용 DRAFT/REVOKED 정책 초안 UI(등록·수정·폐기·감사 조회); **정식 승인 워크플로는 미구현** | 초안 UI 포함 | 실서비스 접근 승인·기관 역할/계약 확정 전 활성화 금지 |
| M5-S2 | 실제 **서비스 인증** (승인된 OAuth2 client credentials/mTLS/OIDC 토큰 검증 방식 우선 검토; 기관이 허용한 경우 서비스키 방식), 정책 강제, 재발급/만료/회수 | 미구현 | TLS/신뢰 프록시/비밀저장소/키 수명 및 사고 대응 정책 승인 |
| M5-L1 | 관리자 전용 LLM **연결 설정 편집** UI·API(엔드포인트/모델/자격증명 참조/활성화), 비밀키 마스킹·회전·감사 | 미구현 | 비밀저장소, LLM endpoint allowlist, 접근권한 및 정책 확정 |
| M5-L2 | metadata-only 연결 시험, 선택적 LLM 사용 정책, 비정상 연결·정보 유출 테스트 | 미구현 | 모델/운영 설치 승인, 데이터 반출·내부망 정책 승인 |

**현재 M5-S0 상태 조회는 설정 변경, 서비스키 발급, 토큰 인증, IP 허용, LLM 연결시험, 임상정보 전송 기능이 아니다.**

## 2. 외부 시스템 서비스 클라이언트 모델

FHIR 변환 시스템, SNUH.AI 및 기타 서버는 **사용자 로그인과 분리된 서비스 주체**로 식별한다.
동일 기관에서 여러 서비스를 호출하더라도 별도 client ID, 소유 기관, 목적, 담당자, 승인 근거, 만료일을 관리한다.

관리 콘솔의 향후 필드:

- 서비스명, client ID, 소유기관/담당자, 환경(개발/운영), 사용 상태(대기/활성/정지/폐기)
- 인증 방식(승인된 OAuth2/mTLS 또는 관리형 서비스키), **원문 키를 재조회할 수 없는 비밀 참조/해시·키 prefix**만 표시
- 허용 API, HTTP method, MCP tool 별 scope, 허용 source/Schema/Query Template 범위, 요청당 조회 상한
- IP/CIDR allowlist(별도 방어선), 제한 시간대/호출량, 유효기간 및 마지막 사용시각
- 신규 등록·허가·갱신·키 교체·정지·폐기·정책 변경 이력과 담당자

강제 규칙:

1. **서비스키 또는 검증 가능한 클라이언트 자격증명이 인증 주체**이며 IP 일치는 추가 검사에 불과하다. IP만으로 호출자 신원을 인정하지 않는다.
2. 서버는 요청의 client ID, 비밀검증 또는 승인된 서명·토큰, 만료/폐기 상태, 최소 scope, IP 정책, 대상 리소스 권한을 **요청마다** 검증한다. 사용자 제공 `X-Role`, `X-User-Id`, `X-Forwarded-For`를 임의 신뢰하지 않는다.
3. 역방향 프록시 뒤의 원 IP는 **승인된 프록시의 접속과 전달 설정**을 검증한 후에만 사용한다. 프록시 경계를 모르면 접속을 차단한다.
4. 서비스키 허용 시 고엔트로피 무작위 발급, 표시 1회, 서버 저장은 원문이 아닌 강한 해시/검증용 구조, 유효기간·폐기·중첩 갱신, 접근 감사, 로그 마스킹, TLS 필수. 비밀키는 일반 설정/프로필 테이블의 평문으로 보관하지 않는다.
5. 기본 정책은 deny-all. 보안상 허용된 API·Tool·범위만 별도로 승인한다. 필드 단위·환자/Encounter 단위 접근은 연계기관의 실제 계약과 권한 모델이 확정되기 전까지 사용 가능하다고 표시하지 않는다.
6. MCP 전용 헤더 bypass나 서비스키만 확인하고 임의 SQL을 실행하는 예외는 금지한다. 기존 SELECT-only validator, Query Template 승인, 감사, 조회 제한이 Web/REST/MCP에 **동일하게** 적용돼야 한다.
7. 인증 불가/미승인/만료/폐기/허용 목록 불일치/프로덕션 IdP 미구현 시 fail-closed. 운영 외부 연계는 인증 하드닝 후 별도 승인을 받는다.
8. RATE 제한, 이상호출 탐지, 회수 즉시 반영, 감사 최소화/보존정책 및 비상 정지 수단을 다음 구현의 필수 조건으로 둔다.

## 3. LLM 연결 설정 모델 (선택 기능)

- **활성화 기본값 OFF.** 연결 프로파일 예: `openai_compatible` + 승인된 내부 ModelOps Gateway (확정된 운영값 아님).
- 설정값: 공급자 종류, base URL, model alias, secret reference, 타임아웃, 활성/비활성, 변경 이력, 마지막 연결시험 결과(민감 응답 제외).
- UI는 관리자의 상태조회/검증과 비밀값 교체를 분리한다. 키는 생성/교체 순간에만 입력 가능하며 응답·감사·로그·사용자 브라우저 저장소에서 원문을 재표시하지 않는다.
- URL 변경은 허용 scheme/host/포트·DNS/rebind·리다이렉션 등 SSRF 위협을 제한한 승인 목록과 기관 방화벽 정책을 통과해야 한다. 임의 내부 URL 접속 프록시로 쓰지 않는다.
- **LLM 연결성 테스트는 모델 메타데이터 등 비임상 신호만 사용**한다. 환자데이터/원문 질의/SQL 결과 row로 테스트하지 않는다.
- LLM 추천/파라미터 추출은 승인 템플릿의 보조 기능일 뿐 실행 자격을 부여하지 않는다. raw-request egress는 기존의 별도 기술 opt-in과 기관 승인 플래그가 모두 있어야 한다. 결과 row는 LLM으로 보내지 않는다.
- LLM이 없는 환경에서도 Query Template 검색·선택·미리보기·조회·감사 경로가 동일하게 동작해야 한다.

## 4. M5-S0 상태 조회 API 계약 (이번 PR)

`GET /api/v1/admin/integration-settings`

- 관리자 `CONNECTION_PROFILE_MANAGE` 권한 필요. 미인증 401, 미허가 403, 제공자 미설정 503.
- 반환: OpenAI 호환 공급자 유형, endpoint/model 설정 여부, 모델명, 키 **존재 여부**, raw-request egress 설정상 허용 여부.
- 서비스 인증은 **관리 기능 미구현**으로 반환. `editable=false`; PUT/PATCH/POST로 값 변경 불가.
- endpoint URL, credential, service key, 비밀 참조, 병원/환자 데이터, 관리 IP, 외부 토큰은 응답에서 제외.
- 화면에서는 상태와 후속 기능의 미구현 여부를 명확히 구분한다. 화면 표시 자체는 호출 권한이 아니며 백엔드가 인가한다.

## 5. 후속 구현 검증 기준

- 관리자/비관리자/미인증/운영 Auth Provider 미설정 상태별 200/403/401/503; 프로덕션 `dev_headers` 불가.
- 등록 클라이언트의 다른 client impersonation, 만료·폐기·변경 중 캐시 무효화, key replay, key rotation, scope 탈취·수평 접근 차단.
- IP allowlist: IPv4/IPv6/CIDR, 프록시 spoofing, 사설망/NAT, 잘못된 X-Forwarded-For, 결여된 원 IP fail-closed.
- 모든 REST/MCP 경로에서 인증 -> authorization -> deterministic SQL SELECT validation -> 실행 -> 감사 일치; 허용되지 않은 Tool이나 조회 결과 본문 저장/LLM egress 불가.
- URL/키 입력과 로그/응답/오류에 대한 secret leakage 검사, outbound SSRF/redirect 차단, non-clinical connection test 검증.
- LLM 없이 Oracle Mock 수동 템플릿·read-only 실행 E2E가 계속 PASS.
- 외부 군 DEMIS/FHIR/SNUH.AI 실서비스는 승인 전 접근 테스트하지 않는다.

## 표준 참고

- [OWASP API Security Top 10 2023](https://api-security.owasp.org/editions/2023/en/0x11-t10/)
- [OWASP REST Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/REST_Security_Cheat_Sheet.html)
- [RFC 9700 OAuth 2.0 Security Best Current Practice](https://www.rfc-editor.org/rfc/rfc9700.html)
