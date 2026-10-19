# S-06-C — Oracle Inspector → Snapshot Diff → v2 WARNING 후보 연계 합성 회귀

> 2026-10-19 / `main@6ae26e8` (S-05-K 머지·서버 소스 동기화 이후).
> U-02-A와 S-06-A/B의 별도 단위 검증을 실제 Oracle Dictionary **FakeEngine 기반
> 단일 연결 흐름**으로 보완한다. 운영 데이터나 외부 기관 승인과는 무관하다.

## 목적과 기존 증거의 간극

- U-02-A (#82)는 고정 Legacy Inspector와 DQA Inspector의 동일 합성 dictionary 응답에 대한
  메타데이터 동등성 및 Oracle READ ONLY 질의 정책을 검증했다.
- S-06-A에서는 DQA의 수제 합성 `SchemaSnapshot`에서
  Diff/내부 v2 `WARNING` 후보 Fingerprint를 검증했다.
- S-06-B에서는 검색 Gold 질의·FK 관계 조회를 합성 DB/Stub 기반으로 확대했다.
- **본 범위:** DQA **Oracle Inspector가 만든 실제 DTO**를 수정 없이
  Diff와 v2 후보 빌더에 전달해 동일 물리 Fingerprint/기본 안전성 불변식을
  확인한다. Fixture를 만드는 데는 U-02-A의 동일 합성 dictionary 행을 재사용하고,
  모의 composite FK가 유효하도록 TB_VISIT 쪽 컬럼 및 대상 composite UNIQUE
  컬럼을 **테스트 내부에서만** 보충한다.

## Acceptance 테스트 4건

1. **완전한 메타데이터 경로:** Synthetic `ALL_*` SELECT 6건/READ ONLY 1회 →
   2 Tables/4 Columns/Composite FK/Index → DQA Snapshot →
   Catalog Package v2 `WARNING`/비활성 → Diff 대상 Fingerprint 동일.
   JSON Manifest에서 business-data/credential/host export 제외도 확인.
2. **실질 주석 변경:** Table·Column Comment만 변경된 dictionary 행의
   Diff가 정확히 2건이어야 하며, 이전/현재 v2 후보의 물리 Fingerprint가
   각각 Diff의 source/target과 맞아야 한다.
3. **정렬 노이즈 제거:** Dictionary의 테이블/컬럼·FK 멤버/Index 반환 순서
   변경은 동일 Fingerprint와 Diff 0건으로 평가한다.
4. **거짓 Parity 차단:** 다른 Database 대상/명시적 Baseline 누락은
   예외로 실패시키며, `NO_BASELINE`을 동일성 근거로 가정하지 않는다.

## 배포·보안 경계

- 변경: `backend/tests/test_s06c_oracle_inspector_candidate_chain.py`와 본 문서만.
- 기존 U-02-A `tests/u02_oracle_parity_runner.py`의 순수 in-memory
  `FakeEngine` 및 합성 dictionary fixture 재사용. 타 Repo의 운영 소스
  Import/읽기, 실제 `DEMIS`/Oracle 접속, PostgreSQL, 인터넷·LLM 호출 없음.
- **실 환자/진료 데이터, 계정·비밀, Oracle Metadata 전체 범위, 임상 생성/Write,
  Catalog READY 발급/Import/Activation, 병원 권한·G1/G2/G5 인수 관련 동작 변경 없음.**
- `WARNING` 후보, Fake READ ONLY, 테스트 Fingerprint는
  **독립 DBA Preflight/READY/기관 승인과 동등하지 않다**.
- Legacy vs DQA 실제 인덱스/문서 검색 동등성이나 실 Oracle permission
  coverage/누락 객체 검사는 여전히 외부 G0/G1 수용 대상이다.

## 서버 Acceptance — 최종 PASS (2026-10-19)

- 서버 실제 검증 코드 HEAD **`9847710`**, 별도 detached Worktree `/tmp/dqa-s06c-review`,
  기준 `main@6ae26e8`.
- `python3 -m venv .venv` 및 `pip install -e '.[dev]'`: **PASS**.
- `python -m pytest -q`: **31 passed / 5 skipped / 0 failed**.
  S-06-C 신규 4건 포함. 5 SKIP은 Legacy 경로 `DQA_U02_LEGACY_ROOT`
  미제공 시 건너뛰도록 설계된 U-02-A 비교 테스트와 일치하지만,
  이번 로그는 `-rs` 출력이 없어 개별 SKIP 이유는 별도 확인하지 않았다.
- `git diff --check 6ae26e8 HEAD`: **PASS**.
  최종 마커 **`DQA_S06C_REVIEW_PASS`** 확인.
- 테스트 과정의 `StarletteDeprecationWarning` 1건은 비차단.
- 수용 기록은 이 **문서만 수정하는 후속 커밋**이다.
  서버 검증된 합성 Test 코드와 의존성은 변경하지 않는다.
- **실 Legacy parity 5건의 PASS 및 실 Oracle/DEMIS/G1/DBA Preflight/
  READY/Activation/운영 전환 승인으로 해석하지 않는다.**
  GitHub Actions CI 및 Docker 운영 배포도 이번 서버 수용에 포함되지 않는다.

## 서버 Acceptance — 실행 완료한 격리 Worktree 명령

기존 DQA `~/dqa`·Docker·DB·실 DEMIS를 건드리지 않는 detached Worktree의
**DB 미사용 Pytest**만 실행한다. DB-backed `db_session`/`db_client` fixtures는
기존 운영/개발 DB에서 `TRUNCATE`할 수 있어 여기서 실행 금지.

```bash
cd ~/dqa && git fetch origin && \
git worktree add --detach /tmp/dqa-s06c-review \
  origin/test/s06c-oracle-inspector-candidate-chain && \
(
  cd /tmp/dqa-s06c-review/backend && \
  python3 -m venv .venv && \
  .venv/bin/pip install -e '.[dev]' && \
  .venv/bin/python -m pytest -q \
    tests/test_s06c_oracle_inspector_candidate_chain.py \
    tests/test_u02_oracle_inspector_parity.py \
    tests/test_schema_snapshot_diff.py \
    tests/test_schema_catalog_candidate.py
) && \
git -C /tmp/dqa-s06c-review diff --check 6ae26e8 HEAD && \
echo DQA_S06C_REVIEW_PASS
```

**주의:** `test_u02_oracle_inspector_parity.py`의 Legacy/DQA 실행 비교는
`DQA_U02_LEGACY_ROOT`가 미설정이면 기존 의도대로 **SKIP**될 수 있다.
실제 Legacy 저장소가 존재한다는 가정 없이 결과에서 skip 수를 정확하게 보고한다.
`tests/test_schema_catalog_candidate.py` 및
`tests/test_schema_snapshot_diff.py`는 순수 오프라인 회귀이다.

서버 테스트 실행 로그와 최종 PASS 마커를 확인했으며 SKIP 5건은 PASS에 포함하지 않는다.
사용자 별도 명시 승인 전 Draft→Ready 여부와 관계없이 `main` Merge/운영 배포 금지.
