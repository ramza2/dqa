import { useEffect, useState } from "react";
import { listCatalogImports } from "../api/catalog";
import { CatalogApiError, type CatalogActiveSummary, type CatalogImportRevisionSummary } from "../types/catalog";

const LIMIT = 10;
type ImportState = {
  source: string;
  status: "loading" | "ready" | "error";
  items: CatalogImportRevisionSummary[];
  message: string | null;
};

function isSafeImport(value: unknown, sourceName: string): value is CatalogImportRevisionSummary {
  if (!value || typeof value !== "object" || Array.isArray(value)) return false;
  const row = value as Partial<CatalogImportRevisionSummary>;
  return row.source_name === sourceName
    && typeof row.id === "number" && Number.isSafeInteger(row.id) && row.id > 0
    && (row.package_readiness === "READY"
      || row.package_readiness === "WARNING" || row.package_readiness === "BLOCKED")
    && typeof row.schema_fingerprint === "string" && /^[a-fA-F0-9]{64}$/.test(row.schema_fingerprint)
    && typeof row.package_version === "string" && row.package_version.length > 0
    && typeof row.validation_status === "string" && row.validation_status.length > 0
    && typeof row.imported_at === "string"
    && typeof row.table_count === "number" && Number.isSafeInteger(row.table_count) && row.table_count >= 0
    && typeof row.column_count === "number" && Number.isSafeInteger(row.column_count) && row.column_count >= 0;
}

function dateLabel(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "—" : date.toLocaleString();
}

function errorText(error: unknown): string {
  if (error instanceof CatalogApiError) {
    if (error.status === 401 || error.status === 403) return "Import 이력 조회 권한이 없습니다.";
    return `Import 이력 조회 실패 (HTTP ${error.status}).`;
  }
  return "Import 이력을 조회하지 못했습니다.";
}

interface Props {
  sourceName: string;
  active: CatalogActiveSummary | null;
}

/** Independent metadata-only GET. No import, READY promotion or activation action. */
export function CatalogImportHistory({ sourceName, active }: Props) {
  const [result, setResult] = useState<ImportState>({
    source: sourceName, status: "loading", items: [], message: null,
  });

  useEffect(() => {
    let cancelled = false;
    void listCatalogImports(sourceName, LIMIT).then((rows) => {
      if (cancelled) return;
      const ids = Array.isArray(rows) ? rows.map((row) => row?.id) : [];
      if (!Array.isArray(rows) || rows.length > LIMIT
        || !rows.every((row) => isSafeImport(row, sourceName))
        || new Set(ids).size !== ids.length) {
        setResult({
          source: sourceName, status: "error", items: [],
          message: "Import 이력 응답의 Source 또는 Revision 계약이 일치하지 않습니다.",
        });
        return;
      }
      setResult({ source: sourceName, status: "ready", items: rows, message: null });
    }).catch((error: unknown) => {
      if (!cancelled) {
        setResult({ source: sourceName, status: "error", items: [], message: errorText(error) });
      }
    });
    return () => { cancelled = true; };
  }, [sourceName]);

  const state = result.source === sourceName ? result : {
    source: sourceName, status: "loading" as const, items: [], message: null,
  };
  const live = active?.source_name === sourceName ? active : null;

  return (
    <section className="dd-index-section" data-testid="catalog-import-history">
      <h3>최근 Catalog Import Revision (조회 전용 · 최대 10건)</h3>
      <p className="dd-guidance">
        Import는 활성화가 아닙니다. READY는 Package 적격 상태일 뿐 별도 수동 활성화가 필요합니다.
        WARNING/BLOCKED는 활성화할 수 없으며, 같은 Fingerprint라도 Snapshot의 승인 계보를 증명하지 않습니다.
      </p>
      {state.status === "loading" ? <p className="dd-guidance">Import 이력 조회 중…</p> : null}
      {state.status === "error" ? (
        <div className="banner banner-error" role="alert" data-testid="catalog-imports-error">
          {state.message}
        </div>
      ) : null}
      {state.status === "ready" && state.items.length === 0 ? (
        <p className="dd-guidance" data-testid="catalog-imports-empty">
          이 Source의 Catalog Import Revision이 없습니다. Snapshot 이력·활성 포인터와 별개입니다.
        </p>
      ) : null}
      {state.status === "ready" && state.items.length > 0 ? (
        <div className="qa-result-table-wrap" data-testid="catalog-imports-table">
          <table className="qa-result-table">
            <thead><tr>
              <th>Import Revision</th><th>Imported at</th><th>Package</th>
              <th>Readiness</th><th>Validation</th><th>Tables / Columns</th>
              <th>Fingerprint</th><th>Active pointer</th>
            </tr></thead>
            <tbody>{state.items.map((row) => {
              const sameId = live?.revision_id === row.id;
              const exactActive = sameId && live?.schema_fingerprint === row.schema_fingerprint;
              return (
                <tr key={row.id}>
                  <td>{row.id}</td>
                  <td>{dateLabel(row.imported_at)}</td>
                  <td>{row.package_version}</td>
                  <td>{row.package_readiness}</td>
                  <td>{row.validation_status}</td>
                  <td>{row.table_count} / {row.column_count}</td>
                  <td><code>{row.schema_fingerprint.slice(0, 12)}…{row.schema_fingerprint.slice(-8)}</code></td>
                  <td>{exactActive
                    ? "현재 활성 포인터와 ID/Fingerprint 일치"
                    : sameId ? "활성 포인터와 Fingerprint 불일치 — 확인 필요" : "—"}</td>
                </tr>
              );
            })}</tbody>
          </table>
        </div>
      ) : null}
    </section>
  );
}
