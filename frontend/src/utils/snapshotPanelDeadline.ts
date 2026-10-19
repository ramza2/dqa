/** Frontend-only deadline for Snapshot detail GET requests (not an API permission).
 * A hung fetch must not hold its panel in loading forever. Other panels remain independent.
 */
export const SNAPSHOT_PANEL_DEADLINE_MS = 15_000;

export class SnapshotPanelTimeoutError extends Error {
  constructor() {
    super("Snapshot 상세 조회 응답 시간이 초과됐습니다. 해당 항목을 다시 조회하세요.");
    this.name = "SnapshotPanelTimeoutError";
  }
}

/** Passes an AbortSignal to the existing GET client and rejects at deadline
 * even when a synthetic/older fetch implementation ignores the signal.
 * The resolved/rejected request is always observed; no unhandled rejection.
 */
export function readSnapshotWithDeadline<T>(
  get: (signal: AbortSignal) => Promise<T>,
  timeoutMs = SNAPSHOT_PANEL_DEADLINE_MS,
): Promise<T> {
  const controller = new AbortController();
  let timer: ReturnType<typeof setTimeout> | undefined;
  const timeout = new Promise<never>((_, reject) => {
    timer = setTimeout(() => {
      reject(new SnapshotPanelTimeoutError());
      controller.abort();
    }, timeoutMs);
  });

  let request: Promise<T>;
  try {
    request = get(controller.signal);
  } catch (error) {
    if (timer !== undefined) clearTimeout(timer);
    return Promise.reject(error);
  }

  return Promise.race([request, timeout]).finally(() => {
    if (timer !== undefined) clearTimeout(timer);
  });
}
