# M2-2C — Snapshot 기반 선택 테이블 DB 분석서 DOCX (초도)

## 목적

MSGPTR이 승인된 DEMIS 조회 경로에 직접 연결하고 DQA는 DB 구조 분석만
맡는 구조를 대비한다. 기존 독립 Schema Analyzer의 Word 보고서 기능 중
**검증된 물리 메타데이터**를 DQA의 append-only Snapshot 계약에 맞춰 이관한다.

## 범위

- Snapshot History → Snapshot ERD → 테이블 선택 → **선택 테이블 분석서 DOCX 다운로드**
- GET /api/v1/schema-inspector/snapshots/{revision_id}/report.docx
- source_name, schema_name, table_name 필수. 실제 DB Target/호스트/SQL/비밀번호를 입력받지 않는다.
- 보고서 항목: Source/DB/Schema/Table, Revision/지문/수집시각,
  Table/Column(자료형, Nullable, DB Comment), PK/UK, FK(복합 컬럼 순서),
  Index(이름, Unique, Method, 구성 컬럼).
- 원본 Schema Analyzer의 업무 Category/추정 의미 및 전체 DB 분석서 기능은
  아직 이관하지 않는다. **선택 테이블 1개만** 출력한다.
- 개발 초기 크기 제한: 컬럼 400, 해당 FK 200, 인덱스 100, DOCX 3MB.
  초과하면 실패 처리하며 내용을 몰래 잘라 내지 않는다.

## 안전·권한

- 대량 메타데이터 내보내기 위험 때문에 권한을 **CATALOG_MANAGE**로 제한.
  다른 Snapshot 조회(CATALOG_READ)와 별개이며 일반 조회자는 403.
- 저장된 Snapshot의 v1·Target·구조 자기비교·Fingerprint·counts 검증을
  M2-2B의 read-only projection 단계와 동일하게 거친다.
- DB default SQL, index_definition, 자격정보, 임상 행 데이터, 원본
  snapshot_json 원문 및 포트/호스트 연결 설정을 내보내지 않는다.
- 실제 DEMIS/Oracle에 조회를 시작하거나 Catalog를 Import/READY/활성화하지 않는다.
- 미승인 Snapshot 결과임을 표지/개요에 반복 명시하고, Cache-Control:no-store,
  attachment Content-Disposition, 안전한 고정 파일명을 사용.
- DB COMMENT는 실제 메타데이터 내용으로 출력하므로 **분석서 외부 배포는 별도
  군 보안정책/DBA 승인 후** 수행해야 한다.
- 실제 DEMIS 전체 스키마와 의미 매핑, 독립 Preflight, 데이터 조회 가능 여부는
  이 결과만으로 증명할 수 없다.

## 검증

격리 Worktree에서 다음만 실행한다 (외부 DB를 건드릴 수 있는
\`tests/test_data_discovery_search.py\` 및 \`db_client\` fixture 테스트 금지).

- Backend: \`tests/test_m2_2c_snapshot_report.py\`
- Frontend: \`SnapshotReportDownload.test.tsx\`, \`SnapshotErdPanel.test.tsx\`,
  \`SchemaSnapshotHistory.test.tsx\`
- Frontend build/lint, git diff --check
- DOCX 패키지 의존성은 backend/pyproject.toml에 명시 (\`python-docx\`).
- 서버에서 실제 파일을 열어 목차/표/줄바꿈을 수동 검토하는 것은 별도
  브라우저/Word 수용 절차로 분리한다.

## 후속

- 선택한 업무 영역별/스키마별 배치 보고서, 대용량 페이지 분할 및
  인증된 export 감사 이력
- 전체 ERD 인쇄용 출력과 MSGPTR 대상 연계 매핑표는 별도 협의
