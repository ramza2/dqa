import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "../App";
import { QueryAssistant } from "../components/QueryAssistant";
import { resolveDevAuthHeaders } from "../api/client";
import { CatalogApiError, type CatalogActiveSummary } from "../types/catalog";
import type {
  ExecutionFormResponse,
  ExecutionPreviewResponse,
  QueryExecutionResponse,
  TemplateRecommendationResponse,
} from "../types/queryAssistant";
import { isEgressNotAllowed } from "../utils/queryAssistant";
import {
  activeSource,
  defaultCatalogHandlers,
  installFetchMock,
  jsonResponse,
  secondSource,
} from "./mocks";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

const recommendation: TemplateRecommendationResponse = {
  source_name: activeSource.source_name,
  catalog_revision_id: 1,
  schema_fingerprint: activeSource.schema_fingerprint,
  needs_clarification: false,
  clarification_question: null,
  confidence: 0.91,
  reason: "병동 조회와 일치",
  recommended_template: {
    template_id: 10,
    version_id: 20,
    version: 2,
    stable_key: "wards.lookup",
    name: "병동 조회",
    description: "병동 코드로 조회",
    target_schemas: ["DEMIS_OWNER"],
    parameter_names: ["ward_cd", "from_date"],
    parameter_count: 2,
  },
  ranked_candidates: [
    {
      template_id: 10,
      version_id: 20,
      version: 2,
      stable_key: "wards.lookup",
      name: "병동 조회",
      description: "병동 코드로 조회",
      target_schemas: ["DEMIS_OWNER"],
      parameter_names: ["ward_cd", "from_date"],
      parameter_count: 2,
    },
    {
      template_id: 11,
      version_id: 21,
      version: 1,
      stable_key: "wards.alt",
      name: "병동 대안",
      description: "대안 템플릿",
      target_schemas: ["DEMIS_OWNER"],
      parameter_names: ["ward_cd"],
      parameter_count: 1,
    },
  ],
};

const clarificationRecommendation: TemplateRecommendationResponse = {
  ...recommendation,
  needs_clarification: true,
  clarification_question: "어느 병동을 조회할까요?",
  recommended_template: null,
  ranked_candidates: [],
  confidence: null,
  reason: null,
};

const formResponse: ExecutionFormResponse = {
  source_name: activeSource.source_name,
  catalog_revision_id: 1,
  catalog_fingerprint: activeSource.schema_fingerprint,
  template: {
    template_id: 10,
    version_id: 20,
    version: 2,
    stable_key: "wards.lookup",
    name: "병동 조회",
    description: "병동 코드로 조회",
  },
  parameters: [
    {
      name: "ward_cd",
      label: "병동 코드",
      description: "민감 병동 코드",
      type: "string",
      required: true,
      default: null,
      allowed_values: null,
      pattern: "^[A-Z][0-9]{2}$",
      min: null,
      max: null,
      min_items: null,
      max_items: null,
      sensitive: true,
    },
    {
      name: "from_date",
      label: "시작일",
      description: null,
      type: "date",
      required: false,
      default: "2024-01-01",
      allowed_values: null,
      pattern: null,
      min: null,
      max: null,
      min_items: null,
      max_items: null,
      sensitive: false,
    },
    {
      name: "active",
      label: "활성",
      description: null,
      type: "boolean",
      required: true,
      default: true,
      allowed_values: null,
      pattern: null,
      min: null,
      max: null,
      min_items: null,
      max_items: null,
      sensitive: false,
    },
    {
      name: "kind",
      label: "종류",
      description: null,
      type: "enum",
      required: true,
      default: "A",
      allowed_values: ["A", "B"],
      pattern: null,
      min: null,
      max: null,
      min_items: null,
      max_items: null,
      sensitive: false,
    },
  ],
  environments: [
    {
      environment: "dev",
      execution_available: false,
      execution_blockers: ["DEMIS_ADAPTER_UNAVAILABLE"],
    },
    {
      environment: "qa",
      execution_available: false,
      execution_blockers: ["CONNECTION_PROFILE_INCOMPLETE"],
    },
  ],
};

