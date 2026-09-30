import { useState } from "react";
import { CatalogExplorer } from "./components/CatalogExplorer";
import { QueryAssistant } from "./components/QueryAssistant";
import "./App.css";

type AppView = "assistant" | "catalog";

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
            aria-selected={view === "catalog"}
            className={view === "catalog" ? "nav-tab active" : "nav-tab"}
            onClick={() => setView("catalog")}
          >
            Catalog Explorer
          </button>
        </div>
      </nav>
      {view === "assistant" ? <QueryAssistant /> : <CatalogExplorer />}
    </div>
  );
}
