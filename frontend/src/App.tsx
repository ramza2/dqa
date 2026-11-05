import { useState } from "react";
import { IntegrationSettingsPortal } from "./components/IntegrationSettingsPortal";
import { DataDiscoveryPortal, type DiscoveryTab } from "./components/DataDiscoveryPortal";
import { QueryAssistant } from "./components/QueryAssistant";
import { TemplateReviewPortal } from "./components/TemplateReviewPortal";
import { ConnectionProfilePortal } from "./components/ConnectionProfilePortal";
import { WorkflowDashboard, type WorkflowDestination } from "./components/WorkflowDashboard";
import "./App.css";

type AppView = "dashboard" | "integration-settings" | WorkflowDestination;

const NAV_GROUPS: { title: string; items: { view: AppView; label: string }[] }[] = [
  { title: "시작", items: [{ view: "dashboard", label: "대시보드" }] },
  { title: "DB 분석", items: [{ view: "profiles", label: "DB 연결 관리" }] },
  { title: "스키마·Catalog", items: [{ view: "discovery", label: "스키마·Catalog" }] },
  { title: "조회 및 관리", items: [
    { view: "assistant", label: "조회 시험" },
    { view: "template-review", label: "템플릿 검토" },
    { view: "integration-settings", label: "환경 설정" },
  ] },
];

const DISCOVERY_PAGES: { tab: DiscoveryTab; label: string }[] = [
  { tab: "search", label: "스키마 검색" },
  { tab: "explorer", label: "테이블 탐색" },
  { tab: "erd", label: "ERD 관계도" },
  { tab: "index", label: "검색 인덱스 상태" },
  { tab: "snapshot", label: "스키마 변경 이력" },
];

export default function App() {
  const [view, setView] = useState<AppView>("dashboard");
  const [discoveryTab, setDiscoveryTab] = useState<DiscoveryTab>("search");

  function navigateTo(nextView: AppView) {
    if (nextView === "discovery") setDiscoveryTab("search");
    setView(nextView);
  }

  function navigateDiscovery(nextTab: DiscoveryTab) {
    setDiscoveryTab(nextTab);
    setView("discovery");
  }

  return (
    <div className="app-root app-sidebar-layout" data-testid="app-root">
      <aside className="app-sidebar">
        <div className="app-sidebar-brand">
          <span className="app-sidebar-brand-mark" aria-hidden="true">DQA</span>
          <div>
            <strong>DEMIS Schema Analyzer</strong>
            <span>DEMIS 데이터 연계 관리</span>
          </div>
        </div>
        <nav aria-label="Primary" className="app-sidebar-nav">
          {NAV_GROUPS.map((group) => (
            <section className="app-sidebar-section" key={group.title} aria-label={group.title}>
              <h2>{group.title}</h2>
              <div role="tablist" aria-label={`${group.title} 주요 메뉴`} aria-orientation="vertical">
                {group.items.map((item) => (
                  <button key={item.view} type="button" role="tab"
                    aria-selected={view === item.view}
                    className={view === item.view ? "app-sidebar-link active" : "app-sidebar-link"}
                    onClick={() => navigateTo(item.view)}>
                    {item.label}
                  </button>
                ))}
              </div>
              {group.title === "DB 분석" ? (
                <p className="app-sidebar-note">Preflight·개발용 Inspector는 Target 상세에서 확인합니다.</p>
              ) : null}
              {group.title === "스키마·Catalog" ? (
                <div className="app-sidebar-subnav" aria-label="Catalog 세부 메뉴">
                  {DISCOVERY_PAGES.map((item) => (
                    <button key={item.tab} type="button"
                      aria-current={view === "discovery" && discoveryTab === item.tab ? "page" : undefined}
                      className={view === "discovery" && discoveryTab === item.tab
                        ? "app-sidebar-link app-sidebar-sublink active"
                        : "app-sidebar-link app-sidebar-sublink"}
                      onClick={() => navigateDiscovery(item.tab)}>
                      {item.label}
                    </button>
                  ))}
                </div>
              ) : null}
            </section>
          ))}
          <section className="app-sidebar-section" aria-label="Analyzer 이관 예정">
            <h2>Analyzer 이관 예정</h2>
            <ul className="app-sidebar-pending">
              <li>DB 분석 보고서 <span>후속 작업</span></li>
              <li>분석 실행 간 Diff <span>후속 작업</span></li>
              <li>Catalog Package 최종화 <span>후속 작업</span></li>
            </ul>
          </section>
        </nav>
        <p className="app-sidebar-boundary">
          개발용 Mock 결과는 실제 DEMIS 접근·DBA 승인 상태를 의미하지 않습니다.
        </p>
      </aside>
      <div className="app-workspace">
        {view === "dashboard" ? <WorkflowDashboard onNavigate={navigateTo} /> : null}
        {view === "profiles" ? <ConnectionProfilePortal /> : null}
        {view === "discovery" ? (
          <DataDiscoveryPortal activeTab={discoveryTab}
            onTabChange={setDiscoveryTab} hideTabNavigation />
        ) : null}
        {view === "assistant" ? <QueryAssistant /> : null}
        {view === "template-review" ? <TemplateReviewPortal /> : null}
        {view === "integration-settings" ? <IntegrationSettingsPortal /> : null}
      </div>
    </div>
  );
}
