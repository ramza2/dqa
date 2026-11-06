import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "../App";
import type { ConnectionProfile, ConnectionProfileDiagnostics } from "../types/connectionProfile";
import { installFetchMock, jsonResponse } from "./mocks";

const ROOT = "/api/v1/connection-profiles";
const HIDDEN = "env:VERY_PRIVATE_SYNTHETIC_SECRET_REFERENCE";

function profile(id: number, source = "oracle_demis_mock"): ConnectionProfile {
  return {
    id, name: `Target ${id}`, source_name: source,
    environment: source === "oracle_demis_mock" ? "development" : "production",
    enabled: true, dbms_type: "oracle", host: "synthetic.invalid", port: 1521,
    database_name: "FREEPDB1", username: "SYNTHETIC_RO",
    credential_secret_ref: HIDDEN, created_by: null, updated_by: null,
    created_at: "2026-11-05T00:00:00Z", updated_at: "2026-11-05T00:00:00Z",
  };
}

function diagnostics(p: ConnectionProfile): ConnectionProfileDiagnostics {
  return {
    profile_id: p.id, source_name: p.source_name, environment: p.environment,
    enabled: p.enabled, status: "CONFIGURED_ENABLED",
    target_metadata_configured: true, credential_reference_configured: true,
    live_connection_tested: false, issues: [],
  };
}

const targetReview = (p: ConnectionProfile) => ({
  profile_id: p.id, profile_enabled: p.enabled,
  inspector_configuration_state: "CONFIGURED_UNVERIFIED",
  comparison_state: "STRUCTURAL_MATCH_UNVERIFIED",
  mismatch_fields: [], inspector_bound_to_profile: false,
  connection_authorized: false, live_connection_tested: false,
  credential_values_resolved: false,
});

afterEach(() => vi.restoreAllMocks());

