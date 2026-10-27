# M2-1I — M2-1A~H 통합 회귀 및 실제 DEMIS 연계 차단조건

> 2026-10-27 / 내부 개발용 통합 점검. 군·DBA 승인 또는 정식 과제 제출 자료 아님.
> 합성 Mock 테스트 성공은 실 DEMIS 접근권한 또는 임상데이터 처리 승인이 아님.

## 개발 통합 검증

새로운 DB/서비스/승인 기능을 추가하지 않고 **기존 검증을 통합 재실행**한다.

- **M2-1A/B:** 개발용 Mock Target 등록과 선택 Profile→Inspector 바인딩
  검사 (외부 Oracle/PG 연결 없는 단위 테스트)
- **M2-1C:** 메타데이터 가시성과 권한분리 진단 스크립트의 오프라인
  Fake-Docker 테스트 **만** 수행; 실제 Oracle 진단 스크립트는 호출 안 함
- **M2-1D/E/F:** 구조정보→출처 주장→수동 검토 **초안** 검증
- **M2-1G:** 저장 Snapshot과 비교하는 read-only 내부 서비스 FakeSession 테스트
- **M2-1H:** 승인 불가능한 CLI JSON 요약과 Frontend 로컬 대조
- **회귀:** Snapshot Review/Diff, Preflight 계약, R-01-D 격리 검증,
  Mock Inspector / Connection Profiles / Snapshot History React UI;
  Frontend Build와 Lint

격리 Worktree에서 실행 (npm 의존성은 **실행 전에** 준비):

\`\`\`bash
cd /tmp/dqa-m2-1i-review
bash scripts/dqa-m2-1i-offline-integration-check.sh
echo "PUTTY_SESSION_ALIVE"
\`\`\`

Python 기본: \`~/dqa/.venv/bin/python\`; 필요시
\`DQA_M2_1I_PYTHON\`으로 오버라이드 가능.
\`frontend/node_modules\`가 없으면 네트워크 설치 없이 BLOCKED로 중단.
성공 표식은 \`M2_1I_BACKEND_OFFLINE_PASS\`,
\`M2_1I_FRONTEND_OFFLINE_PASS\`,
\`M2_1I_INTEGRATION_OFFLINE_PASS\`.
스크립트는 실제 Oracle, DEMIS, PostgreSQL, Docker, 네트워크,
migration, Catalog import/activation/설정 변경을 호출하지 않는다.
Frontend dist 빌드 결과는 격리 Worktree에만 생성된다.

## 외부 연계 선결조건 (현행 Gate 불변)

\`docs/m2-0-operator-workflow.md\`에 기록된 10/26 DBA 협의:
Oracle 19c, 8,000개 이상 테이블, 병원 원천 DB 12개, GoldenGate는
테이블별 반영, 전용 ODS 부재, 대전 DR 조회 미승인.
**이는 저장소에 정리된 회의 정보이며 실제 조회 대상의 신원·접속허가·
DBA 검증 완료를 의미하지 않는다.** 복제 DB 또는 DR 가동을 임의 추정하지 않는다.

| Gate | 기관에서 확인할 정보 | 상태 |
|---|---|---|
| DEC-10 | 공식 조회 원천(DB/API/복제본)과 원본 차단, OGG 범위·최신성, DR 정책, 복제/Oracle 비용·라이선스 | 미확정/미승인 |
| DEC-01 | Source/Schema 승인 Scope, ERD/테이블·컬럼 사전, metadata-only 계정 및 Dictionary 최소권한, 접속경로 | 미확정/미승인 |
| DEC-02 | 독립 Preflight 발급기관·검증키·신원·만료/철회/Replay 계약 | 미확정/미승인 |
| DEC-03 | DEMIS Adapter·FHIR·SNUH.AI 인터페이스/소유권, 판독문·환자·Encounter·Trace·인증·오류 계약 | 미확정/미승인 |
| DEC-04 | Snapshot·Legacy metadata parity와 Gold 검증 기준 및 수용 주체 | 미검증 |
| DEC-05 | 운영 IdP, DB read-only 권한, 망/TLS/감사·보존 | 미승인 |
| DEC-08 | 현장 사용자/운영 화면에서 필수인 범위·권한·검토 시나리오 | 미확정 |
| DEC-09 | 공식 임상기록 반영 API와 진료승인 증빙 (조회와 분리) | 미승인 |

임상정보 "11종"은 **확정 범위 아님**. 실제 대상 테이블/컬럼 매핑은
의료정보체계과·DEMIS 담당자와의 협의 및 승인 후 결정한다.

기존 결정 레지스터 \`docs/u02-external-decision-register.md\` 및
\`docs/r01d-site-operational-readiness-gates.md\`를 상위 미결 목록으로 유지한다.
Mock 테스트 결과만으로 이 Gate를 완료로 변경하지 않는다.

**현 단계 금지:** 실제 DEMIS 접속/Schema Inspection, 승인되지 않은
DR/Replica 조회, WARNING→READY 자동승격, Catalog 활성화, 실환자 행
반출·복제, 임상정보 Insert. 모든 활성화/승인은 별도 증빙과 PR로 진행.
