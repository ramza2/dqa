import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "../App";
import { ConnectionProfilePortal } from "../components/ConnectionProfilePortal";
import type { ConnectionProfile, ConnectionProfileDiagnostics } from "../types/connectionProfile";
import { installFetchMock, jsonResponse } from "./mocks";

const HIDDEN_REF = "vault://SYNTHETIC_INTERNAL_REFERENCE_NOT_FOR_DISPLAY";

function profile(id = 1, enabled = false): ConnectionProfile {
  return {
    id, name: `Mock profile ${id}`, source_name: `test_source_${id}`,
    environment: "development", enabled, dbms_type: "oracle",
    host: "synthetic.invalid", port: 1521, database_name: "SYNTHETIC",
    username: "test_readonly", credential_secret_ref: HIDDEN_REF,
    created_by: "test-admin", updated_by: "test-admin",
    created_at: "2026-10-16T00:00:00Z", updated_at: "2026-10-16T00:00:00Z",
  };
}

function diagnostics(p: ConnectionProfile): ConnectionProfileDiagnostics {
  return {
    profile_id: p.id, source_name: p.source_name, environment: p.environment,
    enabled: p.enabled, credential_reference_configured: true,
    target_metadata_configured: true,
    status: p.enabled ? "CONFIGURED_ENABLED" : "CONFIGURED_DISABLED",
    issues: [], live_connection_tested: false,
  };
}

