# S-05-C2 — Inspector Target 구성 대조 (승인·연결 없음)

기준: main@36d8fc2, 2026-10-16. Inspector Target과 Query Connection Profile은 **서로 독립적인 운영자 설정**이며 실제 연결·승인·권한을 공유하지 않는다.

## 현행 및 구현 범위

- Connection Profile: DQA DB metadata, 관리자 Profile API. 기본 등록 상태 disabled.
- Inspector: DQA_SCHEMA_INSPECTOR_* 환경변수 단독 Target, 개발/테스트만 실행 허용; production/staging 차단, 조회계정과 분리된 Inspector credential namespace.
- 신설 GET /api/v1/connection-profiles/{profile_id}/inspector-target-review: 기존 CONNECTION_PROFILE_MANAGE 권한 검사, DQA DB의 Profile metadata와 서버 Inspector 설정을 오프라인 문자열/숫자 비교.
- 결과: inspector_configuration_state(DISABLED/ENV_BLOCKED/INVALID/CONFIGURED_UNVERIFIED), comparison_state(NOT_COMPARABLE/TARGET_METADATA_MISMATCH/STRUCTURAL_MATCH_UNVERIFIED), mismatch_fields(항목명만). Host, Account, Credential Ref/Password, DSN, 원시 DB metadata 출력 없음.
- 4개 Literal false: inspector_bound_to_profile, connection_authorized, live_connection_tested, credential_values_resolved. 구조 일치도 미검증이며 허가가 아니다.
- 비교 항목: 환경, Source, DBMS, Host, Port, Database Name vs Oracle Service Name, Username. 특히 Database Name과 Oracle Service Name은 의미상 동일하다고 확정된 계약이 아니므로 단순 문자열 비교에 불과하다.
- Frontend Connection Profile 상세에서 관리자 명시적 [설정 대조 조회 (연결 없음)] 버튼을 눌러야 GET 호출. 이전 Profile의 느린 응답 무시; 오류는 고정 메시지만 출력.

## 보안·승인 경계

- 새 Route와 UI는 Schema Inspector의 POST /inspect 및 POST /snapshots/capture을 호출하지 않으며, Profile의 /enable 및 /test-connection을 호출하지 않는다.
- 기존 실접속 API는 그대로 존재하지만, 이번 기능으로 새 실행 경로가 생성되지 않는다. Credential Resolver, Oracle Engine, DNS, DEMIS, 복제/운영 EMR DB, 원시 Schema를 조회하지 않는다.
- 서버 운영자 설정을 수정하거나 Inspector Target을 Connection Profile로 자동 바인딩하지 않는다. 구조적 일치를 군/DBA 승인·Replica 인증·DEC-01/02/08/10 처리 또는 Preflight VERIFIED로 표시하지 않는다.
- 대상 Host/Schema/서비스 진위, 분리 계정 권한, 복제본 라이선스/ACL/물리적 경계는 외부 승인 선결이다. 운영 EMR 직접접속 금지 원칙 유지.
- 이 PR은 제품 Backend에 읽기 전용 GET을 1개 추가하나 DB 모델·Alembic·Settings·Inspector 실행 로직·Query Adapter·Catalog·MCP/Portal 활성화 로직을 변경하지 않는다.

## 오프라인 검증

- backend/tests/test_s05c2_inspector_target_review.py: 합성 설정 13개 케이스(구조 일치/불일치, disabled, production/staging 차단, 누락/namespace 오류, 관리자 접근/Viewer 403, Profile 404). 루트 db_session/db_client(테이블 TRUNCATE) 사용 금지; HTTP 테스트는 fake DB session override.
- frontend/src/test/InspectorTargetReview.test.tsx: 6개 Mock 테스트(수동 요청만, 값 비노출, 변조된 허가 false 위반 거부, stale 응답 무시, 403 오류 sanitization). 기존 ConnectionProfiles.test.tsx 6개 회귀 추가.
- 테스트에서는 실제 DB/Oracle/LLM/ModelOps 네트워크·Credential Resolve를 수행하지 않는다.

## 서버 검증 — 2026-10-19 PASS (PuTTY 실행 로그 확인)

    cd ~/dqa && git fetch origin && \
    git worktree add --detach /tmp/dqa-s05c2-review origin/feature/s05c2-inspector-target-offline-review && \
    (cd /tmp/dqa-s05c2-review/backend && ~/dqa/.venv/bin/python -m pytest -q tests/test_s05c2_inspector_target_review.py) && \
    (cd /tmp/dqa-s05c2-review/frontend && npm ci && npm run build && npm run lint && npm test -- --run src/test/InspectorTargetReview.test.tsx src/test/ConnectionProfiles.test.tsx) && \
    git -C /tmp/dqa-s05c2-review diff --check 36d8fc2 HEAD && \
    echo DQA_S05C2_REVIEW_PASS

- 검증 코드: `feature/s05c2-inspector-target-offline-review@4b7e8a9` (분리된 `/tmp/dqa-s05c2-review` worktree, 기준 `main@36d8fc2`).
- Backend: pytest **13 passed**. Starlette/httpx deprecation warning 1건(테스트 실패 아님).
- Frontend: `npm ci` 성공, `npm run build` PASS, `npm run lint` PASS, Vitest 신규 6 + 회귀 6 = **12 passed**.
- `git diff --check 36d8fc2 HEAD` PASS, 최종 마커 `DQA_S05C2_REVIEW_PASS` 확인.
- `npm ci` 보고: 취약점 4건(Moderate 1 / High 1 / Critical 2). 취약 패키지 및 실제 영향은 **별도 `npm audit` 분석 필요**; 이번 PR은 패키지 의존성 변경 없음. 무검토 `npm audit fix --force` 금지.
- GitHub Actions CI 상태 검증 없음(해당 HEAD의 실행 기록 미확인). 실제 DEMIS/Oracle 연결, 실제 병원 DB, 서비스 배포/런타임 검증 **미실행**.
- 이후 문서-only 변경은 테스트한 `4b7e8a9` 코드 로직을 변경하지 않음. PR 별도 승인 전 머지/실환경 배포 금지.

## 후속

기관 승인 후 Target Identity Trust, Revocation/Issuer, 프로필-Inspector 정식 Binding, 운영시스템 연결 Fail-closed 정책 및 증빙·감사 기능은 별도 설계·PR 대상이다.
