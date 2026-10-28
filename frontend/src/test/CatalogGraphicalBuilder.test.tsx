import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { CatalogGraphicalBuilder } from "../components/CatalogGraphicalBuilder";
import {
  activeSource, secondSource, columnsResponse, defaultCatalogHandlers,
  installFetchMock, jsonResponse, tablesResponse,
} from "./mocks";
import type { CatalogPreviewResponse } from "../types/queryBuilder";

afterEach(() => { cleanup(); vi.restoreAllMocks(); });

const preview: CatalogPreviewResponse = {
  source_name: activeSource.source_name,
  catalog_revision_id: activeSource.revision_id,
  schema_fingerprint: activeSource.schema_fingerprint,
  sql_text: 'SELECT * FROM (SELECT "WARD_CD" FROM "DEMIS_OWNER"."TB_ADM_HIST" WHERE "WARD_CD" = :p1) q WHERE ROWNUM <= :p_limit',
  parameters: [{ name: "p1", column: "WARD_CD", type: "string" }, {
    name: "p_limit", column: null, type: "integer",
  }],
  preview_only: true, executable: false, approved: false, template_id: null,
};

async function chooseColumn(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole("button", { name: "테이블 목록 불러오기" }));
  await user.selectOptions(await screen.findByLabelText("조회 테이블"),
    JSON.stringify(["DEMIS_OWNER", "TB_ADM_HIST"]));
  await user.click(await screen.findByLabelText("컬럼 WARD_CD"));
}

describe("M3-B graphical builder preview-only", () => {
  it("builds an explicit Catalog-bound preview without submitting values or executing", async () => {
    const user = userEvent.setup();
    let previewBody: Record<string, unknown> | null = null;
    let executes = 0;
    const handlers = defaultCatalogHandlers();
    handlers.unshift((url, init) => {
      if (url.pathname.endsWith("/query-executions/execute")) executes++;
      if (url.pathname.endsWith("/query-builder/preview") && init?.method === "POST") {
        previewBody = JSON.parse(String(init.body)) as Record<string, unknown>;
        return jsonResponse(preview);
      }
      return null;
    });
    const restore = installFetchMock(handlers);
    try {
      render(<CatalogGraphicalBuilder active={activeSource} />);
      await chooseColumn(user);
      expect(screen.getByRole("button", { name: "SQL 미리보기 생성" })).toBeEnabled();
      await user.click(screen.getByRole("button", { name: "조건 추가" }));
      await user.selectOptions(screen.getByLabelText("조건 컬럼 1"), "WARD_CD");
      await user.click(screen.getByRole("button", { name: "SQL 미리보기 생성" }));
      expect(await screen.findByTestId("catalog-sql-preview")).toHaveTextContent("실행 불가");
      expect(screen.getByTestId("catalog-sql-preview")).toHaveTextContent(":p1");
      expect(previewBody).toMatchObject({
        source_name: activeSource.source_name, catalog_revision_id: activeSource.revision_id,
        schema_name: "DEMIS_OWNER", table_name: "TB_ADM_HIST",
        columns: ["WARD_CD"], predicates: [{ column: "WARD_CD", operator: "EQ" }], row_limit: 50,
      });
      expect(previewBody).not.toHaveProperty("sql_text");
      expect(previewBody).not.toHaveProperty("value");
      expect(previewBody).not.toHaveProperty("credentials");
      expect(executes).toBe(0);
      // All edits invalidate the previous SQL preview.
      await user.click(screen.getByLabelText("컬럼 WARD_CD"));
      expect(screen.queryByTestId("catalog-sql-preview")).not.toBeInTheDocument();
    } finally { restore(); }
  });

  it("rejects stale Catalog metadata instead of showing selectable tables", async () => {
    const user = userEvent.setup();
    const restore = installFetchMock([() => jsonResponse({
      ...tablesResponse, revision_id: 999,
    })]);
    try {
      render(<CatalogGraphicalBuilder active={activeSource} />);
      await user.click(screen.getByRole("button", { name: "테이블 목록 불러오기" }));
      expect(await screen.findByRole("alert")).toHaveTextContent("Catalog가 변경되었습니다");
      expect(screen.queryByLabelText("조회 테이블")).not.toBeInTheDocument();
    } finally { restore(); }
  });

  it("does not show a late old-source response after source remount", async () => {
    const user = userEvent.setup();
    const pending = { resolve: null as ((value: Response) => void) | null };
    const handlers = defaultCatalogHandlers();
    handlers.unshift((url) => {
      if (url.pathname.endsWith("/tables")) {
        return new Promise<Response>((resolve) => { pending.resolve = resolve; });
      }
      return null;
    });
    const restore = installFetchMock(handlers);
    try {
      const view = render(<CatalogGraphicalBuilder key="one" active={activeSource} />);
      await user.click(screen.getByRole("button", { name: "테이블 목록 불러오기" }));
      await waitFor(() => expect(pending.resolve).not.toBeNull());
      view.rerender(<CatalogGraphicalBuilder key="two" active={secondSource} />);
      pending.resolve?.(jsonResponse(tablesResponse));
      expect(screen.queryByLabelText("조회 테이블")).not.toBeInTheDocument();
      expect(screen.getByRole("button", { name: "테이블 목록 불러오기" })).toBeEnabled();
    } finally { restore(); }
  });

  it("rejects an API preview with changed fingerprint or executable flag", async () => {
    const user = userEvent.setup();
    const handlers = defaultCatalogHandlers();
    handlers.unshift((url) => (
      url.pathname.endsWith("/query-builder/preview")
        ? jsonResponse({ ...preview, executable: true }) : null
    ));
    const restore = installFetchMock(handlers);
    try {
      render(<CatalogGraphicalBuilder active={activeSource} />);
      await chooseColumn(user);
      await user.click(screen.getByRole("button", { name: "SQL 미리보기 생성" }));
      expect(await screen.findByRole("alert")).toHaveTextContent("검증 결과가 현재 Catalog와 일치하지 않습니다");
      expect(screen.queryByTestId("catalog-sql-preview")).not.toBeInTheDocument();
    } finally { restore(); }
  });

  it("does not submit invalid row limit", async () => {
    const user = userEvent.setup();
    const restore = installFetchMock(defaultCatalogHandlers());
    try {
      render(<CatalogGraphicalBuilder active={activeSource} />);
      await chooseColumn(user);
      await user.clear(screen.getByLabelText("미리보기 행 수 상한"));
      await user.type(screen.getByLabelText("미리보기 행 수 상한"), "101");
      expect(screen.getByRole("button", { name: "SQL 미리보기 생성" })).toBeDisabled();
    } finally { restore(); }
  });
});
