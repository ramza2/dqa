# M2-2A — DQA Active Catalog 중심 테이블 1단계 ERD (개발 초안)

## 결정 배경

메디칼스탠다드(MSGPTR)가 DQA API를 경유할지 또는 기관 승인하에
DEMIS 조회 대상에 직접 연결할지는 확정되지 않았다. 양쪽 구조 모두에서
DQA의 스키마 구조 분석·ERD·분석서 역량이 유용하므로 Legacy
demis-schema-search-poc의 ERD Explorer를 **DQA의 immutable Catalog
계약에 맞춰 단계적으로 이관**한다.

## 이번 PR

- 기존 Catalog Explorer의 선택된 테이블 상세화면에 "관계 ERD" 보기를 추가.
- 활성 Source + Revision/Fingerprint가 같은 API 응답 5종을 수용한
  기존 useCatalogExplorer hook을 **그대로 사용**. 새로운 API 호출 없음.
- 기존 FK 관계의 IN/OUT 방향, 복합 FK 컬럼 순서 및 타 스키마 참조를
  선/카드 형태로 확인. 다른 스키마와 테이블 이름이 같을 때 혼동 방지,
  스키마 누락/선택 테이블이 아닌 관계는 표시 제외.
- 후보 관계 최대 40건 표시, 초과·검증 불가 상태에 경고.
- Source·Revision 전환 및 응답 지연시 기존 stale guard를 통한 화면 초기화.
- 읽기 전용. 별도 ERD 데이터 저장/다운로드, 전체 DB 탐색,
  ERD 자동 관계 추정 및 공식 DBA 승인·접속 권한 판정 없음.

## 중요한 제한

1. 화면은 **Active READY Catalog revision**에서만 표시되므로, Inspector
   Snapshot의 WARNING 후보를 자동으로 READY/활성화하지 않는다.
2. API가 각 방향 최대 500개 관계까지만 반환하므로 1단계 표시도
   일부 누락될 수 있다. 8,000개 테이블 전체 ERD 또는 실자료
   완전성 보증이 아니다.
3. 기존 PoC의 Target CRUD/Graph API를 직접 복사하지 않는다.
   운영 Target 접속/Metadata 계정, 스키마 범위, 보안·DBA 승인
   미확정 상태에서는 실제 DEMIS 연결하지 않는다.
4. SQL/임상 레코드 조회, Docker/DB migration, 대외 API, ModelOps
   호출, MSGPTR 직접 접속 지원 코드는 변경하지 않는다.

## 검증

- Frontend 단위/통합 테스트: FocusedErdPanel, CatalogExplorer,
  Snapshot 관련 회귀
- Frontend TypeScript build, eslint
- Oracle Mock 합성 Catalog가 활성화된 개발 화면에서
  실 UI 점검은 **별도 수용 절차**; 이번 코드 검증과 구분
- **후속 M2-2B:** Snapshot/기존 Catalog 데이터에서 의료 원문 및
  비밀정보를 제외하는 DB 분석 DOCX 생성 설계·합성 검증
