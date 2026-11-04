import { useEffect, useState, type FormEvent } from "react";
import { CatalogApiError } from "./types/catalog";
import { getAuthActor, getAuthCapabilities, login, logout, type AuthActor } from "./api/auth";
import { IntegrationSettingsPortal } from "./components/IntegrationSettingsPortal";
import { DataDiscoveryPortal } from "./components/DataDiscoveryPortal";
import { QueryAssistant } from "./components/QueryAssistant";
import { TemplateReviewPortal } from "./components/TemplateReviewPortal";
import { ConnectionProfilePortal } from "./components/ConnectionProfilePortal";
import { WorkflowDashboard, type WorkflowDestination } from "./components/WorkflowDashboard";
import "./App.css";

type AppView = "dashboard" | "integration-settings" | WorkflowDestination;

const NAV_ITEMS: { view: AppView; label: string }[] = [
  { view: "dashboard", label: "대시보드" },
  { view: "profiles", label: "DB 연결 관리" },
  { view: "discovery", label: "스키마·Catalog" },
  { view: "assistant", label: "조회 시험" },
  { view: "template-review", label: "템플릿 검토" },
  { view: "integration-settings", label: "환경 설정" },
];

function AuthenticatedApp({ actor, onLogout }: {
  actor?: AuthActor;
  onLogout?: () => void;
}) {
  const [view, setView] = useState<AppView>("dashboard");

  return (
    <div className="app-root" data-testid="app-root">
      <nav className="app-top-nav" aria-label="Primary">
        <div className="app-top-nav-brand">DEMIS 데이터 연계 관리</div>
        <div className="app-top-nav-tabs" role="tablist" aria-label="주요 메뉴">
          {NAV_ITEMS.map((item) => (
            <button
              key={item.view}
              type="button"
              role="tab"
              aria-selected={view === item.view}
              className={view === item.view ? "nav-tab active" : "nav-tab"}
              onClick={() => setView(item.view)}
            >
              {item.label}
            </button>
          ))}
        </div>
        {actor ? (
          <div className="app-user-status">
            <span>{actor.display_name || actor.actor_id} ({actor.roles.join(", ")})</span>
            <button type="button" onClick={onLogout}>로그아웃</button>
          </div>
        ) : null}
      </nav>
      {view === "dashboard" ? <WorkflowDashboard onNavigate={setView} /> : null}
      {view === "profiles" ? <ConnectionProfilePortal /> : null}
      {view === "discovery" ? <DataDiscoveryPortal /> : null}
      {view === "assistant" ? <QueryAssistant /> : null}
      {view === "template-review" ? <TemplateReviewPortal /> : null}
      {view === "integration-settings" ? <IntegrationSettingsPortal /> : null}
    </div>
  );
}

function LocalLoginApp() {
  const [status, setStatus] = useState<"loading" | "login" | "ready" | "unavailable">("loading");
  const [actor, setActor] = useState<AuthActor | null>(null);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let active = true;
    void (async () => {
      try {
        const caps = await getAuthCapabilities();
        if (!caps.login_supported || caps.mode !== "local_session") {
          if (active) setStatus("unavailable");
          return;
        }
        try {
          const current = await getAuthActor();
          if (active) { setActor(current); setStatus("ready"); }
        } catch (err) {
          if (active) setStatus(err instanceof CatalogApiError && err.status === 401 ? "login" : "unavailable");
        }
      } catch {
        if (active) setStatus("unavailable");
      }
    })();
    return () => { active = false; };
  }, []);

  async function handleLogin(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      const current = await login(username, password);
      setActor(current);
      setPassword("");
      setStatus("ready");
    } catch {
      setError("로그인에 실패했습니다. 계정과 비밀번호를 확인해 주세요.");
    } finally {
      setBusy(false);
    }
  }

  async function handleLogout() {
    setBusy(true);
    try {
      await logout();
      setActor(null);
      setPassword("");
      setStatus("login");
    } catch {
      setError("로그아웃을 완료하지 못했습니다. 관리자에게 문의해 주세요.");
    } finally {
      setBusy(false);
    }
  }

  if (status === "ready" && actor) return <AuthenticatedApp actor={actor} onLogout={() => { void handleLogout(); }} />;
  if (status === "loading") return <div className="auth-screen" role="status">인증 상태를 확인하고 있습니다.</div>;
  if (status === "unavailable") return <div className="auth-screen" role="alert">로그인 서비스가 설정되지 않았습니다. 관리자에게 문의해 주세요.</div>;

  return (
    <main className="auth-screen">
      <form className="auth-card" onSubmit={handleLogin}>
        <h1>DEMIS 데이터 연계 관리</h1>
        <p>등록된 내부 운영자 계정으로 로그인해 주세요.</p>
        <label htmlFor="auth-username">아이디</label>
        <input id="auth-username" autoComplete="username" required minLength={3} maxLength={64}
          value={username} onChange={(event) => setUsername(event.target.value)} disabled={busy} />
        <label htmlFor="auth-password">비밀번호</label>
        <input id="auth-password" type="password" autoComplete="current-password" required
          value={password} onChange={(event) => setPassword(event.target.value)} disabled={busy} />
        {error ? <p role="alert" className="auth-error">{error}</p> : null}
        <button type="submit" disabled={busy}>{busy ? "확인 중..." : "로그인"}</button>
      </form>
    </main>
  );
}

export default function App() {
  // Existing Vite development-header flow remains unchanged for mock workflows.
  // Production uses the server's explicit login capability; no client-side
  // actor assertion grants privileges.
  if (import.meta.env.DEV && import.meta.env.VITE_DQA_LOCAL_LOGIN_ENABLED !== "true") {
    return <AuthenticatedApp />;
  }
  return <LocalLoginApp />;
}
