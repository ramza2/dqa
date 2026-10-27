import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { ConnectionProfilePortal } from "../components/ConnectionProfilePortal";
import { installFetchMock, jsonResponse } from "./mocks";

describe("M2-1A explicit target registration", () => {
  it("does not register until sample selection and explicit Save", async () => {
    const posts: { path: string; body: Record<string, unknown> }[] = [];
    const restore = installFetchMock([(url, init) => {
      const method = init?.method || "GET";
      if (url.pathname.endsWith("/oracle-mock-capability"))
        return jsonResponse({ enabled: true });
      if (url.pathname === "/api/v1/connection-profiles" && method === "GET")
        return jsonResponse({ items: [], total: 0, limit: 20, offset: 0 });
      if (url.pathname.endsWith("/oracle-mock-register") && method === "POST") {
        const body = JSON.parse(String(init?.body)) as Record<string, unknown>;
        posts.push({ path: url.pathname, body });
        return jsonResponse({ ...body, id: 71, enabled: false }, 201);
      }
      return null;
    }]);
    try {
      render(<ConnectionProfilePortal />);
      await userEvent.click(screen.getByRole("button", { name: "비활성 프로필 등록" }));
      await userEvent.click(await screen.findByRole("button", { name: "개발용 Oracle Mock 선택" }));
      expect(posts).toHaveLength(0);
      expect(screen.getByRole("textbox", { name: "Profile host" })).toHaveValue("demis-oracle-test");
      expect(screen.getByRole("textbox", { name: "Profile host" })).toBeDisabled();
      await userEvent.click(screen.getByRole("button", { name: "저장" }));
      await waitFor(() => expect(posts).toHaveLength(1));
      expect(posts[0].body).toMatchObject({
        source_name: "oracle_demis_mock", environment: "development",
        host: "demis-oracle-test", port: 1521, database_name: "FREEPDB1",
      });
      expect(posts[0].body).not.toHaveProperty("credential_secret_ref");
    } finally { restore(); }
  });
});
