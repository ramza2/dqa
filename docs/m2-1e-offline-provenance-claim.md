# M2-1E — 메타데이터 출처 주장 파일의 오프라인 검증 (2026-10-27)

## 목적 및 보안 경계

M2-1D는 구조정보를 읽고 WARNING 후보만 만들었다. M2-1E는 **선택적으로**
함께 전달된 출처 주장 파일(sidecar JSON)을 입력받아 **정확한 파일 바이트**
및 정규화된 스키마 Fingerprint, 개발용 Mock identity가 맞는지만 검사한다.

- 출처 ID, 발행 참조번호, 발행 시각은 **신원 검증되지 않은 주장**이다.
- SHA-256이 일치해도 서명 검증, 실제 DBA 발급, 기관 승인, 허용한 스키마
  범위, 최신성/폐기 여부가 검증된 것은 아니다.
- 구조검증 결과: \`MATCHED_UNTRUSTED\` 또는 \`ABSENT\`.
- 검토 상태는 항상 \`NOT_REVIEWED\`이며, preflight \`NOT_VERIFIED\`,
  Catalog \`WARNING\`, Catalog activation \`false\`로 고정한다.
- 임상 데이터·실제 DEMIS·Oracle·PostgreSQL·MCP·HTTP 접근, 스키마
  권한 추가, DB 적재/활성화는 **없다**.
- 운영 사이트가 승인한 신원·전자서명·폐기/재검증 정책이 마련되기 전에는
  이 검증을 의무사 DBA 승인으로 안내하면 안 된다.

## Sidecar JSON v1

이름: \`dqa-offline-oracle-provenance-claim-v1\`.
필수 정확한 키:

\`\`\`text
format                 dqa-offline-oracle-provenance-claim-v1
source_name            oracle_demis_mock
db_type                oracle
database_name          FREEPDB1
schema_name            DEMIS_OWNER
metadata_file_sha256   실제 메타데이터 JSON 파일 bytes SHA-256
schema_fingerprint     M2-1D 정규화 SchemaSnapshot SHA-256
claimed_issuer_id      미검증 선언값 (예: SYNTHETIC-DBA-ONLY)
claimed_reference      미검증 문서 참조값
claimed_issued_at      ISO 8601 timezone-aware 값
coverage               6개 카테고리 모두
omissions              빈 배열
\`\`\`

사이드카는 최대 16KB. 중복 JSON 키·임의 필드·자료 행·과거 파일의
해시를 다른 파일에 재사용하는 경우를 차단한다. 5분 초과 미래 시각은
잘못된 형식으로 보지만 다른 시각이 진짜 발행 시각이라는 뜻은 아니다.

## 실행

\`\`\`bash
# 별도 격리 Worktree 내 backend에서:
~/dqa/.venv/bin/python -m pytest -q \
  tests/test_m2_1e_offline_provenance.py \
  tests/test_m2_1d_offline_metadata_export.py \
  tests/test_schema_preflight_contract.py

# 파일이 준비된 경우에만 실행하는 선택 사항:
# ~/dqa/.venv/bin/python -m app.cli.offline_metadata_preview \
#   --input /path/to/synthetic-metadata.json --claim /path/to/synthetic-claim.json
\`\`\`

\`--claim\`을 생략하면 M2-1D 기존 실행이 유지되며
\`PROVENANCE_CLAIM_BINDING=ABSENT\`가 출력된다.
지정했는데 누락/위변조/불일치하면 성공으로 진행하지 않는다.

**후속 별도 과제**: 공식 DBA 제공 포맷 협의, 승인기관 정책,
신뢰할 수 있는 검증자/서명/권한/폐기 확인, 감사지속성 및 안전한
Review UI. 이 중 아무것도 자동으로 허용하지 않는다.
