import { useQueryAssistant } from "../hooks/useQueryAssistant";
import type { ExecutionFormParameter } from "../types/queryAssistant";
import {
  blockerMessage,
  formatCellValue,
  listInputDisplayValue,
} from "../utils/queryAssistant";

function ErrorBanner({
  error,
}: {
  error: { code: string | null; message: string } | null;
}) {
  if (!error) {
    return null;
  }
  return (
    <div className="banner banner-error" role="alert">
      {error.code ? <code>{error.code}</code> : null} {error.message}
    </div>
  );
}

function InfoBanner({ message }: { message: string | null }) {
  if (!message) {
    return null;
  }
  return (
    <div className="banner banner-warn" role="status">
      {message}
    </div>
  );
}

function ParameterField({
  param,
  value,
  onChange,
}: {
  param: ExecutionFormParameter;
  value: unknown;
  onChange: (value: unknown) => void;
}) {
  const label = param.label || param.name;
  const id = `param-${param.name}`;
  const requiredMark = param.required ? (
    <span className="required-mark" aria-hidden="true">
      *
    </span>
  ) : null;

  if (param.type === "boolean") {
    return (
      <label className="param-field" htmlFor={id}>
        <span className="param-label">
          {label}
          {requiredMark}
          {param.sensitive ? <span className="badge badge-muted">민감</span> : null}
        </span>
        <select
          id={id}
          value={value === true ? "true" : "false"}
          onChange={(event) => onChange(event.target.value === "true")}
        >
          <option value="false">false</option>
          <option value="true">true</option>
        </select>
        {param.description ? (
          <span className="param-help">{param.description}</span>
        ) : null}
      </label>
    );
  }

  if (param.type === "enum") {
    return (
      <label className="param-field" htmlFor={id}>
        <span className="param-label">
          {label}
          {requiredMark}
          {param.sensitive ? <span className="badge badge-muted">민감</span> : null}
        </span>
        <select
          id={id}
          value={value === null || value === undefined ? "" : String(value)}
          onChange={(event) => onChange(event.target.value)}
        >
          <option value="">선택</option>
          {(param.allowed_values ?? []).map((item) => (
            <option key={String(item)} value={String(item)}>
              {String(item)}
            </option>
          ))}
        </select>
      </label>
    );
  }

  if (param.type === "string_list" || param.type === "integer_list") {
    return (
      <label className="param-field" htmlFor={id}>
        <span className="param-label">
          {label}
          {requiredMark}
          {param.sensitive ? <span className="badge badge-muted">민감</span> : null}
        </span>
        <input
          id={id}
          type={param.sensitive ? "password" : "text"}
          value={listInputDisplayValue(value)}
          onChange={(event) => onChange(event.target.value)}
          placeholder="쉼표로 구분"
          autoComplete="off"
        />
        {param.description ? (
          <span className="param-help">{param.description}</span>
        ) : null}
      </label>
    );
  }

  const inputType =
    param.type === "integer" || param.type === "decimal"
      ? "number"
      : param.type === "date"
        ? "date"
        : param.type === "datetime"
          ? "datetime-local"
          : param.sensitive
            ? "password"
            : "text";

  return (
    <label className="param-field" htmlFor={id}>
      <span className="param-label">
        {label}
        {requiredMark}
        {param.sensitive ? <span className="badge badge-muted">민감</span> : null}
      </span>
      <input
        id={id}
        type={inputType}
        step={param.type === "decimal" ? "any" : param.type === "integer" ? "1" : undefined}
        value={value === null || value === undefined ? "" : String(value)}
        onChange={(event) => {
          if (param.type === "integer") {
            onChange(event.target.value === "" ? "" : Number.parseInt(event.target.value, 10));
            return;
          }
          if (param.type === "decimal") {
            onChange(event.target.value === "" ? "" : Number(event.target.value));
            return;
          }
          onChange(event.target.value);
        }}
        autoComplete="off"
      />
      {param.description ? <span className="param-help">{param.description}</span> : null}
    </label>
  );
}

