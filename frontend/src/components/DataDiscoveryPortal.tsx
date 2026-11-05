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

export type DiscoveryTab = "search" | "explorer" | "erd" | "index" | "snapshot";

type DataDiscoveryPortalProps = {
  activeTab?: DiscoveryTab;
  onTabChange?: (tab: DiscoveryTab) => void;
  hideTabNavigation?: boolean;
};

export function DataDiscoveryPortal({
  activeTab, onTabChange, hideTabNavigation = false,
}: DataDiscoveryPortalProps = {}) {
  const [localTab, setLocalTab] = useState<DiscoveryTab>("search");
  const tab = activeTab ?? localTab;
  const [indexBusy, setIndexBusy] = useState(false);
  const selectTab = useCallback((nextTab: DiscoveryTab) => {
    if (activeTab === undefined) setLocalTab(nextTab);
    onTabChange?.(nextTab);
  }, [activeTab, onTabChange]);
  const openErdTab = useCallback(() => selectTab("erd"), [selectTab]);

  return (
    <div className="dd-portal" data-testid="data-discovery-portal">
      <CatalogSourceProvider>
        <DiscoverySourceToolbar actionBusy={indexBusy} />
        {!hideTabNavigation ? <div className="dd-subnav" role="tablist" aria-label="스키마·Catalog 탐색 메뉴">
          <button type="button" role="tab" aria-selected={tab === "search"}
            className={tab === "search" ? "nav-tab active" : "nav-tab"}
            onClick={() => selectTab("search")} data-testid="dd-tab-search">
            스키마 검색
          </button>
          <button type="button" role="tab" aria-selected={tab === "explorer"}
            className={tab === "explorer" ? "nav-tab active" : "nav-tab"}
            onClick={() => selectTab("explorer")} data-testid="dd-tab-explorer">
            테이블 탐색
          </button>
          <button type="button" role="tab" aria-selected={tab === "erd"}
            className={tab === "erd" ? "nav-tab active" : "nav-tab"}
            onClick={() => selectTab("erd")} data-testid="dd-tab-erd">
            ERD 관계도
          </button>
          <button type="button" role="tab" aria-selected={tab === "index"}
            className={tab === "index" ? "nav-tab active" : "nav-tab"}
            onClick={() => selectTab("index")} data-testid="dd-tab-index">
            검색 인덱스 상태
          </button>
          <button type="button" role="tab" aria-selected={tab === "snapshot"}
            className={tab === "snapshot" ? "nav-tab active" : "nav-tab"}
            onClick={() => selectTab("snapshot")} data-testid="dd-tab-snapshot">
            스키마 변경 이력
          </button>
        </div> : null}

        <ErdFocusProvider onAfterRequest={openErdTab}>
          {tab === "explorer" ? <CatalogExplorer sharedSourceBar /> : null}
          {tab === "erd" ? (
            <Suspense fallback={<p role="status">ERD 관계도 로딩 중…</p>}>
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
