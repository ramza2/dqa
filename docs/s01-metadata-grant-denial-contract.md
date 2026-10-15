# S-01-B — Oracle Inspector 최소권한 Dictionary 조회·거부 회귀 계약 (합성)

> **2026-10-15 / 개발 전용 수용 기준선.**
> 이 문서는 Oracle/DEMIS 운영 계정 권한, 스키마 가시성 및 외부 DBA 승인을
> 증명하지 않는다. 모든 실행 증거는 Synthetic FakeConnection 또는 in-memory
> SQLite stub이다. 진짜 Oracle 계정·호스트·환자 데이터를 사용하지 않는다.

## 1. Inspector 동작 기준선

- 기존 `OracleSchemaInspector`는 읽기 전용 트랜잭션
  `SET TRANSACTION READ ONLY` 이후 고정된 Oracle `ALL_*` 사전 View만
  `SELECT`한다. 스키마는 SQL 문자열에 끼워 넣지 않고 bind `:schema`를 사용한다.
- Inspector 호출은 관리자 `CATALOG_MANAGE`와 서버 설정 Target으로 제한.
  Inspector와 일반 Read Query Credential 참조 접두사는 S-01-A에서 분리했으며,
  **계정명·접두사가 다르다는 사실만으로 실제 DB 최소권한이 입증되지 않는다.**
- Dictionary SELECT는 임상 테이블의 Row SELECT가 아니다. 그러나 Dictionary
  가시성은 사용자 Grant/Role/대상 Schema에 따라 달라질 수 있어,
  성공한 빈 결과도 “정상적으로 모든 스키마가 보였다”는 보증이 아니다.

## 2. 허용 Dictionary View (현 구현 정적·합성 계약)

| 조회 View | Inspector 용도 | 합성 검증 |
|---|---|---|
| `ALL_TABLES` | 가시 스키마 목록·테이블 | 조회 경계·Schema 바인딩 |
| `ALL_TAB_COMMENTS` | 테이블 주석 | join된 Dictionary View 인벤토리 |
| `ALL_TAB_COLUMNS` | 컬럼 속성 | READ ONLY·조회 권한 거부 |
| `ALL_COL_COMMENTS` | 컬럼 주석 | join된 Dictionary View 인벤토리 |
| `ALL_CONSTRAINTS` | PK·UK·FK 관계 | READ ONLY·조회 권한 거부 |
| `ALL_CONS_COLUMNS` | 제약 컬럼 순서 | join된 Dictionary View 인벤토리 |
| `ALL_INDEXES` | Index 메타데이터 | READ ONLY·조회 권한 거부 |
| `ALL_IND_COLUMNS` | Index 컬럼 순서 | join된 Dictionary View 인벤토리 |

**테스트 계약:** 실제 코드의 `FROM/JOIN ALL_*` 참조 집합과 위 8개
View 목록이 **완전 일치**해야 한다. View 추가·제거 시 기존 테스트가
실패하므로 변경의 리뷰 및 DBA 대상 Scope 재협의가 필요하다.
임상 Table, `DBA_*`, `USER_*`, 임의 `SYS` 자료 조회는 위 검증 범위 밖이다.

## 3. Fail-closed 검증·한계

| 테스트 상황 | 예상 동작 | 의미 |
|---|---|---|
| READ ONLY 시작 실패 | Dictionary SELECT 0건, Snapshot 생성 실패 | 방어선 선행 조건 |
| `ALL_TABLES` 조회 거부 | 즉시 실패, 연결 종료 | 불완전한 수집이 성공으로 넘어가지 않음 |
| `ALL_TAB_COLUMNS` 조회 거부 | 즉시 실패, 연결 종료 | 필수 컬럼 메타 누락 |
| `ALL_CONSTRAINTS` 조회 거부 | 즉시 실패, 연결 종료 | PK/UK/FK 불완전 |
| `ALL_INDEXES` 조회 거부 | 즉시 실패, 연결 종료 | Index 정보 불완전 |
| ADMIN 외 계정 | HTTP 403, Inspector 호출 없음 | 인증·인가 실행 경계 |
| Oracle 권한 예외 | HTTP 502 `INSPECTOR_METADATA_FAILED`, 원문 오류·Host/Secret 미반환 | 비밀 보호, 허위 `VERIFIED` 없음 |

**주의:** Oracle `ALL_*`는 권한 부족 시 반드시 예외를 던지는 것이
아니라 보이는 객체를 줄이거나 0건으로 응답할 수 있다.
현재 Inspector의 합성 SELECT 성공·건수 결과만으로 **권한충족 PASS,
실제 스키마 전체 포괄, 유효한 Preflight, READY 활성화**를 판정하지
않는다. 실제 DBA는 허용 Source/Schema·원본 기준 객체 건수·Grant/Role 및
권한 검증 기록을 별도로 제출해야 한다.

## 4. 실기관 DB 권한 검증 시 필요한 외부 의사결정 (미확정)

| 항목 | 요청 증빙 | Gate |
|---|---|---|
| 메타데이터 전용 Oracle 계정 | 관리자/쓰기/환자데이터 Read/불필요 EXECUTE 권한이 없다는 DBA 공식 확인; 역할·간접 Grant 포함 | G0 / DEC-01 |
| Query Reader와 격리 | Oracle 실제 account identity와 Grant/Role·Proxy 분리 및 Credential 유통/보관 정책 | G0 / DEC-01 |
| 대상 Scope | DBA 승인 Schema/Source, 8개 `ALL_*` 가시성, 예상 테이블/컬럼/PK/FK/Index 건수 대조 | G0·G1 |
| 운영 승인을 나타내는 증빙 | 발급자 신뢰, 서명·해시·범위·만료·철회·재검증 정책 | G0 / DEC-02 |
| 실제 DEMIS 첫 조회·접속 | 별도 운영 IdP, 네트워크/TLS, 최소 Read grant, 감사 및 실증 승인 | G2 |

모든 승인 항목은 여전히 `PENDING`. 외부 승인 참조만 안전한 내부
문서관리 시스템에 기록하고 실제 Host/IP, 계정명, DSN, Secret, 임상정보는
Issue/PR/로그에 입력하지 않는다.

## 5. 서버 Acceptance

```bash
cd ~/dqa && git fetch origin && \
git worktree add --detach /tmp/dqa-s01b-review \
  origin/test/s01-metadata-grant-denial-contract && \
(
  cd /tmp/dqa-s01b-review/backend && \
  ~/dqa/.venv/bin/python -m pytest -q -rs \
    tests/test_s01_metadata_grant_denial_contract.py \
    tests/test_s01_inspector_target_policy.py \
    tests/test_schema_inspector_oracle.py \
    tests/test_schema_inspector_admin.py
) && \
git -C /tmp/dqa-s01b-review diff --check 92801e0 HEAD && \
echo "DQA_S01B_METADATA_GRANT_PASS"
```

**수용 조건:** Dictionary 조회 목록 고정/READ ONLY 선행, 단계별 거부 시
즉시 중단·연결 종료, HTTP 오류 원문·Secret 비노출, 관리자 외 실행 불가.
이는 **개발 회귀 검증 성공**이며 G0/G1/DBA 실기관 승인이 아니다.
