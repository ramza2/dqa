# M2-2E — 합성 Snapshot DOCX/ZIP 시각 품질 검증

## 목적과 상태

M2-2C(선택 테이블 DOCX)와 M2-2D(스키마 ZIP 분할 다운로드)는
합성 API/UI 테스트를 통과했지만 실제 한글·표·페이지 레이아웃은
아직 검증하지 않았다. M2-2E는 **운영 생성기/DB 접속 코드를 변경하지
않고** 실제 DOCX/ZIP QA 파일 생성·렌더링과 구조 검증을 추가한다.

## 합성 산출물

- single-table-standard.docx: 복합 FK, PK/UK, 인덱스가 있는 일반 샘플
- single-table-korean-stress.docx: 30컬럼, 반복된 한글 COMMENT와 긴 이름
- schema-batch-000.zip / schema-batch-002.zip: 총 3개 테이블의 분할 ZIP
- batch-001.docx ~ batch-003.docx: ZIP에서 추출한 테이블 분석서
- qa-manifest.json: DOCX 해시·크기·A4 여부·표 헤더 반복·ZIP 분할 증빙

개발용 tests FakeSession을 사용하므로 **실 DEMIS/Oracle/PostgreSQL,
환자기록, 실 의료기관 메타데이터를 읽지 않는다.** 이 QA 결과는
임의의 운영 Snapshot 승인 또는 Catalog READY 승격을 증명하지 않는다.

## 실행 방법

Backend 디렉터리에서 아래 Python 명령으로 파일 생성:
    ~/dqa/.venv/bin/python scripts/m2_2e_docx_layout_qa.py --out-dir artifacts/m2-2e-docx-qa

개발 장비에 LibreOffice가 있다면 다음 선택 스크립트로 PDF/PNG 렌더:
    PYTHON=~/dqa/.venv/bin/python bash scripts/m2_2e_render_docx_qa.sh artifacts/m2-2e-docx-qa

- LibreOffice가 없다면 합성 DOCX/ZIP만 생성하고 RENDER_SKIPPED 출력
- pdftoppm이 있으면 각 DOCX의 **모든 페이지 PNG**를 생성
- pdfinfo가 있으면 PDF별 페이지 수를 출력
- 설치가 필요한 경우 운영 서버에 설치하지 말고 별도 개발 장비에서
  Word나 LibreOffice로 DOCX를 열어 검사

## 육안 수용 기준

1. 모든 페이지의 한글·영문·화살표가 네모·깨진 글자로 대체되지 않음
2. A4 세로 표/열/글자가 페이지 바깥으로 잘리지 않음
3. 긴 컬럼명과 DB COMMENT가 겹치지 않고 읽을 수 있게 줄바꿈
4. 표가 여러 페이지로 넘어갈 때 헤더 반복과 페이지 나눔 자연스러움
5. 표지·장 제목·표 간격·불필요한 빈 페이지 없음
6. ZIP manifest의 파일 순번/테이블명/SHA256이 실제 DOCX와 일치

단순 DOCX 파싱이나 OOXML 구조 검사만으로 시각 QA PASS 판정 금지.
렌더링 후 **모든 페이지를 사람이 확인**하고 필요한 서식만 최소
패치한 뒤 다시 렌더링한다. 표/페이지 시각 검증은 이 PR만으로
완료되지 않으며 별도 수용 기록이 필요하다.

## 검증 범위

- tests/test_m2_2e_docx_layout_qa.py
- tests/test_m2_2d_schema_bundle.py, tests/test_m2_2c_snapshot_report.py
- 별도 외부 DB 연동 없음, 운영 배포 없음
- 구조 QA 산출물은 로컬 artifacts 아래 저장. 운영 API 자동 시작
  과정이나 Git 버전관리 대상에 포함시키지 않는다.
