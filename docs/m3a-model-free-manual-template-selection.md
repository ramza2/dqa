# M3-A — 모델 없이 승인 템플릿 직접 선택 (2026-10-28)

## 배경과 범위

기존 조회 시험(Query Assistant)은 자연어 LLM 추천을 거쳐야 승인된
Query Template의 파라미터 폼으로 이동할 수 있었다. 군 환경에서
SNUH.AI LLM 사용/추가 설치가 미승인일 수 있으므로, 기존 인증 및
검증 경계를 유지하면서 **AI 없이 직접 선택하는 경로**를 추가했다.

- GET `/api/v1/query-executions/manual-templates?source_name=...&limit=100&offset=0`
  - QUERY_OPERATE 권한; 활성 Catalog와 같은 source/revision/fingerprint만
  - 현재 버전이 APPROVED, enabled, SQL safety PASS, parameter schema
    검증 통과, SQL 길이 한도 내인 템플릿만 반환
  - 최대 100개/페이지, stable_key/id 순서, 전체 eligible 개수 표시
  - 반환 메타데이터만: 템플릿 이름/설명/버전/ID/parameter names.
    SQL, DB credential, 행 데이터, 임상 기록, 환경 연결 정보 없음
- 기존 `/query-executions/form`을 그대로 활용해 명시적 파라미터 입력
- 선택/소스 변경 때 진행 중인 응답 무효화; Catalog 지문 불일치 차단
- AI 추천·AI 파라미터 추출 기능은 기존 선택적 시험 기능으로 유지
- **새 실행 기능이 아니다.** 예전 preview/execute는 별도 QUERY_OPERATE,
  Catalog/Template/DB Profile 권한 및 감사 등 기존 Gate를 재검증한다.

## 제한과 안전 경계

기본 Semantic Resource 매핑 미구성(29-A)은 그대로 유지한다. 이번
PR은 자연어→SQL 또는 동적 SQL 빌더를 구현하지 않는다.
M3 그래픽 쿼리 작성/템플릿 심사 워크플로 및 M4/M5 통합은 후속.
실 DEMIS/Oracle/운영 PostgreSQL 접근·쓰기, 운영 배포 없음.

테스트: 합성/격리 Backend 승인·활성화·호환성·unsafe·RBAC,
Frontend 직접 선택/AI 호출 0/타 Source 응답 무효화. 서버 실행으로
재검증 전에는 통과 주장 금지. PR 병합은 사용자 명시적 요청만.
