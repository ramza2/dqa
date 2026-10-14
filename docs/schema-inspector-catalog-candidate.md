# Schema Inspector → Catalog Package v2 후보 생성 (S-03-A)

> 구현 단계: **오프라인 빌더 및 검증 테스트**. Inspector API/UI, 자동 Package Import,
> READY 활성화, 변경 감지/승인, 작업 스케줄러, 운영 DEMIS 접근은 이 PR 범위 외.

## Oracle Mock 검증 근거 (2026-10-14)

DQA PR #69를 `main`에 반영한 뒤 Oracle Mock (`demis-oracle-test`)과
동일 격리 네트워크의 **일회성, 읽기 전용 개발 컨테이너**에서 검사 전용
`DEMIS_INSPECT` 계정으로 실행한 결과:

| 항목 | 실제 수집 수 |
|---|---:|
| Table | 25 |
| Column | 206 |
| PK column | 26 |
| UK column | 9 |
| Foreign Key | 40 |
| Index (PK/UK 지원 인덱스 제외) | 19 |

`INSPECTED` 성공, `imported=false`, `activated=false`.
운영 DQA 컨테이너·데이터·Catalog 활성 Revision은 변경하지 않았음.
이 수치는 **Oracle Mock 검증 결과**이지 실 DEMIS/운영 허가 근거가 아님.

## S-03-A 범위

`app.services.schema_catalog_candidate.build_catalog_v2_candidate(snapshot, source_name, generated_at)`

- 입력: PR #68/#69의 `SchemaSnapshot` DTO; **DB 연결 없음**
- 출력: `demis_catalog_package/` 루트를 갖는 Catalog Package `2.0` ZIP bytes
- Table/Column/PK·UK Flag/FK ordered mapping/Index/comment를 실제 DQA
  Catalog Query/Discovery가 읽는 표준 JSON 키로 변환
- Semantic categories/assignments는 빈 배열. 의료 용어·업무 관계 자동 추론 없음
- Schema Fingerprint는 데이터와 무관한 정렬된 물리 메타데이터의 SHA-256
  (생성 시각 변경만으로 바뀌지 않음); 고정 시각 입력의 ZIP도 재현 가능
- Oracle SQL `DATA_DEFAULT` 및 인덱스 정의문은 값 노출을 피하기 위해 출력 제외
- 필수 11개 JSON, 파일별 SHA-256/byte manifest 구성 후
  기존 `validate_catalog_package_bytes`로 **자체 검증**
- 이전 Snapshot 대비 Diff가 없으므로 `diff/latest.json.available=false`
- 독립적인 DB Preflight 증빙이 없으므로 `validation/preflight.json.available=false`
- **`package_readiness=WARNING` 고정**: 기존 DQA Import 검토 가능하지만
  `activation_eligible=false`여서 READY-only 활성화 정책을 우회하지 못함

## 후속 작업

1. Oracle Mock으로 수집한 실제 `SchemaSnapshot`으로 후보 Package 생성,
   ZIP 검증 및 PoC의 표·컬럼·키·관계·주석 동등성 비교.
2. 검증용 Preview API/관리자 UI의 **명시적** 실행 및 이력/작업 상태 설계.
3. 이전 Snapshot과 Diff, DBA 메타데이터 Preflight, 검토 이력 및 정책
   모두 갖춘 뒤에만 별도 승인 PR에서 `READY` 전환 방식을 설계.
4. 검토 완료 시 기존 불변 Import API를 재사용하고, READY Revision은
   관리자가 **별도 승인·선택**하여 활성화한다. 실패 시 이전 Revision 유지.
5. Rebuild/Embedding Sync는 또 다른 명시적 작업이며 자동 연쇄 실행 금지.

검사 계정 `DEMIS_INSPECT`는 Oracle Mock에 `CREATE SESSION`과
`DEMIS_OWNER` 테이블에 대한 25개 `REFERENCES` 권한만 부여해 실제
메타데이터 수집에 성공했다. 이는 **개발용 예시**일 뿐, 실제 DEMIS
권한 설계는 DBA 검증과 군 승인을 받아야 한다.
