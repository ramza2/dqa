import { lazy, Suspense, useCallback, useState } from "react";
import { CatalogExplorer } from "./CatalogExplorer";
import { CatalogSourceProvider } from "./CatalogSourceContext";
import { DiscoverySourceToolbar } from "./DiscoverySourceToolbar";
import { ErdFocusProvider } from "./ErdFocusContext";
import { DataDiscoveryIndexStatus } from "./DataDiscoveryIndexStatus";
import { SchemaSearch } from "./SchemaSearch";
import { SchemaSnapshotHistory } from "./SchemaSnapshotHistory";

const ActiveCatalogErdExplorer = lazy(() => import("./ActiveCatalogErdExplorer")
  .then((module) => ({ default: module.ActiveCatalogErdExplorer })));

type DiscoveryTab = "search" | "explorer" | "erd" | "index" | "snapshot";

export function DataDiscoveryPortal() {
  const [tab, setTab] = useState<DiscoveryTab>("search");
  const [indexBusy, setIndexBusy] = useState(false);
  const openErdTab = useCallback(() => setTab("erd"), []);

  return (
    <div className="dd-portal" data-testid="data-discovery-portal">
      <CatalogSourceProvider>
        <DiscoverySourceToolbar snapshotTab={tab === "snapshot"} actionBusy={indexBusy} />
        <div className="dd-subnav" role="tablist" aria-label="Data Discovery">
          <button type="button" role="tab" aria-selected={tab === "search"}
            className={tab === "search" ? "nav-tab active" : "nav-tab"}
            onClick={() => setTab("search")} data-testid="dd-tab-search">
            Schema Search
          </button>
          <button type="button" role="tab" aria-selected={tab === "explorer"}
            className={tab === "explorer" ? "nav-tab active" : "nav-tab"}
            onClick={() => setTab("explorer")} data-testid="dd-tab-explorer">
            Table Explorer
          </button>
          <button type="button" role="tab" aria-selected={tab === "erd"}
            className={tab === "erd" ? "nav-tab active" : "nav-tab"}
            onClick={() => setTab("erd")} data-testid="dd-tab-erd">
            ERD Explorer
          </button>
          <button type="button" role="tab" aria-selected={tab === "index"}
            className={tab === "index" ? "nav-tab active" : "nav-tab"}
            onClick={() => setTab("index")} data-testid="dd-tab-index">
            Index Status
          </button>
          <button type="button" role="tab" aria-selected={tab === "snapshot"}
            className={tab === "snapshot" ? "nav-tab active" : "nav-tab"}
            onClick={() => setTab("snapshot")} data-testid="dd-tab-snapshot">
            Snapshot History
          </button>
        </div>

        <ErdFocusProvider onAfterRequest={openErdTab}>
          {tab === "explorer" ? <CatalogExplorer sharedSourceBar /> : null}
          {tab === "erd" ? (
            <Suspense fallback={<p role="status">ERD Explorer 로딩 중…</p>}>
              <ActiveCatalogErdExplorer sharedSourceBar />
            </Suspense>
          ) : null}
        </ErdFocusProvider>
        {tab === "search" ? <SchemaSearch sharedSourceBar /> : null}
        {tab === "index" ? <DataDiscoveryIndexStatus sharedSourceBar onBusyChange={setIndexBusy} /> : null}
        {tab === "snapshot" ? <SchemaSnapshotHistory /> : null}
      </CatalogSourceProvider>
    </div>
  );
}
