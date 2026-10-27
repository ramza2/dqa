# M2-1D — DBA 메타데이터 파일 오프라인 검증 (개발 계약 v1)

**범위:** M2-1C 이후, Oracle SELECT/REFERENCES 권한을 넓히지 않고
외부에서 제공된 **스키마 구조정보 파일**을 검토하는 대안의 첫 구현입니다.

- 현재는 고정된 개발용 Oracle Mock(`oracle_demis_mock`, `FREEPDB1`,
  `DEMIS_OWNER`)만 허용합니다. 실제 DEMIS 데이터·계정에는 적용하지 않습니다.
- 네트워크, Oracle, PostgreSQL, API, 기존 Catalog/Snapshot Revision은
  사용하지 않으며 **검증만 수행**합니다.
- 성공 시 이미 존재하는 v2 Catalog `WARNING` 후보 빌더와 검증기를
  메모리 안에서 실행합니다. 저장·Import·READY·Activation은 없습니다.
- 파일의 `claimed_fingerprint`는 자체 일관성 검사이지 전자서명이나
  **실제 DBA 제공자 신원/승인을 확인하는 수단이 아닙니다.**
  보안 심의·관리자 승인과 혼동하지 않습니다.

## 오프라인 JSON 계약

최상위 정확한 키 5개:
`format`, `source_name`, `metadata_only`, `claimed_fingerprint`, `snapshot`.

`format = "dqa-offline-oracle-metadata-v1"`;
`source_name = "oracle_demis_mock"`;
`metadata_only = true`.

`snapshot`에는 기존 DQA sanitized physical Snapshot v1 포맷을 사용하며,
`snapshot_version=1`, `db_type=oracle`, `database_name=FREEPDB1`,
`schema_name=DEMIS_OWNER`, 필수 6개 배열
`tables / columns / primary_keys / unique_constraints / foreign_keys / indexes`
만 허용합니다. 테이블 구조 DTO 형식은 기존
`backend/app/adapters/schema_inspector/base.py`를 참조하십시오.

- 최대 4MB, 중복 JSON 키·임의 항목·원문 데이터 행·SQL 기본값·인덱스
  DDL 문자열·다른 DB/Schema·누락 구조·고아 키 참조를 차단합니다.
- 컬럼/테이블 설명은 메타데이터라도 민감할 수 있으므로 담당자
  제공 범위를 별도 검토해야 합니다.
- Fingerprint는 DQA `_physical_payload` 정규화 후 SHA-256.
  원천 데이터 완전성이나 제공자 신원은 보증하지 않습니다.
- 사용자가 다른 파일을 지정하거나 외부 서명 없이 체크섬을 맞추는 것은
  **DBA 승인 증거로 인정하지 않습니다.**

## 실행

검증 대상 파일은 사전에 별도로 제공받고, 원문이 허용된 스키마 구조정보인지
DBA 및 담당자가 확인한 다음 격리 Worktree에서만 실행합니다.

```bash
cd /tmp/dqa-m2-1d-review/backend
~/dqa/.venv/bin/python -m pytest -q tests/test_m2_1d_offline_metadata_export.py
# 파일이 준비되면 아래는 검사만 합니다. 파일을 만들거나 DB에 적재하지 않습니다.
# ~/dqa/.venv/bin/python -m app.cli.offline_metadata_preview --input /approved/synthetic-metadata.json
```

성공 출력: `M2_1D_OFFLINE_SHAPE_PASS`,
`CATALOG_PACKAGE_READINESS=WARNING`,
`INDEPENDENT_DBA_PREFLIGHT=NOT_VERIFIED`,
`CATALOG_ACTIVATED=false`.

**다음 별도 단계**: 공급자 신뢰/승인/완전성 검증, 실제 DB 없이 하는
DBA export 변환기 설계, 안전한 Review UI, 독립된 폐기 가능 PostgreSQL에서
명시적 Snapshot append/CAS 테스트. 기존 `dqa-onprem`에 Import 금지.
