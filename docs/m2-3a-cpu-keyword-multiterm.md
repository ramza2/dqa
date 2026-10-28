# M2-3A — LLM/Embedding 없이 동작하는 복합 키워드 후보 우선순위

## 실제 보완한 문제

기존 Data Discovery keyword 검색은 (1) 정확한 물리명 (2) 원문
검색어 OR (3) 용어 확장 OR 순서로 최대 500개 후보를 모은다.
다수 테이블의 설명에 첫 검색어만 나타나면 정렬상 뒤에 있는
**모든 검색어가 들어간 대상**이 후보 제한으로 누락될 수 있다.

## 변경

- 기존 \`keyword_search\` 내부 후보 선정에 **2~6개 원문 검색어를
  모두 포함하는 문서**를 먼저 고르는 AND 계층을 추가한다.
- 각 검색어는 기존 5개 허용 필드(키/Schema/Table/Column/검색문)에
  대하여 OR 검사, 서로 다른 검색어 그룹은 AND로 결합한다.
- 선행 정확한 물리명 우선순위는 바꾸지 않는다.
- 1개 검색어 또는 7개 이상 검색어는 기존 OR 경로를 사용해
  쿼리 복잡도를 제한한다. 기존 original OR, expanded OR 보충 단계,
  가중치·점수·Top-k·API 계약은 유지한다.
- 기존 ILIKE escape + 바인딩을 재사용해 %/_ 와 주입형 입력도
  SQL 문법으로 실행하지 않는다.
- 새로운 Embedding/LLM 라이브러리, 모델 다운로드/설정, 네트워크 접근,
  Oracle/DEMIS 연결, Catalog/Query Template 승인 및 DB schema 변경 없음.

## 격리 수용

\`test_m2_3a_keyword_multiterm.py\`는 SQLAlchemy와 휘발성
**SQLite 메모리 DB**만 사용한다. 합성 "검사 결과" 검색에서
사전순으로 앞선 단일어 문서들이 후보를 채워도 두 단어를 모두 포함한
문서가 반환되는지 검사한다.

기존 DB/Oracle/운영 PostgreSQL 대상 테스트를 실행하지 않으며
주어진 파일이 실제 DEMIS 의료정보 구조에 대응한다고 주장하지 않는다.
스키마 범위, 데이터 사전/용어 Gold Set, 현장 G1 품질 수용은 별개다.
