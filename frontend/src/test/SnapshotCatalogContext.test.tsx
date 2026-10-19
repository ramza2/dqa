import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { SnapshotCatalogContext } from "../components/SnapshotCatalogContext";
import type { CatalogActiveSummary, CatalogActivationEventSummary } from "../types/catalog";
import type { SnapshotSummary } from "../types/schemaSnapshot";
import { installFetchMock, jsonResponse } from "./mocks";

const SOURCE = "synthetic_source_A";
const OTHER = "synthetic_source_B";
const FP_A = "a".repeat(64);
const FP_B = "b".repeat(64);
const sample: SnapshotSummary = {
  id: 42,
  source_name: SOURCE,
  db_type: "oracle",
  database_name: "MOCK_DB",
  schema_name: "MOCK_SCHEMA",
  schema_fingerprint: FP_A,
  previous_revision_id: 41,
  captured_by: "tester",
  captured_at: "2026-10-15T00:00:00Z",
  counts: { tables: 2 },
  diff_status: "COMPARED",
  total_changes: 1,
};
const active: CatalogActiveSummary = {
  source_name: SOURCE,
  revision_id: 42, // Deliberately identical number; not a Snapshot foreign key.
  schema_fingerprint: FP_A,
  package_version: "2.0",
  package_readiness: "READY",
  activated_at: "2026-10-15T00:10:00Z",
};
const activation: CatalogActivationEventSummary = {
  source_name: SOURCE, previous_revision_id: 13,
  activated_revision_id: 42, activated_at: "2026-10-15T00:10:00Z",
};

type Handler = (url: URL, init?: RequestInit) => Response | null | Promise<Response | null>;

afterEach(() => vi.restoreAllMocks());

function handlers(args: {
  getActive?: (source: string) => Response | Promise<Response>;
  getActivations?: (source: string) => Response | Promise<Response>;
  getImports?: (source: string) => Response | Promise<Response>;
} = {}): Handler[] {
  return [(url, init) => {
    const source = url.pathname.startsWith("/api/v1/catalog/active/")
      ? decodeURIComponent(url.pathname.split("/").at(-1) ?? "")
      : url.searchParams.get("source_name") ?? "";
    if (
      !url.pathname.startsWith("/api/v1/catalog/active/")
      && url.pathname !== "/api/v1/catalog/activations"
      && url.pathname !== "/api/v1/catalog/imports"
    ) return null;
    expect(init?.method).toBe("GET");
    if (url.pathname.startsWith("/api/v1/catalog/active/")) {
      return args.getActive?.(source) ?? jsonResponse({ ...active, source_name: source });
    }
    expect(url.searchParams.get("limit")).toBe("10");
    if (url.pathname === "/api/v1/catalog/imports") {
      expect(url.searchParams.get("offset")).toBe("0");
      return args.getImports?.(source) ?? jsonResponse([]);
    }
    return args.getActivations?.(source) ?? jsonResponse([{ ...activation, source_name: source }]);
  }];
}

