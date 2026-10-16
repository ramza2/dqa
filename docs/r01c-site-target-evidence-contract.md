# R-01-C — 복제 EMR DB 기관 확인 증빙 검토 계약 (오프라인 초안)

> 기준: `main@ec65e74`, 2026-10-16. `DEC-10` **미승인**.
> **이 변경은 군/병원·의료정보체계과의 승인 증빙을 검증하는 기능이 아니다.**
> 서명/발급자/철회 상태의 독립 검증과 실제 연결 허용은 구현하지 않는다.

## 1. R-01-B와의 차이

- R-01-B: `ConnectionProfileSnapshot` ↔ `SiteTargetExpectation`의
  **구조적 대상 식별값 동등 비교**. 모든 결과는 `connection_authorized=False`.
- R-01-C: 그 위에 **승인 증빙에 요구할 자료 항목과 시간/용도/범위 검토 규칙**을
  모델링한다. 발급자가 임의로 주장한 값만으로는 운영 EMR과 복제 EMR을 구분하거나
  실제 신뢰 가능한 서명을 증명할 수 없다.
- 두 단계는 모두 연결 허가 또는 실제 군/DBA 정책이 **아니다**.

## 2. 증빙 Envelope(잠정 데이터 계약)

`SiteTargetEvidenceDraft`의 주요 항목:

| 영역 | 필드 | 기준 및 현재 한계 |
|---|---|---|
| 문서 추적 | `evidence_id` | 서면 승인 기록 추적용 식별자(임의 문자열이며 원본 공문 아님) |
| 서명 발급자 | `issuer_id`, `key_id` | **신뢰된 Issuer/검증키가 현재 없음**. 입력 문자열은 신원 증거가 아님 |
| 대상 | `target` | R-01-B의 Profile/Source/Environment/DBMS/Host/Port/DB Service/계정 및 `REPLICA_EMR_READ` 목적 |
| 유효기간 | `issued_at`, `not_before`, `expires_at` | 시간대 명시 필수, 발급/시작/만료 논리 및 검사시각 확인. 기관 승인 유효기간 정책/최대 TTL은 **미정** |
| 서명 표현 | `signature` | 구조만 보유. **실제 서명 알고리즘·키/서명 검증 없음**. 예제/테스트 바이트는 절대 인증 근거가 아님 |
| 철회 진술 | `declared_revoked` | `True`면 보수적으로 거부. `False`는 독립 철회조회/폐기·키회전 확인이 **전혀 아님** |

사용자가 증빙 형태로 동일한 구조를 제출하더라도 **암호학적 진위,
기관 권한, 원본/복제 물리 경계, 네트워크 허용, Oracle License를 증명하지 못한다.**

### 2.1 검토 결과

`review_site_target_evidence(profile, evidence, now=aware_datetime)`
함수는 오직 오프라인 데이터 검토만 수행한다.

| 응답 코드 | 의미 |
|---|---|
| `EVIDENCE_MISSING` | 검토 문서 없음 |
| `CLOCK_INVALID`, `VALIDITY_WINDOW_INVALID` | 검사 시각/증빙 시각에 timezone이 없거나 시간 논리 불일치 |
| `EVIDENCE_INCOMPLETE` | 발급자·Key ID·문서 ID·서명 표현 또는 Target 누락 |
| `PURPOSE_NOT_REPLICA` | 운영 EMR 또는 UNKNOWN 목적 |
| `PROFILE_TARGET_NOT_MATCHED` | R-01-B의 Profile/Target 구조 검토 불일치/비활성 |
| `DECLARED_REVOKED` | 입력 기록 스스로 철회됐다고 표시 |
| `EVIDENCE_NOT_YET_VALID`, `EVIDENCE_EXPIRED` | 아직 유효시작 전이거나 경과. 만료시각 **동일 시각부터 만료** |
| `CLAIMS_MATCH_UNTRUSTED` | 입력 내부 일관성만 확인. **실제 승인 절대 아님** |

