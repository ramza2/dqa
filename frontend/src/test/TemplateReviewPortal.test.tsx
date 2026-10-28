import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "../App";
import { TemplateReviewPortal } from "../components/TemplateReviewPortal";
import type {
  ReviewTemplateDetail, ReviewTemplateList, ReviewTemplateSummary,
  TemplateSqlSafetyReview,
} from "../types/templateReview";
import { installFetchMock, jsonResponse } from "./mocks";

afterEach(() => { cleanup(); vi.restoreAllMocks(); });

const compatibility = {
  mode: "EXACT_FINGERPRINT" as const,
  compatible: true,
  pinned_revision_id: 8,
  pinned_schema_fingerprint: "synthetic-fingerprint",
  current_revision_id: 8,
  current_schema_fingerprint: "synthetic-fingerprint",
};

const row: ReviewTemplateSummary = {
  id: 21, stable_key: "ward.lookup", name: "병동 조회",
  description: "합성 템플릿", source_name: "oracle_demis_mock",
  target_schemas: ["DEMIS_OWNER"], enabled: false,
  current_version_id: 34, current_version: 2,
  approval_status: "IN_REVIEW", compatibility,
  created_at: "2026-10-28T08:00:00Z", updated_at: "2026-10-28T08:05:00Z",
};

const listing: ReviewTemplateList = {
  total: 1, limit: 50, offset: 0, items: [row],
};

const detail: ReviewTemplateDetail = {
  ...row,
  version: {
    id: 34, version: 2,
    sql_text: "SELECT WARD_CD FROM DEMIS_OWNER.T1 WHERE WARD_CD = :ward_cd",
    parameter_schema: [{
      name: "ward_cd", type: "string", required: true, sensitive: true,
    }],
    row_limit: 50, timeout_seconds: 15,
    approval_status: "IN_REVIEW", compatibility,
    created_by: "synthetic-author",
    created_at: "2026-10-28T08:00:00Z",
    approved_by: null, approved_at: null, approval_note: null,
  },
};

const safety: TemplateSqlSafetyReview = {
  template_id: 21, version_id: 34, version: 2,
  safe: true, statement_count: 1,
  referenced_parameters: ["ward_cd"],
  declared_parameters: ["ward_cd"],
  issues: [],
};

function handlers(opts?: {
  list?: ReviewTemplateList;
  detail?: ReviewTemplateDetail;
  safety?: TemplateSqlSafetyReview;
  deny?: boolean;
  onRequest?: (method: string, path: string) => void;
}) {
  return [
    (url: URL, init?: RequestInit) => {
      const path = url.pathname;
      opts?.onRequest?.(init?.method ?? "GET", path);
      if (!path.startsWith("/api/v1/query-templates")) return null;
      if (opts?.deny) return jsonResponse({
        detail: { code: "AUTHORIZATION_DENIED", message: "permission denied" },
      }, 403);
      if (path === "/api/v1/query-templates") return jsonResponse(opts?.list ?? listing);
      if (path === "/api/v1/query-templates/21") return jsonResponse(opts?.detail ?? detail);
      if (path === "/api/v1/query-templates/21/sql-safety") {
        return jsonResponse(opts?.safety ?? safety);
      }
      return null;
    },
  ];
}

