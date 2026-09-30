import { useCallback, useEffect, useMemo, useState } from "react";
import { listActiveCatalogs } from "../api/catalog";
import {
  executeQuery,
  extractParameters,
  getExecutionForm,
  previewExecution,
  recommendTemplates,
} from "../api/queryAssistant";
import type { CatalogActiveSummary } from "../types/catalog";
import type {
  ExecutionFormResponse,
  ExecutionPreviewResponse,
  QueryExecutionResponse,
  RecommendedTemplate,
  TemplateRecommendationResponse,
} from "../types/queryAssistant";
import {
  buildParameterPayload,
  defaultsFromFormParameters,
  formatAssistantError,
  isEgressNotAllowed,
  stableParametersKey,
} from "../utils/queryAssistant";

const MAX_REQUEST_TEXT = 2000;

type LoadState = "idle" | "loading" | "error";

export interface AssistantErrorState {
  code: string | null;
  message: string;
}

export function useQueryAssistant() {
  const [sources, setSources] = useState<CatalogActiveSummary[]>([]);
  const [sourcesState, setSourcesState] = useState<LoadState>("idle");
  const [sourcesError, setSourcesError] = useState<AssistantErrorState | null>(null);
  const [selectedSource, setSelectedSource] = useState<string>("");

  const [requestText, setRequestText] = useState("");
  const [recommendation, setRecommendation] =
    useState<TemplateRecommendationResponse | null>(null);
  const [selectedCandidate, setSelectedCandidate] = useState<RecommendedTemplate | null>(
    null,
  );
  const [recommendState, setRecommendState] = useState<LoadState>("idle");
  const [recommendError, setRecommendError] = useState<AssistantErrorState | null>(null);

  const [form, setForm] = useState<ExecutionFormResponse | null>(null);
  const [formState, setFormState] = useState<LoadState>("idle");
  const [formError, setFormError] = useState<AssistantErrorState | null>(null);

  const [parameterValues, setParameterValues] = useState<Record<string, unknown>>({});
  const [dirtyParams, setDirtyParams] = useState<Set<string>>(() => new Set());
  const [environment, setEnvironment] = useState<string>("");

  const [extractState, setExtractState] = useState<LoadState>("idle");
  const [extractError, setExtractError] = useState<AssistantErrorState | null>(null);
  const [extractInfo, setExtractInfo] = useState<string | null>(null);
  const [extractClarification, setExtractClarification] = useState<string | null>(null);

  const [preview, setPreview] = useState<ExecutionPreviewResponse | null>(null);
  const [previewSnapshot, setPreviewSnapshot] = useState<string | null>(null);
  const [previewState, setPreviewState] = useState<LoadState>("idle");
  const [previewError, setPreviewError] = useState<AssistantErrorState | null>(null);

  const [result, setResult] = useState<QueryExecutionResponse | null>(null);
  const [executeState, setExecuteState] = useState<LoadState>("idle");
  const [executeError, setExecuteError] = useState<AssistantErrorState | null>(null);

  const clearDownstreamFromSource = useCallback(() => {
    setRecommendation(null);
    setSelectedCandidate(null);
    setRecommendState("idle");
    setRecommendError(null);
    setForm(null);
    setFormState("idle");
    setFormError(null);
    setParameterValues({});
    setDirtyParams(new Set());
    setEnvironment("");
    setExtractState("idle");
    setExtractError(null);
    setExtractInfo(null);
    setExtractClarification(null);
    setPreview(null);
    setPreviewSnapshot(null);
    setPreviewState("idle");
    setPreviewError(null);
    setResult(null);
    setExecuteState("idle");
    setExecuteError(null);
  }, []);

  const invalidatePreviewAndResult = useCallback(() => {
    setPreview(null);
    setPreviewSnapshot(null);
    setPreviewState("idle");
    setPreviewError(null);
    setResult(null);
    setExecuteState("idle");
    setExecuteError(null);
  }, []);

  const loadSources = useCallback(async () => {
    setSourcesState("loading");
    setSourcesError(null);
    try {
      const items = await listActiveCatalogs();
      setSources(items);
      setSourcesState("idle");
      if (items.length === 1) {
        setSelectedSource(items[0].source_name);
      }
    } catch (error) {
      setSources([]);
      setSourcesState("error");
      setSourcesError(formatAssistantError(error));
    }
  }, []);

  useEffect(() => {
    void loadSources();
  }, [loadSources]);

  const selectSource = useCallback(
    (sourceName: string) => {
      setSelectedSource(sourceName);
      clearDownstreamFromSource();
    },
    [clearDownstreamFromSource],
  );

  const loadFormForCandidate = useCallback(
    async (candidate: RecommendedTemplate, sourceName: string) => {
      setSelectedCandidate(candidate);
      setForm(null);
      setFormState("loading");
      setFormError(null);
      setParameterValues({});
      setDirtyParams(new Set());
      setEnvironment("");
      setExtractState("idle");
      setExtractError(null);
      setExtractInfo(null);
      setExtractClarification(null);
      invalidatePreviewAndResult();
      try {
        const metadata = await getExecutionForm({
          source_name: sourceName,
          template_id: candidate.template_id,
          version_id: candidate.version_id,
        });
        setForm(metadata);
        setParameterValues(defaultsFromFormParameters(metadata.parameters));
        const available = metadata.environments.find((item) => item.execution_available);
        const preferred = available ?? metadata.environments[0];
        setEnvironment(preferred?.environment ?? "");
        setFormState("idle");
      } catch (error) {
        setFormState("error");
        setFormError(formatAssistantError(error));
      }
    },
    [invalidatePreviewAndResult],
  );

  const submitRecommendation = useCallback(async () => {
    if (!selectedSource || !requestText.trim() || recommendState === "loading") {
      return;
    }
    setRecommendState("loading");
    setRecommendError(null);
    setRecommendation(null);
    setSelectedCandidate(null);
    setForm(null);
    setFormState("idle");
    setFormError(null);
    setParameterValues({});
    setDirtyParams(new Set());
    setEnvironment("");
    setExtractInfo(null);
    setExtractClarification(null);
    invalidatePreviewAndResult();
    try {
      const response = await recommendTemplates({
        source_name: selectedSource,
        request_text: requestText.trim(),
      });
      setRecommendation(response);
      setRecommendState("idle");
      if (!response.needs_clarification && response.recommended_template) {
        await loadFormForCandidate(response.recommended_template, selectedSource);
      }
    } catch (error) {
      setRecommendState("error");
      setRecommendError(formatAssistantError(error));
    }
  }, [
    invalidatePreviewAndResult,
    loadFormForCandidate,
    recommendState,
    requestText,
    selectedSource,
  ]);

  const selectCandidate = useCallback(
    async (candidate: RecommendedTemplate) => {
      if (!selectedSource || formState === "loading") {
        return;
      }
      await loadFormForCandidate(candidate, selectedSource);
    },
    [formState, loadFormForCandidate, selectedSource],
  );

  const setParameterValue = useCallback(
    (name: string, value: unknown) => {
      setParameterValues((prev) => ({ ...prev, [name]: value }));
      setDirtyParams((prev) => {
        const next = new Set(prev);
        next.add(name);
        return next;
      });
      invalidatePreviewAndResult();
    },
    [invalidatePreviewAndResult],
  );

  const setSelectedEnvironment = useCallback(
    (value: string) => {
      setEnvironment(value);
      invalidatePreviewAndResult();
    },
    [invalidatePreviewAndResult],
  );

  const runExtraction = useCallback(async () => {
    if (
      !selectedSource ||
      !selectedCandidate ||
      !requestText.trim() ||
      extractState === "loading"
    ) {
      return;
    }
    setExtractState("loading");
    setExtractError(null);
    setExtractInfo(null);
    setExtractClarification(null);
    try {
      const response = await extractParameters({
        source_name: selectedSource,
        template_id: selectedCandidate.template_id,
        version_id: selectedCandidate.version_id,
        request_text: requestText.trim(),
      });
      setParameterValues((prev) => {
        const next = { ...prev };
        for (const [name, value] of Object.entries(response.resolved_parameters)) {
          if (dirtyParams.has(name)) {
            continue;
          }
          next[name] = value;
        }
        return next;
      });
      invalidatePreviewAndResult();
      if (response.needs_clarification) {
        setExtractClarification(
          response.clarification_question ??
            "일부 조건을 확인한 뒤 직접 입력해주세요.",
        );
      }
      setExtractState("idle");
    } catch (error) {
      if (isEgressNotAllowed(error)) {
        setExtractState("idle");
        setExtractInfo(
          "현재 정책상 자연어 조건 자동 추출이 비활성화되어 있습니다. 직접 입력해주세요.",
        );
        return;
      }
      setExtractState("error");
      setExtractError(formatAssistantError(error));
    }
  }, [
    dirtyParams,
    extractState,
    invalidatePreviewAndResult,
    requestText,
    selectedCandidate,
    selectedSource,
  ]);

  const currentParameterPayload = useMemo(() => {
    if (!form) {
      return {};
    }
    return buildParameterPayload(form.parameters, parameterValues);
  }, [form, parameterValues]);

  const currentPreviewKey = useMemo(() => {
    if (!selectedCandidate || !environment) {
      return null;
    }
    return [
      selectedCandidate.template_id,
      selectedCandidate.version_id,
      environment,
      stableParametersKey(currentParameterPayload),
    ].join("|");
  }, [currentParameterPayload, environment, selectedCandidate]);

  const previewMatchesCurrent =
    preview !== null && previewSnapshot !== null && previewSnapshot === currentPreviewKey;

  const runPreview = useCallback(async () => {
    if (
      !selectedSource ||
      !selectedCandidate ||
      !environment ||
      previewState === "loading"
    ) {
      return;
    }
    setPreviewState("loading");
    setPreviewError(null);
    setResult(null);
    setExecuteError(null);
    try {
      const parameters = buildParameterPayload(
        form?.parameters ?? [],
        parameterValues,
      );
      const response = await previewExecution({
        source_name: selectedSource,
        environment,
        template_id: selectedCandidate.template_id,
        version_id: selectedCandidate.version_id,
        parameters,
      });
      setPreview(response);
      setPreviewSnapshot(
        [
          selectedCandidate.template_id,
          selectedCandidate.version_id,
          environment,
          stableParametersKey(parameters),
        ].join("|"),
      );
      setPreviewState("idle");
    } catch (error) {
      setPreview(null);
      setPreviewSnapshot(null);
      setPreviewState("error");
      setPreviewError(formatAssistantError(error));
    }
  }, [
    environment,
    form?.parameters,
    parameterValues,
    previewState,
    selectedCandidate,
    selectedSource,
  ]);

  const canExecute =
    previewMatchesCurrent &&
    preview !== null &&
    preview.execution_available === true &&
    preview.execution_blockers.length === 0 &&
    executeState !== "loading";

  const runExecute = useCallback(async () => {
    if (!canExecute || !selectedSource || !selectedCandidate || !environment || !preview) {
      return;
    }
    setExecuteState("loading");
    setExecuteError(null);
    try {
      const parameters = buildParameterPayload(
        form?.parameters ?? [],
        parameterValues,
      );
      const response = await executeQuery({
        source_name: selectedSource,
        environment,
        template_id: selectedCandidate.template_id,
        version_id: selectedCandidate.version_id,
        parameters,
      });
      setResult(response);
      setExecuteState("idle");
    } catch (error) {
      setResult(null);
      setExecuteState("error");
      setExecuteError(formatAssistantError(error));
    }
  }, [
    canExecute,
    environment,
    form?.parameters,
    parameterValues,
    preview,
    selectedCandidate,
    selectedSource,
  ]);

  return {
    maxRequestText: MAX_REQUEST_TEXT,
    sources,
    sourcesState,
    sourcesError,
    selectedSource,
    selectSource,
    reloadSources: loadSources,
    requestText,
    setRequestText,
    recommendation,
    selectedCandidate,
    recommendState,
    recommendError,
    submitRecommendation,
    selectCandidate,
    form,
    formState,
    formError,
    parameterValues,
    setParameterValue,
    environment,
    setSelectedEnvironment,
    extractState,
    extractError,
    extractInfo,
    extractClarification,
    runExtraction,
    preview,
    previewState,
    previewError,
    previewMatchesCurrent,
    runPreview,
    canExecute,
    result,
    executeState,
    executeError,
    runExecute,
  };
}
