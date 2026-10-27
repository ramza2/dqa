# M2-1G — 오프라인 메타데이터와 기존 Snapshot 비교 Preview

## 목적

M2-1D의 구조정보 JSON, M2-1E의 출처 주장 JSON, M2-1F의 담당자 검토
**초안** JSON을 검증한 뒤, DQA의 **기존 저장된 Snapshot revision**과
순수 구조를 비교하는 **내부 read-only preview**이다.

- \`preview_offline_snapshot_link(session, source_name, revision_id,
  raw_metadata, raw_claim, raw_review_draft, now=None)\`
- 호출자는 **이미 허가된** DQA PostgreSQL의 source-scoped read Session을
  전달해야 한다. 이 단계 자체는 인증/API/접속계정 생성을 제공하지 않는다.
- 사용자 파일은 기존 M2-1D/E/F 검증기로 검사한다. 출처 및 검토자 문자열,
  주장된 날짜, 바이트 해시는 **신원 인증/외부 DBA 확인을 의미하지 않는다**.
- 저장된 Snapshot은 기존 \`preview_snapshot_review\`에서 변경이력,
  Fingerprint, 개수, Candidate v2 WARNING을 재검증한다.
- 검사 완료 후 기존 \`compare_schema_snapshots\` 재사용:
  \`STRUCTURAL_MATCH_UNTRUSTED\` / \`STRUCTURAL_DIFFERENCE_UNTRUSTED\`;
  비교한 Snapshot이 최신이 아니면 \`SUPERSEDED\`.
- 출력에는 안전한 판정·전체 변경 건수만 포함한다. 원문 메타데이터,
  병원 데이터, 검토자 이름/ID, 변경값·컬럼명은 반환하지 않는다.
- 선행 Snapshot이 없거나 변조된 경우, 형식 오류/대상 불일치 시
  안전한 오류코드로 실패한다.
- 비교 도중 새 Snapshot이 생성되면 최신 revision을 **재확인**해
  \`SUPERSEDED\`로 처리한다. 이 재확인도 원자적 승인을 보장하지 않는다.

## 제한사항

- **\`oracle_demis_mock / FREEPDB1 / DEMIS_OWNER\` 전용.** 실 DEMIS와
  임상정보 11종 등 테이블 범위의 확정을 전제하지 않는다.
- 실제 DB 적재 기능 없음; 이미 저장된 Snapshot의 READ만 설계.
- 테스트는 FakeSession으로 실행하며 Oracle/실제 PostgreSQL에 연결하지 않는다.
- 새로운 API/버튼, DB 마이그레이션, 조회계정/권한, Snapshot capture,
  리뷰 이벤트 생성, Catalog import/READY/activation, 운영 배포 없음.
- 실제 DBA 문서 진위·암호학적 서명/폐기상태, 독립 Preflight 승인,
  관리자/검토자 인증은 별도 기관 승인·보안 설계 후에만 구현.

## 테스트

\`\`\`bash
cd /tmp/dqa-m2-1g-review/backend
~/dqa/.venv/bin/python -m pytest -q \
  tests/test_m2_1g_offline_snapshot_link.py \
  tests/test_m2_1f_offline_review_draft.py \
  tests/test_m2_1e_offline_provenance.py \
  tests/test_m2_1d_offline_metadata_export.py \
  tests/test_schema_snapshot_review.py \
  tests/test_schema_snapshot_diff.py
\`\`\`

모든 결과에서 출처 인증·DBA 승인·independent preflight는 \`false\`,
Catalog 후보는 \`WARNING\`, \`catalog_ready=false\`,
\`activation_eligible=false\`이다.
