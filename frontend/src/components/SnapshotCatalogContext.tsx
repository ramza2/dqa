import { useEffect, useState } from "react";
import { getActiveCatalog, listCatalogActivations } from "../api/catalog";
import { CatalogApiError, type CatalogActiveSummary, type CatalogActivationEventSummary } from "../types/catalog";
import type { SnapshotSummary } from "../types/schemaSnapshot";

type ReadState<T> = {
  status: "loading" | "ready" | "none" | "error";
  data: T | null;
  message: string | null;
};

function errorLabel(error: unknown): string {
  if (error instanceof CatalogApiError) {
    return "HTTP " + error.status + (error.code ? " · " + error.code : "") + ": " + error.message;
  }
  return "Catalog 정보를 조회할 수 없습니다.";
}

function dateLabel(value: string): string {
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? "—" : parsed.toLocaleString();
}

function shortFingerprint(value: string): string {
  return value.length > 24 ? value.slice(0, 12) + "…" + value.slice(-8) : value;
}

interface Props {
  sourceName: string;
  /** Selected Snapshot, or page-1 latest Snapshot; unrelated to Catalog revision IDs. */
  snapshot: SnapshotSummary | null;
}

/** This component only reads existing Catalog endpoints; never activates a revision. */
export function SnapshotCatalogContext({ sourceName, snapshot }: Props) {
  const [active, setActive] = useState<ReadState<CatalogActiveSummary>>({
    status: "loading", data: null, message: null,
  });
  const [events, setEvents] = useState<ReadState<CatalogActivationEventSummary[]>>({
    status: "loading", data: null, message: null,
  });

  useEffect(() => {
    let cancelled = false;
    // The caller keys by Source and unmounts during reload. Independently
    // complete both GET requests, rejecting stale/wrong-Source payloads.
    void getActiveCatalog(sourceName).then((value) => {
      if (cancelled) return;
      if (value.source_name !== sourceName) {
        setActive({ status: "error", data: null, message: "활성 Catalog 응답 Source 불일치" });
        return;
      }
      setActive({ status: "ready", data: value, message: null });
    }).catch((error: unknown) => {
      if (cancelled) return;
      if (error instanceof CatalogApiError && error.status === 404) {
        setActive({ status: "none", data: null, message: null });
        return;
      }
      setActive({ status: "error", data: null, message: errorLabel(error) });
    });

    void listCatalogActivations(sourceName).then((rows) => {
      if (cancelled) return;
      if (!Array.isArray(rows) || rows.some((event) => event.source_name !== sourceName)) {
        setEvents({ status: "error", data: null, message: "Catalog 활성화 이력 Source 불일치" });
        return;
      }
      setEvents({ status: "ready", data: rows, message: null });
    }).catch((error: unknown) => {
      if (!cancelled) setEvents({ status: "error", data: null, message: errorLabel(error) });
    });

    return () => { cancelled = true; };
  }, [sourceName]);

  const live = active.status === "ready" ? active.data : null;
  const comparison = snapshot && live
    ? snapshot.schema_fingerprint === live.schema_fingerprint
      ? "Fingerprint 문자열 일치 — 데이터 계보·승인 증빙 아님"
      : "Fingerprint 불일치 — 다른 상태 또는 범위일 수 있음"
    : null;

  return (
    <section className="dd-index-section" data-testid="snapshot-catalog-context">
      <h3>Active Catalog 상태 (별도 관리 이력)</h3>
      <p className="dd-guidance">
        Snapshot Revision ID와 Catalog Import Revision ID는 서로 다른 번호 체계입니다.
        번호가 같아도 같은 개체가 아니며, Fingerprint 일치도 공식 Import 계보·DBA 승인·READY 전환을 증명하지 않습니다.
      </p>
      {active.status === "loading" ? <p className="dd-guidance">활성 Catalog 조회 중…</p> : null}
      {active.status === "none" ? (
        <p className="dd-guidance" data-testid="snapshot-no-active">
          이 Source에는 현재 활성 Catalog가 없습니다. 저장된 Snapshot 조회와 별개입니다.
        </p>
      ) : null}
      {active.status === "error" ? (
        <div className="banner banner-error" role="alert" data-testid="snapshot-active-error">
          활성 Catalog 조회 실패: {active.message}
        </div>
      ) : null}
      {live ? (
        <div className="status-grid dd-meta-grid" data-testid="snapshot-active-catalog">
          <div className="status-item"><span className="label">Catalog Source</span>
            <span className="value">{live.source_name}</span></div>
          <div className="status-item"><span className="label">Active Catalog Import Revision</span>
            <span className="value">{live.revision_id}</span></div>
          <div className="status-item"><span className="label">Package version / readiness</span>
            <span className="value">{live.package_version} / {live.package_readiness}</span></div>
          <div className="status-item"><span className="label">Activated at</span>
            <span className="value">{dateLabel(live.activated_at)}</span></div>
          <div className="status-item"><span className="label">Active Fingerprint</span>
            <code className="value" title={live.schema_fingerprint}>
              {shortFingerprint(live.schema_fingerprint)}
            </code></div>
        </div>
      ) : null}
      {comparison ? (
        <p className="dd-guidance" data-testid="snapshot-catalog-comparison">
          Snapshot #{snapshot?.id} ↔ Active Catalog Import #{live?.revision_id}: {comparison}
        </p>
      ) : null}
      <h3>최근 Catalog Activation 이벤트 (읽기 전용)</h3>
      {events.status === "loading" ? <p className="dd-guidance">활성화 이력 조회 중…</p> : null}
      {events.status === "error" ? (
        <div className="banner banner-error" role="alert" data-testid="snapshot-activations-error">
          Catalog 활성화 이력 조회 실패: {events.message}
        </div>
      ) : null}
      {events.status === "ready" && events.data?.length === 0 ? (
        <p className="dd-guidance">해당 Source의 활성화 이벤트가 없습니다.</p>
      ) : null}
      {events.status === "ready" && events.data && events.data.length > 0 ? (
        <div className="qa-result-table-wrap" data-testid="snapshot-catalog-activations">
          <table className="qa-result-table">
            <thead><tr>
              <th>Activated at</th><th>Previous Catalog Revision</th><th>Activated Catalog Revision</th>
            </tr></thead>
            <tbody>{events.data.map((event, i) => (
              <tr key={event.activated_revision_id + ":" + event.activated_at + ":" + i}>
                <td>{dateLabel(event.activated_at)}</td>
                <td>{event.previous_revision_id ?? "—"}</td>
                <td>{event.activated_revision_id}</td>
              </tr>
            ))}</tbody>
          </table>
        </div>
      ) : null}
    </section>
  );
}