describe("M5-UX6 read-only DB Analysis Preflight workspace", () => {
  it("shows a separate navigation route and only GET requests for mock config and readiness", async () => {
    const p = profile(41);
    const calls: string[] = [];
    const restore = installFetchMock([(url, init) => {
      if (!url.pathname.startsWith("/api/v1/")) return null;
      calls.push(`${init?.method || "GET"} ${url.pathname}`);
      if (url.pathname === ROOT) return jsonResponse({ total: 1, limit: 20, offset: 0, items: [p] });
      if (url.pathname === `${ROOT}/41`) return jsonResponse(p);
      if (url.pathname === `${ROOT}/41/diagnostics`) return jsonResponse(diagnostics(p));
      if (url.pathname === `${ROOT}/41/inspector-target-review`)
        return jsonResponse({ ...targetReview(p), credential_secret_ref: HIDDEN });
      if (url.pathname === "/api/v1/schema-inspector/mock-targets/41/readiness")
        return jsonResponse({
          profile_id: 41, ready: true, schema_name: "DEMIS_OWNER",
          reason_code: "READY_FOR_DEV_INSPECTION", live_connection_tested: false,
          site_approved: false, catalog_activated: false,
        });
      return null;
    }]);
    try {
      render(<App />);
      await userEvent.click(screen.getByRole("tab", { name: "DB 분석 사전점검" }));
      expect(screen.getByTestId("db-analysis-preflight")).toBeInTheDocument();
      expect(screen.getByTestId("preflight-not-authority")).toHaveTextContent("독립 DBA Preflight");
      expect(calls).toEqual([`GET ${ROOT}`]);

      await userEvent.selectOptions(await screen.findByRole("combobox", { name: "Preflight DB Target" }), "41");
      expect(await screen.findByText("서버 설정 존재 (값 비표시)")).toBeInTheDocument();
      expect(screen.queryByText(HIDDEN)).not.toBeInTheDocument();
      expect(screen.queryByRole("button", { name: "스키마 메타데이터 분석" })).not.toBeInTheDocument();
      expect(screen.queryByRole("button", { name: /Snapshot 저장/ })).not.toBeInTheDocument();

      await userEvent.click(screen.getByRole("button", { name: "설정 대조 조회 (연결 없음)" }));
      expect(await screen.findByText(/문자열\/숫자 일치 \(미검증\)/)).toBeInTheDocument();
      await userEvent.click(screen.getByRole("button", { name: "Inspector 연계 조건 확인 (접속 없음)" }));
      expect(await screen.findByText(/대상 스키마 DEMIS_OWNER/)).toBeInTheDocument();
      expect(screen.getByRole("region", { name: "후속 승인 단계" })).toHaveTextContent("승인 대기");
      expect(calls).toContain("GET /api/v1/schema-inspector/mock-targets/41/readiness");
      expect(calls).toContain(`GET ${ROOT}/41/inspector-target-review`);
      expect(calls.every((c) => c.startsWith("GET "))).toBe(true);
      expect(screen.queryByText(HIDDEN)).not.toBeInTheDocument();
    } finally { restore(); }
  });

  it("blocks live target schema discovery and mock controls even when a profile is enabled", async () => {
    const p = profile(53, "demis_replica_candidate");
    const calls: string[] = [];
    const restore = installFetchMock([(url, init) => {
      calls.push(`${init?.method || "GET"} ${url.pathname}`);
      if (url.pathname === ROOT) return jsonResponse({ total: 1, limit: 20, offset: 0, items: [p] });
      if (url.pathname === `${ROOT}/53`) return jsonResponse(p);
      if (url.pathname === `${ROOT}/53/diagnostics`) return jsonResponse(diagnostics(p));
      return null;
    }]);
    try {
      render(<App />);
      await userEvent.click(screen.getByRole("tab", { name: "DB 분석 사전점검" }));
      await userEvent.selectOptions(await screen.findByRole("combobox", { name: "Preflight DB Target" }), "53");
      expect(await screen.findByTestId("preflight-real-target-blocked")).toHaveTextContent("분석 실행이 차단");
      expect(screen.queryByText(/대상 스키마 DEMIS_OWNER/)).not.toBeInTheDocument();
      expect(screen.queryByRole("button", { name: /Inspector 연계 조건 확인/ })).not.toBeInTheDocument();
      expect(calls.every((c) => c.startsWith("GET "))).toBe(true);
    } finally { restore(); }
  });

  it("resets per-target diagnostic and comparison results when the selection changes", async () => {
    const first = profile(61);
    const second = profile(62, "demis_replica_candidate");
    let finishOld: ((response: Response) => void) | undefined;
    const restore = installFetchMock([(url) => {
      if (url.pathname === ROOT) return jsonResponse({ total: 2, limit: 20, offset: 0, items: [first, second] });
      if (url.pathname === `${ROOT}/61`) return new Promise<Response>((resolve) => { finishOld = resolve; });
      if (url.pathname === `${ROOT}/61/diagnostics`) return jsonResponse(diagnostics(first));
      if (url.pathname === `${ROOT}/62`) return jsonResponse(second);
      if (url.pathname === `${ROOT}/62/diagnostics`) return jsonResponse(diagnostics(second));
      return null;
    }]);
    try {
      render(<App />);
      await userEvent.click(screen.getByRole("tab", { name: "DB 분석 사전점검" }));
      const selector = await screen.findByRole("combobox", { name: "Preflight DB Target" });
      await userEvent.selectOptions(selector, "61");
      await waitFor(() => expect(finishOld).toBeDefined());
      await userEvent.selectOptions(selector, "62");
      expect(await screen.findByTestId("preflight-real-target-blocked")).toBeInTheDocument();
      expect(within(screen.getByRole("region", { name: "Target 설정 진단" }))
        .getByText("demis_replica_candidate")).toBeInTheDocument();
      finishOld!(jsonResponse(first));
      await waitFor(() => expect(screen.getByTestId("preflight-real-target-blocked")).toBeInTheDocument());
      expect(screen.queryByText("oracle_demis_mock")).not.toBeInTheDocument();
    } finally { restore(); }
  });

  it("paginates target selection and handles denied listings without leaking server responses", async () => {
    const pages: number[] = [];
    const restore = installFetchMock([(url) => {
      if (url.pathname !== ROOT) return null;
      const offset = Number(url.searchParams.get("offset"));
      pages.push(offset);
      return offset === 0
        ? jsonResponse({ total: 21, limit: 20, offset: 0, items: Array.from({ length: 20 }, (_, i) => profile(i + 1)) })
        : jsonResponse({ total: 21, limit: 20, offset: 20, items: [profile(21)] });
    }]);
    try {
      render(<App />);
      await userEvent.click(screen.getByRole("tab", { name: "DB 분석 사전점검" }));
      await screen.findByRole("option", { name: /Target 1 \/ oracle_demis_mock/ });
      await userEvent.click(screen.getByRole("button", { name: "다음" }));
      expect(await screen.findByRole("option", { name: /Target 21 \/ oracle_demis_mock/ })).toBeInTheDocument();
      expect(screen.queryByRole("option", { name: /Target 1 \/ oracle_demis_mock/ })).not.toBeInTheDocument();
      expect(pages).toEqual([0, 20]);
    } finally { restore(); }

    cleanup();
    const denied = installFetchMock([(url) => url.pathname === ROOT
      ? jsonResponse({ detail: `403 ${HIDDEN}` }, 403) : null]);
    try {
      render(<App />);
      await userEvent.click(screen.getByRole("tab", { name: "DB 분석 사전점검" }));
      expect(await screen.findByRole("alert")).toHaveTextContent("연결 프로필 관리 권한이 필요합니다");
      expect(screen.queryByText(HIDDEN)).not.toBeInTheDocument();
    } finally { denied(); }
  });

  it.each([
    { status: 401, message: "인증 정보가 확인되지 않았습니다" },
    { status: 503, message: "인증 서비스가 준비되지 않았습니다" },
    { status: 502, message: "서버 연결 상태를 확인" },
  ])("distinguishes HTTP $status without echoing a potentially sensitive API error", async ({ status, message }) => {
    const denied = installFetchMock([(url) => url.pathname === ROOT
      ? jsonResponse({ detail: `untrusted ${HIDDEN}` }, status) : null]);
    try {
      render(<App />);
      await userEvent.click(screen.getByRole("tab", { name: "DB 분석 사전점검" }));
      expect(await screen.findByRole("alert")).toHaveTextContent(message);
      expect(screen.queryByText(HIDDEN)).not.toBeInTheDocument();
      expect(screen.getByRole("combobox", { name: "Preflight DB Target" })).toBeDisabled();
    } finally { denied(); }
  });
});
