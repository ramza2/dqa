import { useState } from "react";
import { DataDiscoveryPortal } from "./components/DataDiscoveryPortal";
import { QueryAssistant } from "./components/QueryAssistant";
import { ConnectionProfilePortal } from "./components/ConnectionProfilePortal";
import { WorkflowDashboard, type WorkflowDestination } from "./components/WorkflowDashboard";
import "./App.css";

type AppView = "dashboard" | WorkflowDestination;

const NAV_ITEMS: { view: AppView; label: string }[] = [
  { view: "dashboard", label: "대시보드" },
  { view: "profiles", label: "DB 연결 관리" },
  { view: "discovery", label: "스키마·Catalog" },
  { view: "assistant", label: "조회 시험" },
];

export default function App() {
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
      </nav>
      {view === "dashboard" ? <WorkflowDashboard onNavigate={setView} /> : null}
      {view === "profiles" ? <ConnectionProfilePortal /> : null}
      {view === "discovery" ? <DataDiscoveryPortal /> : null}
      {view === "assistant" ? <QueryAssistant /> : null}
    </div>
  );
}
