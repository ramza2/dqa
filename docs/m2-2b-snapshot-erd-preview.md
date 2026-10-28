# M2-2B — 저장된 Snapshot 기반 ERD 미리보기

## 왜 필요한가

MSGPTR이 군 승인 조건에서 DEMIS 조회 경로에 직접 연결할 수도
있으므로 DQA는 DB 구조 분석 도구 역할만으로도 실질적인 가치를
제공해야 한다. M2-2A는 활성 READY Catalog 기반, 이번 M2-2B는
**활성화 이전의 저장된 Snapshot** 기반이다.

## 변경

- GET /api/v1/schema-inspector/snapshots/{revision_id}/erd
- CATALOG_READ 권한/Source·Revision 바인딩을 기존 Snapshot API와 동일하게 적용
- Snapshot v1 DTO, Target 일치, 구조 자기비교, Fingerprint, 객체 건수 재검증
- 반환값: 페이지된 테이블 물리명(최대 50, UI 30) 및 선택 테이블의
  직접 FK 40건까지, 복합 FK 컬럼 대응·외부 Snapshot 참조 여부
- Source/Revision/Fingerprint 및 NOT_VERIFIED/activation_eligible=false
  상태를 화면에서 검증하고, Snapshot 선택 시 이전 요청 결과 폐기
- 버튼을 눌러야 추가 GET이 발생하므로 기존 Snapshot 패널의 GET
  요청 수·재시도·deadline 정책에 영향 최소화
- 합성 fixture 기반 Python API/서비스 검사, React UI 검사

## 안전 경계

이 경로는 *저장된 메타데이터 미리보기*이며 독립 DBA Preflight
또는 Catalog READY·활성화가 아니다. 사용자가 요청한 대상 DB에
연결하지 않고, 저장된 snapshot_json 원본과 Oracle default SQL,
index definition, 자격정보를 반환하지 않는다. 타 스키마에 대한
FK 참조는 실제 테이블 접근 권한을 증명하지 않는다.

ERD는 모든 관계를 보장하지 않고, 현재 선택된 테이블 기준
1단계 최대 40개만 표시한다. 의료데이터·자동추론·FHIR 변환,
Query Template·MCP/DB 쓰기는 이 PR에 포함되지 않는다.
후속은 Snapshot 기반 DB 분석 DOCX 이관이다.

## 검증

- Backend: tests/test_m2_2b_snapshot_erd.py (기존 테스트의 FakeSession)
- Frontend: SnapshotErdPanel.test.tsx, SchemaSnapshotHistory.test.tsx,
  FocusedErdPanel.test.tsx
- Frontend build, lint 및 diff check
- 실 DEMIS/Oracle/운영 PostgreSQL/실환자 기록 접속 또는 배포 없음
