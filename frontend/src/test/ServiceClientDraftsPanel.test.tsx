import { render, screen, within, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ServiceClientDraftsPanel } from "../components/ServiceClientDraftsPanel";
import { CatalogApiError } from "../types/catalog";
import {
  createServiceClientDraft,
  getServiceClientDraft,
  listServiceClientDraftEvents,
  listServiceClientDrafts,
  patchServiceClientDraft,
  revokeServiceClientDraft,
  type ServiceClientDraft,
} from "../api/serviceClientDrafts";

vi.mock("../api/serviceClientDrafts", () => ({
  createServiceClientDraft: vi.fn(),
  getServiceClientDraft: vi.fn(),
  listServiceClientDraftEvents: vi.fn(),
  listServiceClientDrafts: vi.fn(),
  patchServiceClientDraft: vi.fn(),
  revokeServiceClientDraft: vi.fn(),
}));

const example: ServiceClientDraft = {
  id: 10,
  client_id: "fhir-demo",
  service_name: "FHIR 시험 서비스",
  organization: "시험 기관",
  owner_contact: "담당 부서",
  purpose: "개발 정책 검토",
  environment: "development",
  requested_scopes: ["catalog:read"],
  proposed_ip_cidrs: ["10.1.2.0/24"],
  status: "DRAFT",
  created_by: "admin",
  updated_by: "admin",
  created_at: "2026-10-30T00:00:00Z",
  updated_at: "2026-10-30T00:00:00Z",
  revoked_at: null,
  authentication_enabled: false,
  external_access_allowed: false,
};

function setupInventory(): void {
  vi.mocked(listServiceClientDrafts).mockResolvedValue({ total: 1, items: [example] });
  vi.mocked(getServiceClientDraft).mockResolvedValue(example);
  vi.mocked(listServiceClientDraftEvents).mockResolvedValue([
    { id: 20, action: "CREATED", actor_id: "admin", changed_fields: ["service_name"],
      policy_sha256: "a".repeat(64), occurred_at: "2026-10-30T00:00:00Z" },
  ]);
}

describe("M5-S1B service client draft administration", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    setupInventory();
  });

  it("shows draft-only status, detail and audit without an activation or credential action", async () => {
    render(<ServiceClientDraftsPanel />);
    const table = await screen.findByRole("table", { name: /등록 정책/ });
    expect(within(table).getByText("초안 · 인증 불가")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "fhir-demo 상세" }));
    const detail = await screen.findByRole("region", { name: "정책 상세" });
    expect(within(detail).getByText("DRAFT · 인증 불가")).toBeInTheDocument();
    const events = within(detail).getByRole("region", { name: "변경 감사 이력" });
    expect(within(events).getByText("CREATED")).toBeInTheDocument();
    expect(within(events).queryByText("a".repeat(64))).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /활성화|키 발급|연결 시험/ })).not.toBeInTheDocument();
  });

  it("creates only a policy draft with safe allowed fields", async () => {
    vi.mocked(createServiceClientDraft).mockResolvedValue(example);
    render(<ServiceClientDraftsPanel />);
    await screen.findByRole("table");
    await userEvent.click(screen.getByRole("button", { name: "정책 초안 등록" }));
    const editor = screen.getByRole("form", { name: "정책 초안 등록 양식" });
    await userEvent.type(within(editor).getByLabelText("클라이언트 ID"), "fhir-demo");
    await userEvent.type(within(editor).getByLabelText("서비스명"), "FHIR 시험 서비스");
    await userEvent.type(within(editor).getByLabelText("기관"), "시험 기관");
    await userEvent.type(within(editor).getByLabelText("담당자 연락처"), "담당 부서");
    await userEvent.type(within(editor).getByLabelText("목적"), "개발 정책 검토");
    await userEvent.type(within(editor).getByLabelText(/요청 scope/), "catalog:read");
    await userEvent.type(within(editor).getByLabelText(/제안 IP\/CIDR/), "10.1.2.0/24");
    await userEvent.click(within(editor).getByRole("button", { name: "초안 저장" }));
    await waitFor(() => expect(createServiceClientDraft).toHaveBeenCalledWith({
      client_id: "fhir-demo", service_name: "FHIR 시험 서비스",
      organization: "시험 기관", owner_contact: "담당 부서",
      purpose: "개발 정책 검토", environment: "development",
      requested_scopes: ["catalog:read"], proposed_ip_cidrs: ["10.1.2.0/24"],
    }));
    expect(screen.queryByLabelText(/서비스키|인증 비밀번호|access token/)).not.toBeInTheDocument();
  });

  it("edits only mutable metadata fields, never client identity or environment", async () => {
    vi.mocked(patchServiceClientDraft).mockResolvedValue({ ...example, service_name: "변경된 서비스" });
    render(<ServiceClientDraftsPanel />);
    await screen.findByRole("table");
    await userEvent.click(screen.getByRole("button", { name: "fhir-demo 상세" }));
    await screen.findByText("DRAFT · 인증 불가");
    await userEvent.click(screen.getByRole("button", { name: "초안 수정" }));
    const editor = screen.getByRole("form", { name: "정책 초안 수정 양식" });
    expect(within(editor).getByLabelText("클라이언트 ID")).toBeDisabled();
    expect(within(editor).getByLabelText("환경")).toBeDisabled();
    await userEvent.clear(within(editor).getByLabelText("서비스명"));
    await userEvent.type(within(editor).getByLabelText("서비스명"), "변경된 서비스");
    await userEvent.click(within(editor).getByRole("button", { name: "초안 저장" }));
    await waitFor(() => expect(patchServiceClientDraft).toHaveBeenCalledWith(
      10, { service_name: "변경된 서비스" },
    ));
  });

  it("requires a deliberate confirmation for irrevocable revoke", async () => {
    vi.mocked(getServiceClientDraft)
      .mockResolvedValueOnce(example)
      .mockResolvedValueOnce({ ...example, status: "REVOKED" });
    vi.mocked(revokeServiceClientDraft).mockResolvedValue({ ...example, status: "REVOKED" });
    render(<ServiceClientDraftsPanel />);
    await screen.findByRole("table");
    await userEvent.click(screen.getByRole("button", { name: "fhir-demo 상세" }));
    await screen.findByText("DRAFT · 인증 불가");
    const revokeButton = screen.getByRole("button", { name: "정책 초안 폐기" });
    expect(revokeButton).toBeDisabled();
    expect(revokeServiceClientDraft).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("checkbox", { name: "영구 폐기를 확인합니다" }));
    await userEvent.click(revokeButton);
    await waitFor(() => expect(revokeServiceClientDraft).toHaveBeenCalledWith(10));
    expect(await screen.findByText("REVOKED · 인증 불가")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "초안 수정" })).not.toBeInTheDocument();
  });

  it("hides the client inventory on denied admin access", async () => {
    vi.mocked(listServiceClientDrafts).mockRejectedValue(
      new CatalogApiError(403, "Forbidden", null),
    );
    render(<ServiceClientDraftsPanel />);
    expect(await screen.findByRole("alert")).toHaveTextContent("권한");
    expect(screen.queryByText("FHIR 시험 서비스")).not.toBeInTheDocument();
    expect(getServiceClientDraft).not.toHaveBeenCalled();
  });
});
