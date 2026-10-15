# S-03-A — 저장된 Schema Snapshot → v2 WARNING 후보 ZIP (내부 연결)

> **2026-10-15 / 개발·합성 검증 범위.** 운영 Catalog 발행/Import/READY
> 승격과는 별개다. 실제 DEMIS, Oracle, 임상 데이터 접근이나 기관 승인 없음.

## 목적과 현재 경계

기존 구현에는 관리자 한정 Oracle metadata Inspector, append-only Schema
Snapshot 이력, Diff/Review 및 순수 `build_catalog_v2_candidate` 생성기가 존재한다.
`preview_snapshot_review`는 무결성 확인과 v2 `WARNING` 후보 검증만
수행하며 ZIP 내용은 반환하지 않는다.

이번 단계의 **내부 함수**
`build_latest_snapshot_warning_candidate(session, source_name, revision_id)`는
검증을 통과한 최신 Source Snapshot에 대해서만 v2 후보 ZIP bytes,
SHA-256 및 Source/Revision/Fingerprint 식별값을 반환한다.

- 저장된 행은 항상 `source_name`과 `revision_id`로 제한해 조회한다.
- 기존 `preview_snapshot_review`로 Snapshot 본문, Counts, Fingerprint,
  이전 Revision Diff 및 v2 Candidate를 먼저 재검증한다.
- 이전/대체된 Revision이면 `SNAPSHOT_CANDIDATE_SUPERSEDED`로 거부한다.
- 저장된 대상 식별자와 결과 ZIP의 Source/Schema/Fingerprint,
  `package_readiness=WARNING` 및 `activation_eligible=false`를 재검증한다.
- ZIP 생성 전후 최신 Revision·Fingerprint·Capture Time을 재조회하여
  후보 생성 중 신규 Capture가 발생하면 **결과를 폐기**한다.
- 오류에 임상 데이터, Oracle 메타데이터, DB 오류·비밀정보 원문을 포함하지
  않고 `SNAPSHOT_CANDIDATE_UNVERIFIABLE`로 차단한다.
- **업무 DB write, Catalog import/activation, Oracle 연결, HTTP Download API,
  관리자 승인 이벤트나 `READY` 발급 기능은 추가하지 않는다.**
- 반환 ZIP에는 스키마/컬럼 주석 등 제한된 메타데이터가 포함될 수 있다.
  내부 서비스의 임의 호출자에게 공개하거나 Logging/LLM egress하지 않는다.
  향후 외부로 제공하려면 별도 권한·감사·패키지 유출방지 검토가 필요하다.

## 기존 Catalog와의 분리

| 단계 | 개발 검증 상태 | 운영 권한 |
|---|---|---|
| Metadata-only Inspector → append-only Snapshot | 기본 비활성 구현, Synthetic 검증 | 실 DEMIS Metadata 권한 미승인 |
| Snapshot 검증·Diff/Review | 저장행 무결성/Source/이력 검증 | DBA 독립 Preflight와 다름 |
| Snapshot → v2 Candidate | 본 PR의 내부 ZIP 생성 및 재검증 | 항상 `WARNING`; 활성화 불가 |
| 독립 외부 Preflight 검증·READY 발급 | 발급자/증빙 신뢰 정책 미확정 (#77 Draft) | **미승인** |
| Package v2 Import 및 수동 READY Activation | 기존 일반 경로 사용 가능 | WARNING 후보를 READY로 승격할 수 없음 |
| PoC Legacy 운영 종료 및 실 Schema Cutover | U-02 합성 기준선만 존재 | G1/G5 서면 수용 후 |

기술적 Snapshot 완료·Diff 동일·Mock 권한 통과는 실제 DBA/기관의 권한 및
정확한 Scope/가시성 검증 완료를 의미하지 않는다. `ALL_*`는 일부
객체가 조용히 보이지 않을 수 있으므로 별도 실제 Source/Schema parity가
필요하다. 미래 승인 전에는 외부용 READY Package 변환을 구현하지 않는다.

## 수용 테스트 (서버 검증 요청, 아직 미실행)

```bash
cd ~/dqa && git fetch origin && \
git worktree add --detach /tmp/dqa-s03a-review \
  origin/feat/s03-snapshot-warning-candidate-internal && \
(
  cd /tmp/dqa-s03a-review/backend && \
  ~/dqa/.venv/bin/python -m pytest -q -rs \
    tests/test_s03_snapshot_warning_candidate.py \
    tests/test_schema_snapshot_review.py \
    tests/test_schema_catalog_candidate.py \
    tests/test_schema_snapshot_history.py \
    tests/test_schema_preflight_snapshot.py
) && \
git -C /tmp/dqa-s03a-review diff --check 47b8365 HEAD && \
echo "DQA_S03A_WARNING_BRIDGE_PASS"
```

**수용 조건:** 최신 Snapshot만 source-bound ZIP 생성, 원본 Capture 불변,
생성 ZIP v2 validator PASS/WARNING/non-activatable, tampering/대체 Capture
fail-closed. 전 과정은 FakeSession+메모리 기반이며 운영 DEMIS 무접속.
