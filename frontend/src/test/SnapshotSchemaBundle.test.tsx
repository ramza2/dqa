import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { SnapshotErdPanel } from "../components/SnapshotErdPanel";
import type { SnapshotSummary } from "../types/schemaSnapshot";
import { installFetchMock, jsonResponse } from "./mocks";

const snapshot: SnapshotSummary = {
  id: 10, source_name: "oracle_demis_mock", db_type: "oracle",
  database_name: "FREEPDB1", schema_name: "DEMIS_OWNER",
  schema_fingerprint: "a".repeat(64),
  previous_revision_id: null, captured_by: "operator",
  captured_at: "2026-10-28T00:00:00Z", counts: { tables: 8 },
  diff_status: "NO_BASELINE", total_changes: null,
};
const erd = {
  source_name: snapshot.source_name,
  revision_id: snapshot.id,
  schema_fingerprint: snapshot.schema_fingerprint,
  preflight_status: "NOT_VERIFIED",
  activation_eligible: false,
  total_tables: 1, offset: 0, limit: 30,
  tables: [{ schema_name: "DEMIS_OWNER", table_name: "TB_MOCK" }],
  focus_schema: null, focus_table: null,
  total_edges: 0, edges_truncated: false, edges: [],
};
const ZIP = "application/zip";

afterEach(() => vi.restoreAllMocks());

async function focusTable(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole("button", { name: "ERD 테이블 조회" }));
  await user.click(await screen.findByRole("button", {
    name: "ERD 테이블 DEMIS_OWNER.TB_MOCK",
  }));
  return screen.findByRole("button", { name: /스키마 DOCX 묶음 ZIP/ });
}

describe("M2-2D Snapshot schema ZIP parts", () => {
  it("downloads 5-table parts sequentially and restarts after final part", async () => {
    const user = userEvent.setup();
    const offsets: string[] = [];
    const downloaded: string[] = [];
    const originalCreate = URL.createObjectURL;
    const originalRevoke = URL.revokeObjectURL;
    Object.defineProperty(URL, "createObjectURL", { configurable: true, value: vi.fn(() => "blob:synthetic") });
    Object.defineProperty(URL, "revokeObjectURL", { configurable: true, value: vi.fn() });
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function(this: HTMLAnchorElement) {
      downloaded.push(this.download);
    });
    const restore = installFetchMock([(url, init) => {
      if (url.pathname.endsWith("/10/erd")) return jsonResponse({
        ...erd, focus_schema: url.searchParams.get("focus_schema"),
        focus_table: url.searchParams.get("focus_table"),
      });
      if (url.pathname.endsWith("/10/schema-report.zip")) {
        expect(init?.method).toBe("GET");
        expect(url.searchParams.get("source_name")).toBe(snapshot.source_name);
        expect(url.searchParams.get("schema_name")).toBe("DEMIS_OWNER");
        expect(url.searchParams.get("limit")).toBe("5");
        const offset = url.searchParams.get("offset")!;
        offsets.push(offset);
        return new Response(new Blob(["PK_zip_payload"], { type: ZIP }), {
          status: 200,
          headers: {
            "Content-Type": ZIP,
            "X-DQA-Schema-Total-Tables": "8",
            "X-DQA-Schema-Next-Offset": offset === "0" ? "5" : "-1",
          },
        });
      }
      return null;
    }]);
    try {
      render(<SnapshotErdPanel snapshot={snapshot} />);
      const button = await focusTable(user);
      expect(offsets).toHaveLength(0);
      await user.click(button);
      await waitFor(() => expect(downloaded).toHaveLength(1));
      expect(screen.getByTestId("schema-report-progress")).toHaveTextContent("다음 묶음 시작: 6번째");
      await user.click(button);
      await waitFor(() => expect(downloaded).toHaveLength(2));
      expect(screen.getByTestId("schema-report-progress")).toHaveTextContent("마지막 묶음까지 완료");
      await user.click(button);
      await waitFor(() => expect(downloaded).toHaveLength(3));
      expect(offsets).toEqual(["0", "5", "0"]);
      expect(downloaded).toEqual([
        "dqa-snapshot-10-schema-batch-0.zip",
        "dqa-snapshot-10-schema-batch-5.zip",
        "dqa-snapshot-10-schema-batch-0.zip",
      ]);
    } finally {
      restore();
      if (originalCreate) Object.defineProperty(URL, "createObjectURL", { configurable: true, value: originalCreate });
      else Reflect.deleteProperty(URL, "createObjectURL");
      if (originalRevoke) Object.defineProperty(URL, "revokeObjectURL", { configurable: true, value: originalRevoke });
      else Reflect.deleteProperty(URL, "revokeObjectURL");
    }
  });

  it("rejects forbidden schema ZIP download without displaying progress", async () => {
    const user = userEvent.setup();
    const restore = installFetchMock([(url) => {
      if (url.pathname.endsWith("/10/erd")) return jsonResponse({
        ...erd, focus_schema: url.searchParams.get("focus_schema"),
        focus_table: url.searchParams.get("focus_table"),
      });
      if (url.pathname.endsWith("/10/schema-report.zip")) {
        return jsonResponse({ detail: { code: "FORBIDDEN", message: "forbidden" } }, 403);
      }
      return null;
    }]);
    try {
      render(<SnapshotErdPanel snapshot={snapshot} />);
      await user.click(await focusTable(user));
      expect(await screen.findByRole("alert")).toHaveTextContent("스키마 분석서 묶음 다운로드 실패");
      expect(screen.queryByTestId("schema-report-progress")).not.toBeInTheDocument();
    } finally { restore(); }
  });

  it("fails closed on missing or invalid pagination headers", async () => {
    const user = userEvent.setup();
    const restore = installFetchMock([(url) => {
      if (url.pathname.endsWith("/10/erd")) return jsonResponse({
        ...erd, focus_schema: url.searchParams.get("focus_schema"),
        focus_table: url.searchParams.get("focus_table"),
      });
      if (url.pathname.endsWith("/10/schema-report.zip")) {
        return new Response(new Blob(["PK_zip_payload"], { type: ZIP }), {
          headers: { "Content-Type": ZIP },
        });
      }
      return null;
    }]);
    try {
      render(<SnapshotErdPanel snapshot={snapshot} />);
      await user.click(await focusTable(user));
      expect(await screen.findByRole("alert")).toHaveTextContent("스키마 분석서 묶음 다운로드 실패");
    } finally { restore(); }
  });
});