const altFormResponse: ExecutionFormResponse = {
  ...formResponse,
  template: {
    template_id: 11,
    version_id: 21,
    version: 1,
    stable_key: "wards.alt",
    name: "병동 대안",
    description: "대안 템플릿",
  },
  parameters: [
    {
      name: "ward_cd",
      label: "병동 코드",
      description: null,
      type: "string",
      required: true,
      default: "Z99",
      allowed_values: null,
      pattern: null,
      min: null,
      max: null,
      min_items: null,
      max_items: null,
      sensitive: false,
    },
  ],
  environments: [
    {
      environment: "dev",
      execution_available: false,
      execution_blockers: ["DEMIS_ADAPTER_UNAVAILABLE"],
    },
  ],
};

const unavailablePreview: ExecutionPreviewResponse = {
  source_name: activeSource.source_name,
  environment: "dev",
  catalog_revision_id: 1,
  catalog_fingerprint: activeSource.schema_fingerprint,
  template_id: 10,
  version_id: 20,
  version: 2,
  connection_profile_id: 99,
  resolved_parameters: {
    ward_cd: "A01",
    from_date: "2024-01-01",
    active: true,
    kind: "A",
  },
  sensitive_parameter_names: ["ward_cd"],
  row_limit: 50,
  timeout_seconds: 15,
  execution_available: false,
  execution_blockers: ["DEMIS_ADAPTER_UNAVAILABLE"],
};

const availablePreview: ExecutionPreviewResponse = {
  ...unavailablePreview,
  execution_available: true,
  execution_blockers: [],
};

const executeResponse: QueryExecutionResponse = {
  audit_id: "audit-123",
  source_name: activeSource.source_name,
  environment: "dev",
  catalog_revision_id: 1,
  catalog_fingerprint: activeSource.schema_fingerprint,
  template_id: 10,
  version_id: 20,
  version: 2,
  connection_profile_id: 99,
  columns: ["ward_cd", "note"],
  rows: [
    { ward_cd: "A01", note: "ok" },
    { ward_cd: "B02", note: null },
  ],
  row_count: 2,
  truncated: false,
  elapsed_ms: 12,
};

type FetchHandler = (
  url: URL,
  init?: RequestInit,
) => Response | Promise<Response | null> | null;

function assistantHandlers(options?: {
  recommendation?: TemplateRecommendationResponse;
  form?: ExecutionFormResponse;
  preview?: ExecutionPreviewResponse;
  execute?: QueryExecutionResponse | null;
  extractStatus?: number;
  extractBody?: unknown;
  actives?: CatalogActiveSummary[];
}): FetchHandler[] {
  const previewPayload = options?.preview ?? unavailablePreview;
  const executePayload = options?.execute === undefined ? executeResponse : options.execute;
  return [
    ...defaultCatalogHandlers({ actives: options?.actives }),
    (url, init) => {
      if (url.pathname.endsWith("/query-recommendations") && init?.method === "POST") {
        return jsonResponse(options?.recommendation ?? recommendation);
      }
      if (url.pathname.endsWith("/query-executions/form")) {
        const templateId = url.searchParams.get("template_id");
        if (templateId === "11") {
          return jsonResponse(altFormResponse);
        }
        return jsonResponse(options?.form ?? formResponse);
      }
      if (url.pathname.endsWith("/query-parameters/extract") && init?.method === "POST") {
        if (options?.extractStatus) {
          return jsonResponse(
            options.extractBody ?? { detail: { code: "X", message: "err" } },
            options.extractStatus,
          );
        }
        return jsonResponse({
          source_name: activeSource.source_name,
          catalog_revision_id: 1,
          schema_fingerprint: activeSource.schema_fingerprint,
          template_id: 10,
          version_id: 20,
          version: 2,
          needs_clarification: false,
          clarification_question: null,
          resolved_parameters: { ward_cd: "A01" },
          issues: [],
          sensitive_parameter_names: ["ward_cd"],
        });
      }
      if (url.pathname.endsWith("/query-executions/preview") && init?.method === "POST") {
        return jsonResponse(previewPayload);
      }
      if (url.pathname.endsWith("/query-executions/execute") && init?.method === "POST") {
        if (executePayload === null) {
          return jsonResponse(
            { detail: { code: "DEMIS_ADAPTER_UNAVAILABLE", message: "blocked" } },
            503,
          );
        }
        return jsonResponse(executePayload);
      }
      return null;
    },
  ];
}

