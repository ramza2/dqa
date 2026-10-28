# M3-C1 — Query Template 검토 현황 UI (2026-10-28)

## 목적
기존 Query Template 등록/검토 API는 이미 `DRAFT → IN_REVIEW →
APPROVED/REJECTED` 상태와 SQL Safety 조회를 지원한다.
M3-C1은 **이 상태를 확인하기 위한 읽기 전용 화면**을 제공한다.

## 변경
- 포털 상단 `템플릿 검토` 탭과 대시보드 읽기 전용 링크
- 기존 권한 검증 API만 호출:
  - `GET /api/v1/query-templates?source_name=...&limit=50&offset=...`
  - `GET /api/v1/query-templates/{id}`
  - `GET /api/v1/query-templates/{id}/sql-safety`
- 권한은 서버의 `TEMPLATE_READ` 그대로 사용. `query_operator` 단독
  역할은 열람 권한이 없으므로 403으로 실패한다.
- Source 필터, 서버 페이지(최대 50건), **현재 페이지의** 승인상태 필터
- 템플릿의 상태/버전/활성 여부, Catalog pinned/current 호환성,
  SQL 안전성 및 오류 코드, 저장된 SQL 텍스트·파라미터 **이름/형식만**
- 서로 다른 API 조회 사이 버전/승인 상태/SQL Safety 식별자가
  어긋나면 **상세 전체를 숨기고 재조회 요구**. 소스/필터 변경 및
  이전 선택의 늦게 도착한 응답은 무시한다.
- SQL 열람은 `cache: no-store`; 어떤 요청도 템플릿 생성/수정,
  review 제출, 승인/반려, enable, 실행 API를 호출하지 않는다.

## 명확한 범위 한계
- M3-B PR #153 위의 **스택형 PR**, #153이 `main`에 병합된 뒤
  이번 PR의 base를 `main`으로 변경하는 순서
- SQL Safety PASS는 승인 또는 실행권한이 **아니다**
- 현행 M3-B SQL 미리보기에서 작성한 SQL을 자동 템플릿으로
  승격하거나 저장·제출·승인하는 연결 **없음**
- 향후 M3-C2는 작성자·승인자 역할과 검토/서명·이력 UX에 대한
  별도 설계/권한·감사 검증 후 진행
- 데이터베이스 스키마 변경 없음. 신규 Backend API 없음.
  실 DEMIS/DB credential/실환자 자료/LLM 호출/운영 배포 없음

## 테스트
Frontend는 기존 API만 Mock하며 POST/PATCH/DELETE 호출이
없음을 검증한다. 서버에서 `npm run test -- --run
src/test/TemplateReviewPortal.test.tsx
src/test/WorkflowDashboard.test.tsx
src/test/QueryAssistant.test.tsx
src/test/CatalogGraphicalBuilder.test.tsx` 및
`npm run build`, `npm run lint` 수행 전 **Draft** 유지.
