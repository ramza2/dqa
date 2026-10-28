import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "../App";
import { TemplateReviewPortal } from "../components/TemplateReviewPortal";
import type {
  ReviewTemplateDetail, ReviewTemplateList, ReviewTemplateSummary,
  TemplateReviewEventList, TemplateSqlSafetyReview,
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

const events: TemplateReviewEventList = {
  items: [{
    id: 1, template_id: 21, version_id: 34,
    from_status: "DRAFT", to_status: "IN_REVIEW",
    actor: "synthetic-author", note: "please review",
    created_at: "2026-10-28T08:01:00Z",
  }],
};

type HandlerOpts = {
  list?: ReviewTemplateList;
  detail?: ReviewTemplateDetail;
  safety?: TemplateSqlSafetyReview;
  events?: TemplateReviewEventList | "deny";
  denyList?: boolean;
  mutateStatus?: number;
  mutateCode?: string;
  mutateBody?: ReviewTemplateDetail;
  onRequest?: (method: string, path: string, body: string | null, url: URL) => void;
};

function handlers(opts?: HandlerOpts) {
  return [
    (url: URL, init?: RequestInit) => {
      const path = url.pathname;
      const method = init?.method ?? "GET";
      const body = typeof init?.body === "string" ? init.body : null;
      opts?.onRequest?.(method, path, body, url);
      if (!path.startsWith("/api/v1/query-templates")) return null;
      if (opts?.denyList && method === "GET" && path === "/api/v1/query-templates") {
        return jsonResponse({
          detail: { code: "AUTHORIZATION_DENIED", message: "permission denied" },
        }, 403);
      }
      if (method === "GET" && path === "/api/v1/query-templates") {
        return jsonResponse(opts?.list ?? listing);
      }
      if (method === "GET" && path === "/api/v1/query-templates/21") {
        return jsonResponse(opts?.detail ?? detail);
      }
      if (method === "GET" && path === "/api/v1/query-templates/21/sql-safety") {
        return jsonResponse(opts?.safety ?? safety);
      }
      if (method === "GET" && path === "/api/v1/query-templates/21/review-events") {
        if (opts?.events === "deny") {
          return jsonResponse({
            detail: { code: "AUTHORIZATION_DENIED", message: "permission denied" },
          }, 403);
        }
        return jsonResponse(opts?.events ?? events);
      }
      if (method !== "GET") {
        const status = opts?.mutateStatus ?? 200;
        if (status >= 400) {
          return jsonResponse({
            detail: {
              code: opts?.mutateCode ?? "AUTHORIZATION_DENIED",
              message: "mutation denied",
            },
          }, status);
        }
        return jsonResponse(opts?.mutateBody ?? {
          ...detail,
          approval_status: "APPROVED",
          version: { ...detail.version, approval_status: "APPROVED" },
        }, method === "POST" && path.endsWith("/versions") ? 201 : status);
      }
      return null;
    },
  ];
}

async function openInReviewDetail(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole("button", { name: "템플릿 목록 조회" }));
  await user.click(await screen.findByRole("button", { name: "검토 대상 병동 조회" }));
  await screen.findByTestId("template-review-detail");
}

