import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { WorkflowDashboard } from "../components/WorkflowDashboard";

describe("M2-0 workflow home", () => {
  it("starts with Target registration and clearly marks pending integrations", () => {
    render(<WorkflowDashboard onNavigate={vi.fn()} />);
    expect(screen.getByRole("heading", { name: "DEMIS 데이터 연계 작업" })).toBeInTheDocument();
    const sequence = screen.getByRole("region", { name: "연계 작업 순서" });
    expect(sequence.querySelectorAll("li")).toHaveLength(6);
    expect(screen.getAllByText("연계 작업 예정")).toHaveLength(3);
    expect(screen.getByText(/실제 DEMIS 접속 승인이나/)).toBeInTheDocument();
  });

  it("opens existing portal destinations without triggering server actions", async () => {
    const onNavigate = vi.fn();
    render(<WorkflowDashboard onNavigate={onNavigate} />);
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "DB 연결 관리로 이동" }));
    await user.click(screen.getByRole("button", { name: "스키마·Catalog로 이동" }));
    await user.click(screen.getByRole("button", { name: "템플릿 작성·검토 열기" }));
    await user.click(screen.getByRole("button", { name: "Mock 조회 시험 열기" }));
    expect(onNavigate.mock.calls).toEqual([
      ["profiles"],
      ["discovery"],
      ["template-review"],
      ["assistant"],
    ]);
  });

  it("clarifies Oracle Mock LLM-free query trial entry separately from admin workflow", () => {
    render(<WorkflowDashboard onNavigate={vi.fn()} />);
    const trial = screen.getByTestId("mock-query-trial");
    expect(trial).toHaveTextContent("Oracle Mock 조회 시험 (LLM 불필요)");
    expect(trial).toHaveTextContent("수동 선택");
    expect(trial).toHaveTextContent("감사 이력");
    expect(trial).toHaveTextContent("실 DEMIS");
  });
});
