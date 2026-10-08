import { useState } from "react";
import { DataDiscoveryPortal } from "./components/DataDiscoveryPortal";
import { QueryAssistant } from "./components/QueryAssistant";
import "./App.css";

type AppView = "assistant" | "discovery";

export default function App() {
  const [view, setView] = useState<AppView>("assistant");

  return (
    <div className="app-root" data-testid="app-root">
      <nav className="app-top-nav" aria-label="Primary">
        <div className="app-top-nav-brand">DEMIS Query Assistant</div>
        <div className="app-top-nav-tabs" role="tablist">
          <button
            type="button"
            role="tab"
            aria-selected={view === "assistant"}
            className={view === "assistant" ? "nav-tab active" : "nav-tab"}
            onClick={() => setView("assistant")}
          >
            Query Assistant
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={view === "discovery"}
            className={view === "discovery" ? "nav-tab active" : "nav-tab"}
            onClick={() => setView("discovery")}
          >
            Data Discovery
          </button>
        </div>
      </nav>
      {view === "assistant" ? <QueryAssistant /> : <DataDiscoveryPortal />}
    </div>
  );
}
