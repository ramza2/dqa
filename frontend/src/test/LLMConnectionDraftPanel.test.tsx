import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { LLMConnectionDraftPanel } from "../components/LLMConnectionDraftPanel";
import { reviewLLMConnectionCandidate, type LLMConnectionCandidateDecision } from "../api/integrationSettings";

vi.mock("../api/integrationSettings", () => ({
  reviewLLMConnectionCandidate: vi.fn(),
}));

const policyResult = (code: LLMConnectionCandidateDecision["code"]): LLMConnectionCandidateDecision => ({
  code,
  server_configuration_changed: false,
  credential_loaded: false,
  ready_for_runtime: false,
  ready_for_connection_test: false,
});

async function fillValidDraft(): Promise<void> {
  await userEvent.type(screen.getByLabelText("연결 이름"), "Dev Candidate");
  await userEvent.type(screen.getByLabelText("API 서버 주소"), "https://model.internal.example/v1");
  await userEvent.type(screen.getByLabelText("모델 식별자"), "qwen3-14b");
}


afterEach(() => {
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

describe("M5-L1A provider-neutral local LLM draft", () => {
  it("shows multiple connection environments without asking for secrets", () => {
    render(<LLMConnectionDraftPanel onClose={vi.fn()} />);
    const options = screen.getByLabelText("연결 환경").querySelectorAll("option");
    expect(Array.from(options).map((option) => option.value)).toEqual([
      "modelops", "snuh_ai", "self_hosted", "other",
    ]);
    expect(screen.getByText(/모델 다운로드 출처와 API 제공 서버는 별개/)).toBeInTheDocument();
    expect(screen.queryByLabelText(/API 키/)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "실제 설정 저장 (미지원)" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "서버 LLM 연결 초기화 (미지원)" })).toBeDisabled();
  });

  it("rejects malformed URL and credential-in-URL without any network call", async () => {
    const fetchSpy = vi.fn();
    vi.stubGlobal("fetch", fetchSpy);
    render(<LLMConnectionDraftPanel onClose={vi.fn()} />);
    await userEvent.type(screen.getByLabelText("연결 이름"), "Test LLM");
    await userEvent.type(screen.getByLabelText("API 서버 주소"), "javascript:alert(1)");
    await userEvent.type(screen.getByLabelText("모델 식별자"), "local");
    await userEvent.click(screen.getByRole("button", { name: "초안 입력 점검" }));
    expect(screen.getByRole("alert")).toHaveTextContent("HTTP(S)");
    await userEvent.clear(screen.getByLabelText("API 서버 주소"));
    await userEvent.type(screen.getByLabelText("API 서버 주소"), "https://user:pass@example.invalid/v1");
    await userEvent.click(screen.getByRole("button", { name: "초안 입력 점검" }));
    expect(screen.getByRole("alert")).toHaveTextContent("계정·암호");
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("accepts an offline self-hosted draft, warns about HTTP and never saves it", async () => {
    const fetchSpy = vi.fn();
    vi.stubGlobal("fetch", fetchSpy);
    render(<LLMConnectionDraftPanel onClose={vi.fn()} />);
    await userEvent.selectOptions(screen.getByLabelText("연결 환경"), "self_hosted");
    await userEvent.type(screen.getByLabelText("연결 이름"), "Offline");
    await userEvent.type(screen.getByLabelText("API 서버 주소"), "http://127.0.0.1:8000/v1");
    await userEvent.type(screen.getByLabelText("모델 식별자"), "my-qwen");
    expect(screen.getByRole("note")).toHaveTextContent("HTTP 주소는 암호화되지 않습니다");
    await userEvent.click(screen.getByRole("button", { name: "초안 입력 점검" }));
    expect(screen.getByRole("status")).toHaveTextContent("저장이나 연결 시험은 실행되지 않았습니다");
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("needs a second confirmation before clearing only the local draft", async () => {
    render(<LLMConnectionDraftPanel onClose={vi.fn()} />);
    await userEvent.type(screen.getByLabelText("연결 이름"), "Candidate");
    await userEvent.click(screen.getByRole("button", { name: "초안 초기화" }));
    expect(screen.getByLabelText("연결 이름")).toHaveValue("Candidate");
    await userEvent.click(screen.getByRole("button", { name: "취소" }));
    expect(screen.getByLabelText("연결 이름")).toHaveValue("Candidate");
    await userEvent.click(screen.getByRole("button", { name: "초안 초기화" }));
    await userEvent.click(screen.getByRole("button", { name: "초안 초기화 확정" }));
    expect(screen.getByLabelText("연결 이름")).toHaveValue("");
    expect(screen.getByRole("status")).toHaveTextContent("서버 설정은 변경되지 않았습니다");
  });

  it("closes without persisting a candidate", async () => {
    const onClose = vi.fn();
    render(<LLMConnectionDraftPanel onClose={onClose} />);
    await userEvent.type(screen.getByLabelText("연결 이름"), "Temporary");
    await userEvent.click(screen.getByRole("button", { name: "닫기" }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});

describe("M5-L1D dev-only explicit server candidate review", () => {
  it("never offers server review without the authenticated server capability flag", async () => {
    render(<LLMConnectionDraftPanel onClose={vi.fn()} serverReviewAvailable={false} />);
    await fillValidDraft();
    await userEvent.click(screen.getByRole("button", { name: "초안 입력 점검" }));
    expect(screen.queryByRole("button", { name: "서버 정책 점검" })).not.toBeInTheDocument();
    expect(reviewLLMConnectionCandidate).not.toHaveBeenCalled();
  });

  it("posts only allowed metadata after explicit click with integer timeout", async () => {
    vi.mocked(reviewLLMConnectionCandidate).mockResolvedValue(policyResult("POLICY_REVIEW_REQUIRED"));
    render(<LLMConnectionDraftPanel onClose={vi.fn()} serverReviewAvailable />);
    await fillValidDraft();
    await userEvent.click(screen.getByRole("button", { name: "초안 입력 점검" }));
    expect(reviewLLMConnectionCandidate).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: "서버 정책 점검" }));
    expect(reviewLLMConnectionCandidate).toHaveBeenCalledTimes(1);
    expect(reviewLLMConnectionCandidate).toHaveBeenCalledWith({
      name: "Dev Candidate",
      environment: "modelops",
      protocol: "openai_compatible",
      baseUrl: "https://model.internal.example/v1",
      modelId: "qwen3-14b",
      timeoutSeconds: 60,
    });
    expect(await screen.findByRole("status")).toHaveTextContent("운영 정책 검토가 필요합니다");
    expect(screen.getByRole("status")).toHaveTextContent("연결·사용 승인 상태가 아닙니다");
  });

  it("does not transmit a malformed candidate even when server review is available", async () => {
    render(<LLMConnectionDraftPanel onClose={vi.fn()} serverReviewAvailable />);
    await userEvent.type(screen.getByLabelText("연결 이름"), "Only name");
    await userEvent.click(screen.getByRole("button", { name: "서버 정책 점검" }));
    expect(screen.getByRole("alert")).toHaveTextContent("서버 주소");
    expect(reviewLLMConnectionCandidate).not.toHaveBeenCalled();
  });

  it("displays HTTPS policy rejection and never promotes a candidate to active", async () => {
    vi.mocked(reviewLLMConnectionCandidate).mockResolvedValue(policyResult("INSECURE_ENDPOINT"));
    render(<LLMConnectionDraftPanel onClose={vi.fn()} serverReviewAvailable />);
    await userEvent.type(screen.getByLabelText("연결 이름"), "Offline");
    await userEvent.type(screen.getByLabelText("API 서버 주소"), "http://127.0.0.1:8000/v1");
    await userEvent.type(screen.getByLabelText("모델 식별자"), "local");
    await userEvent.click(screen.getByRole("button", { name: "서버 정책 점검" }));
    expect(await screen.findByRole("status")).toHaveTextContent("HTTPS 주소가 아니므로");
    expect(screen.getByRole("button", { name: "실제 설정 저장 (미지원)" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "서버 LLM 연결 초기화 (미지원)" })).toBeDisabled();
  });

  it("hides untrusted server error details from the operator", async () => {
    vi.mocked(reviewLLMConnectionCandidate).mockRejectedValue(
      new Error("private.example:8800/api-key-supersecret"),
    );
    render(<LLMConnectionDraftPanel onClose={vi.fn()} serverReviewAvailable />);
    await fillValidDraft();
    await userEvent.click(screen.getByRole("button", { name: "서버 정책 점검" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("서버 정책 점검을 수행할 수 없습니다");
    expect(screen.queryByText(/api-key-supersecret/)).not.toBeInTheDocument();
  });

  it("invalidates an in-flight response when the draft changes", async () => {
    let resolveReview!: (value: LLMConnectionCandidateDecision) => void;
    vi.mocked(reviewLLMConnectionCandidate).mockImplementation(
      () => new Promise<LLMConnectionCandidateDecision>((resolve) => { resolveReview = resolve; }),
    );
    render(<LLMConnectionDraftPanel onClose={vi.fn()} serverReviewAvailable />);
    await fillValidDraft();
    await userEvent.click(screen.getByRole("button", { name: "서버 정책 점검" }));
    expect(screen.getByRole("button", { name: "서버 정책 점검 중…" })).toBeDisabled();
    await userEvent.type(screen.getByLabelText("연결 이름"), " changed");
    await act(async () => { resolveReview(policyResult("POLICY_REVIEW_REQUIRED")); });
    expect(screen.queryByText(/서버 정책 점검 결과:/)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "서버 정책 점검" })).toBeEnabled();
  });
});
