# Cursor Handoff Guide

## 1. Before implementation

Open the repository root in Cursor.

The repository already contains:
- root `AGENTS.md`
- scoped backend/frontend `AGENTS.md`
- `.cursor/rules/*.mdc`
- architecture/security/package/roadmap documents

Do not paste those rules into every prompt.
Ask Cursor to read and follow them.

## 2. Recommended first Cursor task

Use this after the bootstrap PR is merged:

```text
이 저장소는 DEMIS Query Assistant(DQA) 프로젝트다.

작업을 시작하기 전에 다음을 먼저 읽어라.

- AGENTS.md
- backend/AGENTS.md
- frontend/AGENTS.md
- .cursor/rules/*
- docs/architecture.md
- docs/catalog-package-contract.md
- docs/security.md
- docs/roadmap.md

이번 작업은 docs/roadmap.md의 "PR 2 - Backend application skeleton"만 수행한다.

요구사항:
1. FastAPI 애플리케이션 기본 구조를 만든다.
2. Python 3.11+ 기준으로 구성한다.
3. Settings/Pydantic 기반 환경설정을 구성한다.
4. PostgreSQL SQLAlchemy 연결 기본 구조를 만든다.
5. /health API를 만든다.
6. pytest 기본 테스트와 health 테스트를 만든다.
7. Docker 개발용 backend 기본 구조를 준비한다.
8. 아직 Catalog Package import, Query Template, LLM, DEMIS DB 실행 기능은 구현하지 않는다.
9. 기능 브랜치에서 작업하고 PR을 생성하되 머지하지 않는다.
10. 작업 완료 후 변경 파일, 테스트 결과, 알려진 제한사항을 보고한다.

구현 전에 기존 파일과 AGENTS.md를 확인하고 간단한 작업 계획을 먼저 제시한 후 진행해라.
```

## 3. Recommended task discipline

One Cursor conversation/task should normally correspond to one roadmap PR.

Avoid prompts such as:
- "전체 DQA를 구현해줘"
- "Text-to-SQL부터 만들어줘"
- "LLM이 SQL 만들어 실행하게 해줘"

Prefer:
- one bounded feature
- explicit non-goals
- required tests
- PR creation without merge
- runtime validation after local/static validation

## 4. Review checklist after each Cursor PR

Before merge, verify:

- scope matches the requested roadmap PR
- no unrelated refactor
- AGENTS.md/security rules respected
- no secrets committed
- tests added
- focused tests pass
- relevant regression tests pass
- runtime validation performed when applicable
- PR remains unmerged until explicit approval

## 5. When implementation reaches live DEMIS connectivity

Before allowing Cursor to implement actual query execution, provide or confirm:

- actual DBMS/driver requirements
- read-only account constraints
- connection method
- allowed network route
- timeout policy
- maximum row limit
- approved Query Template examples
- audit requirements

Do not let mock schema/table names become production constants.