async function recommendHappyPath(user: ReturnType<typeof userEvent.setup>) {
  await screen.findByLabelText("Active Catalog source");
  await user.selectOptions(screen.getByLabelText("Active Catalog source"), activeSource.source_name);
  await user.type(screen.getByLabelText("자연어 조회 요청"), "병동 조회해줘");
  await user.click(screen.getByRole("button", { name: "조회 방법 찾기" }));
  expect(await screen.findByTestId("recommended-template")).toBeInTheDocument();
  expect(await screen.findByLabelText(/병동 코드/)).toBeInTheDocument();
}

describe("App navigation", () => {
  it("defaults to Query Assistant and can switch to Catalog Explorer", async () => {
    const user = userEvent.setup();
    const restore = installFetchMock(defaultCatalogHandlers());
    render(<App />);

    expect(screen.getByTestId("query-assistant")).toBeInTheDocument();
    expect(screen.queryByText("DQA / Catalog Explorer")).not.toBeInTheDocument();

    await user.click(screen.getByRole("tab", { name: "Catalog Explorer" }));
    expect(await screen.findByText("DQA / Catalog Explorer")).toBeInTheDocument();
    expect(screen.queryByTestId("query-assistant")).not.toBeInTheDocument();

    await user.click(screen.getByRole("tab", { name: "Query Assistant" }));
    expect(await screen.findByTestId("query-assistant")).toBeInTheDocument();
    restore();
  });
});

describe("resolveDevAuthHeaders", () => {
  it("adds headers only in DEV when configured", () => {
    expect(
      resolveDevAuthHeaders({
        DEV: true,
        VITE_DQA_DEV_ACTOR: "query-operator",
        VITE_DQA_DEV_ROLES: "query_operator",
      }),
    ).toEqual({
      "X-DQA-Dev-Actor": "query-operator",
      "X-DQA-Dev-Roles": "query_operator",
    });
    expect(
      resolveDevAuthHeaders({
        DEV: false,
        VITE_DQA_DEV_ACTOR: "query-operator",
        VITE_DQA_DEV_ROLES: "query_operator",
      }),
    ).toEqual({});
    expect(resolveDevAuthHeaders({ DEV: true })).toEqual({});
  });
});

