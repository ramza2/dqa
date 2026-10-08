import { useState } from "react";
import { CatalogExplorer } from "./CatalogExplorer";
import { DataDiscoveryIndexStatus } from "./DataDiscoveryIndexStatus";
import { SchemaSearch } from "./SchemaSearch";

type DiscoveryTab = "search" | "explorer" | "index";

export function DataDiscoveryPortal() {
  const [tab, setTab] = useState<DiscoveryTab>("search");

  return (
    <div className="dd-portal" data-testid="data-discovery-portal">
      <div className="dd-subnav" role="tablist" aria-label="Data Discovery">
        <button
          type="button"
          role="tab"
          aria-selected={tab === "search"}
          className={tab === "search" ? "nav-tab active" : "nav-tab"}
          onClick={() => setTab("search")}
          data-testid="dd-tab-search"
        >
          Schema Search
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={tab === "explorer"}
          className={tab === "explorer" ? "nav-tab active" : "nav-tab"}
          onClick={() => setTab("explorer")}
          data-testid="dd-tab-explorer"
        >
          Schema Explorer
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={tab === "index"}
          className={tab === "index" ? "nav-tab active" : "nav-tab"}
          onClick={() => setTab("index")}
          data-testid="dd-tab-index"
        >
          Index Status
        </button>
      </div>

      {tab === "search" ? <SchemaSearch /> : null}
      {tab === "explorer" ? <CatalogExplorer /> : null}
      {tab === "index" ? <DataDiscoveryIndexStatus /> : null}
    </div>
  );
}
