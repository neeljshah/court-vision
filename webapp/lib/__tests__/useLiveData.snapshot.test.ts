// useLiveData.snapshot.test.ts -- snapshot-build semantics of the hook. NEXT_PUBLIC_DATA_MODE
// is read at module load (lib/fetchHonest isSnapshotMode), so each test re-imports the module
// under a stubbed env. The first Unavailable ends loading (there is no retry), the age
// ticker is off (baked data never flips to STALE on the viewer's clock), and the
// last-known-value cache key carries the build id.
import { afterEach, describe, expect, it, vi } from "vitest";
import { act, renderHook, waitFor } from "@testing-library/react";
import type { Unavailable } from "../types";

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllEnvs();
  vi.resetModules();
  window.sessionStorage.clear();
});

async function load(mode: "snapshot" | "") {
  vi.stubEnv("NEXT_PUBLIC_DATA_MODE", mode);
  vi.stubEnv("NEXT_PUBLIC_BUILD_ID", "build-xyz");
  vi.resetModules();
  return (await import("../useLiveData")).useLiveData;
}
const unavailable: Unavailable = { status: "unavailable", reason: "not in the published snapshot" };

describe("useLiveData in a snapshot build", () => {
  it("ends loading on the first Unavailable instead of keeping the skeleton forever", async () => {
    const useLiveData = await load("snapshot");
    const fetcher = vi.fn(async () => unavailable);
    const { result } = renderHook(() => useLiveData<{ n: number }>(fetcher));
    await waitFor(() => expect(result.current.isLoading).toBe(false), { timeout: 3000 });
    expect(result.current.data).toBeNull();
    expect(result.current.error).toBe("not in the published snapshot");
    expect(fetcher).toHaveBeenCalledTimes(1);
  });

  it("keeps loading after a first Unavailable in a live build, where a retry is coming", async () => {
    const useLiveData = await load("");
    const fetcher = vi.fn(async () => unavailable);
    const { result } = renderHook(() => useLiveData<{ n: number }>(fetcher, { intervalMs: 60_000 }));
    await waitFor(() => expect(result.current.error).toBe("not in the published snapshot"), { timeout: 3000 });
    expect(result.current.isLoading).toBe(true);
  });

  it("runs no age ticker: baked data stays fresh past staleAfterSec, and nothing re-polls", async () => {
    const useLiveData = await load("snapshot");
    vi.useFakeTimers({ shouldAdvanceTime: false });
    const fetcher = vi.fn(async () => ({ n: 1 }));
    const { result } = renderHook(() => useLiveData<{ n: number }>(fetcher, { staleAfterSec: 60, intervalMs: 1_000 }));
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });
    expect(result.current.data).toEqual({ n: 1 });
    await act(async () => { await vi.advanceTimersByTimeAsync(61_000); });
    expect(result.current.ageSec).toBe(0);
    expect(result.current.isStale).toBe(false);
    expect(fetcher).toHaveBeenCalledTimes(1);
  });

  it("prefixes the last-known-value cache key with the build id", async () => {
    const useLiveData = await load("snapshot");
    const fetcher = vi.fn(async () => ({ n: 2 }));
    const { result } = renderHook(() => useLiveData<{ n: number }>(fetcher, { cacheKey: "panel" }));
    await waitFor(() => expect(result.current.data).toEqual({ n: 2 }), { timeout: 3000 });
    expect(window.sessionStorage.getItem("cv-lkv:build-xyz:panel")).toContain('"n":2');
    expect(window.sessionStorage.getItem("cv-lkv:panel")).toBeNull();
  });
});
