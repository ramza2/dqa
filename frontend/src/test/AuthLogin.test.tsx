import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "../App";

vi.mock("../components/WorkflowDashboard", () => ({
  WorkflowDashboard: () => <main>Authenticated Dashboard</main>,
}));

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), {
  status, headers: { "Content-Type": "application/json" },
});

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("local operator session login", () => {
  it("shows login, requires valid credentials, attaches session CSRF, then logs out", async () => {
    vi.stubEnv("VITE_DQA_LOCAL_LOGIN_ENABLED", "true");
    let loggedIn = false;
    let hasCsrf = false;
    const fetchMock = vi.fn(async (path: string | URL | Request, init?: RequestInit) => {
      const url = new URL(String(path), "http://localhost");
      if (url.pathname.endsWith("/auth/capabilities")) {
        return json({ login_supported: true, mode: "local_session" });
      }
      if (url.pathname.endsWith("/auth/me")) {
        return loggedIn ? json({ actor_id: "admin1", display_name: "테스트 관리자",
          roles: ["administrator"], provider: "local_session", csrf_token: "csrf-example" }) :
          json({ detail: { code: "AUTHENTICATION_REQUIRED" } }, 401);
      }
      if (url.pathname.endsWith("/auth/login")) {
        const body = JSON.parse(String(init?.body)) as { password: string };
        if (body.password !== "password-for-test") {
          return json({ detail: { code: "AUTHENTICATION_INVALID" } }, 401);
        }
        loggedIn = true;
        return json({ authenticated: true, csrf_token: "csrf-example" });
      }
      if (url.pathname.endsWith("/auth/logout")) {
        hasCsrf = new Headers(init?.headers).get("X-DQA-CSRF") === "csrf-example";
        loggedIn = false;
        return json({ authenticated: false });
      }
      return json({});
    });
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<App />);
    await screen.findByRole("textbox", { name: "아이디" });
    await user.type(screen.getByRole("textbox", { name: "아이디" }), "admin1");
    await user.type(screen.getByLabelText("비밀번호"), "incorrect-password");
    await user.click(screen.getByRole("button", { name: "로그인" }));
    expect(await screen.findByText("로그인에 실패했습니다. 계정과 비밀번호를 확인해 주세요.")).toBeInTheDocument();
    await user.clear(screen.getByLabelText("비밀번호"));
    await user.type(screen.getByLabelText("비밀번호"), "password-for-test");
    await user.click(screen.getByRole("button", { name: "로그인" }));
    expect(await screen.findByText("Authenticated Dashboard")).toBeInTheDocument();
    expect(screen.getByText(/테스트 관리자/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "로그아웃" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "로그인" })).toBeInTheDocument());
    expect(hasCsrf).toBe(true);
  });

  it("does not show a usable login for disabled or misconfigured providers", async () => {
    vi.stubEnv("VITE_DQA_LOCAL_LOGIN_ENABLED", "true");
    vi.stubGlobal("fetch", vi.fn(async () => json({ login_supported: false, mode: "disabled" })));
    render(<App />);
    expect(await screen.findByRole("alert")).toHaveTextContent("로그인 서비스가 설정되지 않았습니다.");
    expect(screen.queryByRole("button", { name: "로그인" })).toBeNull();
  });
});