describe("S-05-B independent Snapshot/Catalog read-only context", () => {
  it("shows separate IDs and activation history, without inferring lineage from matching IDs or fingerprints", async () => {
    const restore = installFetchMock(handlers());
    render(<SnapshotCatalogContext sourceName={SOURCE} snapshot={sample} />);
    const card = await screen.findByTestId("snapshot-active-catalog");
    expect(card).toHaveTextContent("Active Catalog Import Revision");
    expect(card).toHaveTextContent("READY");
    expect(card).toHaveTextContent("42");
    const compare = screen.getByTestId("snapshot-catalog-comparison");
    expect(compare).toHaveTextContent("Fingerprint 문자열 일치");
    expect(compare).toHaveTextContent("계보·승인 증빙 아님");
    expect(await screen.findByTestId("snapshot-catalog-activations")).toHaveTextContent("13");
    expect(await screen.findByTestId("catalog-imports-empty")).toBeInTheDocument();
    expect(screen.getByTestId("snapshot-catalog-context")).toHaveTextContent("번호가 같아도 같은 개체가 아니며");
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    restore();
  });

  it("shows Source-scoped Import revisions as separate from Snapshot and Activation revisions", async () => {
    const restore = installFetchMock(handlers({
      getImports: (source) => jsonResponse([{
        id: 70, source_name: source, package_version: "2.0",
        package_readiness: "WARNING", activation_eligible: false,
        schema_fingerprint: FP_B, validation_status: "VALID",
        imported_at: "2026-10-15T00:00:00Z", table_count: 2, column_count: 3,
      }]),
    }));
    try {
      render(<SnapshotCatalogContext sourceName={SOURCE} snapshot={sample} />);
      const imports = await screen.findByTestId("catalog-imports-table");
      expect(imports).toHaveTextContent("70");
      expect(imports).toHaveTextContent("WARNING");
      expect(await screen.findByTestId("snapshot-active-catalog")).toHaveTextContent("42");
      expect(await screen.findByTestId("snapshot-catalog-activations")).toHaveTextContent("13");
      expect(screen.queryByRole("button")).not.toBeInTheDocument();
    } finally { restore(); }
  });

  it("never treats mismatching fingerprint as an import/activation decision", async () => {
    const restore = installFetchMock(handlers({
      getActive: () => jsonResponse({ ...active, schema_fingerprint: FP_B }),
    }));
    render(<SnapshotCatalogContext sourceName={SOURCE} snapshot={sample} />);
    expect(await screen.findByTestId("snapshot-catalog-comparison")).toHaveTextContent("Fingerprint 불일치");
    expect(screen.getByTestId("snapshot-active-catalog")).toHaveTextContent("READY");
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    restore();
  });

  it("distinguishes missing active Catalog (404) from missing Snapshot and from API errors", async () => {
    const restore = installFetchMock(handlers({
      getActive: () => jsonResponse({
        detail: { code: "CATALOG_ACTIVE_REVISION_NOT_FOUND", message: "not found" },
      }, 404),
      getActivations: () => jsonResponse([]),
    }));
    render(<SnapshotCatalogContext sourceName={SOURCE} snapshot={sample} />);
    expect(await screen.findByTestId("snapshot-no-active")).toHaveTextContent("저장된 Snapshot 조회와 별개");
    expect(await screen.findByText("해당 Source의 활성화 이벤트가 없습니다.")).toBeInTheDocument();
    expect(screen.queryByTestId("snapshot-catalog-comparison")).not.toBeInTheDocument();
    restore();
  });

  it("separately reports CATALOG_READ 403, not 'no active' or a fabricated approval", async () => {
    const restore = installFetchMock(handlers({
      getActive: () => jsonResponse({ detail: { code: "FORBIDDEN", message: "denied" } }, 403),
      getActivations: () => jsonResponse({ detail: { code: "FORBIDDEN", message: "denied" } }, 403),
    }));
    render(<SnapshotCatalogContext sourceName={SOURCE} snapshot={sample} />);
    expect(await screen.findByTestId("snapshot-active-error")).toHaveTextContent("HTTP 403");
    expect(await screen.findByTestId("snapshot-activations-error")).toHaveTextContent("FORBIDDEN");
    expect(screen.queryByTestId("snapshot-no-active")).not.toBeInTheDocument();
    expect(screen.queryByTestId("snapshot-active-catalog")).not.toBeInTheDocument();
    restore();
  });

  it("rejects cross-Source active pointer without affecting independent activation history", async () => {
    const restore = installFetchMock(handlers({
      getActive: () => jsonResponse({ ...active, source_name: OTHER }),
    }));
    render(<SnapshotCatalogContext sourceName={SOURCE} snapshot={sample} />);
    expect(await screen.findByTestId("snapshot-active-error")).toHaveTextContent("Source 불일치");
    expect(await screen.findByTestId("snapshot-catalog-activations")).toBeInTheDocument();
    expect(screen.queryByTestId("snapshot-active-catalog")).not.toBeInTheDocument();
    restore();
  });

  it("rejects an activation event from a different Source and preserves valid active pointer", async () => {
    const restore = installFetchMock(handlers({
      getActivations: () => jsonResponse([{ ...activation, source_name: OTHER }]),
    }));
    render(<SnapshotCatalogContext sourceName={SOURCE} snapshot={sample} />);
    expect(await screen.findByTestId("snapshot-activations-error")).toHaveTextContent("Source 불일치");
    expect(await screen.findByTestId("snapshot-active-catalog")).toBeInTheDocument();
    expect(screen.queryByTestId("snapshot-catalog-activations")).not.toBeInTheDocument();
    restore();
  });

  it("ignores old Source responses after unmount/replacement", async () => {
    let releaseA: ((result: Response) => void) | undefined;
    const delayed = new Promise<Response>((resolve) => { releaseA = resolve; });
    const restore = installFetchMock(handlers({
      getActive: (src) => src === SOURCE ? delayed : jsonResponse({
        ...active, source_name: OTHER, schema_fingerprint: FP_B, revision_id: 88,
      }),
      getActivations: (src) => src === SOURCE ? delayed : jsonResponse([]),
    }));
    const { rerender } = render(
      <SnapshotCatalogContext key={SOURCE} sourceName={SOURCE} snapshot={sample} />,
    );
    rerender(
      <SnapshotCatalogContext key={OTHER} sourceName={OTHER} snapshot={{
        ...sample, source_name: OTHER, schema_fingerprint: FP_B, id: 77,
      }} />,
    );
    expect(await screen.findByTestId("snapshot-active-catalog")).toHaveTextContent("88");
    releaseA?.(jsonResponse({ ...active, source_name: SOURCE }));
    await waitFor(() => {
      expect(screen.getByTestId("snapshot-active-catalog")).toHaveTextContent(OTHER);
      expect(screen.queryByTestId("snapshot-catalog-activations")).not.toBeInTheDocument();
    });
    restore();
  });

  it("recomputes comparison for a selected Snapshot without conflating its ID with active Catalog ID", async () => {
    const restore = installFetchMock(handlers());
    const { rerender } = render(
      <SnapshotCatalogContext sourceName={SOURCE} snapshot={sample} />,
    );
    expect(await screen.findByTestId("snapshot-catalog-comparison")).toHaveTextContent("문자열 일치");
    rerender(<SnapshotCatalogContext sourceName={SOURCE} snapshot={{
      ...sample, id: 1001, schema_fingerprint: FP_B,
    }} />);
    expect(screen.getByTestId("snapshot-catalog-comparison")).toHaveTextContent("Snapshot #1001");
    expect(screen.getByTestId("snapshot-catalog-comparison")).toHaveTextContent("Fingerprint 불일치");
    restore();
  });

  it("reports activation-history failure without hiding active Catalog", async () => {
    const restore = installFetchMock(handlers({
      getActivations: () => jsonResponse({ detail: { code: "AUDIT_UNAVAILABLE", message: "offline" } }, 503),
    }));
    render(<SnapshotCatalogContext sourceName={SOURCE} snapshot={sample} />);
    expect(await screen.findByTestId("snapshot-active-catalog")).toBeInTheDocument();
    expect(await screen.findByTestId("snapshot-activations-error")).toHaveTextContent("HTTP 503");
    restore();
  });
});
