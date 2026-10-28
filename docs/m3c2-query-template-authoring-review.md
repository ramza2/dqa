# M3-C2 — Query Template 작성·검토 워크플로 UI (2026-10-28)

## 목적
M3-C1 읽기 전용 검토 현황을 확장하여, 기존 Query Template
작성/승인 API로 DRAFT 작성·수정, 검토 제출, 승인·반려, 검토 이력,
정책에 따른 활성/비활성을 수행한다.

## 변경
- Frontend `TemplateReviewPortal` 확장 (기존 목록/상세 fail-closed 유지)
- 기존 API 재사용:
  - `POST /api/v1/query-templates` (TEMPLATE_AUTHOR)
  - `PATCH /api/v1/query-templates/{id}` (TEMPLATE_AUTHOR, DRAFT)
  - `POST .../submit-review` (TEMPLATE_AUTHOR)
  - `POST .../versions` (TEMPLATE_AUTHOR, APPROVED/REJECTED → 새 DRAFT)
  - `POST .../approve` · `POST .../reject` (TEMPLATE_APPROVE)
  - `POST .../enable` · `POST .../disable` (TEMPLATE_APPROVE)
  - `GET .../review-events` (AUDIT_READ)
  - 기존 `GET` 목록/상세/`sql-safety`
- Backend 최소 게이트: 승인·활성화 시 서버가 SQL Safety와 Active Catalog
  호환성을 다시 검증. 실패 시 `QUERY_TEMPLATE_SQL_UNSAFE` /
  `QUERY_TEMPLATE_INCOMPATIBLE_CATALOG`로 fail-closed.
- 작성자/승인자 권한은 기존 RBAC 분리 유지. 자기 승인 금지는
  현행 정책상 optional(미구현)이며 이번 PR에서 새로 도입하지 않음.
- 상태·버전 불일치·중복 전이는 기존 `INVALID_TRANSITION` /
  `NOT_DRAFT` 등으로 차단. UI는 응답 후 상세를 재검증한다.
- 대시보드 05단계를 화면 이용 가능으로 갱신.

## 범위 한계
- M3-B SQL 미리보기 자동 저장·템플릿 승격 없음
- 실 DEMIS 접속, 동적 SQL 실행, LLM, 신규 실행 권한 없음
- 운영 DB·배포 설정·스키마 마이그레이션 없음
- 화면의 SQL 안전성 표시만으로 승인·활성화를 허용하지 않음
  (서버 재검증 필수)

## 테스트
- Frontend: `TemplateReviewPortal`, `WorkflowDashboard`
- Backend (일회용/테스트 DB): `test_query_template_approval`의
  SQL unsafe 승인 차단, Catalog drift 승인 차단, enable 시 SQL unsafe 차단
