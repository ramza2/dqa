# M2-2D — Snapshot 스키마 단위 분할 DOCX 묶음

## 배경·설계 선택

DQA가 독립적인 DEMIS DB 메타데이터 분석 도구가 되어야 한다는 요구와,
MSGPTR의 DEMIS 직접 연결 여부가 아직 확정되지 않은 상황을 고려한다.

M2-2C는 한 테이블의 분석서를 DOCX로 다운로드한다. 한 번에 수천
테이블의 Word 파일을 생성하면 서버 메모리·실행시간·Word 열람성이
악화될 수 있으므로, M2-2D는 **스키마별 테이블 이름순 1·5·10개씩**
DOCX를 생성하고 ZIP으로 묶어 순차 내려받게 한다. 이 PR은 **전체
스키마를 하나의 DOCX로 합치지 않으며**, 백그라운드 대량 작업도
시작하지 않는다.

## 인터페이스

- \`GET /api/v1/schema-inspector/snapshots/{revision_id}/schema-report.zip\`
- Query: \`source_name\`, \`schema_name\`, \`offset\`(0부터), \`limit\`(1~10)
- Auth: \`CATALOG_MANAGE\` 필수. \`CATALOG_READ\`만 있는 일반 사용자는 403
- 반환: \`application/zip\` (10MB 상한), \`Content-Disposition: attachment\`,
  \`Cache-Control: no-store\`, \`X-Content-Type-Options: nosniff\`
- Range headers: \`X-DQA-Schema-Total-Tables\`,
  \`X-DQA-Schema-Next-Offset\` (-1 = 최종 묶음).
- ZIP 구성:
  - \`tables/table-000001.docx\` 등 번호 기반 DOCX (파일명 충돌·경로조작 차단)
  - \`manifest.json\`: Source, Revision, Fingerprint, Schema, 전체/선택 건수,
    DOCX별 실제 테이블명·순번·SHA-256, 다음 offset
  - \`README.txt\`: NOT_VERIFIED/외부 공유 승인 필요 경고

정렬된 테이블을 분할하므로 같은 Snapshot의 여러 묶음을 합쳐
하나의 스키마를 빠짐없이 분석할 수 있다. 한 테이블이라도 문서
생성에 실패하면 해당 묶음 전체가 실패(409/413/500)하며 일부 성공
ZIP은 내보내지 않는다. 같은 리비전이라도 테이블 변경은 새 Snapshot을
생성하므로 이전 리비전의 묶음과 혼합하면 안 된다.

## 보안 범위

- 저장된 Snapshot v1, Target, Fingerprint, 물리구조·Counts 정합성 재검증
- M2-2C의 테이블별 allowlist DOCX 생성기 재사용: 컬럼 데이터 기본값
  SQL, Index Definition SQL, 접속 호스트/계정·비밀번호, 환자 레코드 미포함
- 실제 DEMIS/Oracle 접속·조회, Catalog Import/READY/Activation,
  FHIR 연계 변경, 운영 DB 쓰기 없음
- 물리 DB COMMENT는 원문 그대로 들어갈 수 있으므로 군 보안 승인 전
  외부기관 배포 금지
- DBA 승인/독립 Preflight를 대체하지 않으며 ZIP은
  \`UNAPPROVED_SNAPSHOT_METADATA_ONLY\`와 \`NOT_VERIFIED\`로 명시

## 검증 및 후속

격리 Worktree에서 합성 Snapshot으로 다음만 검증한다.

- Backend: \`tests/test_m2_2d_schema_bundle.py\`,
  \`tests/test_m2_2c_snapshot_report.py\`,
  \`tests/test_m2_2b_snapshot_erd.py\`
- Frontend: \`SnapshotSchemaBundle.test.tsx\`,
  \`SnapshotReportDownload.test.tsx\`,
  \`SnapshotErdPanel.test.tsx\`,
  \`SchemaSnapshotHistory.test.tsx\`
- Frontend build/lint, \`git diff --check\`
- **실제 생성 DOCX의 페이지·표·한글 표시 검사는 별도 시각 QA 절차**.
  통과 전 레이아웃 품질을 확정하거나 운영 배포하지 않는다.
- 추후: 일괄 작업 큐/다운로드 감사·개인정보 포함 가능성 점검, 여러
  묶음을 하나의 문서로 조합하는 선택 기능, MSGPTR용 관계·매핑표.
