# M3-C2A — Query Template 검토 제출·승인·반려 UI 및 서버 검증

## 범위
M3-C1 읽기 전용 조회 화면에 **명시적인 권한 확인** 단계를 추가하고,
기존 Query Template API의 상태 전이를 연결한다. UI의 역할 게이트는
`GET /api/v1/auth/me`의 서버 인증 결과를 참고하며, 최종 권한은
기존 `require_permission(TEMPLATE_AUTHOR/TEMPLATE_APPROVE)`가 판정한다.

- 작성자 `template_author` : DRAFT → IN_REVIEW 제출
- 승인자 `template_approver` : IN_REVIEW → APPROVED/REJECTED
- 관리자: 기존 역할 기반 권한 정책에 따라 두 작업 가능.
  **작성자와 승인자의 인물별 분리(4-eyes)는 이번 범위의 서버 정책이 아님**
- 모든 작업은 확인 체크박스·검토 메모·버전 재조회가 필요.
  반려 사유는 필수(기존 API).
- 검토/승인은 SQL Safety 및 active Catalog 호환성이 PASS이고
  current template가 enabled=false일 때만 UI 활성화.
  반려는 SQL/호환성 불량 시에도 가능.
- UI는 실제 SQL 텍스트·파라미터 정의를 **재조회하여 변경 여부 검사**,
  `expected_version_id`, `expected_updated_at` 값을 함께 전송.
  SQL이나 의료 데이터 본문을 POST 본문에 재전송하지 않는다.

## 서버 방어
- 기존 승인/검토/반려 요청 DTO에 **선택적**
  `expected_version_id`, `expected_updated_at` 추가.
  기존 호출자는 이 필드를 생략할 수 있어 하위 호환.
- Repository `get_by_id_for_update` 잠금 안에서 버전·수정일
  불일치 409 `QUERY_TEMPLATE_STALE_VERSION`.
- **APPROVED로 전이할 때** 활성 Catalog 호환성을 서버에서 재평가.
  불일치 409 `QUERY_TEMPLATE_INCOMPATIBLE_CATALOG`.
- **APPROVED로 전이할 때** SQL AST Safety 재검증.
  불합격 422 `QUERY_TEMPLATE_SQL_UNSAFE`.
- 승인은 **활성화가 아님**: `enabled=false`로 유지.
  기존 독립 enable 및 실행 SQL Safety/권한/감사 Gate는 변경 없음.

## 범위 제한
- 신규 템플릿 DRAFT 생성/편집 폼은 **M3-C2B**로 분리.
- M3-B의 preview SQL 자동 저장·승격·실행 없음.
- 별도 임상 HITL UI, 승인 증명/서명, DB 계정, LLM,
  실제 DEMIS/환자행 데이터 연계, Write API 및 운영 배포 없음.
- 역할별 권한은 기존 RBAC를 따른다. 서버에서 작성자와 승인자의
  actor_id가 반드시 달라야 하는 4-eyes 정책은 기관 협의가 필요하며
  본 변경이 이를 보장한다고 표현하면 안 됨.

## 검증
`bash scripts/m3c2a-test-isolated.sh`.
- 개발 Fixture는 localhost:5432에 `TRUNCATE` 수행하므로 실행 전
  포트 점유 확인 후 거부, 일회용 Docker tmpfs PostgreSQL에서만 테스트.
- Backend: 승인 workflow/Query Template/M3-A 회귀, 버전·수정일
  경합, SQL 불안전, Catalog 변경 차단 등.
- Frontend: 권한 확인 기본 opt-in, 작성자/승인자 노출, 재조회 후
  POST, 반려 메모, stale blocking, 기존 M3-C1/M3-B 회귀.
- 최신 PR 브랜치의 서버 검증 결과를 확인하기 전까지
  `PASS` 또는 운영 배포 완료로 표기하지 않는다.
