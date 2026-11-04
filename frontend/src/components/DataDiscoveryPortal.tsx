import { lazy, Suspense, useState } from "react";
import { CatalogExplorer } from "./CatalogExplorer";
import { DataDiscoveryIndexStatus } from "./DataDiscoveryIndexStatus";
import { SchemaSearch } from "./SchemaSearch";
import { SchemaSnapshotHistory } from "./SchemaSnapshotHistory";

const ActiveCatalogErdExplorer = lazy(() => import("./ActiveCatalogErdExplorer")
  .then((module) => ({ default: module.ActiveCatalogErdExplorer })));

type DiscoveryTab = "search" | "explorer" | "erd" | "index" | "snapshot";

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
          Table Explorer
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={tab === "erd"}
          className={tab === "erd" ? "nav-tab active" : "nav-tab"}
          onClick={() => setTab("erd")}
          data-testid="dd-tab-erd"
        >
          ERD Explorer
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
        <button
          type="button"
          role="tab"
          aria-selected={tab === "snapshot"}
          className={tab === "snapshot" ? "nav-tab active" : "nav-tab"}
          onClick={() => setTab("snapshot")}
          data-testid="dd-tab-snapshot"
        >
          Snapshot History
        </button>
      </div>

      {tab === "search" ? <SchemaSearch /> : null}
      {tab === "explorer" ? <CatalogExplorer /> : null}
      {tab === "erd" ? <Suspense fallback={<p role="status">ERD Explorer 로딩 중…</p>}>
        <ActiveCatalogErdExplorer />
      </Suspense> : null}
      {tab === "index" ? <DataDiscoveryIndexStatus /> : null}
      {tab === "snapshot" ? <SchemaSnapshotHistory /> : null}
    </div>
  );
}
