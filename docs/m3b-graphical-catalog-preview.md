# M3-B — 그래픽 조회 조건 작성 및 단일 테이블 SQL 미리보기 (2026-10-28)

## 목적

LLM 없는 Query Assistant M3-A 후속. Query Operator가 Catalog 기준
테이블·표시 컬럼·비교 조건을 클릭해 **SELECT 구문 예시만** 확인하도록 한다.

- 활성 v2 Catalog의 테이블/컬럼 API 재사용. 일치하는 Source,
  Revision, Fingerprint를 UI와 Backend에서 각각 확인한다.
- 최대 1테이블, 표시 컬럼 16개, 조건 4개, row_limit 1~100.
- 비교연산자: =, <>, <, <=, >, >=, LIKE, IS NULL, IS NOT NULL.
  LIKE는 문자형만; 미지원 데이터 타입은 거부. 조건값은 **입력받지 않음**.
- `POST /api/v1/query-builder/preview`는 QUERY_OPERATE 권한 필요.
  요청의 `extra` 금지. 서버가 **active Catalog에 실제로 있는**
  스키마·테이블·컬럼의 원문 표기를 확인하고 Oracle identifier를 검증한다.
- SQL은 **중첩된 단일 SELECT** + `ROWNUM <= :p_limit`.
  사용자 값·임의 SQL·조인·표현식 삽입을 허용하지 않고, 비교값은
  `:p1` 등 placeholder로만 표시한다. 기존 `validate_sql_safety`를 통과해야 반환.
- 반환은 SQL 텍스트+변수명/자료형 **메타데이터만**.
  `preview_only=true`, `approved=false`, `executable=false`,
  `template_id=null` 고정.
- 표시된 SQL을 저장·승인·실행 API로 전송하는 기능 **없음**.
  M3-A 승인 템플릿 실행 경로는 완전히 독립.

## 중요: Phase 29-C와의 경계

기존 `compile_structured_query_plan`은 Semantic Resource 매핑이
미승인/미구성인 경우 `NOT_CONFIGURED`로 실패한다.
M3-B의 물리 Catalog **표시-only 예시**는 논리 매핑을 임의
승인하거나 Phase 29-C/29-D 컴파일러·실행 Gate를 우회하는
`ValidatedLogicalPlan`이 아니다. 기능·의료 의미 자동추정 없음.

복합 JOIN, 그룹화, 결과 실행, 쿼리 템플릿 생성/심사, SQL→실행
승격, 동적 조건값 입력은 **미구현**. 실 DEMIS/환자 데이터/의료
테스트·운영 배포, LLM 호출, 자격증명 해석/DB connection 없음.

## 검증

- Backend 합성 DB 테스트: 메타데이터 일치, SQL 안전성, stale,
  미존재·비허용 컬럼, 401/403, 조회 어댑터 호출 0.
- Frontend 테스트: 목록 조회→컬럼·조건 선택→미리보기, Source
  전환/응답 지연, 잘못된 응답 차단, 값/SQL 미전송, 입력한도.
- 실행: `bash scripts/m3b-test-isolated.sh`. 일회용 pgvector/Postgres
  만 사용하며 기존 DQA DB 연결 금지.
