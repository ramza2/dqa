import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { InspectorTargetReviewPanel } from "../components/InspectorTargetReviewPanel";
import type { InspectorTargetReview } from "../types/inspectorTargetReview";
import { installFetchMock, jsonResponse } from "./mocks";

const URL_PREFIX = "/api/v1/connection-profiles/";
const SECRET = "env:DEMIS_INSPECT_SECRET_SYNTHETIC_DO_NOT_SHOW";

function review(id: number, overrides: Partial<InspectorTargetReview> = {}): InspectorTargetReview {
  return {
    profile_id: id,
    inspector_configuration_state: "CONFIGURED_UNVERIFIED",
    comparison_state: "STRUCTURAL_MATCH_UNVERIFIED",
    mismatch_fields: [], profile_enabled: false,
    inspector_bound_to_profile: false, connection_authorized: false,
    live_connection_tested: false, credential_values_resolved: false,
    ...overrides,
  };
}

afterEach(() => { vi.restoreAllMocks(); });

describe("S-05-C2 offline-only Inspector target review", () => {
  it("calls only explicit review GET and shows unverified structural equality", async () => {
    const requests: string[] = [];
    const restore = installFetchMock([(url, init) => {
      requests.push(`${init?.method || "GET"} ${url.pathname}`);
      if (url.pathname === `${URL_PREFIX}3/inspector-target-review`)
        return jsonResponse(review(3));
      return null;
    }]);
    try {
      render(<InspectorTargetReviewPanel profileId={3} />);
      expect(requests).toHaveLength(0);
      await userEvent.click(screen.getByRole("button", { name: "설정 대조 조회 (연결 없음)" }));
      expect(await screen.findByText(/문자열\/숫자 일치 \(미검증\)/)).toBeInTheDocument();
      expect(requests).toEqual(["GET /api/v1/connection-profiles/3/inspector-target-review"]);
      expect(screen.getByText(/연결 승인 없음/)).toBeInTheDocument();
    } finally { restore(); }
  });

  it("shows sanitized mismatch field names only, never server secrets or connection details", async () => {
    const restore = installFetchMock([(url) => url.pathname.endsWith("/inspector-target-review")
      ? jsonResponse({ ...review(4, {
        comparison_state: "TARGET_METADATA_MISMATCH",
        mismatch_fields: ["host", "port", "database_name_vs_service_name"],
      }), secret: SECRET, target_host: "sensitive.internal" }) : null]);
    try {
      render(<InspectorTargetReviewPanel profileId={4} />);
      await userEvent.click(screen.getByRole("button", { name: "설정 대조 조회 (연결 없음)" }));
      expect(await screen.findByText(/구조 불일치/)).toBeInTheDocument();
      expect(screen.getByText(/Host, Port, Database Name/)).toBeInTheDocument();
      expect(screen.queryByText(SECRET)).not.toBeInTheDocument();
      expect(screen.queryByText("sensitive.internal")).not.toBeInTheDocument();
    } finally { restore(); }
  });

  it("displays disabled/environment-blocked without claiming approval", async () => {
    const restore = installFetchMock([(url) => url.pathname.endsWith("/inspector-target-review")
      ? jsonResponse(review(5, {
        inspector_configuration_state: "ENV_BLOCKED",
        comparison_state: "NOT_COMPARABLE",
      })) : null]);
    try {
      render(<InspectorTargetReviewPanel profileId={5} />);
      await userEvent.click(screen.getByRole("button", { name: "설정 대조 조회 (연결 없음)" }));
      expect(await screen.findByText(/현재 환경에서 Inspector 실행 차단/)).toBeInTheDocument();
      expect(screen.getByText(/설정 구조 대조 불가/)).toBeInTheDocument();
    } finally { restore(); }
  });

  it("rejects forged connection-authorized results instead of displaying a pass", async () => {
    const restore = installFetchMock([(url) => url.pathname.endsWith("/inspector-target-review")
      ? jsonResponse({ ...review(6), connection_authorized: true }) : null]);
    try {
      render(<InspectorTargetReviewPanel profileId={6} />);
      await userEvent.click(screen.getByRole("button", { name: "설정 대조 조회 (연결 없음)" }));
      expect(await screen.findByRole("alert")).toHaveTextContent("안전한 설정 대조 응답");
      expect(screen.queryByText(/문자열\/숫자 일치/)).not.toBeInTheDocument();
    } finally { restore(); }
  });

  it("ignores an old request after switching profile IDs", async () => {
    let resolveOld: ((value: Response) => void) | undefined;
    const restore = installFetchMock([(url) => {
      if (url.pathname === `${URL_PREFIX}7/inspector-target-review`)
        return new Promise<Response>((resolve) => { resolveOld = resolve; });
      if (url.pathname === `${URL_PREFIX}8/inspector-target-review`)
        return jsonResponse(review(8, {
          inspector_configuration_state: "DISABLED", comparison_state: "NOT_COMPARABLE",
        }));
      return null;
    }]);
    try {
      const { rerender } = render(<InspectorTargetReviewPanel profileId={7} />);
      await userEvent.click(screen.getByRole("button", { name: "설정 대조 조회 (연결 없음)" }));
      await waitFor(() => expect(resolveOld).toBeDefined());
      rerender(<InspectorTargetReviewPanel profileId={8} />);
      await userEvent.click(screen.getByRole("button", { name: "설정 대조 조회 (연결 없음)" }));
      expect(await screen.findByText(/Inspector 비활성/)).toBeInTheDocument();
      resolveOld!(jsonResponse(review(7)));
      await waitFor(() => expect(screen.getByText(/Inspector 비활성/)).toBeInTheDocument());
      expect(screen.queryByText(/문자열\/숫자 일치/)).not.toBeInTheDocument();
    } finally { restore(); }
  });

  it("handles 403 without echoing untrusted message payloads", async () => {
    const restore = installFetchMock([(url) => url.pathname.endsWith("/inspector-target-review")
      ? jsonResponse({ detail: { code: "DENIED", message: SECRET } }, 403) : null]);
    try {
      render(<InspectorTargetReviewPanel profileId={9} />);
      await userEvent.click(screen.getByRole("button", { name: "설정 대조 조회 (연결 없음)" }));
      expect(await screen.findByRole("alert")).toHaveTextContent("설정 대조에 실패했습니다");
      expect(screen.queryByText(SECRET)).not.toBeInTheDocument();
    } finally { restore(); }
  });
});
