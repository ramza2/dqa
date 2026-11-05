import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "../App";
import { defaultCatalogHandlers, installFetchMock, jsonResponse } from "./mocks";

afterEach(() => vi.restoreAllMocks());

describe("M5-UX5 Analyzer-style sidebar navigation", () => {
  it("keeps all existing primary destinations and labels unmigrated pages as pending", () => {
    render(<App />);
    expect(screen.getByRole("navigation", { name: "Primary" })).toBeInTheDocument();
    expect(screen.getByRole("complementary")).toHaveTextContent("DEMIS 데이터 연계 관리");
    for (const label of ["대시보드", "DB 연결 관리", "스키마·Catalog", "조회 시험", "템플릿 검토", "환경 설정"]) {
      expect(screen.getByRole("tab", { name: label })).toBeInTheDocument();
    }
    const pending = screen.getByRole("region", { name: "Analyzer 이관 예정" });
    expect(pending).toHaveTextContent("DB 분석 보고서");
    expect(pending).toHaveTextContent("Catalog Package 최종화");
    expect(pending.querySelector("button")).toBeNull();
    expect(screen.getByTestId("workflow-dashboard")).toBeInTheDocument();
  });

  it("opens Catalog pages directly from the sidebar without duplicate in-page navigation", async () => {
    const user = userEvent.setup();
    const restore = installFetchMock([
      (url) => url.pathname === "/api/v1/schema-inspector/snapshots" ? jsonResponse([]) : null,
      ...defaultCatalogHandlers(),
    ]);

    render(<App />);
    await user.click(screen.getByRole("button", { name: "테이블 탐색" }));
    expect(await screen.findByRole("heading", { name: "테이블 탐색" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "테이블 탐색" })).toHaveAttribute("aria-current", "page");
    expect(screen.queryByRole("tablist", { name: "스키마·Catalog 탐색 메뉴" })).not.toBeInTheDocument();
    expect(screen.getAllByLabelText("Active Catalog source")).toHaveLength(1);

    await user.click(screen.getByRole("button", { name: "스키마 변경 이력" }));
    expect(await screen.findByRole("heading", { name: "스키마 변경 이력" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "스키마 변경 이력" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("button", { name: "테이블 탐색" })).not.toHaveAttribute("aria-current");

    await user.click(screen.getByRole("tab", { name: "조회 시험" }));
    expect(await screen.findByTestId("query-assistant")).toBeInTheDocument();
    await user.click(screen.getByRole("tab", { name: "스키마·Catalog" }));
    expect(await screen.findByTestId("schema-search")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "스키마 검색" })).toHaveAttribute("aria-current", "page");
    restore();
  });
});
