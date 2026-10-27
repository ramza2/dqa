import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MockInspectorPanel } from "../components/MockInspectorPanel";
import type { ConnectionProfile } from "../types/connectionProfile";
import { installFetchMock, jsonResponse } from "./mocks";

function profile(): ConnectionProfile {
  return {
    id: 71, name: "Mock", source_name: "oracle_demis_mock", environment: "development",
    enabled: true, dbms_type: "oracle", host: "demis-oracle-test", port: 1521,
    database_name: "FREEPDB1", username: "DEMIS_RO",
    credential_secret_ref: "env:DEMIS_SECRET_ORACLE_PASSWORD",
    created_by: null, updated_by: null,
    created_at: "2026-10-27T00:00:00Z", updated_at: "2026-10-27T00:00:00Z",
  };
}
const root = "/api/v1/schema-inspector/mock-targets/71";
const ready = {
  profile_id: 71, ready: true, reason_code: "READY_FOR_DEV_INSPECTION",
  schema_name: "DEMIS_OWNER", live_connection_tested: false,
  site_approved: false, catalog_activated: false,
};
const summary = {
  status: "INSPECTED", source_name: "oracle_demis_mock", schema_name: "DEMIS_OWNER",
  table_count: 3, column_count: 12, primary_key_column_count: 2,
  unique_key_column_count: 0, foreign_key_count: 1, index_count: 1,
  imported: false, activated: false,
};

afterEach(() => vi.restoreAllMocks());

describe("M2-1B Mock Inspector explicit flow", () => {
  it("does not inspect or capture on mount / readiness check", async () => {
    const calls: string[] = [];
    const restore = installFetchMock([(url, init) => {
      calls.push(`${init?.method || "GET"} ${url.pathname}`);
      if (url.pathname === root + "/readiness") return jsonResponse({
        ...ready, ready: false, reason_code: "INSPECTOR_NOT_CONFIGURED", schema_name: null,
      });
      return null;
    }]);
    try {
      render(<MockInspectorPanel profile={profile()} />);
      expect(calls).toHaveLength(0);
      await userEvent.click(screen.getByRole("button", { name: "Inspector 연계 조건 확인 (접속 없음)" }));
      expect(await screen.findByText(/별도 Inspector 계정\/스키마 설정 필요/)).toBeInTheDocument();
      expect(screen.queryByRole("button", { name: "스키마 메타데이터 분석" })).not.toBeInTheDocument();
      expect(calls).toEqual([`GET ${root}/readiness`]);
    } finally { restore(); }
  });

  it("inspects only after check, captures only after confirmation", async () => {
    const calls: string[] = [];
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
    const restore = installFetchMock([(url, init) => {
      const method = init?.method || "GET";
      calls.push(`${method} ${url.pathname}`);
      if (url.pathname === root + "/readiness") return jsonResponse(ready);
      if (url.pathname === root + "/inspect") return jsonResponse(summary);
      if (url.pathname === "/api/v1/schema-inspector/snapshots")
        return jsonResponse([]);
      return null;
    }]);
    try {
      render(<MockInspectorPanel profile={profile()} />);
      await userEvent.click(screen.getByRole("button", { name: "Inspector 연계 조건 확인 (접속 없음)" }));
      await userEvent.click(await screen.findByRole("button", { name: "스키마 메타데이터 분석" }));
      expect(await screen.findByText(/메타데이터 분석 완료/)).toBeInTheDocument();
      expect(calls).toEqual([`GET ${root}/readiness`, `POST ${root}/inspect`]);
      await userEvent.click(screen.getByRole("button", { name: "Snapshot 저장 (별도 확인)" }));
      expect(confirm).toHaveBeenCalledOnce();
      expect(calls).toHaveLength(2);
    } finally { restore(); }
  });

  it("rejects a forged readiness approval flag", async () => {
    const calls: string[] = [];
    const restore = installFetchMock([(url, init) => {
      calls.push(`${init?.method || "GET"} ${url.pathname}`);
      if (url.pathname === root + "/readiness")
        return jsonResponse({ ...ready, site_approved: true });
      return null;
    }]);
    try {
      render(<MockInspectorPanel profile={profile()} />);
      await userEvent.click(screen.getByRole("button", { name: "Inspector 연계 조건 확인 (접속 없음)" }));
      expect(await screen.findByRole("alert")).toHaveTextContent("안전 조건");
      expect(screen.queryByRole("button", { name: "스키마 메타데이터 분석" })).not.toBeInTheDocument();
      expect(calls).toEqual([`GET ${root}/readiness`]);
    } finally { restore(); }
  });

  it("does not show Mock controls for a production source", () => {
    const restore = installFetchMock([() => null]);
    try {
      const { container } = render(<MockInspectorPanel profile={{
        ...profile(), source_name: "demis_live", environment: "production",
      }} />);
      expect(container.textContent).toBe("");
    } finally { restore(); }
  });
});
