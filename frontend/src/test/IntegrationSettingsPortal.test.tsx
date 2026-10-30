import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { IntegrationSettingsPortal } from "../components/IntegrationSettingsPortal";
import {
  getIntegrationSettingsStatus,
  type IntegrationSettingsStatus,
} from "../api/integrationSettings";

vi.mock("../api/integrationSettings", () => ({
  getIntegrationSettingsStatus: vi.fn(),
}));

const current: IntegrationSettingsStatus = {
  llm: {
    provider: "openai_compatible",
    endpoint_configured: true,
    model_configured: true,
    model: "qwen3-14b",
    api_key_present: true,
    raw_request_egress_allowed: false,
  },
  external_service: {
    service_client_management_available: false,
    managed_service_authentication_available: false,
  },
  editable: false,
};

describe("M5-S0 integration settings portal", () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it("shows only safe LLM status and explicitly marks service security as unavailable", async () => {
    vi.mocked(getIntegrationSettingsStatus).mockResolvedValue(current);
    render(<IntegrationSettingsPortal />);
    const llm = await screen.findByRole("region", { name: "LLM 연결 상태" });
    expect(within(llm).getByText("qwen3-14b")).toBeInTheDocument();
    expect(within(llm).getByText("설정됨 (값 비공개)")).toBeInTheDocument();
    expect(within(llm).getByText("차단")).toBeInTheDocument();
    const service = screen.getByRole("region", { name: "외부 서비스 접근 제어" });
    expect(within(service).getAllByText("미구현")).toHaveLength(2);
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
    expect(screen.queryByText(/비밀키 실제값/)).not.toBeInTheDocument();
  });

  it("does not render admin inventory on denied access", async () => {
    vi.mocked(getIntegrationSettingsStatus).mockRejectedValue(new Error("403"));
    render(<IntegrationSettingsPortal />);
    expect(await screen.findByRole("alert")).toHaveTextContent("권한");
    expect(screen.queryByRole("region", { name: "LLM 연결 상태" })).not.toBeInTheDocument();
  });

  it("refreshes state without mutating a connection configuration", async () => {
    vi.mocked(getIntegrationSettingsStatus).mockResolvedValue(current);
    render(<IntegrationSettingsPortal />);
    await screen.findByRole("region", { name: "LLM 연결 상태" });
    await userEvent.click(screen.getByRole("button", { name: "상태 새로고침" }));
    expect(await screen.findByRole("region", { name: "외부 서비스 접근 제어" })).toBeInTheDocument();
    expect(getIntegrationSettingsStatus).toHaveBeenCalledTimes(2);
  });
});
