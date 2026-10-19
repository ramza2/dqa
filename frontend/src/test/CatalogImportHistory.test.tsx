import { render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { CatalogImportHistory } from "../components/CatalogImportHistory";
import type { CatalogActiveSummary, CatalogImportRevisionSummary } from "../types/catalog";
import { installFetchMock, jsonResponse } from "./mocks";

const SRC = "synthetic_alpha";
const OTHER = "synthetic_beta";
const FP_A = "a".repeat(64);
const FP_B = "b".repeat(64);

const ready: CatalogImportRevisionSummary = {
  id: 42, source_name: SRC, db_type: "oracle",
  database_name: "SYN_DB", default_schema: "SYN_OWNER",
  package_format: "demis-catalog-package", package_version: "2.0",
  package_readiness: "READY", activation_eligible: true,
  schema_fingerprint: FP_A, archive_sha256: "c".repeat(64),
  manifest_sha256: "d".repeat(64), validation_status: "VALID",
  generated_at: "2026-10-15T00:00:00Z", imported_at: "2026-10-16T00:00:00Z",
  table_count: 25, column_count: 180, relation_count: 30, index_count: 11,
  category_count: 4, category_assignment_count: 6, managed_file_count: 10,
};
const active: CatalogActiveSummary = {
  source_name: SRC, revision_id: ready.id, schema_fingerprint: FP_A,
  package_version: "2.0", package_readiness: "READY",
  activated_at: "2026-10-16T01:00:00Z",
};
type Handler = (url: URL) => Response | Promise<Response>;
function importMock(handler: Handler) {
  return installFetchMock([(url, init) => {
    if (url.pathname !== "/api/v1/catalog/imports") return null;
    expect(init?.method).toBe("GET");
    expect(url.searchParams.get("limit")).toBe("10");
    expect(url.searchParams.get("offset")).toBe("0");
    return handler(url);
  }]);
}
afterEach(() => vi.restoreAllMocks());

describe("S-05-E Catalog Import metadata-only history", () => {
  it("shows READY/WARNING/BLOCKED as import metadata without presenting activation actions", async () => {
    const restore = importMock((url) => {
      expect(url.searchParams.get("source_name")).toBe(SRC);
      return jsonResponse([
        ready,
        { ...ready, id: 41, package_readiness: "WARNING", activation_eligible: false, schema_fingerprint: FP_B },
        { ...ready, id: 40, package_readiness: "BLOCKED", activation_eligible: false },
      ]);
    });
    try {
      render(<CatalogImportHistory sourceName={SRC} active={active} />);
      const view = await screen.findByTestId("catalog-imports-table");
      const body = within(view).getAllByRole("row");
      expect(body).toHaveLength(4);
      expect(view).toHaveTextContent("READY");
      expect(view).toHaveTextContent("WARNING");
      expect(view).toHaveTextContent("BLOCKED");
      expect(view).toHaveTextContent("현재 활성 포인터와 ID/Fingerprint 일치");
      expect(view).not.toHaveTextContent(ready.archive_sha256);
      expect(view).not.toHaveTextContent("SYN_DB");
      expect(screen.getByTestId("catalog-import-history")).toHaveTextContent("Import는 활성화가 아닙니다.");
      expect(within(screen.getByTestId("catalog-import-history")).queryByRole("button")).not.toBeInTheDocument();
    } finally { restore(); }
  });

  it("shows an empty import history independently of active Catalog state", async () => {
    const restore = importMock(() => jsonResponse([]));
    try {
      render(<CatalogImportHistory sourceName={SRC} active={active} />);
      expect(await screen.findByTestId("catalog-imports-empty")).toHaveTextContent("Snapshot 이력·활성 포인터와 별개");
    } finally { restore(); }
  });

  it("fails closed on cross-source rows, duplicate IDs and invalid readiness", async () => {
    const inputs: unknown[] = [
      [{ ...ready, source_name: OTHER }],
      [ready, ready],
      [{ ...ready, package_readiness: "VERIFIED" }],
      [{ ...ready, schema_fingerprint: "malformed" }],
      { items: [ready] },
    ];
    for (const payload of inputs) {
      const restore = importMock(() => jsonResponse(payload));
      try {
        const { unmount } = render(<CatalogImportHistory sourceName={SRC} active={active} />);
        expect(await screen.findByTestId("catalog-imports-error")).toHaveTextContent("계약이 일치하지 않습니다");
        expect(screen.queryByTestId("catalog-imports-table")).not.toBeInTheDocument();
        unmount();
      } finally { restore(); }
    }
  });

  it("keeps permission errors distinct from an empty history", async () => {
    const restore = importMock(() => jsonResponse({
      detail: { code: "FORBIDDEN", message: "internal secret" },
    }, 403));
    try {
      render(<CatalogImportHistory sourceName={SRC} active={null} />);
      expect(await screen.findByTestId("catalog-imports-error")).toHaveTextContent("권한이 없습니다");
      expect(screen.queryByText("internal secret")).not.toBeInTheDocument();
      expect(screen.queryByTestId("catalog-imports-empty")).not.toBeInTheDocument();
    } finally { restore(); }
  });

  it("sanitizes server failure messages", async () => {
    const restore = importMock(() => jsonResponse({
      detail: { code: "DB_FAILURE", message: "sensitive backend contents" },
    }, 500));
    try {
      render(<CatalogImportHistory sourceName={SRC} active={null} />);
      expect(await screen.findByTestId("catalog-imports-error")).toHaveTextContent("HTTP 500");
      expect(screen.queryByText(/sensitive backend contents/)).not.toBeInTheDocument();
    } finally { restore(); }
  });

  it("ignores a delayed Source A response after the component switches to Source B", async () => {
    let release: ((response: Response) => void) | undefined;
    const pending = new Promise<Response>((resolve) => { release = resolve; });
    const restore = importMock((url) => url.searchParams.get("source_name") === SRC
      ? pending : jsonResponse([{ ...ready, source_name: OTHER, id: 77, schema_fingerprint: FP_B }]));
    try {
      const { rerender } = render(<CatalogImportHistory sourceName={SRC} active={active} />);
      rerender(<CatalogImportHistory sourceName={OTHER} active={null} />);
      expect(await screen.findByTestId("catalog-imports-table")).toHaveTextContent("77");
      release?.(jsonResponse([ready]));
      await waitFor(() => {
        expect(screen.getByTestId("catalog-imports-table")).toHaveTextContent("77");
        expect(screen.getByTestId("catalog-imports-table")).not.toHaveTextContent("42");
      });
    } finally { restore(); }
  });

  it("does not mark an unverified active pointer or mismatched fingerprint as active", async () => {
    const restore = importMock(() => jsonResponse([ready]));
    try {
      const { rerender } = render(<CatalogImportHistory sourceName={SRC} active={null} />);
      expect(await screen.findByTestId("catalog-imports-table")).not.toHaveTextContent("현재 활성 포인터");
      rerender(<CatalogImportHistory sourceName={SRC} active={{ ...active, schema_fingerprint: FP_B }} />);
      expect(screen.getByTestId("catalog-imports-table")).toHaveTextContent("Fingerprint 불일치");
      expect(screen.getByTestId("catalog-imports-table")).not.toHaveTextContent("현재 활성 포인터와 ID/Fingerprint 일치");
    } finally { restore(); }
  });
});
