import { useEffect, useRef, useState } from "react";
import {
  getSnapshotHistoryDetail, getSnapshotReviewPreview,
  listSnapshotHistory, listSnapshotReviewEvents,
} from "../api/schemaSnapshot";
import { CatalogApiError } from "../types/catalog";
import type {
  SnapshotDetail, SnapshotReviewEvent, SnapshotReviewPreview, SnapshotSummary,
} from "../types/schemaSnapshot";

type DataState<T> = {
  status: "idle" | "loading" | "ready" | "error";
  data: T | null;
  error: string | null;
};
const idle = <T,>(): DataState<T> => ({ status: "idle", data: null, error: null });
const loading = <T,>(): DataState<T> => ({ status: "loading", data: null, error: null });
const ready = <T,>(data: T): DataState<T> => ({ status: "ready", data, error: null });
const failed = <T,>(error: string): DataState<T> => ({ status: "error", data: null, error });

const SOURCE_PATTERN = /^[A-Za-z0-9][A-Za-z0-9_.:-]{0,254}$/;
const PAGE_SIZE = 50;

function errorText(error: unknown): string {
  if (error instanceof CatalogApiError) {
    return "HTTP " + error.status + (error.code ? " · " + error.code : "") + ": " + error.message;
  }
  return "요청을 완료하지 못했습니다. 잠시 후 다시 조회하세요.";
}

function dateLabel(value: string): string {
  const time = new Date(value);
  return Number.isNaN(time.getTime()) ? "—" : time.toLocaleString();
}

