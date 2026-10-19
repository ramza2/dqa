import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { DataDiscoveryPortal } from "../components/DataDiscoveryPortal";
import { SchemaSnapshotHistory } from "../components/SchemaSnapshotHistory";
import type {
  SnapshotDetail, SnapshotReviewEvent, SnapshotReviewPreview, SnapshotSummary,
} from "../types/schemaSnapshot";
import { SNAPSHOT_PANEL_DEADLINE_MS } from "../utils/snapshotPanelDeadline";
import { defaultCatalogHandlers, installFetchMock, jsonResponse } from "./mocks";

const SRC_A = "oracle_demis_mock";
const SRC_B = "oracle_demis_other";
const FP_A = "a".repeat(64);
const FP_B = "b".repeat(64);

const snapshot: SnapshotSummary = {
  id: 10, source_name: SRC_A, db_type: "oracle", database_name: "FREEPDB1",
  schema_name: "DEMIS_OWNER", schema_fingerprint: FP_A,
  previous_revision_id: 9, captured_by: "operator",
  captured_at: "2026-10-15T05:00:00Z", counts: { tables: 3, columns: 12 },
  diff_status: "COMPARED", total_changes: 1,
};
const detail: SnapshotDetail = {
  ...snapshot, diff_counts: { TABLE: { added: 0, removed: 0, changed: 1 } },
  changes: [{ object_type: "TABLE", change_type: "CHANGED",
    object_key: ["DEMIS_OWNER", "TB_SYNTH"], changed_fields: ["table_comment"] }],
};
const preview: SnapshotReviewPreview = {
  source_name: SRC_A, revision_id: 10, latest_revision_id: 10,
  is_latest: true, schema_fingerprint: FP_A, captured_at: snapshot.captured_at,
  review_status: "REVIEW_REQUIRED", diff_status: "COMPARED",
  identical: false, total_changes: 1, snapshot_verified: true,
  candidate_package_valid: true, candidate_package_readiness: "WARNING",
  preflight_status: "NOT_VERIFIED", activation_eligible: false, required_gates: [
    "MANUAL_CHANGE_REVIEW", "INDEPENDENT_PREFLIGHT", "EXPLICIT_CATALOG_IMPORT",
    "READY_ELIGIBILITY_VERIFICATION", "MANUAL_ACTIVATION",
  ],
};
const event: SnapshotReviewEvent = {
  id: 11, source_name: SRC_A, snapshot_revision_id: 10,
  schema_fingerprint: FP_A, previous_review_event_id: null,
  decision: "CHANGES_REQUESTED", reason_code: "RECHECK_REQUIRED",
  reviewed_by: "reviewer", reviewed_at: snapshot.captured_at,
  independent_preflight_verified: false, catalog_ready: false, catalog_activated: false,
};

type Handler = (url: URL, init?: RequestInit) => Response | null | Promise<Response | null>;

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

function responses(options: {
  items?: SnapshotSummary[];
  onList?: (url: URL) => Promise<Response> | Response;
  onDetail?: (url: URL) => Promise<Response> | Response;
  previewStatus?: number;
  onPreview?: (url: URL) => Promise<Response> | Response;
  onReviews?: (url: URL) => Promise<Response> | Response;
} = {}): Handler[] {
  return [
    (url, init) => {
      if (!url.pathname.startsWith("/api/v1/schema-inspector/snapshots")) return null;
      // This whole view must remain GET-only; no activation, review-write or
      // patient read route may be invoked by UI interaction.
      expect(init?.method).toBe("GET");
      const suffix = url.pathname.slice("/api/v1/schema-inspector/snapshots".length);
      if (!suffix) return options.onList?.(url) ?? jsonResponse(options.items ?? [snapshot]);
      if (suffix === "/10") return options.onDetail?.(url) ?? jsonResponse(detail);
      if (suffix === "/10/review") {
        if (options.onPreview) return options.onPreview(url);
        if (options.previewStatus) return jsonResponse(
          { detail: { code: "SNAPSHOT_REVIEW_UNVERIFIABLE", message: "not verifiable" } },
          options.previewStatus,
        );
        return jsonResponse(preview);
      }
      if (suffix === "/10/reviews") return options.onReviews?.(url) ?? jsonResponse([event]);
      return jsonResponse({ detail: { code: "NOT_FOUND", message: "not found" } }, 404);
    },
    (url) => url.pathname === "/api/v1/catalog/imports" ? jsonResponse([]) : null,
    (url) => url.pathname === "/api/v1/catalog/activations" ? jsonResponse([]) : null,
    ...defaultCatalogHandlers(),
  ];
}