export function QueryAssistant() {
  const qa = useQueryAssistant();

  const selectedEnvMeta = qa.form?.environments.find(
    (item) => item.environment === qa.environment,
  );

  return (
    <div className="app-shell qa-shell" data-testid="query-assistant">
      <header className="app-header">
        <div className="app-title-row">
          <h1>DQA / Query Assistant</h1>
          <span className="subtitle">승인된 Query Template 기반 조회</span>
        </div>
        <label className="source-field">
          <span className="label">Active Catalog source</span>
          <select
            className="source-select"
            aria-label="Active Catalog source"
            value={qa.selectedSource}
            disabled={qa.sourcesState === "loading"}
            onChange={(event) => qa.selectSource(event.target.value)}
          >
            <option value="">소스 선택</option>
            {qa.sources.map((source) => (
              <option key={source.source_name} value={source.source_name}>
                {source.source_name}
              </option>
            ))}
          </select>
        </label>
        <ErrorBanner error={qa.sourcesError} />
      </header>

      <div className="qa-layout">
        <section className="qa-panel" aria-labelledby="qa-request-heading">
          <h2 id="qa-request-heading">자연어 요청</h2>
          <textarea
            aria-label="자연어 조회 요청"
            maxLength={qa.maxRequestText}
            rows={4}
            value={qa.requestText}
            onChange={(event) => qa.setRequestText(event.target.value)}
            placeholder="조회하려는 내용을 입력하세요"
            disabled={!qa.selectedSource}
          />
          <div className="qa-actions">
            <span className="muted">
              {qa.requestText.length}/{qa.maxRequestText}
            </span>
            <button
              type="button"
              onClick={() => void qa.submitRecommendation()}
              disabled={
                !qa.selectedSource ||
                !qa.requestText.trim() ||
                qa.recommendState === "loading"
              }
            >
              {qa.recommendState === "loading" ? "찾는 중…" : "조회 방법 찾기"}
            </button>
          </div>
          <ErrorBanner error={qa.recommendError} />
        </section>

        {qa.recommendation ? (
          <section className="qa-panel" aria-labelledby="qa-template-heading">
            <h2 id="qa-template-heading">추천 템플릿</h2>
            {qa.recommendation.needs_clarification ? (
              <div className="banner banner-warn" role="status">
                {qa.recommendation.clarification_question ??
                  "요청을 조금 더 구체적으로 입력해주세요."}
              </div>
            ) : null}
            {qa.recommendation.recommended_template ? (
              <div className="qa-template-card" data-testid="recommended-template">
                <div className="qa-template-title">
                  {qa.recommendation.recommended_template.name}
                </div>
                {qa.recommendation.recommended_template.description ? (
                  <p>{qa.recommendation.recommended_template.description}</p>
                ) : null}
                {qa.recommendation.confidence !== null ? (
                  <p className="muted">
                    템플릿 라우팅 신뢰도:{" "}
                    {(qa.recommendation.confidence * 100).toFixed(0)}%
                  </p>
                ) : null}
                {qa.recommendation.reason ? (
                  <p className="muted">이유: {qa.recommendation.reason}</p>
                ) : null}
              </div>
            ) : null}
            {qa.recommendation.ranked_candidates.length > 0 ? (
              <div className="qa-candidates" data-testid="ranked-candidates">
                <h3>대안 후보</h3>
                <ul>
                  {qa.recommendation.ranked_candidates.map((candidate) => {
                    const selected =
                      qa.selectedCandidate?.template_id === candidate.template_id &&
                      qa.selectedCandidate?.version_id === candidate.version_id;
                    return (
                      <li key={`${candidate.template_id}-${candidate.version_id}`}>
                        <button
                          type="button"
                          className={selected ? "candidate selected" : "candidate"}
                          onClick={() => void qa.selectCandidate(candidate)}
                          disabled={qa.formState === "loading"}
                        >
                          <strong>{candidate.name}</strong>
                          {candidate.description ? (
                            <span className="muted">{candidate.description}</span>
                          ) : null}
                        </button>
                      </li>
                    );
                  })}
                </ul>
              </div>
            ) : null}
          </section>
        ) : null}

        {qa.form || qa.formState === "loading" || qa.formError ? (
          <section className="qa-panel" aria-labelledby="qa-form-heading">
            <h2 id="qa-form-heading">조건 및 실행 환경</h2>
            {qa.formState === "loading" ? <p className="muted">폼 불러오는 중…</p> : null}
            <ErrorBanner error={qa.formError} />
            {qa.form ? (
              <>
                <div className="qa-template-meta">
                  <div>
                    <strong>{qa.form.template.name}</strong>
                    <span className="muted"> v{qa.form.template.version}</span>
                  </div>
                  {qa.form.template.description ? (
                    <p className="muted">{qa.form.template.description}</p>
                  ) : null}
                </div>

                <label className="param-field">
                  <span className="param-label">실행 환경</span>
                  <select
                    aria-label="실행 환경"
                    value={qa.environment}
                    onChange={(event) => qa.setSelectedEnvironment(event.target.value)}
                  >
                    {qa.form.environments.length === 0 ? (
                      <option value="">사용 가능한 환경 없음</option>
                    ) : (
                      qa.form.environments.map((env) => (
                        <option key={env.environment} value={env.environment}>
                          {env.environment}
                          {env.execution_available ? "" : " (실행 불가)"}
                        </option>
                      ))
                    )}
                  </select>
                </label>
                {selectedEnvMeta && !selectedEnvMeta.execution_available ? (
                  <div className="banner banner-warn" data-testid="env-blockers">
                    {selectedEnvMeta.execution_blockers.map((code) => (
                      <div key={code}>{blockerMessage(code)}</div>
                    ))}
                  </div>
                ) : null}

                <div className="param-grid">
                  {qa.form.parameters.map((param) => (
                    <ParameterField
                      key={param.name}
                      param={param}
                      value={qa.parameterValues[param.name]}
                      onChange={(value) => qa.setParameterValue(param.name, value)}
                    />
                  ))}
                </div>

                <div className="qa-actions">
                  <button
                    type="button"
                    onClick={() => void qa.runExtraction()}
                    disabled={
                      !qa.selectedCandidate ||
                      !qa.requestText.trim() ||
                      qa.extractState === "loading"
                    }
                  >
                    {qa.extractState === "loading" ? "추출 중…" : "AI로 조건 채우기"}
                  </button>
                </div>
                <InfoBanner message={qa.extractInfo} />
                <InfoBanner message={qa.extractClarification} />
                <ErrorBanner error={qa.extractError} />
              </>
            ) : null}
          </section>
        ) : null}

        {qa.form ? (
          <section className="qa-panel" aria-labelledby="qa-preview-heading">
            <h2 id="qa-preview-heading">조회 미리보기</h2>
            <div className="qa-actions">
              <button
                type="button"
                onClick={() => void qa.runPreview()}
                disabled={
                  !qa.selectedCandidate ||
                  !qa.environment ||
                  qa.previewState === "loading"
                }
              >
                {qa.previewState === "loading" ? "미리보기 중…" : "조회 미리보기"}
              </button>
              <button
                type="button"
                className="primary"
                onClick={() => void qa.runExecute()}
                disabled={!qa.canExecute}
                title={
                  qa.canExecute
                    ? "승인된 템플릿으로 조회 실행"
                    : "미리보기가 가능하고 실행 가능한 상태에서만 실행할 수 있습니다"
                }
              >
                {qa.executeState === "loading" ? "실행 중…" : "조회 실행"}
              </button>
            </div>
            <ErrorBanner error={qa.previewError} />
            <ErrorBanner error={qa.executeError} />
            {qa.preview && qa.previewMatchesCurrent ? (
              <div className="qa-preview-summary" data-testid="preview-summary">
                <dl className="status-grid">
                  <div className="status-item">
                    <span className="label">템플릿</span>
                    <span className="value">
                      {qa.form.template.name} / v{qa.preview.version}
                    </span>
                  </div>
                  <div className="status-item">
                    <span className="label">환경</span>
                    <span className="value">{qa.preview.environment}</span>
                  </div>
                  <div className="status-item">
                    <span className="label">row_limit</span>
                    <span className="value">{qa.preview.row_limit}</span>
                  </div>
                  <div className="status-item">
                    <span className="label">timeout_seconds</span>
                    <span className="value">{qa.preview.timeout_seconds}</span>
                  </div>
                  <div className="status-item">
                    <span className="label">execution_available</span>
                    <span className="value">
                      {qa.preview.execution_available ? "true" : "false"}
                    </span>
                  </div>
                </dl>
                {qa.preview.execution_blockers.length > 0 ? (
                  <div className="banner banner-warn">
                    {qa.preview.execution_blockers.map((code) => (
                      <div key={code}>{blockerMessage(code)}</div>
                    ))}
                  </div>
                ) : null}
                <h3>확정 파라미터</h3>
                <ul className="qa-param-summary">
                  {Object.entries(qa.preview.resolved_parameters).map(([name, value]) => {
                    const sensitive =
                      qa.preview?.sensitive_parameter_names.includes(name) ||
                      qa.form?.parameters.find((item) => item.name === name)?.sensitive;
                    return (
                      <li key={name}>
                        <code>{name}</code>:{" "}
                        {sensitive ? "입력됨" : formatCellValue(value)}
                      </li>
                    );
                  })}
                </ul>
              </div>
            ) : (
              <p className="muted">미리보기를 실행한 뒤에만 조회를 실행할 수 있습니다.</p>
            )}
          </section>
        ) : null}

        {qa.result ? (
          <section className="qa-panel" aria-labelledby="qa-result-heading">
            <h2 id="qa-result-heading">조회 결과</h2>
            <dl className="status-grid">
              <div className="status-item">
                <span className="label">row_count</span>
                <span className="value">{qa.result.row_count}</span>
              </div>
              <div className="status-item">
                <span className="label">truncated</span>
                <span className="value">{qa.result.truncated ? "true" : "false"}</span>
              </div>
              <div className="status-item">
                <span className="label">elapsed_ms</span>
                <span className="value">{qa.result.elapsed_ms}</span>
              </div>
              <div className="status-item">
                <span className="label">감사 추적 ID</span>
                <span className="value" data-testid="audit-id">
                  {qa.result.audit_id}
                </span>
              </div>
            </dl>
            <div className="qa-result-table-wrap">
              <table className="data-table qa-result-table">
                <thead>
                  <tr>
                    {qa.result.columns.map((column) => (
                      <th key={column}>{column}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {qa.result.rows.map((row, index) => (
                    <tr key={`row-${index}`}>
                      {qa.result!.columns.map((column) => (
                        <td key={column}>{formatCellValue(row[column])}</td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        ) : null}
      </div>
    </div>
  );
}
