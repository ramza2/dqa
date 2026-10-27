# M2-1A Explicit Target registration

Selected operator workflow: 대시보드 → DB 연결 관리 → 비활성 프로필 등록
→ 개발용 Oracle Mock 선택 → inspect visible non-secret settings → 저장
→ select profile → read-only Mock connection probe → explicit activation.

Only synthetic Mock is eligible for development probe/activation. Server
validates the full pinned target identity and environment/auth/feature gates,
injects env secret reference, rejects duplicates; no implicit target selection.
Generic profiles remain configuration-only. The legacy M1 quick-prepare API
remains for compatibility but is not used by the UI.

**Not part of M2-1A:** Profile→Inspector Target authorization, schema analysis,
Snapshot, Catalog Package v2 creation/READY activation, clinical rows, production
DEMIS, or any ModelOps/LLM integration. Separate Inspector metadata credentials
and DBA grants required for next M2-1B (isolated Mock first).
Real DEMIS approvals/DB source remain undecided.
