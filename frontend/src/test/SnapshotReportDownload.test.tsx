import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { SnapshotErdPanel } from "../components/SnapshotErdPanel";
import type { SnapshotSummary } from "../types/schemaSnapshot";
import { installFetchMock, jsonResponse } from "./mocks";

const MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document";
const snapshot: SnapshotSummary = {
  id: 10, source_name: "oracle_demis_mock", db_type: "oracle",
  database_name: "FREEPDB1", schema_name: "DEMIS_OWNER",
  schema_fingerprint: "a".repeat(64),
  previous_revision_id: null, captured_by: "operator",
  captured_at: "2026-10-28T00:00:00Z", counts: { tables: 1 },
  diff_status: "NO_BASELINE", total_changes: null,
};
const focus = {
  source_name: snapshot.source_name, revision_id: snapshot.id,
  schema_fingerprint: snapshot.schema_fingerprint,
  preflight_status: "NOT_VERIFIED", activation_eligible: false,
  total_tables: 1, offset: 0, limit: 30,
  tables: [{ schema_name: "DEMIS_OWNER", table_name: "TB_MOCK" }],
  focus_schema: "DEMIS_OWNER", focus_table: "TB_MOCK",
  total_edges: 0, edges_truncated: false, edges: [],
};

afterEach(() => vi.restoreAllMocks());

async function selectTable(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole("button", { name: "ERD 테이블 조회" }));
  await user.click(await screen.findByRole("button", { name: "ERD 테이블 DEMIS_OWNER.TB_MOCK" }));
  return screen.findByRole("button", { name: /선택 테이블 DB 분석서 DOCX/ });
}

describe("M2-2C Snapshot DOCX export UI", () => {
  it("requires user click, sends bounded GET, and saves a DOCX with a fixed filename", async () => {
    const user = userEvent.setup();
    let reportCalls = 0;
    const saved: string[] = [];
    const originalCreate = URL.createObjectURL;
    const originalRevoke = URL.revokeObjectURL;
    Object.defineProperty(URL, "createObjectURL", { configurable: true, value: vi.fn(() => "blob:test-report") });
    Object.defineProperty(URL, "revokeObjectURL", { configurable: true, value: vi.fn() });
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (this: HTMLAnchorElement) { saved.push(this.download); });
    const restore = installFetchMock([(url, init) => {
      if (url.pathname.endsWith("/10/erd")) return jsonResponse({
        ...focus, focus_schema: url.searchParams.get("focus_schema"),
        focus_table: url.searchParams.get("focus_table"),
      });
      if (url.pathname.endsWith("/10/report.docx")) {
        reportCalls++;
        expect(init?.method).toBe("GET");
        expect(url.searchParams.get("source_name")).toBe(snapshot.source_name);
        expect(url.searchParams.get("schema_name")).toBe("DEMIS_OWNER");
        expect(url.searchParams.get("table_name")).toBe("TB_MOCK");
        return new Response(new Blob(["PK-report"], { type: MIME }), {
          status: 200, headers: { "Content-Type": MIME },
        });
      }
      return null;
    }]);
    try {
      render(<SnapshotErdPanel snapshot={snapshot} />);
      const button = await selectTable(user);
      expect(reportCalls).toBe(0);
      await user.click(button);
      await waitFor(() => expect(reportCalls).toBe(1));
      await waitFor(() => expect(saved).toEqual(["dqa-snapshot-10-table-analysis.docx"]));
    } finally {
      restore();
      if (originalCreate) Object.defineProperty(URL, "createObjectURL", { configurable: true, value: originalCreate });
      else Reflect.deleteProperty(URL, "createObjectURL");
      if (originalRevoke) Object.defineProperty(URL, "revokeObjectURL", { configurable: true, value: originalRevoke });
      else Reflect.deleteProperty(URL, "revokeObjectURL");
    }
  });

  it("does not download when the export permission is denied", async () => {
    const user = userEvent.setup();
    const restore = installFetchMock([(url) => {
      if (url.pathname.endsWith("/10/erd")) return jsonResponse({
        ...focus, focus_schema: url.searchParams.get("focus_schema"),
        focus_table: url.searchParams.get("focus_table"),
      });
      if (url.pathname.endsWith("/10/report.docx")) {
        return jsonResponse({ detail: { code: "FORBIDDEN", message: "forbidden" } }, 403);
      }
      return null;
    }]);
    try {
      render(<SnapshotErdPanel snapshot={snapshot} />);
      const button = await selectTable(user);
      await user.click(button);
      expect(await screen.findByRole("alert")).toHaveTextContent("관리자 권한");
    } finally { restore(); }
  });
});
