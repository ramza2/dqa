import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { getAuditEventsById } from "../api/auditEvents";
import { listActiveCatalogs } from "../api/catalog";
import {
  executeQuery,
  extractParameters,
  getExecutionForm,
  listManualTemplates,
  previewExecution,
  recommendTemplates,
} from "../api/queryAssistant";
import type { QueryAuditEventBundleResponse } from "../types/auditEvents";
import type { CatalogActiveSummary } from "../types/catalog";
import type {
  ExecutionFormResponse,
  ManualTemplateListResponse,
  ExecutionPreviewResponse,
  QueryExecutionResponse,
  RecommendedTemplate,
  TemplateRecommendationResponse,
} from "../types/queryAssistant";
import {
  buildParameterPayload,
  defaultsFromFormParameters,
  formatAssistantError,
  isAuditReadDenied,
  isEgressNotAllowed,
  stableParametersKey,
  validateParameterValues,
} from "../utils/queryAssistant";

const MAX_REQUEST_TEXT = 2000;

type LoadState = "idle" | "loading" | "error";

export interface AssistantErrorState {
  code: string | null;
  message: string;
}

export function useQueryAssistant() {
  const workflowGeneration = useRef(0);
  // Paging is tied to the loaded catalog, not to preview/parameter edits.
  const manualListEpoch = useRef(0);

  const [sources, setSources] = useState<CatalogActiveSummary[]>([]);
  const [sourcesState, setSourcesState] = useState<LoadState>("idle");
  const [sourcesError, setSourcesError] = useState<AssistantErrorState | null>(null);
  const [selectedSource, setSelectedSource] = useState<string>("");

  const [manualCatalog, setManualCatalog] = useState<ManualTemplateListResponse | null>(null);
  const [manualState, setManualState] = useState<LoadState>("idle");
  const [manualError, setManualError] = useState<AssistantErrorState | null>(null);
  const [manualMoreState, setManualMoreState] = useState<LoadState>("idle");
  const [manualMoreError, setManualMoreError] = useState<AssistantErrorState | null>(null);

  const [requestText, setRequestTextState] = useState("");
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

  const [auditBundle, setAuditBundle] = useState<QueryAuditEventBundleResponse | null>(null);
  const [auditState, setAuditState] = useState<LoadState>("idle");
  const [auditError, setAuditError] = useState<AssistantErrorState | null>(null);
  const [auditForbidden, setAuditForbidden] = useState(false);
  const auditRequestRef = useRef(0);
  const resultAuditIdRef = useRef<string | null>(null);

  const bumpGeneration = useCallback(() => {
    workflowGeneration.current += 1;
    return workflowGeneration.current;
  }, []);

  const isCurrentGeneration = useCallback((generation: number) => {
    return generation === workflowGeneration.current;
  }, []);

  const clearAuditLifecycle = useCallback(() => {
    auditRequestRef.current += 1;
    setAuditBundle(null);
    setAuditState("idle");
    setAuditError(null);
    setAuditForbidden(false);
  }, []);

  const clearDownstreamWorkflow = useCallback(() => {
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
    resultAuditIdRef.current = null;
    setExecuteState("idle");
    setExecuteError(null);
    clearAuditLifecycle();
  }, [clearAuditLifecycle]);

  const clearDownstreamFromSource = useCallback(() => {
    bumpGeneration();
    clearDownstreamWorkflow();
  }, [bumpGeneration, clearDownstreamWorkflow]);

  const invalidatePreviewAndResult = useCallback(() => {
    setPreview(null);
    setPreviewSnapshot(null);
    setPreviewState("idle");
    setPreviewError(null);
    setResult(null);
    resultAuditIdRef.current = null;
    setExecuteState("idle");
    setExecuteError(null);
    clearAuditLifecycle();
  }, [clearAuditLifecycle]);

  const setRequestText = useCallback(
    (text: string) => {
      setRequestTextState(text);
      const hasWorkflow =
        recommendation !== null ||
        selectedCandidate !== null ||
        form !== null ||
        preview !== null ||
        result !== null ||
        recommendState === "loading" ||
        formState === "loading" ||
        previewState === "loading" ||
        executeState === "loading" ||
        extractState === "loading";
      if (hasWorkflow) {
        bumpGeneration();
        clearDownstreamWorkflow();
      }
    },
    [
      bumpGeneration,
      clearDownstreamWorkflow,
      executeState,
      extractState,
      form,
      formState,
      preview,
      previewState,
      recommendState,
      recommendation,
      result,
      selectedCandidate,
    ],
  );

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
      manualListEpoch.current += 1;
      setSelectedSource(sourceName);
      setManualCatalog(null);
      setManualState("idle");
      setManualError(null);
      setManualMoreState("idle");
      setManualMoreError(null);
      clearDownstreamFromSource();
    },
    [clearDownstreamFromSource],
  );

  const loadManualTemplates = useCallback(async () => {
    if (!selectedSource || manualState === "loading") {
      return;
    }
    manualListEpoch.current += 1;
    // A manual selection starts a new workflow, invalidating any LLM/preview
    // response that was initiated before this action.
    const generation = bumpGeneration();
    clearDownstreamWorkflow();
    setManualCatalog(null);
    setManualState("loading");
    setManualError(null);
    setManualMoreState("idle");
    setManualMoreError(null);
    try {
      const data = await listManualTemplates(selectedSource);
      if (!isCurrentGeneration(generation)) {
        return;
      }
      const active = sources.find((item) => item.source_name === selectedSource);
      if (
        data.source_name !== selectedSource ||
        !active ||
        data.catalog_revision_id !== active.revision_id ||
        data.schema_fingerprint !== active.schema_fingerprint
      ) {
        // This is an expected catalog-consistency rejection, not a network
        // exception. Show an explicit, safe operator-facing error instead of
        // passing a generic Error through formatAssistantError().
        setManualState("error");
        setManualError({
          code: "CATALOG_MISMATCH",
          message: "Catalog가 변경되었습니다. 소스를 다시 선택하고 목록을 갱신하세요.",
        });
        return;
      }
      setManualCatalog(data);
      setManualState("idle");
    } catch (error) {
      if (!isCurrentGeneration(generation)) {
        return;
      }
      setManualState("error");
      setManualError(formatAssistantError(error));
    }
  }, [
    bumpGeneration, clearDownstreamWorkflow, isCurrentGeneration,
    manualState, selectedSource, sources,
  ]);

  const loadMoreManualTemplates = useCallback(async () => {
    if (!selectedSource || !manualCatalog || manualState === "loading" ||
        manualMoreState === "loading" || manualCatalog.items.length >= manualCatalog.total) {
      return;
    }
    const listEpoch = manualListEpoch.current;
    const offset = manualCatalog.items.length;
    setManualMoreState("loading");
    setManualMoreError(null);
    try {
      const page = await listManualTemplates(selectedSource, offset);
      if (listEpoch !== manualListEpoch.current) return;
      if (page.source_name !== manualCatalog.source_name ||
          page.catalog_revision_id !== manualCatalog.catalog_revision_id ||
          page.schema_fingerprint !== manualCatalog.schema_fingerprint ||
          page.offset !== offset || page.total !== manualCatalog.total ||
          page.items.length === 0) {
        setManualMoreState("error");
        setManualMoreError({
          code: "CATALOG_MISMATCH",
          message: "목록 또는 Catalog가 변경되었습니다. 처음부터 다시 불러오세요.",
        });
        return;
      }
      setManualCatalog((previous) => previous ? {
        ...previous,
        items: [...previous.items, ...page.items],
      } : null);
      setManualMoreState("idle");
    } catch (error) {
      if (listEpoch !== manualListEpoch.current) return;
      setManualMoreState("error");
      setManualMoreError(formatAssistantError(error));
    }
  }, [manualCatalog, manualMoreState, manualState, selectedSource]);

  const loadFormForCandidate = useCallback(
    async (candidate: RecommendedTemplate, sourceName: string, generation?: number) => {
      const opGeneration = generation ?? bumpGeneration();
      setSelectedCandidate(candidate);
      setForm(null);
      setFormState("loading");
      setFormError(null);
      setManualMoreState("idle");
      setManualMoreError(null);
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
        if (!isCurrentGeneration(opGeneration)) {
          return;
        }
        const active = sources.find((item) => item.source_name === sourceName);
        if (!active ||
            metadata.source_name !== sourceName ||
            metadata.catalog_revision_id !== active.revision_id ||
            metadata.catalog_fingerprint !== active.schema_fingerprint ||
            metadata.template.template_id !== candidate.template_id ||
            metadata.template.version_id !== candidate.version_id) {
          setFormState("error");
          setFormError({
            code: "CATALOG_MISMATCH",
            message: "Catalog 또는 템플릿 버전이 변경되었습니다. 목록을 갱신하세요.",
          });
          return;
        }
        setForm(metadata);
        setParameterValues(defaultsFromFormParameters(metadata.parameters));
        const available = metadata.environments.find((item) => item.execution_available);
        const preferred = available ?? metadata.environments[0];
        setEnvironment(preferred?.environment ?? "");
        setFormState("idle");
      } catch (error) {
        if (!isCurrentGeneration(opGeneration)) {
          return;
        }
        setFormState("error");
        setFormError(formatAssistantError(error));
      }
    },
    [bumpGeneration, invalidatePreviewAndResult, isCurrentGeneration, sources],
  );

  const submitRecommendation = useCallback(async () => {
    if (!selectedSource || !requestText.trim() || recommendState === "loading") {
      return;
    }
    const opGeneration = bumpGeneration();
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
      if (!isCurrentGeneration(opGeneration)) {
        return;
      }
      setRecommendation(response);
      setRecommendState("idle");
      if (!response.needs_clarification && response.recommended_template) {
        await loadFormForCandidate(
          response.recommended_template,
          selectedSource,
          opGeneration,
        );
      }
    } catch (error) {
      if (!isCurrentGeneration(opGeneration)) {
        return;
      }
      setRecommendState("error");
      setRecommendError(formatAssistantError(error));
    }
  }, [
    bumpGeneration,
    invalidatePreviewAndResult,
    isCurrentGeneration,
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

  const selectManualTemplate = useCallback(async (candidate: RecommendedTemplate) => {
    if (!selectedSource || !manualCatalog || formState === "loading" ||
        !manualCatalog.items.some((item) =>
          item.template_id === candidate.template_id && item.version_id === candidate.version_id
        )) {
      return;
    }
    setRecommendation(null);
    setRecommendState("idle");
    setRecommendError(null);
    setRequestTextState("");
    await loadFormForCandidate(candidate, selectedSource);
  }, [formState, loadFormForCandidate, manualCatalog, selectedSource]);

  const setParameterValue = useCallback(
    (name: string, value: unknown) => {
      // Parameter edits supersede extraction/preview/execute operations that
      // were started with the previous parameter state.
      bumpGeneration();
      setParameterValues((prev) => {
        const next = { ...prev };
        if (value === undefined) {
          delete next[name];
        } else {
          next[name] = value;
        }
        return next;
      });
      setDirtyParams((prev) => {
        const next = new Set(prev);
        next.add(name);
        return next;
      });
      invalidatePreviewAndResult();
    },
    [bumpGeneration, invalidatePreviewAndResult],
  );

  const setSelectedEnvironment = useCallback(
    (value: string) => {
      // Environment changes supersede preview/execute operations that were
      // started against the previous execution target.
      bumpGeneration();
      setEnvironment(value);
      invalidatePreviewAndResult();
    },
    [bumpGeneration, invalidatePreviewAndResult],
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
    const opGeneration = bumpGeneration();
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
      if (!isCurrentGeneration(opGeneration)) {
        return;
      }
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
      if (!isCurrentGeneration(opGeneration)) {
        return;
      }
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
    bumpGeneration,
    dirtyParams,
    extractState,
    invalidatePreviewAndResult,
    isCurrentGeneration,
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

  const validationErrors = useMemo(() => form
    ? validateParameterValues(form.parameters, parameterValues)
    : {}, [form, parameterValues]);
  const invalidParameterCount = Object.keys(validationErrors).length;

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
      invalidParameterCount > 0 ||
      previewState === "loading"
    ) {
      return;
    }
    const opGeneration = bumpGeneration();
    setPreviewState("loading");
    setPreviewError(null);
    setResult(null);
    resultAuditIdRef.current = null;
    setExecuteError(null);
    clearAuditLifecycle();
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
      if (!isCurrentGeneration(opGeneration)) {
        return;
      }
      if (!form || response.source_name !== selectedSource ||
          response.catalog_revision_id !== form.catalog_revision_id ||
          response.catalog_fingerprint !== form.catalog_fingerprint ||
          response.template_id !== selectedCandidate.template_id ||
          response.version_id !== selectedCandidate.version_id ||
          response.environment !== environment) {
        setPreview(null);
        setPreviewSnapshot(null);
        setPreviewState("error");
        setPreviewError({
          code: "CATALOG_MISMATCH",
          message: "미리보기의 Catalog·템플릿·환경이 현재 선택과 다릅니다. 다시 시도하세요.",
        });
        return;
      }
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
      if (!isCurrentGeneration(opGeneration)) {
        return;
      }
      setPreview(null);
      setPreviewSnapshot(null);
      setPreviewState("error");
      setPreviewError(formatAssistantError(error));
    }
  }, [
    bumpGeneration,
    clearAuditLifecycle,
    environment,
    form,
    invalidParameterCount,
    isCurrentGeneration,
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
    invalidParameterCount === 0 &&
    previewState !== "loading" &&
    executeState !== "loading";

  const runExecute = useCallback(async () => {
    if (!canExecute || !selectedSource || !selectedCandidate || !environment || !preview) {
      return;
    }
    const opGeneration = bumpGeneration();
    setExecuteState("loading");
    setExecuteError(null);
    // Drop prior rows/audit UI immediately so a new run (or failure) never
    // leaves the previous success surface visible.
    setResult(null);
    resultAuditIdRef.current = null;
    clearAuditLifecycle();
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
      if (!isCurrentGeneration(opGeneration)) {
        return;
      }
      setResult(response);
      resultAuditIdRef.current = response.audit_id;
      setExecuteState("idle");
    } catch (error) {
      if (!isCurrentGeneration(opGeneration)) {
        return;
      }
      setResult(null);
      resultAuditIdRef.current = null;
      setExecuteState("error");
      setExecuteError(formatAssistantError(error));
    }
  }, [
    bumpGeneration,
    canExecute,
    clearAuditLifecycle,
    environment,
    form?.parameters,
    isCurrentGeneration,
    parameterValues,
    preview,
    selectedCandidate,
    selectedSource,
  ]);

  const loadAuditLifecycle = useCallback(async () => {
    const auditId = result?.audit_id;
    if (!auditId || auditState === "loading") {
      return;
    }
    const requestId = auditRequestRef.current + 1;
    auditRequestRef.current = requestId;
    setAuditState("loading");
    setAuditError(null);
    setAuditForbidden(false);
    setAuditBundle(null);
    try {
      const bundle = await getAuditEventsById(auditId);
      if (
        auditRequestRef.current !== requestId ||
        resultAuditIdRef.current !== auditId
      ) {
        return;
      }
      setAuditBundle(bundle);
      setAuditState("idle");
    } catch (error) {
      if (
        auditRequestRef.current !== requestId ||
        resultAuditIdRef.current !== auditId
      ) {
        return;
      }
      if (isAuditReadDenied(error)) {
        // History denied only — keep query result rows visible.
        setAuditForbidden(true);
        setAuditBundle(null);
        setAuditError(null);
        setAuditState("idle");
        return;
      }
      setAuditForbidden(false);
      setAuditBundle(null);
      setAuditState("error");
      setAuditError(formatAssistantError(error));
    }
  }, [auditState, result?.audit_id]);

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
    manualCatalog,
    manualState,
    manualError,
    manualMoreState,
    manualMoreError,
    loadManualTemplates,
    loadMoreManualTemplates,
    selectManualTemplate,
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
    validationErrors,
    invalidParameterCount,
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
    auditBundle,
    auditState,
    auditError,
    auditForbidden,
    loadAuditLifecycle,
  };
}
