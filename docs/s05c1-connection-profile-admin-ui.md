# S-05-C1 — Connection Profile 관리자용 설정 관리 UI

기준 `main@65df930` (P30-A/B/C 머지 후). **S-05-C1은 기존 Backend API를 재사용하는 Frontend 변경만 포함**한다.

## 1. 목적과 기능

- 기존 DQA 상단 메뉴에 **Connection Profiles** 추가
- Backend `GET /api/v1/connection-profiles`: Source/Environment 정확일치 필터, 20건 페이지네이션, 수동 재조회
- `GET /{id}`: 상세 메타데이터 (Name/Source/Environment/DBMS/Host/Port/Database/Username)
- `GET /{id}/diagnostics`: **설정 수준만** 진단 (자격증명 참조 설정 여부, 대상 Host/Port 메타데이터 설정 여부, 이슈 코드)
- `POST /`: 신규 등록. 기존 Backend가 **무조건 disabled 생성**
- `PATCH /{id}`: 이름·DBMS·Host·Port·Database·Username **변경된 필드만** 업데이트. Source/Environment는 변경 불가. 활성 프로필은 UI에서 편집 불가(비활성 후 수정).
- `POST /{id}/disable`: 기존 활성 프로필에서 관리자 명시적 확인 후에만 실행
- 목록/상세/진단 조회가 겹치면 이전 Source·Profile 응답을 적용하지 않도록 React Effect cleanup으로 stale 응답 차단
- 403/404/409/422/5xx API 오류는 화면에서 고정 안내문으로 처리. 서버 예외·참조 문자열 등 임의 응답문구 노출 금지

## 2. 보안·접속/승인 경계

**이 UI에는 다음 기능이 없다.**

1. `POST /{id}/enable`: **비노출·미호출**
2. `POST /{id}/test-connection`: **비노출·미호출** — 기존 API는 실제 DB 연결을 시도하므로 임의 사용 금지
3. `credential_secret_ref` 입력/출력·복사·수정: **비노출·미전송**. 화면은 설정 여부 Boolean만 표시. 실제 암호/토큰 입력 UI도 없음.
4. DEMIS/Oracle 쿼리/Schema Inspector/승인 Preflight/Oracle Credential Resolver/환자정보 조회
5. 개별 Target의 승격·활성화 또는 자동 재시도·자동 연결

Backend는 `CONNECTION_PROFILE_MANAGE` 권한을 모든 Profile Endpoint에서 검사한다. Frontend는 인증·승인을 대신하지 않으며 비권한 사용자는 403 안내를 본다. 기존 Backend에는 활성화/접속 시험 API가 **여전히 존재**하며, 이 PR은 UI에서만 호출을 배제한다. 전체 시스템 차단을 주장하지 않는다.

`CONFIGURED_ENABLED`는 **설정 메타데이터 상태이지 실제 접근 가능성/복제 DB 연결 승인/군 보안 통과를 의미하지 않는다**. 운영 EMR 직접 연결 금지·별도 복제 EMR DB 필요(2026.10.15 의무사 회의), DBMS·라이선스·접속 ACL·DBA 승인 미확정 원칙 유지.

## 3. 코드 및 수용 테스트

| 파일 | 범위 |
|---|---|
| `frontend/src/App.tsx` | 상단 Connection Profiles 탭 |
| `frontend/src/components/ConnectionProfilePortal.tsx` | 관리 목록·상세·설정 진단·생성·수정·비활성화 |
| `frontend/src/api/connectionProfiles.ts` | 메타데이터 관리 API(활성화·실접속 함수 정의 없음) |
| `frontend/src/api/client.ts` | 기존 auth/error 공통경계로 PATCH 추가 |
| `frontend/src/types/connectionProfile.ts` | 기존 Backend Schema와 일치하는 타입 |
| `frontend/src/App.css` | 테이블/상세/입력 UI |
| `frontend/src/test/ConnectionProfiles.test.tsx` | Mock HTTP 기반 5건 신규 테스트 |
| `docs/s05c1-connection-profile-admin-ui.md` | 설계/위험/검증 계약 |

테스트(실 DB, DEMIS, 네트워크 호출 없음):
- 메인 메뉴→목록→상세→Diagnostics, credential ref 비노출, live probe/enable 호출 없음
- 신규 등록은 `enabled=false`, secret reference 미전송. 변경된 필드만 PATCH, Source/Environment 변경 불가
- 활성 프로필 수정 차단, `window.confirm` 비활성화 거부/동의 분기
- 403 오류 메시지의 임의 문자열 미출력
- 이전 프로필 상세 응답이 늦게 돌아와도 새 선택을 덮지 않음

### 서버 Frontend 검증 — 아직 미실행

운영 서비스에는 아무것도 배포하지 않은 상태에서 별도 Git worktree로 검증:

```bash
cd ~/dqa && \
git fetch origin && \
git worktree add --detach /tmp/dqa-s05c1-review \
  origin/feature/s05c1-connection-profile-admin-ui && \
(
  cd /tmp/dqa-s05c1-review/frontend && \
  npm ci && \
  npm run build && \
  npm run lint && \
  npm test -- --run
) && \
git -C /tmp/dqa-s05c1-review diff --check 65df930 HEAD && \
echo "DQA_S05C1_REVIEW_PASS"
```

**PASS 출력 전 테스트 성공 주장 금지.** `npm run build`는 해당 worktree의 로컬 `dist/`만 생성하며 운영 Frontend 재빌드/Compose 재시작 없이 실행한다.

## 4. 다음 단계와 비범위

S-05-C2 기존 Inspector Target 통합은 별도 검토: 10/15 회의의 복제 DB 필수·운영 EMR 직접 연결 금지, R-01 사전접근승인/Preflight, SNUH.AI 승인 경계를 우선 확정해야 한다. 이 PR로 Source/Target을 자동 생성·승인·활성화하지 않는다.