describe("QueryAssistant", () => {
  it("covers recommendation, form, blockers, preview gate, and execute path", async () => {
    const user = userEvent.setup();
    const consoleSpy = vi.spyOn(console, "log").mockImplementation(() => undefined);
    let previewCalls = 0;
    let executeCalls = 0;
    let lastPreviewBody: Record<string, unknown> | null = null;
    let lastExecuteBody: Record<string, unknown> | null = null;

    const handlers = assistantHandlers({ preview: availablePreview });
    handlers.unshift((url, init) => {
      if (url.pathname.endsWith("/query-executions/preview") && init?.method === "POST") {
        previewCalls += 1;
        lastPreviewBody = JSON.parse(String(init.body)) as Record<string, unknown>;
        return jsonResponse(availablePreview);
      }
      if (url.pathname.endsWith("/query-executions/execute") && init?.method === "POST") {
        executeCalls += 1;
        lastExecuteBody = JSON.parse(String(init.body)) as Record<string, unknown>;
        return jsonResponse(executeResponse);
      }
      return null;
    });
    const restore = installFetchMock(handlers);
    render(<QueryAssistant />);

    await recommendHappyPath(user);

    expect(screen.getByText(/템플릿 라우팅 신뢰도/)).toBeInTheDocument();
    expect(screen.queryByText(/clinical|의료 신뢰/i)).not.toBeInTheDocument();

    const wardInput = screen.getByLabelText(/병동 코드/);
    expect(wardInput).toHaveAttribute("type", "password");
    expect(screen.getByLabelText(/시작일/)).toHaveValue("2024-01-01");
    expect(screen.getByLabelText(/^활성/)).toHaveValue("true");
    // Enum options use stable indexes so exact JSON types are preserved.
    expect(screen.getByLabelText(/^종류/)).toHaveValue("0");
    expect(screen.getByLabelText(/^종류/)).toHaveDisplayValue("A");

    expect(screen.getByTestId("env-blockers")).toHaveTextContent(
      "DEMIS 실행 어댑터가 아직 구성되지 않았습니다.",
    );
    await user.selectOptions(screen.getByLabelText("실행 환경"), "qa");
    expect(screen.getByTestId("env-blockers")).toHaveTextContent(
      "실행 환경 설정이 완료되지 않았습니다.",
    );
    await user.selectOptions(screen.getByLabelText("실행 환경"), "dev");

    await user.type(screen.getByLabelText(/병동 코드/), "A01");
    expect(previewCalls).toBe(0);
    expect(executeCalls).toBe(0);

    await user.click(screen.getByRole("button", { name: "조회 미리보기" }));
    expect(await screen.findByTestId("preview-summary")).toBeInTheDocument();
    expect(previewCalls).toBe(1);
    expect(executeCalls).toBe(0);
    expect(screen.getByTestId("preview-summary")).toHaveTextContent("입력됨");
    expect(screen.getByTestId("preview-summary")).not.toHaveTextContent("A01");

    expect(lastPreviewBody).toMatchObject({
      source_name: activeSource.source_name,
      environment: "dev",
      template_id: 10,
      version_id: 20,
    });
    expect(lastPreviewBody).not.toHaveProperty("sql_text");
    expect(lastPreviewBody).not.toHaveProperty("connection_profile_id");
    expect(lastPreviewBody).not.toHaveProperty("row_limit");
    expect(lastPreviewBody).not.toHaveProperty("timeout_seconds");
    expect(lastPreviewBody).not.toHaveProperty("catalog_revision_id");

    const executeButton = screen.getByRole("button", { name: "조회 실행" });
    expect(executeButton).toBeEnabled();
    await user.click(executeButton);
    expect(executeCalls).toBe(1);
    expect(await screen.findByTestId("audit-id")).toHaveTextContent("audit-123");
    expect(screen.getByText("감사 추적 ID")).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "ward_cd" })).toBeInTheDocument();
    expect(screen.getByText("ok")).toBeInTheDocument();
    expect(screen.getByText("-")).toBeInTheDocument();

    expect(lastExecuteBody).toMatchObject({
      source_name: activeSource.source_name,
      environment: "dev",
      template_id: 10,
      version_id: 20,
    });
    expect(lastExecuteBody).not.toHaveProperty("sql_text");
    expect(lastExecuteBody).not.toHaveProperty("connection_profile_id");

    const logged = consoleSpy.mock.calls.map((call) => call.map(String).join(" ")).join("\n");
    expect(logged).not.toContain("A01");
    expect(logged).not.toContain("ok");
    consoleSpy.mockRestore();
    restore();
  });

  it("disables execute when DEMIS adapter is unavailable", async () => {
    const user = userEvent.setup();
    let executeCalls = 0;
    const handlers = assistantHandlers({ preview: unavailablePreview, execute: null });
    handlers.unshift((url, init) => {
      if (url.pathname.endsWith("/query-executions/execute") && init?.method === "POST") {
        executeCalls += 1;
        return jsonResponse(
          { detail: { code: "DEMIS_ADAPTER_UNAVAILABLE", message: "blocked" } },
          503,
        );
      }
      return null;
    });
    const restore = installFetchMock(handlers);
    render(<QueryAssistant />);
    await recommendHappyPath(user);
    await user.type(screen.getByLabelText(/병동 코드/), "A01");
    await user.click(screen.getByRole("button", { name: "조회 미리보기" }));
    expect(await screen.findByTestId("preview-summary")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "조회 실행" })).toBeDisabled();
    expect(executeCalls).toBe(0);
    restore();
  });

  it("clarification prevents form progression", async () => {
    const user = userEvent.setup();
    const restore = installFetchMock(
      assistantHandlers({ recommendation: clarificationRecommendation }),
    );
    render(<QueryAssistant />);
    await screen.findByLabelText("Active Catalog source");
    await user.selectOptions(
      screen.getByLabelText("Active Catalog source"),
      activeSource.source_name,
    );
    await user.type(screen.getByLabelText("자연어 조회 요청"), "뭔가 조회");
    await user.click(screen.getByRole("button", { name: "조회 방법 찾기" }));
    expect(await screen.findByText("어느 병동을 조회할까요?")).toBeInTheDocument();
    expect(screen.queryByLabelText(/병동 코드/)).not.toBeInTheDocument();
    restore();
  });

  it("selecting an alternative candidate loads its form metadata", async () => {
    const user = userEvent.setup();
    const restore = installFetchMock(assistantHandlers());
    render(<QueryAssistant />);
    await recommendHappyPath(user);
    await user.click(screen.getByRole("button", { name: /병동 대안/ }));
    expect(await screen.findByLabelText(/병동 코드/)).toHaveValue("Z99");
    expect(screen.getByRole("heading", { name: "조건 및 실행 환경" }).closest("section")).toHaveTextContent(
      "병동 대안",
    );
    restore();
  });

  it("parameter and environment changes invalidate preview", async () => {
    const user = userEvent.setup();
    const restore = installFetchMock(assistantHandlers({ preview: availablePreview }));
    render(<QueryAssistant />);
    await recommendHappyPath(user);
    await user.type(screen.getByLabelText(/병동 코드/), "A01");
    await user.click(screen.getByRole("button", { name: "조회 미리보기" }));
    expect(await screen.findByTestId("preview-summary")).toBeInTheDocument();
    await user.clear(screen.getByLabelText(/시작일/));
    await user.type(screen.getByLabelText(/시작일/), "2024-02-02");
    await waitFor(() => {
      expect(screen.queryByTestId("preview-summary")).not.toBeInTheDocument();
    });
    expect(screen.getByRole("button", { name: "조회 실행" })).toBeDisabled();

    await user.click(screen.getByRole("button", { name: "조회 미리보기" }));
    expect(await screen.findByTestId("preview-summary")).toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText("실행 환경"), "qa");
    await waitFor(() => {
      expect(screen.queryByTestId("preview-summary")).not.toBeInTheDocument();
    });
    restore();
  });

  it("AI extraction fills parameters and EGRESS_NOT_ALLOWED falls back", async () => {
    const user = userEvent.setup();
    const restore = installFetchMock(assistantHandlers());
    render(<QueryAssistant />);
    await recommendHappyPath(user);
    await user.click(screen.getByRole("button", { name: "AI로 조건 채우기" }));
    await waitFor(() => {
      expect(screen.getByLabelText(/병동 코드/)).toHaveValue("A01");
    });
    restore();
    cleanup();

    const restore2 = installFetchMock(
      assistantHandlers({
        extractStatus: 403,
        extractBody: {
          detail: {
            code: "PARAMETER_EXTRACTION_EGRESS_NOT_ALLOWED",
            message: "egress blocked",
          },
        },
      }),
    );
    render(<QueryAssistant />);
    await recommendHappyPath(user);
    await user.click(screen.getByRole("button", { name: "AI로 조건 채우기" }));
    expect(
      await screen.findByText(
        "현재 정책상 자연어 조건 자동 추출이 비활성화되어 있습니다. 직접 입력해주세요.",
      ),
    ).toBeInTheDocument();
    expect(screen.getByLabelText(/병동 코드/)).toBeEnabled();
    restore2();
  });

  it("source change clears recommendation and form state", async () => {
    const user = userEvent.setup();
    const restore = installFetchMock(
      assistantHandlers({ actives: [activeSource, secondSource] }),
    );
    render(<QueryAssistant />);
    await screen.findByLabelText("Active Catalog source");
    await user.selectOptions(
      screen.getByLabelText("Active Catalog source"),
      activeSource.source_name,
    );
    await user.type(screen.getByLabelText("자연어 조회 요청"), "병동");
    await user.click(screen.getByRole("button", { name: "조회 방법 찾기" }));
    expect(await screen.findByTestId("recommended-template")).toBeInTheDocument();
    await user.selectOptions(
      screen.getByLabelText("Active Catalog source"),
      secondSource.source_name,
    );
    expect(screen.queryByTestId("recommended-template")).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/병동 코드/)).not.toBeInTheDocument();
    restore();
  });

  it("request text edit invalidates recommendation/form/preview/result but keeps text", async () => {
    const user = userEvent.setup();
    const restore = installFetchMock(assistantHandlers({ preview: availablePreview }));
    render(<QueryAssistant />);
    await recommendHappyPath(user);
    expect(screen.getByTestId("recommended-template")).toBeInTheDocument();
    const requestBox = screen.getByLabelText("자연어 조회 요청");
    await user.type(requestBox, " (수정)");
    expect(requestBox).toHaveValue("병동 조회해줘 (수정)");
    expect(screen.queryByTestId("recommended-template")).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/병동 코드/)).not.toBeInTheDocument();
    expect(screen.queryByTestId("preview-summary")).not.toBeInTheDocument();
    expect(screen.queryByTestId("audit-id")).not.toBeInTheDocument();
    restore();
  });

  it("required boolean without default starts unselected and preserves false", async () => {
    const user = userEvent.setup();
    const formWithoutBoolDefault: ExecutionFormResponse = {
      ...formResponse,
      parameters: formResponse.parameters.map((item) =>
        item.name === "active" ? { ...item, default: null } : item,
      ),
    };
    const restore = installFetchMock(assistantHandlers({ form: formWithoutBoolDefault }));
    render(<QueryAssistant />);
    await recommendHappyPath(user);
    const active = screen.getByLabelText(/^활성/);
    expect(active).toHaveValue("");
    await user.selectOptions(active, "false");
    expect(active).toHaveValue("false");
    restore();
  });

  it("typed enum selection submits exact JSON types in preview payload", async () => {
    const user = userEvent.setup();
    const previewCapture: { body: Record<string, unknown> | null } = { body: null };
    const typedForm: ExecutionFormResponse = {
      ...formResponse,
      parameters: [
        {
          name: "code",
          label: "코드",
          description: null,
          type: "enum",
          required: true,
          default: null,
          allowed_values: [1, "1"],
          pattern: null,
          min: null,
          max: null,
          min_items: null,
          max_items: null,
          sensitive: false,
        },
      ],
      environments: [
        {
          environment: "dev",
          execution_available: false,
          execution_blockers: ["DEMIS_ADAPTER_UNAVAILABLE"],
        },
      ],
    };
    const handlers = assistantHandlers({ form: typedForm, preview: unavailablePreview });
    handlers.unshift((url, init) => {
      if (url.pathname.endsWith("/query-executions/preview") && init?.method === "POST") {
        previewCapture.body = JSON.parse(String(init.body)) as Record<string, unknown>;
        return jsonResponse({
          ...unavailablePreview,
          resolved_parameters: previewCapture.body.parameters as Record<string, unknown>,
          sensitive_parameter_names: [],
        });
      }
      return null;
    });
    const restore = installFetchMock(handlers);
    render(<QueryAssistant />);
    await screen.findByLabelText("Active Catalog source");
    await user.selectOptions(
      screen.getByLabelText("Active Catalog source"),
      activeSource.source_name,
    );
    await user.type(screen.getByLabelText("자연어 조회 요청"), "병동 조회해줘");
    await user.click(screen.getByRole("button", { name: "조회 방법 찾기" }));
    expect(await screen.findByTestId("recommended-template")).toBeInTheDocument();
    const codeSelect = await screen.findByLabelText(/^코드/);

    // Option labels both display as "1"; drive the stable index value directly.
    fireEvent.change(codeSelect, { target: { value: "0" } });
    await user.click(screen.getByRole("button", { name: "조회 미리보기" }));
    await screen.findByTestId("preview-summary");
    expect((previewCapture.body?.parameters as Record<string, unknown>).code).toBe(1);
    expect(typeof (previewCapture.body?.parameters as Record<string, unknown>).code).toBe(
      "number",
    );

    fireEvent.change(codeSelect, { target: { value: "1" } });
    await user.click(screen.getByRole("button", { name: "조회 미리보기" }));
    await screen.findByTestId("preview-summary");
    expect((previewCapture.body?.parameters as Record<string, unknown>).code).toBe("1");
    expect(typeof (previewCapture.body?.parameters as Record<string, unknown>).code).toBe(
      "string",
    );
    restore();
  });

  it("ignores stale execute response after source change", async () => {
    const user = userEvent.setup();
    const pending = {
      resolve: null as null | ((value: Response) => void),
    };
    const pendingExecute = new Promise<Response>((resolve) => {
      pending.resolve = resolve;
    });
    const handlers = assistantHandlers({
      actives: [activeSource, secondSource],
      preview: availablePreview,
    });
    handlers.unshift((url, init) => {
      if (url.pathname.endsWith("/query-executions/preview") && init?.method === "POST") {
        return jsonResponse(availablePreview);
      }
      if (url.pathname.endsWith("/query-executions/execute") && init?.method === "POST") {
        return pendingExecute;
      }
      return null;
    });
    const restore = installFetchMock(handlers);
    render(<QueryAssistant />);
    await recommendHappyPath(user);
    await user.type(screen.getByLabelText(/병동 코드/), "A01");
    await user.click(screen.getByRole("button", { name: "조회 미리보기" }));
    await screen.findByTestId("preview-summary");
    await user.click(screen.getByRole("button", { name: "조회 실행" }));
    await user.selectOptions(
      screen.getByLabelText("Active Catalog source"),
      secondSource.source_name,
    );
    expect(screen.queryByTestId("recommended-template")).not.toBeInTheDocument();
    pending.resolve?.(jsonResponse(executeResponse));
    await waitFor(() => {
      expect(screen.queryByTestId("audit-id")).not.toBeInTheDocument();
      expect(screen.queryByText("ok")).not.toBeInTheDocument();
    });
    restore();
  });
});

describe("egress helper", () => {
  it("detects PARAMETER_EXTRACTION_EGRESS_NOT_ALLOWED", () => {
    expect(
      isEgressNotAllowed(
        new CatalogApiError(403, "blocked", "PARAMETER_EXTRACTION_EGRESS_NOT_ALLOWED"),
      ),
    ).toBe(true);
    expect(isEgressNotAllowed(new CatalogApiError(403, "denied", "AUTHORIZATION_DENIED"))).toBe(
      false,
    );
  });
});