function mockProfiles(initial: ConnectionProfile[]) {
  let profiles = [...initial];
  const calls: { path: string; method: string; body: unknown }[] = [];
  const restore = installFetchMock([
    (url, init) => {
      if (!url.pathname.startsWith("/api/v1/connection-profiles")) return null;
      const method = init?.method || "GET";
      const body = init?.body ? JSON.parse(String(init.body)) as unknown : null;
      calls.push({ path: url.pathname, method, body });
      if (url.pathname === "/api/v1/connection-profiles" && method === "GET") {
        const filtered = profiles.filter((p) =>
          (!url.searchParams.get("source_name") || p.source_name === url.searchParams.get("source_name")) &&
          (!url.searchParams.get("environment") || p.environment === url.searchParams.get("environment")));
        const limit = Number(url.searchParams.get("limit") || 20);
        const offset = Number(url.searchParams.get("offset") || 0);
        return jsonResponse({ items: filtered.slice(offset, offset + limit),
          total: filtered.length, limit, offset });
      }
      if (url.pathname === "/api/v1/connection-profiles" && method === "POST") {
        const request = body as { name: string; source_name: string; environment: string };
        const created = { ...profile(90), ...request, enabled: false, credential_secret_ref: null };
        profiles = [...profiles, created];
        return jsonResponse(created, 201);
      }
      const match = url.pathname.match(/^\/api\/v1\/connection-profiles\/(\d+)(\/diagnostics|\/disable)?$/);
      if (!match) return null;
      const id = Number(match[1]);
      const p = profiles.find((item) => item.id === id);
      if (!p) return jsonResponse({ detail: { code: "CONNECTION_PROFILE_NOT_FOUND" } }, 404);
      if (match[2] === "/diagnostics" && method === "GET") return jsonResponse(diagnostics(p));
      if (!match[2] && method === "GET") return jsonResponse(p);
      if (!match[2] && method === "PATCH") {
        const updated = { ...p, ...(body as object) };
        profiles = profiles.map((item) => item.id === id ? updated : item);
        return jsonResponse(updated);
      }
      if (match[2] === "/disable" && method === "POST") {
        const updated = { ...p, enabled: false };
        profiles = profiles.map((item) => item.id === id ? updated : item);
        return jsonResponse(updated);
      }
      return jsonResponse({ detail: { code: "UNEXPECTED_ACTION" } }, 500);
    },
  ]);
  return { calls, restore };
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("S-05-C1 Connection Profile metadata UI", () => {
  it("mounts from primary nav, loads configuration-only detail and masks credential ref", async () => {
    const mock = mockProfiles([profile()]);
    try {
      render(<App />);
      await userEvent.click(screen.getByRole("tab", { name: "Connection Profiles" }));
      expect(await screen.findByTestId("connection-profile-portal")).toBeInTheDocument();
      await userEvent.click(await screen.findByRole("button", { name: "상세: Mock profile 1" }));
      const panel = await screen.findByRole("region", { name: "Connection Profile 상세" });
      expect(await within(panel).findByText("설정됨 (값 비표시)")).toBeInTheDocument();
      expect(await within(panel).findByText("설정 완료 · 비활성")).toBeInTheDocument();
      expect(screen.queryByText(HIDDEN_REF)).not.toBeInTheDocument();
      expect(mock.calls.some((c) => /test-connection|\/enable/.test(c.path))).toBe(false);
      expect(mock.calls.some((c) => c.path.endsWith("/diagnostics"))).toBe(true);
    } finally {
      mock.restore();
    }
  });

  it("creates disabled metadata without credential input, then updates only changed fields", async () => {
    const mock = mockProfiles([]);
    try {
      render(<ConnectionProfilePortal />);
      await userEvent.click(await screen.findByRole("button", { name: "비활성 프로필 등록" }));
      fireEvent.change(screen.getByRole("textbox", { name: "Profile name" }), {
        target: { value: "Synthetic replica metadata" },
      });
      fireEvent.change(screen.getByRole("textbox", { name: "Profile source_name" }), {
        target: { value: "synthetic_replica" },
      });
      fireEvent.change(screen.getByRole("textbox", { name: "Profile environment" }), {
        target: { value: "test" },
      });
      await userEvent.click(screen.getByRole("button", { name: "저장" }));
      await waitFor(() => expect(mock.calls.some((c) =>
        c.method === "POST" && c.path === "/api/v1/connection-profiles")).toBe(true));
      const create = mock.calls.find((c) => c.method === "POST");
      expect(create?.body).toMatchObject({
        name: "Synthetic replica metadata",
        source_name: "synthetic_replica",
        environment: "test",
      });
      expect(create?.body).not.toHaveProperty("credential_secret_ref");
      await screen.findByRole("region", { name: "Connection Profile 상세" });
      await userEvent.click(await screen.findByRole("button", { name: "정보 수정" }));
      const sourceField = screen.getByRole("textbox", { name: "Profile source_name" });
      expect(sourceField).toBeDisabled();
      expect(screen.getByRole("textbox", { name: "Profile environment" })).toBeDisabled();
      fireEvent.change(screen.getByRole("textbox", { name: "Profile name" }), {
        target: { value: "Renamed mock" },
      });
      await userEvent.click(screen.getByRole("button", { name: "저장" }));
      await waitFor(() => expect(mock.calls.some((c) => c.method === "PATCH")).toBe(true));
      const patch = mock.calls.find((c) => c.method === "PATCH");
      expect(patch?.body).toEqual({ name: "Renamed mock" });
      expect(mock.calls.some((c) => /test-connection|\/enable/.test(c.path))).toBe(false);
    } finally {
      mock.restore();
    }
  });

  it("requires confirmation to disable an enabled profile and offers no enable action", async () => {
    const mock = mockProfiles([profile(2, true)]);
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
    try {
      render(<ConnectionProfilePortal />);
      await userEvent.click(await screen.findByRole("button", { name: "상세: Mock profile 2" }));
      const panel = await screen.findByRole("region", { name: "Connection Profile 상세" });
      expect(await within(panel).findByRole("button", { name: /정보 수정/ })).toBeDisabled();
      await userEvent.click(within(panel).getByRole("button", { name: "비활성화" }));
      expect(confirm).toHaveBeenCalledOnce();
      expect(mock.calls.some((c) => c.path.endsWith("/disable"))).toBe(false);
      confirm.mockReturnValue(true);
      await userEvent.click(within(panel).getByRole("button", { name: "비활성화" }));
      await waitFor(() => expect(mock.calls.some((c) => c.path.endsWith("/disable"))).toBe(true));
      expect(mock.calls.some((c) => /test-connection|\/enable/.test(c.path))).toBe(false);
    } finally {
      mock.restore();
    }
  });

  it("shows generic 403 error without reflecting untrusted API diagnostic fields", async () => {
    const restore = installFetchMock([
      (url) => url.pathname === "/api/v1/connection-profiles"
        ? jsonResponse({ detail: { code: "DENIED", message: HIDDEN_REF } }, 403) : null,
    ]);
    try {
      render(<ConnectionProfilePortal />);
      expect(await screen.findByRole("alert")).toHaveTextContent("관리 권한이 없습니다");
      expect(screen.queryByText(HIDDEN_REF)).not.toBeInTheDocument();
    } finally {
      restore();
    }
  });

  it("drops stale detail responses after switching selected profiles", async () => {
    const a = profile(1), b = profile(2);
    let resolveFirst: ((value: Response) => void) | undefined;
    const restore = installFetchMock([
      (url) => {
        if (url.pathname === "/api/v1/connection-profiles") {
          return jsonResponse({ items: [a, b], total: 2, limit: 20, offset: 0 });
        }
        if (url.pathname.endsWith("/1/diagnostics")) return jsonResponse(diagnostics(a));
        if (url.pathname.endsWith("/2/diagnostics")) return jsonResponse(diagnostics(b));
        if (url.pathname.endsWith("/1")) {
          return new Promise<Response>((resolve) => { resolveFirst = resolve; });
        }
        if (url.pathname.endsWith("/2")) return jsonResponse(b);
        return null;
      },
    ]);
    try {
      render(<ConnectionProfilePortal />);
      await userEvent.click(await screen.findByRole("button", { name: "상세: Mock profile 1" }));
      await waitFor(() => expect(resolveFirst).toBeDefined());
      await userEvent.click(screen.getByRole("button", { name: "상세: Mock profile 2" }));
      const panel = await screen.findByRole("region", { name: "Connection Profile 상세" });
      expect(await within(panel).findByText("Mock profile 2")).toBeInTheDocument();
      resolveFirst!(jsonResponse(a));
      await waitFor(() => expect(within(panel).getByText("Mock profile 2")).toBeInTheDocument());
      expect(within(panel).queryByText("Mock profile 1")).not.toBeInTheDocument();
    } finally {
      restore();
    }
  });
});
