import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { TemplateReviewActions } from "../components/TemplateReviewActions";
import { TemplateReviewPortal } from "../components/TemplateReviewPortal";
import type { TemplateReviewActor } from "../api/templateReview";
import type { ReviewTemplateDetail, TemplateSqlSafetyReview } from "../types/templateReview";
import { installFetchMock, jsonResponse } from "./mocks";

afterEach(() => { cleanup(); vi.restoreAllMocks(); });

const compat = {
  mode: "EXACT_FINGERPRINT" as const, compatible: true,
  pinned_revision_id: 8, pinned_schema_fingerprint: "synthetic-fp",
  current_revision_id: 8, current_schema_fingerprint: "synthetic-fp",
};
const base: ReviewTemplateDetail = {
  id: 21, stable_key: "synthetic.test", name: "합성 병동 조회",
  description: null, source_name: "oracle_demis_mock",
  target_schemas: ["DEMIS_OWNER"], enabled: false,
  current_version_id: 31, current_version: 1,
  approval_status: "IN_REVIEW", compatibility: compat,
  created_at: "2026-10-28T07:00:00Z", updated_at: "2026-10-28T07:01:00Z",
  version: {
    id: 31, version: 1,
    sql_text: "SELECT WARD_CD FROM DEMIS_OWNER.T1 WHERE WARD_CD = :ward",
    parameter_schema: [{ name: "ward", type: "string", required: true, sensitive: false }],
    row_limit: 50, timeout_seconds: 15, approval_status: "IN_REVIEW",
    compatibility: compat, created_by: "author-1",
    created_at: "2026-10-28T07:00:00Z", approved_by: null,
    approved_at: null, approval_note: null,
  },
};
const safety: TemplateSqlSafetyReview = {
  template_id: 21, version_id: 31, version: 1,
  safe: true, statement_count: 1,
  referenced_parameters: ["ward"], declared_parameters: ["ward"], issues: [],
};
const author: TemplateReviewActor = { actor_id: "author-1", provider: "dev_headers", roles: ["template_author"] };
const approver: TemplateReviewActor = { actor_id: "reviewer-1", provider: "dev_headers", roles: ["template_approver"] };

type RequestRecord = { method: string; path: string; body: unknown };
function routes(args: {
  current?: ReviewTemplateDetail;
  safe?: TemplateSqlSafetyReview;
  result?: ReviewTemplateDetail;
  calls: RequestRecord[];
}) {
  return [(url: URL, init?: RequestInit) => {
    const path = url.pathname, method = init?.method ?? "GET";
    args.calls.push({ method, path, body: init?.body ? JSON.parse(String(init.body)) as unknown : null });
    if (method === "GET" && path === "/api/v1/query-templates/21") {
      return jsonResponse(args.current ?? base);
    }
    if (method === "GET" && path === "/api/v1/query-templates/21/sql-safety") {
      return jsonResponse(args.safe ?? safety);
    }
    if (method === "POST" && path.startsWith("/api/v1/query-templates/21/")) {
      const expected = path.endsWith("/approve") ? "APPROVED" :
        path.endsWith("/reject") ? "REJECTED" : "IN_REVIEW";
      return jsonResponse(args.result ?? {
        ...base, approval_status: expected,
        version: { ...base.version, approval_status: expected },
      });
    }
    if (method === "GET" && path === "/api/v1/auth/me") return jsonResponse(approver);
    if (method === "GET" && path === "/api/v1/query-templates") return jsonResponse({
      total: 1, limit: 50, offset: 0, items: [base],
    });
    return null;
  }];
}

