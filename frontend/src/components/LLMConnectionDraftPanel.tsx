import { useState, type FormEvent } from "react";

/**
 * M5-L1A: review a proposed connection locally only.
 * No endpoint is called, no secret is entered, and no draft is persisted.
 */
type ConnectionEnvironment = "modelops" | "snuh_ai" | "self_hosted" | "other";
type ApiProtocol = "openai_compatible" | "custom_api";

interface ConnectionDraft {
  name: string;
  environment: ConnectionEnvironment;
  protocol: ApiProtocol;
  baseUrl: string;
  modelId: string;
  timeoutSeconds: string;
}

const EMPTY_DRAFT: ConnectionDraft = {
  name: "",
  environment: "modelops",
  protocol: "openai_compatible",
  baseUrl: "",
  modelId: "",
  timeoutSeconds: "60",
};

function validateDraft(draft: ConnectionDraft): string | null {
  const name = draft.name.trim();
  if (!name || name.length > 100) {
    return "연결 이름을 1~100자로 입력하세요.";
  }
  const urlText = draft.baseUrl.trim();
  if (!urlText || urlText.length > 2048 || /\s/.test(urlText)) {
    return "공백 없이 올바른 API 서버 주소를 입력하세요.";
  }
  try {
    const url = new URL(urlText);
    if (
      !["https:", "http:"].includes(url.protocol) ||
      !url.hostname ||
      url.username ||
      url.password ||
      url.search ||
      url.hash
    ) {
      return "주소는 HTTP(S) 서버 URL만 허용하며 계정·암호·쿼리·해시를 포함할 수 없습니다.";
    }
  } catch {
    return "API 서버 주소 형식이 올바르지 않습니다.";
  }
  const modelId = draft.modelId.trim();
  if (!modelId || modelId.length > 200) {
    return "모델 식별자를 1~200자로 입력하세요.";
  }
  const timeout = Number(draft.timeoutSeconds);
  if (!/^\d+$/.test(draft.timeoutSeconds) || !Number.isInteger(timeout) ||
      timeout < 1 || timeout > 300) {
    return "응답 제한 시간은 1~300초 사이의 정수로 입력하세요.";
  }
  return null;
}

