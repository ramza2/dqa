# M2-3B — CPU 키워드 검색 합성 Gold 품질 회귀 (2026-10-28)

## 목적

M2-3A 복합 검색어 후보 우선순위의 결과를 수치화하여 작은 회귀
기준선으로 보존한다. 기존 S-06-A/B의 일회용 PostgreSQL Gold 평가는
별도의 통합 경로이다. 본 테스트는 이 평가를 대체하지 않는다.

## 범위

- 새 파일: backend/tests/test_m2_3b_keyword_quality_gold.py
- 실제 제품 Backend, API, DB migration 또는 설정 파일은 수정하지 않는다.
- SQLAlchemy SQLite 인메모리에서 합성 TABLE/COLUMN 검색 문서 생성,
  기존 keyword_search 호출 (Embedding/LLM 호출 없음).
- 검색어 8개: 검사 결과, 환자 방문, 진료 검사, 처방 약물,
  TB_LAB_RESULT, 간수치, 혈당, GLUCOSE.
- 검사 결과에 정답 2개를 설정해 다중 정답도 측정한다.
- 후보 상한 3에서 Recall@1/Recall@3/MRR@3 및 질의별 결과 검사.
- 합성 회귀 목표: macro Recall@1 >= 0.93,
  macro Recall@3 = 1.0, MRR@3 = 1.0.
- 입력 순서 역전 시 결과 동일성, 타 Revision/타 객체 종류 제외,
  미존재 검색어 무결과, 지표 자체의 분모/역순위 검사.

## 지표

Recall@k = 상위 k개 검색 결과에 포함된 정답 수 / 전체 정답 수.
Reciprocal Rank@k = 상위 k에 처음 등장하는 정답의 순위 역수, 없으면 0.
MRR@k = 모든 Gold 질의의 Reciprocal Rank@k 평균.
Macro Recall@k = Gold 질의별 Recall@k 평균.

위 지표는 인위적으로 정의한 합성 레이블과 키워드 검색 코드만
평가한다. 실제 군 DEMIS 규모/한국어 의학용어 검색 품질,
의료기록 적절성, GPU·CPU 임베딩 품질 또는 운영 지연을 나타내지 않는다.
실기관 G1 검사/DBA 승인 및 Schema/Table Scope 결정은 별개다.

## 수용 명령

격리 Worktree의 backend 폴더에서 다음 명령을 실행한다.

    ~/dqa/.venv/bin/python -m pytest -q -s tests/test_m2_3b_keyword_quality_gold.py tests/test_m2_3a_keyword_multiterm.py

실행 시 각 질의의 R1, R3, RR3와 M2_3B_GOLD_SUMMARY 출력을 확인한다.
실제 Oracle/DEMIS/운영 PostgreSQL 연결·쓰기, API/스키마 변경,
Catalog READY/Activation, 모델 다운로드나 네트워크는 수행하지 않는다.
서버 검증이 완료되기 전에는 품질 PASS를 주장하지 않는다.