describe("M3-C2A role-gated review actions", () => {
  it("does not fetch actor identity or mutate templates before explicitly enabling controls", async () => {
    const user = userEvent.setup(), calls: RequestRecord[] = [];
    const restore = installFetchMock(routes({ calls }));
    try {
      render(<TemplateReviewPortal />);
      expect(calls).toEqual([]);
      await user.click(screen.getByRole("button", { name: "검토 작업 권한 확인" }));
      expect(await screen.findByText(/계정 권한:/)).toHaveTextContent("template_approver");
      expect(calls.map(x => x.path)).toEqual(["/api/v1/auth/me"]);
    } finally { restore(); }
  });

  it("allows an authorized approver to confirm approval only after re-fetching identity and safety", async () => {
    const user = userEvent.setup(), calls: RequestRecord[] = [], complete = vi.fn();
    const restore = installFetchMock(routes({ calls }));
    try {
      render(<TemplateReviewActions actor={approver} detail={base} safety={safety} onCompleted={complete} />);
      expect(screen.queryByText("검토 제출 선택")).not.toBeInTheDocument();
      await user.click(screen.getByRole("button", { name: "승인 선택" }));
      const confirm = screen.getByRole("button", { name: "선택한 작업 확정" });
      expect(confirm).toBeDisabled();
      await user.click(screen.getByRole("checkbox"));
      await user.click(confirm);
      await vi.waitFor(() => expect(complete).toHaveBeenCalledWith("승인 완료. 템플릿은 자동 활성화되지 않습니다."));
      expect(calls.map(x => x.method)).toEqual(["GET", "GET", "POST"]);
      expect(calls[2].body).toMatchObject({ expected_version_id: 31, expected_updated_at: base.updated_at });
    } finally { restore(); }
  });

  it("author can submit but cannot approve; reviewer cannot submit draft", async () => {
    const user = userEvent.setup(), calls: RequestRecord[] = [], done = vi.fn();
    const draft: ReviewTemplateDetail = {
      ...base, approval_status: "DRAFT",
      version: { ...base.version, approval_status: "DRAFT" },
    };
    const restore = installFetchMock(routes({
      current: draft,
      result: { ...draft, approval_status: "IN_REVIEW",
        version: { ...draft.version, approval_status: "IN_REVIEW" } },
      calls,
    }));
    try {
      render(<TemplateReviewActions actor={author} detail={draft} safety={safety} onCompleted={done} />);
      expect(screen.getByRole("button", { name: "검토 제출 선택" })).toBeInTheDocument();
      expect(screen.queryByRole("button", { name: "승인 선택" })).not.toBeInTheDocument();
      await user.click(screen.getByRole("button", { name: "검토 제출 선택" }));
      await user.click(screen.getByRole("checkbox"));
      await user.click(screen.getByRole("button", { name: "선택한 작업 확정" }));
      await vi.waitFor(() => expect(done).toHaveBeenCalledTimes(1));
      const post = calls.filter(x => x.method === "POST");
      expect(post).toHaveLength(1);
      expect(post[0].path).toBe("/api/v1/query-templates/21/submit-review");
      expect(post[0].body).toMatchObject({
        expected_version_id: 31, expected_updated_at: base.updated_at,
      });
    } finally { restore(); }
  });

  it("refuses approval when SQL safety fails or Catalog is stale", () => {
    const restore = installFetchMock([]);
    try {
      const screenView = render(<TemplateReviewActions
        actor={approver} detail={base} safety={{ ...safety, safe: false }}
        onCompleted={vi.fn()}
      />);
      expect(screen.queryByRole("button", { name: "승인 선택" })).not.toBeInTheDocument();
      screenView.rerender(<TemplateReviewActions
        actor={approver}
        detail={{ ...base, compatibility: { ...compat, compatible: false } }}
        safety={safety} onCompleted={vi.fn()}
      />);
      expect(screen.queryByRole("button", { name: "승인 선택" })).not.toBeInTheDocument();
    } finally { restore(); }
  });

  it("reject requires a reason and does not enable a template", async () => {
    const user = userEvent.setup(), calls: RequestRecord[] = [], done = vi.fn();
    const restore = installFetchMock(routes({ calls }));
    try {
      render(<TemplateReviewActions actor={approver} detail={base} safety={safety} onCompleted={done} />);
      await user.click(screen.getByRole("button", { name: "반려 선택" }));
      await user.click(screen.getByRole("checkbox"));
      expect(screen.getByRole("button", { name: "선택한 작업 확정" })).toBeDisabled();
      await user.type(screen.getByLabelText("검토 메모"), "테이블 확인 필요");
      await user.click(screen.getByRole("checkbox"));
      await user.click(screen.getByRole("button", { name: "선택한 작업 확정" }));
      await vi.waitFor(() => expect(done).toHaveBeenCalled());
      expect(calls.filter(x=>x.method === "POST")[0]).toMatchObject({
        path: "/api/v1/query-templates/21/reject",
        body: { note: "테이블 확인 필요", expected_version_id: 31 },
      });
    } finally { restore(); }
  });

  it("blocks stale changed SQL content before POST even when version id is unchanged", async () => {
    const user = userEvent.setup(), calls: RequestRecord[] = [], done = vi.fn();
    const restore = installFetchMock(routes({
      calls, current: { ...base,
        version: { ...base.version, sql_text: "SELECT changed FROM dual" },
      },
    }));
    try {
      render(<TemplateReviewActions actor={approver} detail={base} safety={safety} onCompleted={done} />);
      await user.click(screen.getByRole("button", { name: "승인 선택" }));
      await user.click(screen.getByRole("checkbox"));
      await user.click(screen.getByRole("button", { name: "선택한 작업 확정" }));
      expect(await screen.findByRole("alert")).toHaveTextContent("검토 중 SQL·버전·Catalog 상태가 변경됐습니다");
      expect(calls.some(x=>x.method==="POST")).toBe(false);
      expect(done).not.toHaveBeenCalled();
    } finally { restore(); }
  });

  it("read-only actor cannot see mutation controls", () => {
    render(<TemplateReviewActions actor={{
      actor_id: "viewer", roles: ["viewer"], provider: "dev_headers",
    }} detail={base} safety={safety} onCompleted={vi.fn()} />);
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    expect(screen.getByText(/조회 권한만 있습니다/)).toBeInTheDocument();
  });
});
