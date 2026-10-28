import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { SnapshotErdPanel } from "../components/SnapshotErdPanel";
import type { SnapshotSummary } from "../types/schemaSnapshot";
import { installFetchMock, jsonResponse } from "./mocks";

const snapshot: SnapshotSummary = {
  id: 10, source_name: "oracle_demis_mock", db_type: "oracle",
  database_name: "FREEPDB1", schema_name: "DEMIS_OWNER",
  schema_fingerprint: "a".repeat(64),
  previous_revision_id: null, captured_by: "operator",
  captured_at: "2026-10-28T00:00:00Z", counts: { tables: 1 },
  diff_status: "NO_BASELINE", total_changes: null,
};

const safe = {
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

describe("M2-2B Snapshot ERD preview", () => {
  it("does not call GET before user action, then shows a source-bound FK", async () => {
    const user = userEvent.setup();
    let count = 0;
    const restore = installFetchMock([(url, init) => {
      if (!url.pathname.endsWith("/10/erd")) return null;
      expect(init?.method).toBe("GET");
      expect(url.searchParams.get("source_name")).toBe(snapshot.source_name);
      count++;
      if (url.searchParams.get("focus_table")) {
        return jsonResponse({ ...safe,
          focus_schema: "DEMIS_OWNER", focus_table: "TB_MOCK",
          total_edges: 1, edges: [{
            direction: "OUT", constraint_name: "FK_MOCK_REF",
            source_schema: "DEMIS_OWNER", source_table: "TB_MOCK",
            target_schema: "OTHER_SCHEMA", target_table: "TB_EXTERNAL",
            referenced_only: true,
            column_mapping: [{ source: "ID", target: "REF_ID" }],
          }],
        });
      }
      return jsonResponse(safe);
    }]);
    try {
      render(<SnapshotErdPanel snapshot={snapshot} />);
      expect(count).toBe(0);
      expect(screen.getByText(/Catalog READY·활성화/)).toBeInTheDocument();
      await user.click(screen.getByRole("button", { name: "ERD 테이블 조회" }));
      const button = await screen.findByRole("button", { name: "ERD 테이블 DEMIS_OWNER.TB_MOCK" });
      await user.click(button);
      expect(await screen.findByText(/FK_MOCK_REF/)).toBeInTheDocument();
      expect(screen.getByText(/Snapshot 외부 참조/)).toBeInTheDocument();
      expect(count).toBe(2);
    } finally { restore(); }
  });

  it("rejects response that claims activation eligibility", async () => {
    const user = userEvent.setup();
    const restore = installFetchMock([(url) =>
      url.pathname.endsWith("/10/erd") ? jsonResponse({
        ...safe, activation_eligible: true,
      }) : null,
    ]);
    try {
      render(<SnapshotErdPanel snapshot={snapshot} />);
      await user.click(screen.getByRole("button", { name: "ERD 테이블 조회" }));
      expect(await screen.findByRole("alert")).toHaveTextContent("Fingerprint 정합성");
      expect(screen.queryByRole("button", { name: /ERD 테이블 DEMIS_OWNER.TB_MOCK/ })).not.toBeInTheDocument();
    } finally { restore(); }
  });

  it("ignores late success when the selected revision unmounts", async () => {
    const user = userEvent.setup();
    let resolve: ((value: Response) => void) | undefined;
    const pending = new Promise<Response>(r => { resolve = r; });
    const restore = installFetchMock([(url) =>
      url.pathname.endsWith("/10/erd") ? pending : null,
    ]);
    try {
      const view = render(<SnapshotErdPanel snapshot={snapshot} />);
      await user.click(screen.getByRole("button", { name: "ERD 테이블 조회" }));
      view.unmount();
      resolve?.(jsonResponse(safe));
      await Promise.resolve();
      expect(screen.queryByText("TB_MOCK")).not.toBeInTheDocument();
    } finally { restore(); }
  });
});