describe("M3-C2 template authoring and review workflow", () => {
  it("navigates from the dashboard to the authoring portal", async () => {
    const user = userEvent.setup();
    const restore = installFetchMock(handlers());
    try {
      render(<App />);
      await user.click(screen.getByRole("button", { name: "템플릿 작성·검토 열기" }));
      expect(await screen.findByRole("heading", { name: "Query Template 작성·검토" }))
        .toBeInTheDocument();
    } finally { restore(); }
  });

  it("loads detail and review history without inventing execution", async () => {
    const user = userEvent.setup();
    const methods: string[] = [];
    const restore = installFetchMock(handlers({
      onRequest: (method) => { methods.push(method); },
    }));
    try {
      render(<TemplateReviewPortal />);
      await openInReviewDetail(user);
      expect(screen.getByTestId("template-review-detail"))
        .toHaveTextContent("검증 통과 (승인 아님)");
      await user.click(screen.getByRole("button", { name: "검토 이력 불러오기" }));
      expect(await screen.findByText(/초안 → 검토 중/)).toBeInTheDocument();
      expect(screen.queryByRole("button", { name: "조회 실행" })).not.toBeInTheDocument();
      expect(methods.filter((m) => m === "GET").length).toBeGreaterThanOrEqual(3);
    } finally { restore(); }
  });

  it("creates a DRAFT and reloads the list with the created source_name", async () => {
    const user = userEvent.setup();
    const posts: string[] = [];
    const listSourceFilters: string[] = [];
    const created: ReviewTemplateDetail = {
      ...detail,
      id: 21,
      approval_status: "DRAFT",
      version: { ...detail.version, approval_status: "DRAFT" },
    };
    const restore = installFetchMock(handlers({
      mutateBody: created,
      detail: created,
      list: { ...listing, items: [{ ...row, approval_status: "DRAFT" }] },
      onRequest: (method, path, _body, url) => {
        if (method === "POST") posts.push(path);
        if (method === "GET" && path === "/api/v1/query-templates") {
          listSourceFilters.push(url.searchParams.get("source_name") ?? "");
        }
      },
    }));
    try {
      render(<TemplateReviewPortal />);
      // Source filter starts empty; create must not list with stale "".
      expect(screen.getByLabelText("템플릿 Source 필터")).toHaveValue("");
      await user.click(screen.getByRole("button", { name: "새 템플릿 DRAFT 작성" }));
      await user.clear(screen.getByLabelText("작성 stable_key"));
      await user.type(screen.getByLabelText("작성 stable_key"), "ward.lookup");
      await user.clear(screen.getByLabelText("작성 이름"));
      await user.type(screen.getByLabelText("작성 이름"), "병동 조회");
      await user.clear(screen.getByLabelText("작성 Source 이름"));
      await user.type(screen.getByLabelText("작성 Source 이름"), "oracle_demis_mock");
      await user.click(screen.getByRole("button", { name: "DRAFT 생성" }));
      await waitFor(() => expect(posts).toContain("/api/v1/query-templates"));
      await waitFor(() => expect(listSourceFilters).toContain("oracle_demis_mock"));
      expect(await screen.findByText("DRAFT 템플릿을 생성했습니다.")).toBeInTheDocument();
      expect(screen.getByLabelText("템플릿 Source 필터")).toHaveValue("oracle_demis_mock");
    } finally { restore(); }
  });

  it("submits DRAFT for review via submit-review when editor matches server", async () => {
    const user = userEvent.setup();
    const draftDetail: ReviewTemplateDetail = {
      ...detail,
      approval_status: "DRAFT",
      version: { ...detail.version, approval_status: "DRAFT" },
    };
    const posts: string[] = [];
    const restore = installFetchMock(handlers({
      list: { ...listing, items: [{ ...row, approval_status: "DRAFT" }] },
      detail: draftDetail,
      mutateBody: {
        ...draftDetail,
        approval_status: "IN_REVIEW",
        version: { ...draftDetail.version, approval_status: "IN_REVIEW" },
      },
      onRequest: (method, path) => {
        if (method === "POST") posts.push(path);
      },
    }));
    try {
      render(<TemplateReviewPortal />);
      await user.click(screen.getByRole("button", { name: "템플릿 목록 조회" }));
      await user.click(await screen.findByRole("button", { name: "검토 대상 병동 조회" }));
      await screen.findByTestId("template-draft-editor");
      expect(screen.getByRole("button", { name: "검토 제출" })).toBeEnabled();
      await user.click(screen.getByRole("button", { name: "검토 제출" }));
      await waitFor(() =>
        expect(posts).toContain("/api/v1/query-templates/21/submit-review"),
      );
    } finally { restore(); }
  });

  it("blocks review submit while unsaved DRAFT edits remain", async () => {
    const user = userEvent.setup();
    const draftDetail: ReviewTemplateDetail = {
      ...detail,
      approval_status: "DRAFT",
      version: { ...detail.version, approval_status: "DRAFT" },
    };
    const posts: string[] = [];
    const restore = installFetchMock(handlers({
      list: { ...listing, items: [{ ...row, approval_status: "DRAFT" }] },
      detail: draftDetail,
      onRequest: (method, path) => {
        if (method === "POST") posts.push(path);
      },
    }));
    try {
      render(<TemplateReviewPortal />);
      await user.click(screen.getByRole("button", { name: "템플릿 목록 조회" }));
      await user.click(await screen.findByRole("button", { name: "검토 대상 병동 조회" }));
      await screen.findByTestId("template-draft-editor");
      await user.type(screen.getByLabelText("DRAFT SQL"), "\n-- unsaved");
      expect(screen.getByRole("button", { name: "검토 제출" })).toBeDisabled();
      expect(screen.getByText(/저장되지 않은 변경이 있습니다/)).toBeInTheDocument();
      expect(posts).not.toContain("/api/v1/query-templates/21/submit-review");
    } finally { restore(); }
  });

  it("approves only when UI gates pass and posts to approve API", async () => {
    const user = userEvent.setup();
    const posts: Array<{ path: string; body: string | null }> = [];
    const restore = installFetchMock(handlers({
      onRequest: (method, path, body) => {
        if (method === "POST") posts.push({ path, body });
      },
    }));
    try {
      render(<TemplateReviewPortal />);
      await openInReviewDetail(user);
      const approve = screen.getByRole("button", { name: "승인" });
      expect(approve).toBeEnabled();
      await user.click(approve);
      await waitFor(() =>
        expect(posts.some((p) => p.path === "/api/v1/query-templates/21/approve")).toBe(true),
      );
    } finally { restore(); }
  });

  it("disables approve and enable when SQL safety fails", async () => {
    const user = userEvent.setup();
    const restore = installFetchMock(handlers({
      safety: {
        ...safety,
        safe: false,
        issues: [{ code: "FORBIDDEN_STATEMENT", message: "DELETE blocked" }],
      },
    }));
    try {
      render(<TemplateReviewPortal />);
      await openInReviewDetail(user);
      expect(screen.getByRole("button", { name: "승인" })).toBeDisabled();
      expect(screen.getByText(/서버가 승인·활성화를 거부합니다/)).toBeInTheDocument();
    } finally { restore(); }
  });

  it("surfaces server SQL_UNSAFE reject instead of trusting the UI gate alone", async () => {
    const user = userEvent.setup();
    const restore = installFetchMock(handlers({
      mutateStatus: 409,
      mutateCode: "QUERY_TEMPLATE_SQL_UNSAFE",
    }));
    try {
      render(<TemplateReviewPortal />);
      await openInReviewDetail(user);
      await user.click(screen.getByRole("button", { name: "승인" }));
      expect(await screen.findByRole("alert")).toHaveTextContent(
        "SQL 안전성 검증 실패로 서버가 승인·활성화를 차단했습니다.",
      );
    } finally { restore(); }
  });

  it("rejects with a required note and enables approved templates", async () => {
    const user = userEvent.setup();
    const approved: ReviewTemplateDetail = {
      ...detail,
      approval_status: "APPROVED",
      enabled: false,
      version: { ...detail.version, approval_status: "APPROVED" },
    };
    const posts: string[] = [];
    const restore = installFetchMock(handlers({
      list: { ...listing, items: [{ ...row, approval_status: "APPROVED" }] },
      detail: approved,
      mutateBody: { ...approved, enabled: true },
      onRequest: (method, path) => {
        if (method === "POST") posts.push(path);
      },
    }));
    try {
      render(<TemplateReviewPortal />);
      await user.click(screen.getByRole("button", { name: "템플릿 목록 조회" }));
      await user.click(await screen.findByRole("button", { name: "검토 대상 병동 조회" }));
      await screen.findByTestId("template-enable-actions");
      await user.click(screen.getByRole("button", { name: "활성화" }));
      await waitFor(() =>
        expect(posts).toContain("/api/v1/query-templates/21/enable"),
      );
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
    } finally { restore(); }
  });

  it("does not reveal SQL for a caller without TEMPLATE_READ", async () => {
    const user = userEvent.setup();
    const restore = installFetchMock(handlers({ denyList: true }));
    try {
      render(<TemplateReviewPortal />);
      await user.click(screen.getByRole("button", { name: "템플릿 목록 조회" }));
      expect(await screen.findByRole("alert")).toHaveTextContent("요청한 템플릿 작업 권한이 없습니다.");
      expect(screen.queryByTestId("template-review-detail")).not.toBeInTheDocument();
    } finally { restore(); }
  });
});
