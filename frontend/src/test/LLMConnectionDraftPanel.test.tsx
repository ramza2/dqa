import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { LLMConnectionDraftPanel } from "../components/LLMConnectionDraftPanel";

afterEach(() => vi.unstubAllGlobals());

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