async function enterSource(user: ReturnType<typeof userEvent.setup>, source = SRC_A) {
  await user.type(screen.getByRole("textbox", { name: "Snapshot source name" }), source);
  await user.click(screen.getByRole("button", { name: "Snapshot 조회" }));
}

describe("S-05-A Snapshot read-only UI", () => {
  it("exposes a Data Discovery tab, renders a safe Diff, WARNING preview and audit events", async () => {
    const user = userEvent.setup();
    const restore = installFetchMock(responses());
    render(<DataDiscoveryPortal />);
    await user.click(screen.getByTestId("dd-tab-snapshot"));
    expect(screen.getByTestId("snapshot-not-authority")).toHaveTextContent("독립 DBA Preflight");
    await enterSource(user);
    expect(await screen.findByRole("button", { name: "Snapshot 10 상세 보기" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Snapshot 10 상세 보기" }));
    expect(await screen.findByTestId("snapshot-diff")).toHaveTextContent("table_comment");
    const status = await screen.findByTestId("snapshot-preview");
    expect(status).toHaveTextContent("NOT_VERIFIED");
    expect(status).toHaveTextContent("WARNING");
    expect(status).toHaveTextContent("false");
    const gates = await screen.findByTestId("snapshot-review-gates");
    expect(within(gates).getAllByRole("listitem")).toHaveLength(5);
    expect(gates).toHaveTextContent("INDEPENDENT_PREFLIGHT");
    expect(await screen.findByTestId("snapshot-reviews")).toHaveTextContent("CHANGES_REQUESTED");
    expect(screen.queryByRole("button", { name: /activate|approve|READY|capture|import/i })).not.toBeInTheDocument();
    restore();
  });

  it("shows object-type Diff aggregates without deriving Catalog approval", async () => {
    const user = userEvent.setup();
    const restore = installFetchMock(responses());
    try {
      render(<SchemaSnapshotHistory />);
      await enterSource(user);
      await user.click(await screen.findByRole("button", { name: "Snapshot 10 상세 보기" }));
      expect(await screen.findByTestId("snapshot-diff-total")).toHaveTextContent("총 1건 변경");
      const overview = screen.getByTestId("snapshot-diff-overview");
      expect(overview).toHaveTextContent("TABLE");
      expect(within(overview).getAllByRole("row")).toHaveLength(2);
      expect(overview).toHaveTextContent("Changed");
      expect(await screen.findByTestId("snapshot-diff")).toHaveTextContent("table_comment");
      expect(screen.getByTestId("snapshot-diff-total")).toHaveTextContent("DBA 승인 증빙이 아닙니다");
    } finally { restore(); }
  });

  it("distinguishes NO_BASELINE from a verified comparison with zero changes", async () => {
    const user = userEvent.setup();
    const initial = {
      ...snapshot, previous_revision_id: null,
      diff_status: "NO_BASELINE" as const, total_changes: null,
    };
    const initialDetail: SnapshotDetail = { ...initial, diff_counts: {}, changes: [] };
    const restore = installFetchMock(responses({
      items: [initial],
      onDetail: () => jsonResponse(initialDetail),
    }));
    try {
      render(<SchemaSnapshotHistory />);
      await enterSource(user);
      await user.click(await screen.findByRole("button", { name: "Snapshot 10 상세 보기" }));
      expect(await screen.findByTestId("snapshot-diff-no-baseline")).toHaveTextContent("변경 0건으로 해석하지 않습니다");
      expect(screen.queryByTestId("snapshot-diff-overview")).not.toBeInTheDocument();
    } finally { restore(); }
  });

  it("fails closed on inconsistent Diff counts without hiding independent Preview and Gate information", async () => {
    const user = userEvent.setup();
    const restore = installFetchMock(responses({
      onDetail: () => jsonResponse({
        ...detail, diff_counts: { TABLE: { added: 0, removed: 0, changed: 99 } },
      }),
    }));
    try {
      render(<SchemaSnapshotHistory />);
      await enterSource(user);
      await user.click(await screen.findByRole("button", { name: "Snapshot 10 상세 보기" }));
      expect(await screen.findByRole("alert")).toHaveTextContent("변경 건수 정합성");
      expect(screen.queryByTestId("snapshot-diff")).not.toBeInTheDocument();
      expect(await screen.findByTestId("snapshot-preview")).toHaveTextContent("WARNING");
      expect(await screen.findByTestId("snapshot-review-gates")).toHaveTextContent("INDEPENDENT_PREFLIGHT");
    } finally { restore(); }
  });

  it("shows linked review-event IDs without mistaking ACKNOWLEDGED for DBA approval", async () => {
    const user = userEvent.setup();
    const newest = {
      ...event, id: 12, previous_review_event_id: 11,
      decision: "ACKNOWLEDGED", reason_code: "REVIEWED_CHANGES",
    };
    const restore = installFetchMock(responses({
      onReviews: () => jsonResponse([newest, event]),
    }));
    try {
      render(<SchemaSnapshotHistory />);
      await enterSource(user);
      await user.click(await screen.findByRole("button", { name: "Snapshot 10 상세 보기" }));
      const table = await screen.findByTestId("snapshot-reviews");
      expect(within(table).getAllByRole("row")).toHaveLength(3);
      expect(table).toHaveTextContent("Previous event");
      expect(table).toHaveTextContent("ACKNOWLEDGED");
      expect(table).toHaveTextContent("첫 기록");
      expect(screen.getByTestId("snapshot-review-journal-note")).toHaveTextContent("독립 DBA Preflight");
      expect(screen.queryByRole("button", { name: /approve|activate|READY|import/i })).not.toBeInTheDocument();
    } finally { restore(); }
  });

  it("fails closed on a broken review journal while preserving independent Diff and Preview", async () => {
    const user = userEvent.setup();
    const restore = installFetchMock(responses({
      onReviews: () => jsonResponse([{ ...event, previous_review_event_id: 999 }]),
    }));
    try {
      render(<SchemaSnapshotHistory />);
      await enterSource(user);
      await user.click(await screen.findByRole("button", { name: "Snapshot 10 상세 보기" }));
      expect(await screen.findByTestId("snapshot-diff")).toHaveTextContent("table_comment");
      expect(await screen.findByTestId("snapshot-preview")).toHaveTextContent("WARNING");
      expect(await screen.findByRole("alert")).toHaveTextContent("이벤트 연결 관계");
      expect(screen.queryByTestId("snapshot-reviews")).not.toBeInTheDocument();
    } finally { restore(); }
  });

  it("supports Snapshot-only Source even when there is no active Catalog, and shows no-baseline correctly", async () => {
    const user = userEvent.setup();
    const only: SnapshotSummary = {
      ...snapshot, id: 1, previous_revision_id: null,
      diff_status: "NO_BASELINE", total_changes: null,
    };
    const restore = installFetchMock(responses({ items: [only] }));
    render(<SchemaSnapshotHistory />);
    await enterSource(user);
    const button = await screen.findByRole("button", { name: "Snapshot 1 상세 보기" });
    expect(within(button.closest("tr")!).getByText("— (기준 없음)")).toBeInTheDocument();
    restore();
  });

  it("ignores stale list success when Source input changes mid-request", async () => {
    const user = userEvent.setup();
    let releaseA: ((response: Response) => void) | undefined;
    const pendingA = new Promise<Response>((resolve) => { releaseA = resolve; });
    const restore = installFetchMock(responses({
      onList: (url) => url.searchParams.get("source_name") === SRC_A
        ? pendingA : jsonResponse([{ ...snapshot, id: 20, source_name: SRC_B, schema_fingerprint: FP_B }]),
    }));
    render(<SchemaSnapshotHistory />);
    await enterSource(user);
    await user.clear(screen.getByRole("textbox", { name: "Snapshot source name" }));
    await enterSource(user, SRC_B);
    expect(await screen.findByRole("button", { name: "Snapshot 20 상세 보기" })).toBeInTheDocument();
    releaseA?.(jsonResponse([snapshot]));
    await waitFor(() => expect(screen.queryByRole("button", { name: "Snapshot 10 상세 보기" })).not.toBeInTheDocument());
    expect(screen.getByRole("button", { name: "Snapshot 20 상세 보기" })).toBeInTheDocument();
    restore();
  });

  it("ignores stale detail/review responses across a Source switch", async () => {
    const user = userEvent.setup();
    let releaseDetail: ((response: Response) => void) | undefined;
    const pendingDetail = new Promise<Response>((resolve) => { releaseDetail = resolve; });
    const restore = installFetchMock(responses({
      onList: (url) => jsonResponse(
        url.searchParams.get("source_name") === SRC_A ? [snapshot] : [],
      ),
      onDetail: () => pendingDetail,
    }));
    render(<SchemaSnapshotHistory />);
    await enterSource(user);
    await user.click(await screen.findByRole("button", { name: "Snapshot 10 상세 보기" }));
    await user.clear(screen.getByRole("textbox", { name: "Snapshot source name" }));
    await enterSource(user, SRC_B);
    expect(await screen.findByText("이 Source에 저장된 Snapshot이 없습니다.")).toBeInTheDocument();
    releaseDetail?.(jsonResponse(detail));
    await waitFor(() => expect(screen.queryByTestId("snapshot-detail-panel")).not.toBeInTheDocument());
    restore();
  });

  it("renders a valid Diff and journal without waiting for a slow Review Preview", async () => {
    const user = userEvent.setup();
    let releasePreview: ((response: Response) => void) | undefined;
    const pending = new Promise<Response>((resolve) => { releasePreview = resolve; });
    const restore = installFetchMock(responses({ onPreview: () => pending }));
    try {
      render(<SchemaSnapshotHistory />);
      await enterSource(user);
      await user.click(await screen.findByRole("button", { name: "Snapshot 10 상세 보기" }));
      expect(await screen.findByTestId("snapshot-diff")).toHaveTextContent("table_comment");
      expect(await screen.findByTestId("snapshot-reviews")).toHaveTextContent("CHANGES_REQUESTED");
      expect(screen.queryByTestId("snapshot-preview")).not.toBeInTheDocument();
      expect(screen.getByText("검토 미리보기 조회 중…")).toBeInTheDocument();
      releasePreview?.(jsonResponse(preview));
      expect(await screen.findByTestId("snapshot-preview")).toHaveTextContent("WARNING");
    } finally { restore(); }
  });

  it("renders Preview and journal while Diff is slow, and isolates a later Diff failure", async () => {
    const user = userEvent.setup();
    let releaseDetail: ((response: Response) => void) | undefined;
    const pending = new Promise<Response>((resolve) => { releaseDetail = resolve; });
    const restore = installFetchMock(responses({ onDetail: () => pending }));
    try {
      render(<SchemaSnapshotHistory />);
      await enterSource(user);
      await user.click(await screen.findByRole("button", { name: "Snapshot 10 상세 보기" }));
      expect(await screen.findByTestId("snapshot-preview")).toHaveTextContent("WARNING");
      expect(await screen.findByTestId("snapshot-reviews")).toHaveTextContent("CHANGES_REQUESTED");
      expect(screen.getByText("변경 Diff 조회 중…")).toBeInTheDocument();
      expect(screen.queryByTestId("snapshot-diff")).not.toBeInTheDocument();
      releaseDetail?.(jsonResponse({ detail: { code: "SNAPSHOT_DETAIL_FAILED", message: "synthetic error" } }, 503));
      expect(await screen.findByRole("alert")).toHaveTextContent("HTTP 503");
      expect(screen.getByTestId("snapshot-preview")).toHaveTextContent("WARNING");
      expect(screen.getByTestId("snapshot-reviews")).toHaveTextContent("CHANGES_REQUESTED");
    } finally { restore(); }
  });

  it("ignores late responses from an earlier click on the same Source and Snapshot", async () => {
    const user = userEvent.setup();
    let releaseFirst: ((response: Response) => void) | undefined;
    const pending = new Promise<Response>((resolve) => { releaseFirst = resolve; });
    let previewCalls = 0;
    const restore = installFetchMock(responses({
      onPreview: () => (++previewCalls === 1 ? pending : jsonResponse(preview)),
    }));
    try {
      render(<SchemaSnapshotHistory />);
      await enterSource(user);
      const button = await screen.findByRole("button", { name: "Snapshot 10 상세 보기" });
      await user.click(button);
      await user.click(button);
      expect(await screen.findByTestId("snapshot-preview")).toHaveTextContent("WARNING");
      expect(previewCalls).toBe(2);
      await act(async () => {
        releaseFirst?.(jsonResponse({ ...preview, activation_eligible: true }));
      });
      expect(screen.getByTestId("snapshot-preview")).toHaveTextContent("NOT_VERIFIED");
      expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    } finally { restore(); }
  });

  it("retries only a failed Diff GET and preserves successful Preview and journal", async () => {
    const user = userEvent.setup();
    let detailCalls = 0;
    let previewCalls = 0;
    let reviewCalls = 0;
    const restore = installFetchMock(responses({
      onDetail: () => ++detailCalls === 1
        ? jsonResponse({ detail: { code: "DIFF_UNAVAILABLE", message: "synthetic" } }, 503)
        : jsonResponse(detail),
      onPreview: () => { previewCalls += 1; return jsonResponse(preview); },
      onReviews: () => { reviewCalls += 1; return jsonResponse([event]); },
    }));
    try {
      render(<SchemaSnapshotHistory />);
      await enterSource(user);
      await user.click(await screen.findByRole("button", { name: "Snapshot 10 상세 보기" }));
      expect(await screen.findByRole("alert")).toHaveTextContent("HTTP 503");
      expect(await screen.findByTestId("snapshot-preview")).toHaveTextContent("WARNING");
      expect(await screen.findByTestId("snapshot-reviews")).toHaveTextContent("CHANGES_REQUESTED");
      await user.click(screen.getByRole("button", { name: "변경 Diff 다시 조회" }));
      expect(await screen.findByTestId("snapshot-diff")).toHaveTextContent("table_comment");
      expect(screen.queryByRole("button", { name: "변경 Diff 다시 조회" })).not.toBeInTheDocument();
      expect([detailCalls, previewCalls, reviewCalls]).toEqual([2, 1, 1]);
    } finally { restore(); }
  });

  it("retries only a failed Preview GET without elevating Gate status", async () => {
    const user = userEvent.setup();
    let detailCalls = 0;
    let previewCalls = 0;
    let reviewCalls = 0;
    const restore = installFetchMock(responses({
      onDetail: () => { detailCalls += 1; return jsonResponse(detail); },
      onPreview: () => jsonResponse(++previewCalls === 1
        ? { ...preview, activation_eligible: true } : preview),
      onReviews: () => { reviewCalls += 1; return jsonResponse([event]); },
    }));
    try {
      render(<SchemaSnapshotHistory />);
      await enterSource(user);
      await user.click(await screen.findByRole("button", { name: "Snapshot 10 상세 보기" }));
      expect(await screen.findByRole("alert")).toHaveTextContent("Gate 안전 상태");
      expect(await screen.findByTestId("snapshot-diff")).toHaveTextContent("table_comment");
      expect(await screen.findByTestId("snapshot-reviews")).toHaveTextContent("CHANGES_REQUESTED");
      await user.click(screen.getByRole("button", { name: "검토 미리보기 다시 조회" }));
      expect(await screen.findByTestId("snapshot-preview")).toHaveTextContent("NOT_VERIFIED");
      expect(screen.getByTestId("snapshot-preview")).toHaveTextContent("WARNING");
      expect(screen.getByTestId("snapshot-review-gates")).toHaveTextContent("INDEPENDENT_PREFLIGHT");
      expect([detailCalls, previewCalls, reviewCalls]).toEqual([1, 2, 1]);
    } finally { restore(); }
  });

  it("retries only a broken Review Journal and retains independent Diff and Preview", async () => {
    const user = userEvent.setup();
    let detailCalls = 0;
    let previewCalls = 0;
    let reviewCalls = 0;
    const restore = installFetchMock(responses({
      onDetail: () => { detailCalls += 1; return jsonResponse(detail); },
      onPreview: () => { previewCalls += 1; return jsonResponse(preview); },
      onReviews: () => jsonResponse(++reviewCalls === 1
        ? [{ ...event, previous_review_event_id: 999 }] : [event]),
    }));
    try {
      render(<SchemaSnapshotHistory />);
      await enterSource(user);
      await user.click(await screen.findByRole("button", { name: "Snapshot 10 상세 보기" }));
      expect(await screen.findByRole("alert")).toHaveTextContent("이벤트 연결 관계");
      expect(await screen.findByTestId("snapshot-diff")).toHaveTextContent("table_comment");
      expect(await screen.findByTestId("snapshot-preview")).toHaveTextContent("WARNING");
      await user.click(screen.getByRole("button", { name: "변경 검토 이력 다시 조회" }));
      expect(await screen.findByTestId("snapshot-reviews")).toHaveTextContent("CHANGES_REQUESTED");
      expect([detailCalls, previewCalls, reviewCalls]).toEqual([1, 1, 2]);
    } finally { restore(); }
  });

  it("discards a pending panel-only retry after switching Sources", async () => {
    const user = userEvent.setup();
    let releaseRetry: ((response: Response) => void) | undefined;
    const pending = new Promise<Response>((resolve) => { releaseRetry = resolve; });
    let detailCalls = 0;
    const restore = installFetchMock(responses({
      onList: (url) => jsonResponse(url.searchParams.get("source_name") === SRC_A
        ? [snapshot] : []),
      onDetail: () => ++detailCalls === 1
        ? jsonResponse({ detail: { code: "DIFF_UNAVAILABLE", message: "synthetic" } }, 503)
        : pending,
    }));
    try {
      render(<SchemaSnapshotHistory />);
      await enterSource(user);
      await user.click(await screen.findByRole("button", { name: "Snapshot 10 상세 보기" }));
      await screen.findByRole("button", { name: "변경 Diff 다시 조회" });
      await user.click(screen.getByRole("button", { name: "변경 Diff 다시 조회" }));
      expect(screen.getByText("변경 Diff 조회 중…")).toBeInTheDocument();
      await user.clear(screen.getByRole("textbox", { name: "Snapshot source name" }));
      await enterSource(user, SRC_B);
      expect(await screen.findByText("이 Source에 저장된 Snapshot이 없습니다.")).toBeInTheDocument();
      await act(async () => { releaseRetry?.(jsonResponse(detail)); });
      expect(screen.queryByTestId("snapshot-detail-panel")).not.toBeInTheDocument();
      expect(screen.queryByTestId("snapshot-diff")).not.toBeInTheDocument();
      expect(detailCalls).toBe(2);
    } finally { restore(); }
  });

  it("times out only a hung Diff GET and allows retry without refreshing Preview or Journal", async () => {
    const user = userEvent.setup();
    let detailCalls = 0;
    let previewCalls = 0;
    let reviewCalls = 0;
    const pending = new Promise<Response>(() => undefined);
    const restore = installFetchMock(responses({
      onDetail: () => ++detailCalls === 1 ? pending : jsonResponse(detail),
      onPreview: () => { previewCalls += 1; return jsonResponse(preview); },
      onReviews: () => { reviewCalls += 1; return jsonResponse([event]); },
    }));
    try {
      render(<SchemaSnapshotHistory />);
      await enterSource(user);
      const button = await screen.findByRole("button", { name: "Snapshot 10 상세 보기" });
      vi.useFakeTimers();
      fireEvent.click(button);
      await act(async () => {
        await vi.advanceTimersByTimeAsync(SNAPSHOT_PANEL_DEADLINE_MS);
      });
      expect(screen.getByRole("alert")).toHaveTextContent("응답 시간이 초과");
      expect(screen.getByTestId("snapshot-preview")).toHaveTextContent("NOT_VERIFIED");
      expect(screen.getByTestId("snapshot-reviews")).toHaveTextContent("CHANGES_REQUESTED");
      expect(screen.queryByTestId("snapshot-diff")).not.toBeInTheDocument();
      vi.useRealTimers();
      await user.click(screen.getByRole("button", { name: "변경 Diff 다시 조회" }));
      expect(await screen.findByTestId("snapshot-diff")).toHaveTextContent("table_comment");
      expect([detailCalls, previewCalls, reviewCalls]).toEqual([2, 1, 1]);
    } finally { restore(); }
  });

  it("ignores a late Preview after its deadline and keeps the safe retry result", async () => {
    const user = userEvent.setup();
    let releaseOld: ((response: Response) => void) | undefined;
    const pending = new Promise<Response>((resolve) => { releaseOld = resolve; });
    let previewCalls = 0;
    const restore = installFetchMock(responses({
      onPreview: () => ++previewCalls === 1 ? pending : jsonResponse(preview),
    }));
    try {
      render(<SchemaSnapshotHistory />);
      await enterSource(user);
      const button = await screen.findByRole("button", { name: "Snapshot 10 상세 보기" });
      vi.useFakeTimers();
      fireEvent.click(button);
      await act(async () => {
        await vi.advanceTimersByTimeAsync(SNAPSHOT_PANEL_DEADLINE_MS);
      });
      expect(screen.getByRole("alert")).toHaveTextContent("응답 시간이 초과");
      expect(screen.getByTestId("snapshot-diff")).toHaveTextContent("table_comment");
      expect(screen.getByTestId("snapshot-reviews")).toHaveTextContent("CHANGES_REQUESTED");
      vi.useRealTimers();
      await user.click(screen.getByRole("button", { name: "검토 미리보기 다시 조회" }));
      expect(await screen.findByTestId("snapshot-preview")).toHaveTextContent("WARNING");
      await act(async () => {
        releaseOld?.(jsonResponse({ ...preview, activation_eligible: true }));
      });
      expect(screen.getByTestId("snapshot-preview")).toHaveTextContent("NOT_VERIFIED");
      expect(screen.getByTestId("snapshot-review-gates")).toHaveTextContent("INDEPENDENT_PREFLIGHT");
      expect(screen.queryByRole("alert")).not.toBeInTheDocument();
      expect(previewCalls).toBe(2);
    } finally { restore(); }
  });

  it("keeps Diff visible if independent review preview returns 409, and shows HTTP errors", async () => {
    const user = userEvent.setup();
    const restore = installFetchMock(responses({ previewStatus: 409 }));
    render(<SchemaSnapshotHistory />);
    await enterSource(user);
    await user.click(await screen.findByRole("button", { name: "Snapshot 10 상세 보기" }));
    expect(await screen.findByTestId("snapshot-diff")).toHaveTextContent("table_comment");
    expect(await screen.findByRole("alert")).toHaveTextContent("SNAPSHOT_REVIEW_UNVERIFIABLE");
    expect(screen.queryByTestId("snapshot-preview")).not.toBeInTheDocument();
    expect(screen.queryByTestId("snapshot-review-gates")).not.toBeInTheDocument();
    restore();
  });

  it("rejects a promoted or unknown Gate review payload without hiding an independent Diff", async () => {
    const user = userEvent.setup();
    const restore = installFetchMock(responses({
      onPreview: () => jsonResponse({
        ...preview, activation_eligible: true,
        required_gates: ["INDEPENDENT_PREFLIGHT", "UNRECOGNIZED_SECRET"],
      }),
    }));
    try {
      render(<SchemaSnapshotHistory />);
      await enterSource(user);
      await user.click(await screen.findByRole("button", { name: "Snapshot 10 상세 보기" }));
      expect(await screen.findByTestId("snapshot-diff")).toHaveTextContent("table_comment");
      expect(await screen.findByRole("alert")).toHaveTextContent("Gate 안전 상태");
      expect(screen.queryByTestId("snapshot-preview")).not.toBeInTheDocument();
      expect(screen.queryByTestId("snapshot-review-gates")).not.toBeInTheDocument();
      expect(screen.queryByText("UNRECOGNIZED_SECRET")).not.toBeInTheDocument();
    } finally {
      restore();
    }
  });
  it("handles null review preview safely while leaving the Diff accessible", async () => {
    const user = userEvent.setup();
    const restore = installFetchMock(responses({ onPreview: () => jsonResponse(null) }));
    try {
      render(<SchemaSnapshotHistory />);
      await enterSource(user);
      await user.click(await screen.findByRole("button", { name: "Snapshot 10 상세 보기" }));
      expect(await screen.findByTestId("snapshot-diff")).toHaveTextContent("table_comment");
      expect(await screen.findByRole("alert")).toHaveTextContent("Gate 안전 상태");
      expect(screen.queryByTestId("snapshot-review-gates")).not.toBeInTheDocument();
    } finally { restore(); }
  });
  it("fails closed on list Source mismatch without rendering cross-source rows", async () => {
    const user = userEvent.setup();
    const restore = installFetchMock(responses({
      items: [{ ...snapshot, source_name: SRC_B, schema_fingerprint: FP_B }],
    }));
    render(<SchemaSnapshotHistory />);
    await enterSource(user);
    expect(await screen.findByRole("alert")).toHaveTextContent("응답 정합성");
    expect(screen.queryByRole("button", { name: "Snapshot 10 상세 보기" })).not.toBeInTheDocument();
    restore();
  });

  it("rejects malformed list payloads without rendering Snapshot or Catalog content", async () => {
    const user = userEvent.setup();
    const restore = installFetchMock(responses({ onList: () => jsonResponse(null) }));
    try {
      render(<SchemaSnapshotHistory />);
      await enterSource(user);
      expect(await screen.findByRole("alert")).toHaveTextContent("응답 정합성");
      expect(screen.queryByRole("button", { name: "Snapshot 10 상세 보기" })).not.toBeInTheDocument();
      expect(screen.queryByTestId("snapshot-catalog-context")).not.toBeInTheDocument();
    } finally { restore(); }
  });

  it("rejects a source-scoped page with broken predecessor linkage", async () => {
    const user = userEvent.setup();
    const restore = installFetchMock(responses({
      items: [
        { ...snapshot, id: 10, previous_revision_id: 8 },
        { ...snapshot, id: 9, previous_revision_id: null,
          diff_status: "NO_BASELINE", total_changes: null },
      ],
    }));
    try {
      render(<SchemaSnapshotHistory />);
      await enterSource(user);
      expect(await screen.findByRole("alert")).toHaveTextContent("응답 정합성");
      expect(screen.queryByRole("button", { name: "Snapshot 10 상세 보기" })).not.toBeInTheDocument();
      expect(screen.queryByTestId("snapshot-catalog-context")).not.toBeInTheDocument();
    } finally { restore(); }
  });

  it("recovers after a malformed list when the operator explicitly retries GET", async () => {
    const user = userEvent.setup();
    let requests = 0;
    const restore = installFetchMock(responses({
      onList: () => jsonResponse(++requests === 1 ? [null] : [snapshot]),
    }));
    try {
      render(<SchemaSnapshotHistory />);
      await enterSource(user);
      expect(await screen.findByRole("alert")).toHaveTextContent("응답 정합성");
      await user.click(screen.getByRole("button", { name: "Snapshot 조회" }));
      expect(await screen.findByRole("button", { name: "Snapshot 10 상세 보기" })).toBeInTheDocument();
      expect(screen.queryByRole("alert")).not.toBeInTheDocument();
      expect(await screen.findByTestId("snapshot-catalog-context")).toBeInTheDocument();
      expect(requests).toBe(2);
    } finally { restore(); }
  });

  it("shows a CATALOG_READ authorization error without Snapshot rows", async () => {
    const user = userEvent.setup();
    const restore = installFetchMock(responses({
      onList: () => jsonResponse({
        detail: { code: "FORBIDDEN", message: "CATALOG_READ required" },
      }, 403),
    }));
    render(<SchemaSnapshotHistory />);
    await enterSource(user);
    expect(await screen.findByRole("alert")).toHaveTextContent("HTTP 403");
    expect(screen.getByRole("alert")).toHaveTextContent("FORBIDDEN");
    expect(screen.queryByRole("button", { name: "Snapshot 10 상세 보기" })).not.toBeInTheDocument();
    restore();
  });

  it("rejects invalid Source input before issuing a Snapshot request", () => {
    const restore = installFetchMock(responses());
    render(<SchemaSnapshotHistory />);
    fireEvent.change(screen.getByRole("textbox", { name: "Snapshot source name" }),
      { target: { value: "../bad" } });
    fireEvent.click(screen.getByRole("button", { name: "Snapshot 조회" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Source 이름은");
    restore();
  });
});