describe("M3-C1 read-only template review portal", () => {
  it("navigates from the dashboard without invoking a review mutation", async () => {
    const user = userEvent.setup();
    const methods: string[] = [];
    const restore = installFetchMock(handlers({
      onRequest: (method) => { methods.push(method); },
    }));
    try {
      render(<App />);
      await user.click(screen.getByRole("button", { name: "템플릿 검토 현황 보기 (읽기 전용)" }));
      expect(await screen.findByRole("heading", { name: "Query Template 검토 현황" })).toBeInTheDocument();
      expect(methods).toEqual([]);
    } finally { restore(); }
  });

  it("shows existing workflow, Catalog compatibility and SQL safety without write calls", async () => {
    const user = userEvent.setup();
    const methods: string[] = [];
    const restore = installFetchMock(handlers({
      onRequest: (method) => { methods.push(method); },
    }));
    try {
      render(<TemplateReviewPortal />);
      await user.type(screen.getByLabelText("템플릿 Source 필터"), "oracle_demis_mock");
      await user.click(screen.getByRole("button", { name: "템플릿 목록 조회" }));
      const choose = await screen.findByRole("button", { name: "검토 대상 병동 조회" });
      expect(choose).toHaveTextContent("검토 중");
      await user.click(choose);
      const reviewed = await screen.findByTestId("template-review-detail");
      expect(reviewed).toHaveTextContent("검증 통과 (승인 아님)");
      expect(reviewed).toHaveTextContent("고정 Revision #8");
      expect(reviewed).toHaveTextContent("WARD_CD");
      expect(screen.queryByRole("button", { name: "승인" })).not.toBeInTheDocument();
      expect(screen.queryByRole("button", { name: "반려" })).not.toBeInTheDocument();
      expect(screen.queryByRole("button", { name: "조회 실행" })).not.toBeInTheDocument();
      expect(methods).toEqual(["GET", "GET", "GET"]);
    } finally { restore(); }
  });

  it("fails closed if SQL safety references another template version", async () => {
    const user = userEvent.setup();
    const restore = installFetchMock(handlers({
      safety: { ...safety, version_id: 999 },
    }));
    try {
      render(<TemplateReviewPortal />);
      await user.click(screen.getByRole("button", { name: "템플릿 목록 조회" }));
      await user.click(await screen.findByRole("button", { name: "검토 대상 병동 조회" }));
      expect(await screen.findByRole("alert")).toHaveTextContent("버전·상태 또는 Catalog가 변경되었습니다");
      expect(screen.queryByTestId("template-review-detail")).not.toBeInTheDocument();
      expect(screen.queryByText(detail.version.sql_text)).not.toBeInTheDocument();
    } finally { restore(); }
  });

  it("does not reveal SQL for a caller without TEMPLATE_READ", async () => {
    const user = userEvent.setup();
    const restore = installFetchMock(handlers({ deny: true }));
    try {
      render(<TemplateReviewPortal />);
      await user.click(screen.getByRole("button", { name: "템플릿 목록 조회" }));
      expect(await screen.findByRole("alert")).toHaveTextContent("템플릿 검토 현황 열람 권한이 없습니다.");
      expect(screen.queryByRole("button", { name: "검토 대상 병동 조회" })).not.toBeInTheDocument();
      expect(screen.queryByTestId("template-review-detail")).not.toBeInTheDocument();
    } finally { restore(); }
  });

  it("invalidates in-flight list responses when source filter changes", async () => {
    const user = userEvent.setup();
    const pending = { resolve: null as ((value: Response) => void) | null };
    const restore = installFetchMock([
      (url: URL) => {
        if (url.pathname === "/api/v1/query-templates") {
          return new Promise<Response>((resolve) => { pending.resolve = resolve; });
        }
        return null;
      },
    ]);
    try {
      render(<TemplateReviewPortal />);
      await user.click(screen.getByRole("button", { name: "템플릿 목록 조회" }));
      await waitFor(() => expect(pending.resolve).not.toBeNull());
      await user.type(screen.getByLabelText("템플릿 Source 필터"), "another_source");
      pending.resolve?.(jsonResponse(listing));
      await waitFor(() =>
        expect(screen.queryByRole("button", { name: "검토 대상 병동 조회" })).not.toBeInTheDocument()
      );
    } finally { restore(); }
  });

  it("filters review status within the page and resets selected details", async () => {
    const user = userEvent.setup();
    const restore = installFetchMock(handlers());
    try {
      render(<TemplateReviewPortal />);
      await user.click(screen.getByRole("button", { name: "템플릿 목록 조회" }));
      await screen.findByRole("button", { name: "검토 대상 병동 조회" });
      await user.selectOptions(screen.getByLabelText("템플릿 승인 상태 필터"), "APPROVED");
      expect(screen.queryByRole("button", { name: "검토 대상 병동 조회" })).not.toBeInTheDocument();
      expect(screen.getByText("현재 페이지에 해당 상태의 템플릿이 없습니다.")).toBeInTheDocument();
      await user.selectOptions(screen.getByLabelText("템플릿 승인 상태 필터"), "IN_REVIEW");
      expect(screen.getByRole("button", { name: "검토 대상 병동 조회" })).toBeInTheDocument();
    } finally { restore(); }
  });
});
