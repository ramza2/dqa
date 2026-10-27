import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { OracleMockActions } from "../components/OracleMockActions";
import type { ConnectionProfile } from "../types/connectionProfile";
import { installFetchMock, jsonResponse } from "./mocks";

const REF = "env:DO_NOT_SHOW_THIS_REFERENCE";

function profile(overrides: Partial<ConnectionProfile> = {}): ConnectionProfile {
  return {
    id: 21, name: "Demo", source_name: "oracle_demis_mock",
    environment: "development", enabled: false, dbms_type: "oracle",
    host: "demis-oracle-test", port: 1521, database_name: "FREEPDB1",
    username: "DEMIS_RO", credential_secret_ref: REF,
    created_by: null, updated_by: null,
    created_at: "2026-10-23T00:00:00Z", updated_at: "2026-10-23T00:00:00Z",
    ...overrides,
  };
}

afterEach(() => vi.restoreAllMocks());

describe("M1 Oracle Mock development-only controls", () => {
  it("hides every action when the capability is disabled", async () => {
    const calls: string[] = [];
    const restore = installFetchMock([(url, init) => {
      calls.push(`${init?.method || "GET"} ${url.pathname}`);
      if (url.pathname.endsWith("/oracle-mock-capability")) {
        return jsonResponse({ enabled: false });
      }
      return null;
    }]);
    try {
      const { container } = render(<OracleMockActions
        profile={profile()} onRefresh={vi.fn()} />);
      await waitFor(() => expect(calls.length).toBeGreaterThan(0));
      expect(container.querySelector("button")).toBeNull();
      expect(calls.every((x) => x.startsWith("GET "))).toBe(true);
    } finally { restore(); }
  });

  it("allows only mock candidate to show probe and refuses non-mock probe", async () => {
    const calls: string[] = [];
    const restore = installFetchMock([(url, init) => {
      calls.push(`${init?.method || "GET"} ${url.pathname}`);
      if (url.pathname.endsWith("/oracle-mock-capability")) return jsonResponse({ enabled: true });
      return null;
    }]);
    try {
      render(<OracleMockActions
        profile={profile({ source_name: "real_demis" })}
        onRefresh={vi.fn()} />);
      // Flush the async capability response before the negative UI assertions.
      await act(async () => { await Promise.resolve(); });
      expect(screen.queryByRole("button", { name: "Oracle Mock 대상 준비" })).not.toBeInTheDocument();
      expect(screen.queryByRole("button", { name: "읽기 전용 연결 검사" })).not.toBeInTheDocument();
      expect(screen.queryByRole("button", { name: "연결 검사 후 활성화" })).not.toBeInTheDocument();
      expect(calls.every((x) => x.startsWith("GET "))).toBe(true);
    } finally { restore(); }
  });

  it("probe on disabled mock succeeds without enable until explicit confirmation", async () => {
    const calls: string[] = [], onRefresh = vi.fn();
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
    const restore = installFetchMock([(url, init) => {
      const method = init?.method || "GET";
      calls.push(`${method} ${url.pathname}`);
      if (url.pathname.endsWith("/oracle-mock-capability")) return jsonResponse({ enabled: true });
      if (url.pathname.endsWith("/21/oracle-mock-test") && method === "POST") return jsonResponse({
        profile_id: 21, source_name: "oracle_demis_mock", environment: "development",
        status: "SUCCEEDED", live_connection_tested: true, reachable: true, read_only: true,
        failure_category: null,
      });
      if (url.pathname.endsWith("/21/oracle-mock-enable") && method === "POST") return jsonResponse(profile({ enabled: true }));
      return null;
    }]);
    try {
      render(<OracleMockActions profile={profile()}
        onRefresh={onRefresh} />);
      const activate = await screen.findByRole("button", { name: "연결 검사 후 활성화" });
      expect(activate).toBeDisabled();
      await userEvent.click(screen.getByRole("button", { name: "읽기 전용 연결 검사" }));
      expect(await screen.findByText(/연결 검사 성공/)).toBeInTheDocument();
      expect(activate).toBeEnabled();
      await userEvent.click(activate);
      expect(confirm).toHaveBeenCalledOnce();
      expect(calls).not.toContain("POST /api/v1/connection-profiles/21/oracle-mock-enable");
      confirm.mockReturnValue(true);
      await userEvent.click(activate);
      await waitFor(() => expect(onRefresh).toHaveBeenCalledOnce());
      expect(calls).toContain("POST /api/v1/connection-profiles/21/oracle-mock-enable");
      expect(screen.queryByText(REF)).not.toBeInTheDocument();
      expect(calls.some((c) => c.endsWith("/test-connection") || c.endsWith("/enable"))).toBe(false);
    } finally { restore(); }
  });

  it("failed probe never enables and never displays attacker-controlled response", async () => {
    const raw = "SENSITIVE_ERROR_UNTRUSTED";
    const calls: string[] = [];
    const restore = installFetchMock([(url, init) => {
      calls.push(`${init?.method || "GET"} ${url.pathname}`);
      if (url.pathname.endsWith("/oracle-mock-capability")) return jsonResponse({ enabled: true });
      if (url.pathname.endsWith("/oracle-mock-test")) return jsonResponse({
        profile_id: 21, source_name: "oracle_demis_mock", environment: "development",
        status: "FAILED", live_connection_tested: true, reachable: false, read_only: null,
        failure_category: raw,
      });
      return null;
    }]);
    try {
      render(<OracleMockActions profile={profile()}
        onRefresh={vi.fn()} />);
      await userEvent.click(await screen.findByRole("button", { name: "읽기 전용 연결 검사" }));
      expect(await screen.findByText(/연결 검사 실패/)).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "연결 검사 후 활성화" })).toBeDisabled();
      expect(screen.queryByText(raw)).not.toBeInTheDocument();
      expect(calls.every((c) => !c.includes("oracle-mock-enable"))).toBe(true);
    } finally { restore(); }
  });

  it("does not apply stale probe result after selecting another profile", async () => {
    let finish!: (r: Response) => void;
    const restore = installFetchMock([(url) => {
      if (url.pathname.endsWith("/oracle-mock-capability")) return jsonResponse({ enabled: true });
      if (url.pathname.endsWith("/21/oracle-mock-test")) {
        return new Promise<Response>((resolve) => { finish = resolve; });
      }
      return null;
    }]);
    try {
      const { rerender } = render(<OracleMockActions profile={profile()}
        onRefresh={vi.fn()} />);
      await userEvent.click(await screen.findByRole("button", { name: "읽기 전용 연결 검사" }));
      await waitFor(() => expect(typeof finish).toBe("function"));
      rerender(<OracleMockActions profile={profile({ id: 22 })}
        onRefresh={vi.fn()} />);
      finish(jsonResponse({
        profile_id: 21, source_name: "oracle_demis_mock", environment: "development",
        status: "SUCCEEDED", live_connection_tested: true, reachable: true, read_only: true,
        failure_category: null,
      }));
      await waitFor(() => expect(screen.getByRole("button", { name: "연결 검사 후 활성화" })).toBeDisabled());
      expect(screen.queryByText(/연결 검사 성공/)).not.toBeInTheDocument();
    } finally { restore(); }
  });
});
