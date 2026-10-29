export type WorkflowDestination = "profiles" | "discovery" | "assistant" | "template-review";

type Step = {
  number: string;
  title: string;
  description: string;
  availability: "available" | "integration-pending";
  actionLabel?: string;
  destination?: WorkflowDestination;
};

const STEPS: Step[] = [
  {
    number: "01",
    title: "DB Target 등록",
    description: "연계 대상 DB의 연결 설정을 등록하고 접근 권한을 검토합니다. 개발용 Oracle Mock도 별도 대상입니다.",
    availability: "available",
    actionLabel: "DB 연결 관리로 이동",
    destination: "profiles",
  },
  {
    number: "02",
    title: "스키마 분석",
    description: "선택한 Target에서 테이블·컬럼·키·관계 메타데이터를 수집합니다. 프로필 기반 실행 연결은 후속 개발입니다.",
    availability: "integration-pending",
  },
  {
    number: "03",
    title: "Catalog 검토 및 검색",
    description: "기존 Catalog 검색, 탐색, 스냅샷 이력을 확인합니다. 신규 분석 결과의 승인·활성화 연계는 후속 개발입니다.",
    availability: "available",
    actionLabel: "스키마·Catalog로 이동",
    destination: "discovery",
  },
  {
    number: "04",
    title: "임상정보 11종 매핑",
    description: "의무사 업무 담당자 확인 후 실제 테이블·컬럼과 임상정보 항목의 대응 관계를 검토·저장합니다.",
    availability: "integration-pending",
  },
  {
    number: "05",
    title: "Query Template 생성·승인",
    description: "DRAFT 작성·수정, 검토 제출, 승인·반려, 이력 조회, 정책에 따른 활성/비활성 화면입니다. 서버 권한·SQL Safety·Catalog 검증이 최종 기준입니다.",
    availability: "available",
    actionLabel: "템플릿 작성·검토 열기",
    destination: "template-review",
  },
  {
    number: "06",
    title: "MCP Tool 조회 연계",
    description: "승인·활성화된 템플릿만 지정 파라미터로 조회합니다. 외부 서비스 연계에는 별도 인증·승인이 필요합니다.",
    availability: "integration-pending",
  },
];

export function WorkflowDashboard({ onNavigate }: {
  onNavigate: (destination: WorkflowDestination) => void;
}) {
  return (
    <main className="workflow-home" data-testid="workflow-dashboard">
      <header className="workflow-hero">
        <span className="workflow-eyebrow">DQA 운영·개발 포털</span>
        <h1>DEMIS 데이터 연계 작업</h1>
        <p>DB 등록부터 스키마 분석, Catalog, Query Template, MCP 조회까지 진행할 순서입니다.</p>
        <p className="workflow-notice">
          아래 표시는 <strong>화면 이용 가능 여부</strong>이며, 실제 DEMIS 접속 승인이나
          분석·데이터 연계 완료 상태를 뜻하지 않습니다.
        </p>
      </header>
      <section className="workflow-section" aria-label="연계 작업 순서">
        <h2>업무 진행 순서</h2>
        <ol className="workflow-steps">
          {STEPS.map((step) => (
            <li key={step.number} className="workflow-step">
              <span className="workflow-step-number" aria-hidden="true">{step.number}</span>
              <div className="workflow-step-body">
                <div className="workflow-step-title">
                  <h3>{step.title}</h3>
                  <span className={step.availability === "available"
                    ? "workflow-status workflow-status-available"
                    : "workflow-status workflow-status-pending"}>
                    {step.availability === "available" ? "화면 이용 가능" : "연계 작업 예정"}
                  </span>
                </div>
                <p>{step.description}</p>
                {step.destination && step.actionLabel ? (
                  <button type="button" className="dd-secondary-btn"
                    onClick={() => onNavigate(step.destination!)}>
                    {step.actionLabel}
                  </button>
                ) : null}
              </div>
            </li>
          ))}
        </ol>
      </section>
      <section
        className="workflow-section workflow-legacy"
        aria-label="Oracle Mock 조회 시험"
        data-testid="mock-query-trial"
      >
        <h2>Oracle Mock 조회 시험 (LLM 불필요)</h2>
        <p>
          승인·활성화된 Query Template으로{" "}
          <strong>수동 선택 → 조건 입력 → 미리보기 → 실행 → 감사 이력</strong>을
          시험하는 기존 Query Assistant 경로입니다. LLM 추천·파라미터 추출 없이도
          동작합니다.
        </p>
        <p className="muted">
          개발용 Oracle Mock Target·READY Catalog·승인 템플릿·연결 Profile이 준비된
          뒤에만 실제 조회가 가능합니다. Target 등록·스키마 분석부터 시작하는
          관리자 업무의 첫 단계는 아닙니다. 실 DEMIS·MCP·운영 배포와는 별도입니다.
        </p>
        <button
          type="button"
          className="dd-secondary-btn"
          onClick={() => onNavigate("assistant")}
        >
          Mock 조회 시험 열기
        </button>
      </section>
    </main>
  );
}
