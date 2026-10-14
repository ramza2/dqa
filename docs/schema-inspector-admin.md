# Schema Inspector Admin — S-01/S-02 개발용 메타데이터 검사

> **상태:** 개발/테스트 전용 Preview 경로. `DQA_SCHEMA_INSPECTOR_ENABLED=false`
> 기본값이며, `APP_ENV=production`에서는 설정을 true로 바꿔도 차단.
> 실제 DEMIS에서의 metadata 수집은 군/DBA 권한 및 운영 IdP 승인 전 금지.
> 기존 `demis-schema-search-poc`와 DQA Catalog는 자동 변경되지 않는다.

## 1. 현재 구현

- `POST /api/v1/schema-inspector/inspect` — `CATALOG_MANAGE` 관리자 권한 필수.
- Body는 **빈 JSON 객체 `{}`만** 허용한다. 요청자가 임의 DB 주소, 계정, Schema,
  SQL, 테이블명 또는 자격정보를 전달해 검사를 실행할 수 없다.
- 서버에서 고정한 한 개 **Schema allowlist**와 분리된 Inspector 계정으로
  `ALL_*` **dictionary metadata SELECT**만 수행. Oracle read-only transaction
  설정 후 Table/Column/PK/UK/FK/Index/Comment 메타데이터를 수집.
- API에는 원문 Snapshot, 컬럼명, SQL, 연결정보, Credential 또는 환자 데이터
  대신 **종류별 개수만** 응답. 데이터 원본 및 Catalog Revision은 저장하지 않음.
- 기존 Query Template `OracleReadOnlyDemisAdapter` / Connection Profile /
  `QUERY_OPERATE` 및 MCP Tool은 수정·재사용하지 않음.
- Inspector DBMS는 이 단계에서 **Oracle만** 지원. 접속은 명시적 관리자 요청 시에만,
  `NullPool`, TCP 연결 제한 5초, Oracle call timeout 15초로 처리.

## 2. 개발/Oracle Mock 연결 설정 예시

모든 설정은 **개발망에서만** 사용한다. 별도 메타데이터 조회 전용
최소권한 계정을 준비한 경우에만 런타임 환경변수를 주입한다.
아래는 이름 예시일 뿐이며 운영 호스트/계정·실제 비밀번호가 아니다.

```dotenv
APP_ENV=development
DQA_SCHEMA_INSPECTOR_ENABLED=false
DQA_SCHEMA_INSPECTOR_SOURCE_NAME=oracle_demis_mock
DQA_SCHEMA_INSPECTOR_SCHEMA_NAME=DEMIS_OWNER
DQA_SCHEMA_INSPECTOR_HOST=your-development-oracle-host
DQA_SCHEMA_INSPECTOR_PORT=1521
DQA_SCHEMA_INSPECTOR_SERVICE_NAME=FREEPDB1
DQA_SCHEMA_INSPECTOR_USERNAME=dedicated_metadata_reader
DQA_SCHEMA_INSPECTOR_CREDENTIAL_REF=env:DEMIS_INSPECT_SECRET_METADATA
# DEMIS_INSPECT_SECRET_METADATA should be injected from protected runtime secrets.
```

1. 관리자·개발환경·검사계정 최소권한·허용 스키마를 각각 검증하고,
   테스트 직전에만 `DQA_SCHEMA_INSPECTOR_ENABLED=true`를 주입한다.
2. `POST /api/v1/schema-inspector/inspect` body `{}`. 비관리자는 403,
   비인증은 401, 기능 비활성/미설정/production은 503.
3. 성공: `INSPECTED`와 table/column/key/FK/index **counts**,
   `imported=false`, `activated=false`를 확인한다.
4. 작업 종료 후 feature gate를 다시 false로 둔다.

## 3. 보안 경계와 이후 작업

- 기존 read Query Profile의 `DEMIS_SECRET_` 접두사를 검사 Credential에
  재사용 금지. 검사 계정은 오직 `env:DEMIS_INSPECT_SECRET_*`만 허용.
  계정 권한과 대상 스키마는 DBA가 최소 SELECT 범위로 별도 승인해야 한다.
- 실제 임상/업무 테이블의 **데이터 행은 조회하지 않는다**. 의도적으로
  Oracle dictionary `ALL_*` 메타데이터 뷰만 사용한다.
- 외부 API/MCP 공개, 주기 실행, 의료진 UI, 임의 SQL, DML/DDL,
  Package Import, Catalog 자동 활성화, Revision DB 이관은 이 PR 범위 밖.
- 다음 단계(S-03): Snapshot candidate → Catalog Package **v2** 생성/검증,
  Fingerprint/변경 Diff, immutable revision Import와 관리자가 승인하는
  READY Activation. 먼저 PoC와 동일 Mock 스키마의 parity를 입증한다.
- 현 단계의 메타데이터 검사 성공은 실 DEMIS 적합성, 운영 IdP, DBA 권한
  승인이나 임상 Insert 승인 근거가 아니다.