export function LLMConnectionDraftPanel({ onClose }: { onClose: () => void }) {
  const [draft, setDraft] = useState<ConnectionDraft>({ ...EMPTY_DRAFT });
  const [reviewMessage, setReviewMessage] = useState<string | null>(null);
  const [reviewError, setReviewError] = useState<string | null>(null);
  const [confirmReset, setConfirmReset] = useState(false);

  function update<K extends keyof ConnectionDraft>(key: K, value: ConnectionDraft[K]): void {
    setDraft((previous) => ({ ...previous, [key]: value }));
    setReviewMessage(null);
    setReviewError(null);
    setConfirmReset(false);
  }

  function review(event: FormEvent<HTMLFormElement>): void {
    event.preventDefault();
    setConfirmReset(false);
    const error = validateDraft(draft);
    setReviewError(error);
    setReviewMessage(error ? null : "입력 항목 점검 완료. 저장이나 연결 시험은 실행되지 않았습니다.");
  }

  function resetDraft(): void {
    setDraft({ ...EMPTY_DRAFT });
    setReviewMessage("입력 중이던 로컬 초안만 초기화했습니다. 서버 설정은 변경되지 않았습니다.");
    setReviewError(null);
    setConfirmReset(false);
  }

  return (
    <section className="cp-editor" aria-label="LLM 연결 후보 로컬 초안">
      <h4>LLM 연결 후보 입력 · 로컬 초안</h4>
      <p className="dd-guidance">
        ModelOps, SNUH.AI, 별도 설치한 Hugging Face 기반 모델 등을 검토하기 위한 입력 폼입니다.
        실제 서버에 반영되지 않고, 화면을 닫으면 입력 내용이 사라집니다.
        API 키·토큰·환자정보는 입력하지 마세요.
      </p>
      <form onSubmit={review} aria-label="LLM 연결 초안 검토 양식">
        <div className="cp-editor-form">
          <label className="dd-field">
            연결 이름
            <input value={draft.name} maxLength={100}
              placeholder="예: 개발용 내부 LLM"
              onChange={(event) => update("name", event.target.value)} />
          </label>
          <label className="dd-field">
            연결 환경
            <select value={draft.environment}
              onChange={(event) => update("environment", event.target.value as ConnectionEnvironment)}>
              <option value="modelops">사내 ModelOps Gateway</option>
              <option value="snuh_ai">SNUH.AI 등 기관 제공 API</option>
              <option value="self_hosted">별도 설치·운영한 LLM (Hugging Face 등)</option>
              <option value="other">기타 API 제공자</option>
            </select>
          </label>
          <label className="dd-field">
            API 호출 형식
            <select value={draft.protocol}
              onChange={(event) => update("protocol", event.target.value as ApiProtocol)}>
              <option value="openai_compatible">OpenAI 호환 API</option>
              <option value="custom_api">기타 API (추후 어댑터 필요)</option>
            </select>
          </label>
          <label className="dd-field">
            API 서버 주소
            <input value={draft.baseUrl} maxLength={2048} spellCheck={false}
              placeholder="https://llm.example.internal/v1"
              onChange={(event) => update("baseUrl", event.target.value)} />
          </label>
          <label className="dd-field">
            모델 식별자
            <input value={draft.modelId} maxLength={200} spellCheck={false}
              placeholder="예: qwen3-14b 또는 서버가 제공하는 모델 ID"
              onChange={(event) => update("modelId", event.target.value)} />
          </label>
          <label className="dd-field">
            응답 제한 시간 (초)
            <input type="number" min={1} max={300} step={1}
              value={draft.timeoutSeconds}
              onChange={(event) => update("timeoutSeconds", event.target.value)} />
          </label>
        </div>
        <p className="muted">
          모델 다운로드 출처와 API 제공 서버는 별개입니다. 자체 설치 모델은 vLLM 등 API 서버를
          통해 호출할 수 있어야 합니다. 기타 API 형식은 전용 어댑터를 검토해야 합니다.
        </p>
        {draft.baseUrl.trim().startsWith("http://") && (
          <p className="banner banner-warn" role="note">
            HTTP 주소는 암호화되지 않습니다. 실제 연동은 기관이 승인한 내부망·보안 정책에서만 허용합니다.
          </p>
        )}
        {draft.protocol === "custom_api" && (
          <p className="banner banner-warn" role="note">
            기타 API는 연결 어댑터가 아직 없습니다. 이 초안으로 실제 호출할 수 없습니다.
          </p>
        )}
        {reviewError && <p className="banner banner-error" role="alert">{reviewError}</p>}
        {reviewMessage && <p role="status">{reviewMessage}</p>}
        <div className="dd-action-row">
          <button type="submit" className="dd-primary-btn">초안 입력 점검</button>
          <button type="button" className="dd-secondary-btn"
            onClick={() => setConfirmReset(true)}>초안 초기화</button>
          <button type="button" className="dd-secondary-btn" onClick={onClose}>닫기</button>
        </div>
        {confirmReset && (
          <div className="banner banner-warn">
            <p>입력 중인 항목을 지울까요? 서버 설정은 영향을 받지 않습니다.</p>
            <div className="dd-action-row">
              <button type="button" onClick={resetDraft}>초안 초기화 확정</button>
              <button type="button" onClick={() => setConfirmReset(false)}>취소</button>
            </div>
          </div>
        )}
        <div className="dd-action-row">
          <button type="button" disabled>실제 설정 저장 (미지원)</button>
          <button type="button" disabled>서버 LLM 연결 초기화 (미지원)</button>
        </div>
      </form>
      <p className="muted">
        연결 후보 점검은 브라우저 내부 형식 검사만 수행합니다.
        실제 서버 저장·비밀키 교체·API 호출·감사 기록은 후속 보안 구현 대상입니다.
      </p>
    </section>
  );
}
