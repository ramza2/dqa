# M2-1H — 오프라인 메타데이터 요약 로컬 대조 화면 (2026-10-27)

## 운영자 흐름 (개발용 Mock 한정)

1. 별도 승인된 안전한 환경에서 메타데이터 파일을 준비하고 M2-1D/E/F
   CLI 검증을 수행한다. 이번 단계에서 실제 DBA·DEMIS 데이터는 취급하지 않는다.
2. 선택적으로 실행 예:
   \`python -m app.cli.offline_metadata_preview --input /path/mock.json
   --claim /path/claim.json --review-draft /path/review.json --summary-json\`
   (sidecar 부재 시 \`--claim\`·\`--review-draft\` 생략 가능)
3. 출력은 2KB 이하의 **sanitized status JSON** 한 줄이다.
   파일 원문, 컬럼/환자 정보, 주장된 DBA·검토자 ID는 포함하지 않는다.
4. DQA 운영자 화면 → Data Discovery → Snapshot 이력 → 상세 → 
   **오프라인 메타데이터 요약 대조**에 해당 JSON을 붙여넣고
   \`요약 로컬 대조\`를 클릭한다.
5. 브라우저는 현재 조회한 Snapshot의 승인된 GET 미리보기와
   **주장된** Fingerprint/객체 수를 로컬 비교한다. 해당 요약은
   어떤 서버 API로도 전송·저장되지 않는다.

## 명확한 제한

- UI에 입력한 JSON은 신뢰할 수 없는 사용자 자료이며 화면은 메타데이터
  파일 자체를 재검증하지 않는다. 일치해도 결과명은
  \`FINGERPRINT_MATCH_UNTRUSTED\`이며, 실제 구조 일치 검증이 아니다.
- \`FINGERPRINT_DIFFERENCE_UNTRUSTED\`, \`COUNT_CONFLICT_UNTRUSTED\`,
  \`SUPERSEDED\`, \`OUT_OF_SCOPE\`, \`SNAPSHOT_PREVIEW_UNAVAILABLE\`을
  명시적으로 표시한다. 다른 Source/미검증 Snapshot은 동등 비교하지 않는다.
- 기존 내부 M2-1G 구조 Diff 서비스는 유지하지만 브라우저에서
  호출하는 API로 개방하지 않는다.
- 항상 \`preflight=NOT_VERIFIED\`, \`readiness=WARNING\`,
  \`catalog_ready=false\`, \`activation_eligible=false\`.
- 기존 S-05 API/Catalog 관리 권한·Snapshot 이력의 조회 가드를 유지한다.
  이번 기능에는 **파일 업로드/DB 쓰기/실제 DEMIS/정식 리뷰 승인 없음**.
- 임상정보 11종 고정이나 PACS 연계를 전제하지 않는다.

## 검증

Backend pytest: \`tests/test_m2_1h_offline_summary.py\` + M2-1D/E/F
Frontend vitest: \`src/test/OfflineMetadataSummary.test.tsx\` + 기존
\`SchemaSnapshotHistory.test.tsx\`
Frontend \`npm run build\`, \`npm run lint\` (격리 worktree에서 실행).

배포 및 UI 실접속은 별도 검증 후 단계이며 이 PR은 실제 운영 반입이 아니다.
