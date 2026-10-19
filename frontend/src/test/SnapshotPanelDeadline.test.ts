import { afterEach, describe, expect, it, vi } from "vitest";
import {
  readSnapshotWithDeadline, SnapshotPanelTimeoutError, SNAPSHOT_PANEL_DEADLINE_MS,
} from "../utils/snapshotPanelDeadline";

afterEach(() => {
  vi.useRealTimers();
});

describe("S-05-K Snapshot panel request deadline", () => {
  it("returns a successful GET and clears its timeout", async () => {
    vi.useFakeTimers();
    let signal: AbortSignal | undefined;
    const value = await readSnapshotWithDeadline((requestSignal) => {
      signal = requestSignal;
      return Promise.resolve("safe metadata");
    });
    expect(value).toBe("safe metadata");
    expect(signal?.aborted).toBe(false);
    expect(vi.getTimerCount()).toBe(0);
  });

  it("rejects a hung GET at the deadline and aborts its signal", async () => {
    vi.useFakeTimers();
    let signal: AbortSignal | undefined;
    const get = readSnapshotWithDeadline<string>((requestSignal) => {
      signal = requestSignal;
      return new Promise<string>(() => undefined);
    });
    const rejection = expect(get).rejects.toBeInstanceOf(SnapshotPanelTimeoutError);
    await vi.advanceTimersByTimeAsync(SNAPSHOT_PANEL_DEADLINE_MS - 1);
    expect(signal?.aborted).toBe(false);
    await vi.advanceTimersByTimeAsync(1);
    await rejection;
    expect(signal?.aborted).toBe(true);
    expect(vi.getTimerCount()).toBe(0);
  });

  it("clears the deadline when GET fails before timeout", async () => {
    vi.useFakeTimers();
    const error = new Error("HTTP read failed");
    await expect(readSnapshotWithDeadline(() => Promise.reject(error))).rejects.toBe(error);
    expect(vi.getTimerCount()).toBe(0);
  });

  it("clears the deadline when a GET throws before creating a Promise", async () => {
    vi.useFakeTimers();
    await expect(readSnapshotWithDeadline(() => { throw new Error("sync fail"); }))
      .rejects.toThrow("sync fail");
    expect(vi.getTimerCount()).toBe(0);
  });

  it("ignores the eventual late success of a fetch that did not honor abort", async () => {
    vi.useFakeTimers();
    let release: ((value: string) => void) | undefined;
    const pending = new Promise<string>((resolve) => { release = resolve; });
    const get = readSnapshotWithDeadline(() => pending);
    const rejection = expect(get).rejects.toBeInstanceOf(SnapshotPanelTimeoutError);
    await vi.advanceTimersByTimeAsync(SNAPSHOT_PANEL_DEADLINE_MS);
    await rejection;
    release?.("late data");
    await Promise.resolve();
    expect(vi.getTimerCount()).toBe(0);
  });
});