**모든 상태에서 `cryptographically_verified=False` 및
`connection_authorized=False`.** 결과 구조는 발급자/Target Host,
계정·서명 내용 없이 코드와 Boolean만 반환한다. 입력 Envelope 자체도
메타데이터가 포함될 수 있으므로 영구 저장·평문 로그/회신·대외 공개 금지.

## 3. 실제 정책·승인 연결 금지

- 기존 `backend/app/services/replica_target_screening.py` 및
  Read Query/Preview/Eligibility/MCP, Inspector, Connection Profile,
  Credential Resolver, Oracle adapter, Catalog/READY는 **변경·연계하지 않음**.
- 미승인된 동적 Host/IP/DB Service, 실제 계정·환자 데이터, 실제 증빙/서명키,
  서버 비밀번호, VPN·방화벽 설정을 코드/테스트에 기록하거나 실조회하지 않음.
- `CLAIMS_MATCH_UNTRUSTED`를 ‘승인 완료’, ‘복제 DB 인증’,
  ‘보안정책 적용’, ‘접근 허용’으로 표현하는 UI/API 사용 금지.
- 기관 서명 없이 Reviewer의 입력 검토만으로 운영 DB 차단을 보장할 수 없다.

## 4. DEC-10 이후 실운영 준비 조건(미구현)

1. **의료정보체계과/DEMIS 운영사/DBA**가 복제 EMR DB와 원본 운영 EMR의
   물리/논리 경계, 승인 Source, 목적, Reader 계정·인증 방식, 데이터 Scope를
   **서면 승인**.
2. 기관과 합의한 증빙 발행자 신원·서명 포맷/알고리즘, 검증키의 독립
   Trust Store 배포·회전/폐기, 증빙 버전 및 최대 유효기간 확정.
3. 승인된 Scope에 대한 `Source+Environment+Profile+Target+권한`
   binding; 철회·만료·키회전 시 세션 재평가/차단 기준 및 감사 설계.
4. DNS/VIP/실 IP·서비스 Alias/방화벽 Egress 원본 DB 차단의 독립 검증,
   복제본 변경·장애·전환 시 안전한 fail-closed 동작 확인.
5. Oracle DB/복제 License, HA/백업, 기관/운영사 담당과 비용 확인.
6. 이후 별도 **실행 차단 Gate 구현 PR + 승인된 통합검증**으로만
   실제 Source 변경/연결 허용 정책을 연결.
7. **임상 원장 Write는 별도 DEC-09/G4**이며 위 read 승인과 무관.

상기 항목은 제안된 **승인 증빙 수집 체크리스트**이며, 아직 수령·검증된
자료는 없다. 더 자세한 기관 질문은 `docs/u01-replicated-emr-db-architecture-review.md`
의 **P0-Q01~Q04, P0-Q06, P1-Q07~Q09** 참조.

## 5. 테스트/서버 Acceptance

변경 파일 4개(모두 신규):
- `backend/app/services/site_target_evidence_review.py`
- `backend/tests/test_r01c_site_target_evidence_review.py`
- `scripts/dqa-r01c-offline-evidence-review-check.sh`
- `docs/r01c-site-target-evidence-contract.md`

```bash
cd ~/dqa && \
git fetch origin && \
git worktree add --detach /tmp/dqa-r01c-review \
  origin/feat/r01c-offline-site-evidence-review && \
(
  cd /tmp/dqa-r01c-review && \
  bash scripts/dqa-r01c-offline-evidence-review-check.sh
) && \
git -C /tmp/dqa-r01c-review diff --check ec65e74 HEAD && \
echo "DQA_R01C_REVIEW_PASS"
```

R-01-A 18건 + R-01-B 25건 + R-01-C 추가 검증을 동시에 실행하되,
**`db_session` fixture/실 DB 연결·운영 Docker 실행 없음**.
`DQA_R01C_OFFLINE_EVIDENCE_REVIEW_PASS`와
`DQA_R01C_REVIEW_PASS`가 모두 나오면 오프라인 검증 완료.
**테스트/CI 검증 전에는 Draft를 Merge하지 않는다.**
