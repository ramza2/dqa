# M5-S1B — 외부 서비스 클라이언트 정책 초안 관리자 UI

## 범위

- 기존 **환경 설정 → FHIR·외부 시스템 접근 제어 → 정책 초안 관리 열기**에 배치.
- 관리자 인증/인가가 성공한 경우에만 초안 관리 화면을 표시. 관리 기능 API는 M5-S1A의 기존 CONNECTION_PROFILE_MANAGE 서버 게이트를 그대로 사용.
- 서비스 클라이언트 목록 API: 25건 단위 목록/페이지 탐색.
- 상세 조회 + 감사 API: CREATED/UPDATED/REVOKED 작업, 수행자, 변경 필드명 표시. 원문 자격증명 없음.
- 등록 API: 필수 메타데이터 및 제안 scope·IP/CIDR으로 DRAFT 등록.
- 수정 API: DRAFT 상태의 서비스명·기관·담당·목적·요청 scope·제안 CIDR만 수정. client ID 및 환경 변경 UI는 잠금.
- 폐기 API: **사용자의 별도 확인**을 요구하는 영구 폐기. REVOKED는 수정 버튼이 없음.
- 401/403/503/409/422에 대한 일반화된 한국어 오류. 서버가 최종 입력·인가 판단.
- 변경 후 목록/상세/감사 재조회. 이탈/선택 변경으로 과거 응답이 현재 상세를 덮지 않도록 effect cleanup 사용.

## 비허용 및 후속

1. UI는 **DRAFT / REVOKED**만 표현하며 실제 서비스를 ACTIVE로 만들 수 없습니다.
2. 서비스키/비밀번호/토큰 입력·발급·조회·교체, IP allowlist 적용, 외부 MCP/REST 접근 허용, 임상 승인·실 DEMIS 조회 기능은 구현하지 않습니다.
3. M5-S0의 service_client_management_available=false는 **실제 인증·서비스키 관리 미구현**을 뜻합니다. 본 초안 편집 UI의 존재와 구분합니다.
4. 컨소시엄에서 검토 중인 역할분리 구성도 v1.1과 DEMIS MCP 인터페이스 정의서 v1.3은 여전히 미승인입니다.
5. 제안 scope/CIDR은 **신청 초안**이지 인증 또는 권한 목록이 아닙니다. 모든 최종 검증은 M5-S1A Backend에서 시행합니다.
6. M5-S2 인증·인가, 승인자 기반 정식 정책 승인 워크플로, LLM 설정 수정 및 외부 네트워크 연결은 각각 별도의 승인·검증 후 개발합니다.

## 검증

- frontend/src/test/ServiceClientDraftsPanel.test.tsx: 초안 상태/감사, 등록 payload, 불변 필드 잠금, 편집 PATCH, 확인 후 폐기, 권한 거부.
- frontend/src/test/IntegrationSettingsPortal.test.tsx: 관리자 상태 성공 후만 초안 UI 노출, 거부 시 미노출, 기존 LLM 상태 보호.
- 독립 Worktree에서 npm run build / npm run lint / npm run test -- --run을 실행.
- 실제 DB 마이그레이션/서버 재배포 없음. S1A의 Alembic revision 필요 여부는 배포 전 별도 확인.