export function SchemaSnapshotHistory() {
  // Source may have Snapshots without an active Catalog. Direct entry does not
  // imply permission to access unapproved databases or elevate WARNING.
  const [sourceInput, setSourceInput] = useState("");
  const [source, setSource] = useState<string | null>(null);
  const sourceRef = useRef<string | null>(null);
  const listSeq = useRef(0);
  const detailSeq = useRef(0);

  const [offset, setOffset] = useState(0);
  const [history, setHistory] = useState<DataState<SnapshotSummary[]>>(() => idle<SnapshotSummary[]>());
  const [selection, setSelection] = useState<SnapshotSummary | null>(null);
  const [detail, setDetail] = useState<DataState<SnapshotDetail>>(() => idle<SnapshotDetail>());
  const [preview, setPreview] = useState<DataState<SnapshotReviewPreview>>(() => idle<SnapshotReviewPreview>());
  const [reviews, setReviews] = useState<DataState<SnapshotReviewEvent[]>>(() => idle<SnapshotReviewEvent[]>());

  useEffect(() => () => {
    listSeq.current += 1;
    detailSeq.current += 1;
    sourceRef.current = null;
  }, []);

  const resetDetail = () => {
    detailSeq.current += 1;
    setSelection(null);
    setDetail(idle());
    setPreview(idle());
    setReviews(idle());
  };

  const editSource = (next: string) => {
    listSeq.current += 1;
    sourceRef.current = null;
    setSourceInput(next);
    setSource(null);
    setHistory(idle());
    setOffset(0);
    resetDetail();
  };

  const loadHistory = async (nextSource: string, nextOffset: number) => {
    const requestId = ++listSeq.current;
    sourceRef.current = nextSource;
    setSource(nextSource);
    setOffset(nextOffset);
    setHistory(loading());
    resetDetail();
    try {
      const rows = await listSnapshotHistory(nextSource, nextOffset, PAGE_SIZE);
      if (requestId !== listSeq.current || sourceRef.current !== nextSource) return;
      if (!rows.every((row) => row.source_name === nextSource)) {
        setHistory(failed("Snapshot 응답의 Source가 요청과 일치하지 않습니다."));
        return;
      }
      setHistory(ready(rows));
    } catch (error) {
      if (requestId === listSeq.current && sourceRef.current === nextSource) {
        setHistory(failed(errorText(error)));
      }
    }
  };

  const openSnapshot = async (row: SnapshotSummary) => {
    if (!source || !history.data || !history.data.some((item) => item.id === row.id)) return;
    const requestId = ++detailSeq.current;
    const expectedSource = source;
    setSelection(row);
    setDetail(loading());
    setPreview(loading());
    setReviews(loading());

    // Three GET-only requests. Preview failure must not hide a readable Diff.
    const [detailResult, previewResult, reviewsResult] = await Promise.allSettled([
      getSnapshotHistoryDetail(expectedSource, row.id),
      getSnapshotReviewPreview(expectedSource, row.id),
      listSnapshotReviewEvents(expectedSource, row.id),
    ] as const);
    if (requestId !== detailSeq.current || sourceRef.current !== expectedSource) return;
    if (detailResult.status === "fulfilled") {
      const value = detailResult.value;
      setDetail(
        value.id === row.id
        && value.source_name === expectedSource
        && value.schema_fingerprint === row.schema_fingerprint
          ? ready(value)
          : failed("Snapshot 상세 정보의 Revision/Source/Fingerprint가 일치하지 않습니다."),
      );
    } else {
      setDetail(failed(errorText(detailResult.reason)));
    }
    if (previewResult.status === "fulfilled") {
      const value = previewResult.value;
      setPreview(
        value.revision_id === row.id
        && value.source_name === expectedSource
        && value.schema_fingerprint === row.schema_fingerprint
          ? ready(value)
          : failed("검토 미리보기의 Revision/Source/Fingerprint가 일치하지 않습니다."),
      );
    } else {
      setPreview(failed(errorText(previewResult.reason)));
    }
    if (reviewsResult.status === "fulfilled") {
      const values = reviewsResult.value;
      setReviews(
        values.every((value) => value.snapshot_revision_id === row.id
          && value.source_name === expectedSource
          && value.schema_fingerprint === row.schema_fingerprint)
          ? ready(values)
          : failed("변경 검토 이력의 Revision/Source/Fingerprint가 일치하지 않습니다."),
      );
    } else {
      setReviews(failed(errorText(reviewsResult.reason)));
    }
  };

  const status = <T,>(value: DataState<T>, label: string) => {
    if (value.status === "loading") return <p className="dd-guidance">{label} 조회 중…</p>;
    if (value.status === "error") return <div className="banner banner-error" role="alert">{value.error}</div>;
    return null;
  };

  return (
    <section className="dd-panel" data-testid="schema-snapshot-history">
      <header className="dd-panel-header">
        <h2>Schema Snapshot History</h2>
        <span className="subtitle">메타데이터 이력·변경 Diff · 조회 전용</span>
      </header>
      <div className="banner banner-warn" data-testid="snapshot-not-authority">
        Snapshot 검토 및 WARNING 후보 확인은 독립 DBA Preflight, Catalog READY 승인 또는 활성화를 의미하지 않습니다.
      </div>

      <form className="dd-search-form" onSubmit={(event) => {
        event.preventDefault();
        const name = sourceInput.trim();
        if (!SOURCE_PATTERN.test(name)) {
          setHistory(failed("Source 이름은 영문·숫자로 시작하고 영문·숫자·_·.·:·-만 허용합니다."));
          return;
        }
        void loadHistory(name, 0);
      }}>
        <div className="dd-form-row">
          <label className="dd-field">
            <span>Source name</span>
            <input
              aria-label="Snapshot source name"
              value={sourceInput}
              maxLength={255}
              onChange={(event) => editSource(event.target.value)}
              placeholder="예: oracle_demis_mock"
            />
          </label>
        </div>
        <button type="submit" className="dd-primary-btn">Snapshot 조회</button>
      </form>

      {status(history, "Snapshot 이력")}
      {history.status === "ready" && history.data?.length === 0 ? (
        <p className="dd-guidance">이 Source에 저장된 Snapshot이 없습니다.</p>
      ) : null}
      {history.status === "ready" && history.data && history.data.length > 0 ? (
        <section className="dd-index-section">
          <h3>Snapshot 이력 — {source} (페이지 {Math.floor(offset / PAGE_SIZE) + 1})</h3>
          <div className="qa-result-table-wrap">
            <table className="qa-result-table">
              <thead><tr>
                <th>Revision</th><th>Captured at</th><th>Schema</th><th>Diff</th>
                <th>Changes</th><th>상세</th>
              </tr></thead>
              <tbody>
                {history.data.map((row) => (
                  <tr key={row.id}>
                    <td>{row.id}</td>
                    <td>{dateLabel(row.captured_at)}</td>
                    <td>{row.schema_name}</td>
                    <td>{row.diff_status}</td>
                    <td>{row.total_changes ?? "— (기준 없음)"}</td>
                    <td>
                      <button
                        type="button"
                        className="dd-secondary-btn"
                        aria-label={"Snapshot " + row.id + " 상세 보기"}
                        onClick={() => void openSnapshot(row)}
                      >상세 보기</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="dd-action-row">
            <button type="button" className="dd-secondary-btn"
              disabled={offset === 0} onClick={() => source && void loadHistory(source, offset - PAGE_SIZE)}>
              이전
            </button>
            <button type="button" className="dd-secondary-btn"
              disabled={history.data.length < PAGE_SIZE}
              onClick={() => source && void loadHistory(source, offset + PAGE_SIZE)}>
              다음
            </button>
          </div>
        </section>
      ) : null}

      {selection ? (
        <section className="dd-index-section" data-testid="snapshot-detail-panel">
          <h3>Snapshot Revision {selection.id} — {selection.source_name}</h3>
          <div className="status-grid dd-meta-grid">
            <div className="status-item"><span className="label">Fingerprint</span>
              <code className="value">{selection.schema_fingerprint}</code></div>
            <div className="status-item"><span className="label">Previous Revision</span>
              <span className="value">{selection.previous_revision_id ?? "—"}</span></div>
            <div className="status-item"><span className="label">Captured by</span>
              <span className="value">{selection.captured_by}</span></div>
          </div>
          {status(detail, "변경 Diff")}
          {detail.status === "ready" && detail.data ? (
            <div data-testid="snapshot-diff">
              <p className="dd-guidance">상세 Diff: {detail.data.diff_status}, 총 {detail.data.total_changes ?? "기준 없음"}건</p>
              {detail.data.changes.length === 0 ? (
                <p className="dd-guidance">표시할 변경 항목이 없습니다.</p>
              ) : (
                <div className="qa-result-table-wrap">
                  <table className="qa-result-table">
                    <thead><tr><th>Object</th><th>Change</th><th>Identity</th><th>Changed fields</th></tr></thead>
                    <tbody>{detail.data.changes.map((change, i) => (
                      <tr key={change.object_type + ":" + change.object_key.join("/") + ":" + i}>
                        <td>{change.object_type}</td>
                        <td>{change.change_type}</td>
                        <td>{change.object_key.join(" / ")}</td>
                        <td>{change.changed_fields?.join(", ") || "—"}</td>
                      </tr>
                    ))}</tbody>
                  </table>
                </div>
              )}
            </div>
          ) : null}
          <h3>검토 미리보기 (조회 전용)</h3>
          {status(preview, "검토 미리보기")}
          {preview.status === "ready" && preview.data ? (
            <div className="status-grid dd-meta-grid" data-testid="snapshot-preview">
              <div className="status-item"><span className="label">Review</span>
                <span className="value">{preview.data.review_status}</span></div>
              <div className="status-item"><span className="label">Preflight</span>
                <span className="value">{preview.data.preflight_status}</span></div>
              <div className="status-item"><span className="label">Candidate</span>
                <span className="value">{preview.data.candidate_package_readiness}</span></div>
              <div className="status-item"><span className="label">Activation eligible</span>
                <span className="value">{String(preview.data.activation_eligible)}</span></div>
              <div className="status-item"><span className="label">Latest Revision</span>
                <span className="value">{preview.data.latest_revision_id}{preview.data.is_latest ? "" : " (선택본 이전)"}</span></div>
            </div>
          ) : null}
          <h3>변경 검토 이력 (관리자 승인 아님)</h3>
          {status(reviews, "변경 검토 이력")}
          {reviews.status === "ready" && reviews.data?.length === 0 ? (
            <p className="dd-guidance">기록된 검토 이벤트가 없습니다.</p>
          ) : null}
          {reviews.status === "ready" && reviews.data && reviews.data.length > 0 ? (
            <div className="qa-result-table-wrap" data-testid="snapshot-reviews">
              <table className="qa-result-table">
                <thead><tr><th>일시</th><th>Decision</th><th>Reason</th><th>Reviewer</th></tr></thead>
                <tbody>{reviews.data.map((event) => (
                  <tr key={event.id}>
                    <td>{dateLabel(event.reviewed_at)}</td>
                    <td>{event.decision}</td>
                    <td>{event.reason_code}</td>
                    <td>{event.reviewed_by}</td>
                  </tr>
                ))}</tbody>
              </table>
            </div>
          ) : null}
        </section>
      ) : null}
    </section>
  );
}
