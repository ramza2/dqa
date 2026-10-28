import { useEffect, useRef, useState } from "react";
import { getSnapshotErd } from "../api/schemaSnapshot";
import type { SnapshotErdResponse, SnapshotSummary } from "../types/schemaSnapshot";
import { readSnapshotWithDeadline } from "../utils/snapshotPanelDeadline";

const PAGE_SIZE = 30;

function valid(
  value: SnapshotErdResponse,
  snapshot: SnapshotSummary,
  focus: { schema: string; table: string } | undefined,
  offset: number,
): boolean {
  return value.source_name === snapshot.source_name
    && value.revision_id === snapshot.id
    && value.schema_fingerprint === snapshot.schema_fingerprint
    && value.preflight_status === "NOT_VERIFIED"
    && value.activation_eligible === false
    && Number.isInteger(value.total_tables) && value.total_tables >= 0
    && value.offset === offset && value.limit === PAGE_SIZE
    && Array.isArray(value.tables) && value.tables.length <= PAGE_SIZE
    && value.tables.every(t =>
      typeof t.schema_name === "string" && typeof t.table_name === "string")
    && Array.isArray(value.edges) && value.edges.length <= 40
    && Number.isInteger(value.total_edges) && value.total_edges >= value.edges.length
    && value.edges.every(e =>
      (e.direction === "IN" || e.direction === "OUT")
      && typeof e.source_schema === "string" && typeof e.source_table === "string"
      && typeof e.target_schema === "string" && typeof e.target_table === "string"
      && typeof e.constraint_name === "string"
      && typeof e.referenced_only === "boolean"
      && Array.isArray(e.column_mapping)
      && e.column_mapping.every(c =>
        typeof c.source === "string" && typeof c.target === "string"))
    && value.focus_schema === (focus?.schema ?? null)
    && value.focus_table === (focus?.table ?? null);
}

export function SnapshotErdPanel({ snapshot }: { snapshot: SnapshotSummary }) {
  const [text, setText] = useState("");
  const [query, setQuery] = useState("");
  const [offset, setOffset] = useState(0);
  const [data, setData] = useState<SnapshotErdResponse | null>(null);
  const [status, setStatus] = useState<"idle" | "loading" | "ready" | "error">("idle");
  const sequence = useRef(0);

  // Parent uses Source/Revision/Fingerprint as the component key.
  useEffect(() => () => { sequence.current += 1; }, []);

  const load = async (q: string, nextOffset: number, focus?: { schema: string; table: string }) => {
    const id = ++sequence.current;
    setStatus("loading");
    setData(null);
    try {
      const result = await readSnapshotWithDeadline(signal => getSnapshotErd(
        snapshot.source_name, snapshot.id,
        { q, offset: nextOffset, limit: PAGE_SIZE,
          focusSchema: focus?.schema, focusTable: focus?.table },
        { signal },
      ));
      if (sequence.current !== id) return;
      if (!valid(result, snapshot, focus, nextOffset)) {
        setStatus("error");
        return;
      }
      setQuery(q);
      setOffset(nextOffset);
      setData(result);
      setStatus("ready");
    } catch {
      if (sequence.current === id) setStatus("error");
    }
  };

  return (
    <section className="dd-index-section" aria-label="Snapshot ERD 미리보기"
      data-testid="snapshot-erd-panel">
      <h3>Snapshot ERD 미리보기</h3>
      <div className="banner banner-warn">
        미승인 메타데이터 · 독립 DBA Preflight NOT_VERIFIED.
        이 ERD는 Catalog READY·활성화 또는 DEMIS 조회 권한을 뜻하지 않습니다.
      </div>
      <form className="dd-search-form" onSubmit={event => {
        event.preventDefault();
        void load(text.trim(), 0);
      }}>
        <label className="dd-field">
          <span>테이블 이름 검색</span>
          <input aria-label="Snapshot ERD 테이블 검색" maxLength={128}
            value={text} onChange={event => setText(event.target.value)}
            placeholder="예: TB_PATIENT" />
        </label>
        <button type="submit" className="dd-secondary-btn">ERD 테이블 조회</button>
      </form>
      {status === "loading" ? <p role="status">ERD 조회 중…</p> : null}
      {status === "error" ? (
        <div role="alert" className="banner banner-error">
          ERD 조회 실패, 시간 초과 또는 Source/Revision/Fingerprint 정합성 오류입니다.
        </div>
      ) : null}
      {data ? (
        <>
          <p className="dd-guidance">
            검색 대상 {data.total_tables}개 · 최대 {PAGE_SIZE}개씩 표시
          </p>
          {data.tables.length === 0 ? <p>검색된 테이블이 없습니다.</p> : (
            <div className="qa-result-table-wrap">
              <table className="qa-result-table">
                <thead><tr><th>Schema</th><th>Table</th><th>FK 관계</th></tr></thead>
                <tbody>{data.tables.map(t => (
                  <tr key={t.schema_name + "." + t.table_name}>
                    <td>{t.schema_name}</td><td>{t.table_name}</td>
                    <td><button type="button" className="dd-secondary-btn"
                      aria-label={"ERD 테이블 " + t.schema_name + "." + t.table_name}
                      onClick={() => void load(query, offset, { schema: t.schema_name, table: t.table_name })}>
                      관계 보기
                    </button></td>
                  </tr>
                ))}</tbody>
              </table>
            </div>
          )}
          <div className="dd-action-row">
            <button type="button" className="dd-secondary-btn" disabled={offset === 0}
              onClick={() => void load(query, Math.max(0, offset - PAGE_SIZE))}>이전 페이지</button>
            <button type="button" className="dd-secondary-btn"
              disabled={offset + PAGE_SIZE >= data.total_tables}
              onClick={() => void load(query, offset + PAGE_SIZE)}>다음 페이지</button>
          </div>
          {data.focus_schema && data.focus_table ? (
            <section className="section" aria-label="Snapshot FK 관계">
              <h4>{data.focus_schema}.{data.focus_table} — 1단계 FK {data.total_edges}건</h4>
              {data.edges_truncated ? (
                <p role="status" className="banner banner-warn">
                  최대 40개 FK만 표시하므로 전체 관계가 아닐 수 있습니다.
                </p>
              ) : null}
              {data.edges.length === 0 ? <p>표시 가능한 FK가 없습니다.</p> : (
                <ul className="erd-list">
                  {data.edges.map((e, i) => (
                    <li className="erd-edge" key={e.constraint_name + ":" + i}>
                      <strong>{e.source_schema}.{e.source_table} → {e.target_schema}.{e.target_table}</strong>
                      <div className="erd-edge-meta">
                        {e.direction === "OUT" ? "나가는 참조" : "들어오는 참조"}
                        {" · "}{e.constraint_name}
                      </div>
                      <div className="erd-edge-meta">
                        {e.column_mapping.map(c => c.source + " → " + c.target).join(", ")}
                      </div>
                      {e.referenced_only ? (
                        <span className="badge badge-warn">Snapshot 외부 참조 · 권한 미확인</span>
                      ) : null}
                    </li>
                  ))}
                </ul>
              )}
            </section>
          ) : null}
        </>
      ) : null}
    </section>
  );
}
