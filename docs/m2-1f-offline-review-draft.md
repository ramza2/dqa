# M2-1F — 오프라인 메타데이터 검토 기록 **초안** (2026-10-27)

## 기존 시스템과 관계

기존 \`schema_snapshot_review_events\`는 저장된 Snapshot의 관리자 인증·
변경 검토 이벤트를 별도로 관리한다. 해당 이벤트의 ACKNOWLEDGED 역시
독립적 DBA Preflight나 Catalog READY가 아님.

M2-1F는 **아직 Snapshot 저장/원본 DBA 확인을 하지 않은 합성 파일**에
대해서만 오프라인 검토 주장(draft)을 읽는다. 기존 검토 이벤트와
동일한 권한/승인 경로를 만들지 않는다.

1. 메타데이터 구조 검증: M2-1D (\`WARNING\` 후보)
2. 출처 주장 측면파일과 바이트 일치: M2-1E (\`MATCHED_UNTRUSTED\`)
3. 검토 기록 초안과 **두 파일** 해시 일치: M2-1F
   (\`ACKNOWLEDGED_UNVERIFIED\`/\`CHANGES_REQUESTED_UNVERIFIED\`)
4. 진짜 DBA 신원/스키마 범위 승인/독립 검증/검토자 권한은 모두 **미검증**
5. 정식 Snapshot 검토 및 별도 READY 승인·활성화는 이후 승인된 경로만.

## 검토 초안 파일 계약

JSON \`format=dqa-offline-metadata-review-draft-v1\`, 최대 8KB. 필수 필드:
\`format\`, \`source_name\`(oracle_demis_mock),
\`metadata_file_sha256\`(원본 bytes), \`claim_file_sha256\`(출처 주장 파일 bytes),
\`schema_fingerprint\`, \`claimed_reviewer_id\`,
\`decision\`(ACKNOWLEDGED / CHANGES_REQUESTED),
\`reason_code\`(REVIEWED_METADATA / RECHECK_REQUIRED / SCOPE_UNCLEAR),
\`claimed_reviewed_at\`(timezone-aware).

검토자가 제공한 \`claimed_reviewer_id\`는 **신원 인증이 아닌 문자열**이다.
전자서명, 승인자 권한, revocation, 유효기간/변경 경쟁, 감사 이력,
재전송 방지는 구현하지 않았다. SHA만 일치시키는 위조는 가능하다.
\`ACKNOWLEDGED\`는 업무용 검토 초안 표현이며 **공식 승인이 아니다**.
병원 실데이터나 실 DEMIS/운영 PostgreSQL 접근 없음.

CLI의 선택적 \`--review-draft\`는 **\`--claim\`과 함께 지정**한다.
미지정 시 M2-1E 동작 유지. 오류는 \`M2_1F_BLOCKED=...\` 또는 기존
\`M2_1D_BLOCKED\`에 안전한 코드만 표시하며 입력 원문·사람명은 출력하지 않음.

모든 성공 응답에서도:
\`METADATA_REVIEW_STATUS=NOT_REVIEWED\`,
\`REVIEW_DRAFT_ACTOR_AUTHENTICATED=false\`,
\`DBA_SITE_APPROVAL_VERIFIED=false\`,
\`INDEPENDENT_DBA_PREFLIGHT=NOT_VERIFIED\`,
\`CATALOG_PACKAGE_READINESS=WARNING\`,
\`CATALOG_READY=false\`,
\`CATALOG_ACTIVATED=false\`.

## 오프라인 검증

\`\`\`bash
cd /tmp/dqa-m2-1f-review/backend
~/dqa/.venv/bin/python -m pytest -q \
  tests/test_m2_1f_offline_review_draft.py \
  tests/test_m2_1e_offline_provenance.py \
  tests/test_m2_1d_offline_metadata_export.py \
  tests/test_schema_snapshot_review_events.py
\`\`\`

**미구현:** 실제 사이트 출처/검토자 인증, 자동 승인, Review UI, 영속화,
전자서명 신뢰검증, READY/import/activation, Oracle/DEMIS/운영 DB 연결.
