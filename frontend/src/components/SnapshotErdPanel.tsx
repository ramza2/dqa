import { useEffect, useRef, useState } from "react";
import { getSnapshotErd, getSnapshotTableReportDocx, getSnapshotSchemaBatchZip } from "../api/schemaSnapshot";
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
  const [reportStatus, setReportStatus] = useState<"idle" | "loading" | "error">("idle");
  const [batchStatus, setBatchStatus] = useState<"idle" | "loading" | "error">("idle");
  const [batchSize, setBatchSize] = useState(5);
  const [batchProgress, setBatchProgress] = useState<{
    schema: string; lastOffset: number; nextOffset: number | null; total: number;
  } | null>(null);

  // Parent uses Source/Revision/Fingerprint as the component key.
  useEffect(() => () => { sequence.current += 1; }, []);

  const load = async (q: string, nextOffset: number, focus?: { schema: string; table: string }) => {
    const id = ++sequence.current;
    setStatus("loading");
    setData(null);
    // Invalidate any earlier report download state when the selected table changes.
    setReportStatus("idle");
    setBatchStatus("idle");
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

  const downloadReport = async (schema: string, table: string) => {
    const current = sequence.current;
    setReportStatus("loading");
    try {
      const blob = await readSnapshotWithDeadline(signal => getSnapshotTableReportDocx(
        snapshot.source_name, snapshot.id, schema, table, { signal },
      ));
      if (sequence.current !== current) return;
      const url = URL.createObjectURL(blob);
      try {
        const link = document.createElement("a");
        link.href = url;
        link.download = "dqa-snapshot-" + snapshot.id + "-table-analysis.docx";
        document.body.appendChild(link);
        link.click();
        link.remove();
      } finally {
        URL.revokeObjectURL(url);
      }
      setReportStatus("idle");
    } catch {
      if (sequence.current === current) setReportStatus("error");
    }
  };

  const downloadSchemaPart = async (schema: string) => {
    const token = sequence.current;
    const offset = batchProgress?.schema === schema
      ? (batchProgress.nextOffset ?? 0) : 0;
    setBatchStatus("loading");
    try {
      const result = await readSnapshotWithDeadline(signal => getSnapshotSchemaBatchZip(
        snapshot.source_name, snapshot.id, schema, offset, batchSize, { signal },
      ));
      if (sequence.current !== token) return;
      // These paging headers are informational and scoped to the requested part.
      if (result.nextOffset !== null &&
          (result.nextOffset <= offset || result.nextOffset > offset + batchSize)) {
        setBatchStatus("error");
        return;
      }
      const url = URL.createObjectURL(result.blob);
      try {
        const link = document.createElement("a");
        link.href = url;
        link.download = "dqa-snapshot-" + snapshot.id + "-schema-batch-" + offset + ".zip";
        document.body.appendChild(link);
        link.click();
        link.remove();
      } finally {
        URL.revokeObjectURL(url);
      }
      setBatchProgress({
        schema, lastOffset: offset,
        nextOffset: result.nextOffset,
        total: result.totalTables,
      });
      setBatchStatus("idle");
    } catch {
      if (sequence.current === token) setBatchStatus("error");
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
              <div className="dd-action-row">
                <button type="button" className="dd-secondary-btn"
                  disabled={reportStatus === "loading"}
                  onClick={() => void downloadReport(data.focus_schema!, data.focus_table!)}>
                  선택 테이블 DB 분석서 DOCX (관리자)
                </button>
                <span className="muted">선택 테이블 1개만 · 미승인 메타데이터 · 외부 공유 주의</span>

              <div className="dd-action-row">
                <label>
                  스키마 ZIP 묶음 크기
                  <select aria-label="스키마 ZIP 묶음 크기"
                    value={batchSize}
                    disabled={batchStatus === "loading"}
                    onChange={event => setBatchSize(Number(event.target.value))}>
                    <option value={1}>1개</option>
                    <option value={5}>5개</option>
                    <option value={10}>10개</option>
                  </select>
                </label>
                <button type="button" className="dd-secondary-btn"
                  disabled={batchStatus === "loading" || reportStatus === "loading"}
                  onClick={() => void downloadSchemaPart(data.focus_schema!)}>
                  스키마 DOCX 묶음 ZIP (관리자)
                </button>
                <span className="muted">
                  {data.focus_schema}의 모든 테이블을 이름순으로 나누어 다운로드 ·
                  파일별 manifest 포함 · 미승인 메타데이터
                </span>
              </div>
              {batchStatus === "loading" ? <p role="status">스키마 분석서 묶음 생성 중…</p> : null}
              {batchStatus === "error" ? (
                <p className="banner banner-error" role="alert">
                  스키마 분석서 묶음 다운로드 실패: 권한, 데이터 정합성 또는 허용 크기를 확인하세요.
                </p>
              ) : null}
              {batchProgress?.schema === data.focus_schema ? (
                <p className="dd-guidance" data-testid="schema-report-progress">
                  {batchProgress.lastOffset + 1}번째부터 다운로드 완료 /
                  스키마 전체 {batchProgress.total}개 테이블.
                  {batchProgress.nextOffset !== null
                    ? " 다음 묶음 시작: " + (batchProgress.nextOffset + 1) + "번째"
                    : " 마지막 묶음까지 완료. 다시 다운로드하면 처음부터 시작합니다."}
                </p>
              ) : null}

              </div>
              {reportStatus === "error" ? (
                <p className="banner banner-error" role="alert">
                  분석서 다운로드 실패: 관리자 권한 또는 Snapshot 상태를 확인하세요.
                </p>
              ) : null}
              {reportStatus === "loading" ? <p role="status">분석서 생성 중…</p> : null}
              {data.edges_truncated ? (
                <p role="status" className="banner banner-warn">
                  최대 40개 FK만 표시하므로 전체 관계가 아닐 수 있습니다.
                </p>
              ) : null}
              {data.edges.length === 0 ? <p>표시 가능한 FK가 없습니다.</p> : (
                <div className="erd-layout">
                  <div className="erd-side">
                    <h4>들어오는 FK</h4>
                    <ul className="erd-list">
                      {data.edges.filter(e => e.direction === "IN").map((e, i) => (
                        <li className="erd-edge" key={e.constraint_name + ":in:" + i}>
                          <strong>{e.source_schema}.{e.source_table}</strong>
                          <div className="erd-edge-meta">{e.constraint_name}</div>
                          <div className="erd-edge-meta">
                            {e.column_mapping.map(c => c.source + " → " + c.target).join(", ")}
                          </div>
                          {e.referenced_only ? (
                            <span className="badge badge-warn">Snapshot 외부 참조 · 권한 미확인</span>
                          ) : null}
                        </li>
                      ))}
                    </ul>
                    <span className="erd-arrow">→ 중심 테이블</span>
                  </div>
                  <div className="erd-center" aria-label="Snapshot 중심 테이블">
                    <span className="muted">Snapshot 선택 테이블</span>
                    <strong>{data.focus_schema}.{data.focus_table}</strong>
                  </div>
                  <div className="erd-side">
                    <h4>나가는 FK</h4>
                    <span className="erd-arrow">중심 테이블 →</span>
                    <ul className="erd-list">
                      {data.edges.filter(e => e.direction === "OUT").map((e, i) => (
                        <li className="erd-edge" key={e.constraint_name + ":out:" + i}>
                          <strong>{e.target_schema}.{e.target_table}</strong>
                          <div className="erd-edge-meta">{e.constraint_name}</div>
                          <div className="erd-edge-meta">
                            {e.column_mapping.map(c => c.source + " → " + c.target).join(", ")}
                          </div>
                          {e.referenced_only ? (
                            <span className="badge badge-warn">Snapshot 외부 참조 · 권한 미확인</span>
                          ) : null}
                        </li>
                      ))}
                    </ul>
                  </div>
                </div>
              )}
            </section>
          ) : null}
        </>
      ) : null}
    </section>
  );
}
