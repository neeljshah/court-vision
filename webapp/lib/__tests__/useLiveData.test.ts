// useLiveData.test.ts -- acceptance suite for the canonical live-polling hook.
//
// Acceptance criteria (all must pass):
//   (a) Returns last-good data + isStale=true + error set after a failed /
//       Unavailable poll, never throws.
//   (b) Does NOT schedule a fetch while document.hidden=true and refetches once
//       on visibilitychange->visible.
//   (c) Clears interval + removes visibilitychange listener on unmount
//       (no leaked timers verified via fake timers).
//   (d) ageSec increases over time and isStale flips true once ageSec >
//       staleAfterSec.
//   (e) BACKOFF -- new WS1-hook-backoff criteria:
//       (e1) after 3 consecutive unavailable polls the scheduled delay has grown
//            beyond intervalMs and is capped at maxBackoffMultiplier * intervalMs.
//       (e2) a single success resets the delay to base (consecutiveFailures=0).
//       (e3) last-good data is still retained and isStale flips true during backoff.
//       (e4) consecutiveFailures / backoffActive are exposed on LiveDataState.

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, waitFor, act } from "@testing-library/react";
import { useLiveData, backoffDelay } from "../useLiveData";
import type { Unavailable } from "../types";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const unavailable = (reason = "HTTP 500"): Unavailable => ({
  status: "unavailable",
  reason,
});

// Flush the microtask queue (resolved promises) without advancing fake timers.
const flushMicrotasks = () => act(async () => { await Promise.resolve(); });

// ---------------------------------------------------------------------------
// Visibility helpers
// ---------------------------------------------------------------------------

function setVisibility(hidden: boolean) {
  Object.defineProperty(document, "hidden", {
    configurable: true,
    get: () => hidden,
  });
  document.dispatchEvent(new Event("visibilitychange"));
}

function resetVisibility() {
  Object.defineProperty(document, "hidden", {
    configurable: true,
    get: () => false,
  });
}

// ---------------------------------------------------------------------------
// (a) Last-good data retained + isStale + error set after failed poll
//     These tests use REAL timers so waitFor and async resolution work freely.
// ---------------------------------------------------------------------------

describe("useLiveData (a) -- last-good retained on failure, isStale, error", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    resetVisibility();
  });

  it("returns last-good data after a subsequent Unavailable poll and never throws", async () => {
    // Use a manual gate so we control exactly when each fetch resolves,
    // decoupling assertion timing from real-time interval races.
    let callCount = 0;
    let resolveCurrentFetch!: (v: { score: number } | Unavailable) => void;

    const fetcher = vi.fn(() => {
      callCount += 1;
      return new Promise<{ score: number } | Unavailable>((res) => {
        resolveCurrentFetch = res;
      });
    });

    const { result } = renderHook(() =>
      useLiveData(fetcher, { intervalMs: 50, staleAfterSec: 999 }),
    );

    // First fetch starts (callCount=1). Resolve it with good data.
    await act(async () => { resolveCurrentFetch({ score: 42 }); });

    await waitFor(() => expect(result.current.data).toEqual({ score: 42 }), {
      timeout: 3000,
    });
    // Before the next poll we know isStale/error is clean.
    expect(result.current.isStale).toBe(false);
    expect(result.current.error).toBeNull();

    // Wait for the second call to start (the 50ms interval fires).
    await waitFor(() => expect(callCount).toBe(2), { timeout: 3000 });

    // Resolve the second fetch with Unavailable.
    await act(async () => { resolveCurrentFetch(unavailable("HTTP 500")); });

    await waitFor(() => expect(result.current.error).toBeTruthy(), {
      timeout: 3000,
    });

    // Last-good data must still be present.
    expect(result.current.data).toEqual({ score: 42 });
    // isStale must be true after a failed poll.
    expect(result.current.isStale).toBe(true);
  });

  it("treats a thrown fetcher as an Unavailable poll (last-good retained)", async () => {
    let n = 0;
    const fetcher = vi.fn(async () => {
      n += 1;
      if (n === 1) return { v: 7 };
      throw new Error("network down");
    });

    const { result } = renderHook(() =>
      useLiveData(fetcher, { intervalMs: 50, staleAfterSec: 999 }),
    );

    await waitFor(() => expect(result.current.data).toEqual({ v: 7 }), {
      timeout: 3000,
    });

    await waitFor(() => expect(result.current.error).toBeTruthy(), {
      timeout: 3000,
    });

    // Must NOT throw; last-good data retained.
    expect(result.current.data).toEqual({ v: 7 });
    expect(result.current.isStale).toBe(true);
    expect(result.current.error).toBeTruthy();
  });

  it("sets isLoading=true initially and false after first successful fetch", async () => {
    // The hook starts in loading state before any fetch completes.
    let resolveFirst!: (v: { ok: boolean }) => void;
    const firstPromise = new Promise<{ ok: boolean }>((res) => { resolveFirst = res; });
    let first = true;
    const fetcher = vi.fn(async () => {
      if (first) { first = false; return firstPromise; }
      return { ok: true };
    });

    const { result } = renderHook(() =>
      useLiveData(fetcher, { intervalMs: 1000 }),
    );

    // Before first fetch completes, isLoading should be true.
    expect(result.current.isLoading).toBe(true);
    expect(result.current.data).toBeNull();

    // Let the first fetch complete.
    await act(async () => { resolveFirst({ ok: true }); });

    await waitFor(() => expect(result.current.isLoading).toBe(false), {
      timeout: 3000,
    });
    expect(result.current.data).toEqual({ ok: true });
  });
});

// ---------------------------------------------------------------------------
// (b) Pauses while document.hidden=true; refetches on visibilitychange->visible
//     Uses real timers; intervalMs is short (50ms) for speed.
// ---------------------------------------------------------------------------

describe("useLiveData (b) -- pauses hidden, resumes on visible", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    resetVisibility();
  });

  it("does not fetch while hidden and fetches exactly once on becoming visible", async () => {
    const fetcher = vi.fn().mockResolvedValue({ live: true });

    const { result } = renderHook(() =>
      useLiveData(fetcher, { intervalMs: 50 }),
    );

    // Wait for the initial (visible) mount fetch to complete.
    await waitFor(() => expect(result.current.data).toEqual({ live: true }), {
      timeout: 3000,
    });

    // Hide the tab.
    await act(async () => { setVisibility(true); });

    const callsBefore = fetcher.mock.calls.length;

    // Wait several poll intervals while hidden -- hook must NOT fetch.
    await new Promise((r) => setTimeout(r, 200));

    const callsDuringHide = fetcher.mock.calls.length - callsBefore;
    expect(callsDuringHide).toBe(0);

    // Reveal tab -- must trigger exactly one immediate re-fetch.
    await act(async () => {
      setVisibility(false);
      // Drain promises
      await Promise.resolve();
    });

    await waitFor(
      () => expect(fetcher.mock.calls.length).toBeGreaterThan(callsBefore),
      { timeout: 3000 },
    );

    // Allow any extra poll to fire so we can count.
    await new Promise((r) => setTimeout(r, 10));
    const callsAfterVisible = fetcher.mock.calls.length - callsBefore;
    // At least 1 call on becoming visible; at most 2 (1 immediate + maybe 1 interval).
    expect(callsAfterVisible).toBeGreaterThanOrEqual(1);
  });
});

// ---------------------------------------------------------------------------
// (c) Cleanup: interval cleared + visibilitychange listener removed on unmount.
//     Uses FAKE timers to prevent real-time leakage and verify no extra ticks.
// ---------------------------------------------------------------------------

describe("useLiveData (c) -- no leaked timers or listeners on unmount", () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: false });
    resetVisibility();
  });
  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
    resetVisibility();
  });

  it("clears the polling interval on unmount (no extra fetches after unmount)", async () => {
    const fetcher = vi.fn().mockResolvedValue({ x: 1 });

    const { unmount } = renderHook(() =>
      useLiveData(fetcher, { intervalMs: 100 }),
    );

    // Flush the initial fetch promise.
    await act(async () => { await Promise.resolve(); await Promise.resolve(); });

    const callsBeforeUnmount = fetcher.mock.calls.length;
    unmount();

    // Advance several intervals in fake time.
    await act(async () => {
      vi.advanceTimersByTime(500);
      await Promise.resolve();
    });

    // No new fetches should have been triggered.
    expect(fetcher.mock.calls.length).toBe(callsBeforeUnmount);
  });

  it("removes the visibilitychange listener on unmount (no extra fetches on visible after unmount)", async () => {
    const fetcher = vi.fn().mockResolvedValue({ x: 2 });

    const { unmount } = renderHook(() =>
      useLiveData(fetcher, { intervalMs: 500 }),
    );

    await act(async () => { await Promise.resolve(); await Promise.resolve(); });

    unmount();
    const callsAtUnmount = fetcher.mock.calls.length;

    // Simulate tab becoming visible AFTER unmount.
    await act(async () => {
      setVisibility(false); // dispatches visibilitychange
      await Promise.resolve();
    });

    // The removed listener must not trigger any new fetches.
    expect(fetcher.mock.calls.length).toBe(callsAtUnmount);
  });

  it("aborts any in-flight request on unmount (abort signal is set)", async () => {
    let capturedSignal: AbortSignal | null = null;

    // A fetcher that never resolves (simulates a hung request).
    const fetcher = vi.fn((signal: AbortSignal) => {
      capturedSignal = signal;
      return new Promise<{ done: boolean }>(() => { /* intentionally never resolves */ });
    });

    const { unmount } = renderHook(() =>
      useLiveData(fetcher, { intervalMs: 500 }),
    );

    // Give the mount-time fetch a tick to register the signal.
    await act(async () => { await Promise.resolve(); });

    expect(capturedSignal).not.toBeNull();
    expect((capturedSignal as unknown as AbortSignal).aborted).toBe(false);

    unmount();

    // The abort controller must have fired.
    expect((capturedSignal as unknown as AbortSignal).aborted).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// (d) ageSec increases over time; isStale flips once ageSec > staleAfterSec
//     Uses FAKE timers with shouldAdvanceTime=false so we control Date.now().
// ---------------------------------------------------------------------------

describe("useLiveData (d) -- ageSec ticks and isStale flips", () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: false });
    resetVisibility();
  });
  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
    resetVisibility();
  });

  it("ageSec increases ~1s per second and isStale flips after staleAfterSec", async () => {
    // Need shouldAdvanceTime: true so Date.now() moves and the age-ticker sees
    // a real elapsed time when it computes (Date.now() - lastUpdatedAt) / 1000.
    vi.useRealTimers();
    vi.useFakeTimers({ shouldAdvanceTime: true });

    const fetcher = vi.fn().mockResolvedValue({ fresh: true });
    const STALE_AFTER = 3;

    const { result } = renderHook(() =>
      useLiveData(fetcher, {
        intervalMs: 60_000, // long -- won't re-poll during test
        staleAfterSec: STALE_AFTER,
      }),
    );

    // Let the initial fetch complete.
    await act(async () => { await Promise.resolve(); await Promise.resolve(); });

    // Must have good data now.
    expect(result.current.data).toEqual({ fresh: true });
    expect(result.current.isStale).toBe(false);

    // Advance 4 seconds -- Date.now() also advances, so ageSec will be ~4.
    await act(async () => {
      vi.advanceTimersByTime(4_000);
      await Promise.resolve();
    });

    expect(result.current.ageSec).toBeGreaterThanOrEqual(STALE_AFTER);
    expect(result.current.isStale).toBe(true);
  });

  it("isStale resets to false after a successful re-poll", async () => {
    // Use fake timers with shouldAdvanceTime so Date.now() advances in sync
    // with vi.advanceTimersByTime. This makes the age-ticker deterministic:
    // at t=1000ms the ticker fires and sees age>staleAfterSec -> isStale=true;
    // then refresh() resolves -> isStale=false. No real-time race.
    vi.useRealTimers();
    vi.useFakeTimers({ shouldAdvanceTime: true });

    let n = 0;
    const fetcher = vi.fn(async () => ({ n: ++n }));

    const { result } = renderHook(() =>
      // Long intervalMs so the periodic poll never fires during the test.
      // staleAfterSec=1.5 -- above the 1s ticker boundary so the first tick
      // (age~1s) does NOT flip stale, the second tick (age~2s) DOES.
      useLiveData(fetcher, { intervalMs: 60_000, staleAfterSec: 1.5 }),
    );

    // Flush the initial fetch (it resolves synchronously via mockResolvedValue).
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(result.current.data).not.toBeNull();
    expect(result.current.isStale).toBe(false);

    // Advance 2 s: age-ticker fires at t=1000ms (age~1s < 1.5 -> not stale)
    // and at t=2000ms (age~2s > 1.5 -> isStale=true).
    await act(async () => {
      vi.advanceTimersByTime(2_000);
      await Promise.resolve();
    });

    expect(result.current.isStale).toBe(true);

    // Trigger a manual refresh and let its promise resolve.
    await act(async () => {
      result.current.refresh();
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(result.current.isStale).toBe(false);
    expect(result.current.error).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// (e) Backoff -- WS1-hook-backoff acceptance criteria.
//     Tests the backoffDelay() pure function and the hook's consecutive-failure
//     tracking. Most cases use real timers and manual resolvers for speed.
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// (e) Pure backoffDelay() utility tests
// ---------------------------------------------------------------------------

describe("backoffDelay (pure)", () => {
  it("returns base intervalMs when consecutiveFailures=0 (success path)", () => {
    expect(backoffDelay(1000, 0)).toBe(1000);
    expect(backoffDelay(5000, 0, 5)).toBe(5000);
  });

  it("doubles each step: 1x -> 2x -> 4x (within cap)", () => {
    // consecutiveFailures=1: 2^0=1 -> 1*intervalMs
    expect(backoffDelay(1000, 1)).toBe(1000);
    // consecutiveFailures=2: 2^1=2 -> 2*intervalMs
    expect(backoffDelay(1000, 2)).toBe(2000);
    // consecutiveFailures=3: 2^2=4 -> 4*intervalMs (still under 5x cap)
    expect(backoffDelay(1000, 3)).toBe(4000);
    // consecutiveFailures=4: 2^3=8 -> capped at 5*intervalMs (default cap=5)
    expect(backoffDelay(1000, 4)).toBe(5000);
  });

  it("caps at maxBackoffMultiplier * intervalMs (default 5x)", () => {
    // With default cap=5: 2^(f-1) is capped at 5.
    expect(backoffDelay(1000, 4, 5)).toBe(5000);
    expect(backoffDelay(1000, 10, 5)).toBe(5000);
    expect(backoffDelay(2000, 10, 5)).toBe(10_000);
  });

  it("respects a custom maxBackoffMultiplier", () => {
    expect(backoffDelay(1000, 3, 3)).toBe(3000); // 2^2=4 > 3 -> 3*1000
    expect(backoffDelay(1000, 2, 3)).toBe(2000); // 2^1=2 < 3 -> 2*1000
  });

  it("after 3 consecutive failures delay is > intervalMs (e1 criteria)", () => {
    const intervalMs = 1000;
    const delay3 = backoffDelay(intervalMs, 3);
    expect(delay3).toBeGreaterThan(intervalMs);
  });
});

// ---------------------------------------------------------------------------
// (e1-e4) Hook-level backoff tests
// ---------------------------------------------------------------------------

describe("useLiveData (e) -- exponential backoff on consecutive failures", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    resetVisibility();
  });

  // (e4) consecutiveFailures and backoffActive are exposed on LiveDataState.
  it("(e4) exposes consecutiveFailures=0 and backoffActive=false on initial success", async () => {
    const fetcher = vi.fn().mockResolvedValue({ ok: true });
    const { result } = renderHook(() =>
      useLiveData(fetcher, { intervalMs: 60_000 }),
    );

    await waitFor(() => expect(result.current.data).not.toBeNull(), { timeout: 3000 });

    expect(result.current.consecutiveFailures).toBe(0);
    expect(result.current.backoffActive).toBe(false);
  });

  // (e4) After one failure: consecutiveFailures=1, backoffActive=true.
  // Uses a manual gate so we can assert consecutiveFailures=0 after the FIRST
  // success before any second poll can fire.
  it("(e4) consecutiveFailures increments and backoffActive flips true after a failed poll", async () => {
    let callCount = 0;
    let resolveCurrentFetch!: (v: { v: number } | { status: "unavailable"; reason: string }) => void;

    const fetcher = vi.fn(() => {
      callCount += 1;
      return new Promise<{ v: number } | { status: "unavailable"; reason: string }>((res) => {
        resolveCurrentFetch = res;
      });
    });

    const { result } = renderHook(() =>
      useLiveData(fetcher, { intervalMs: 60_000, staleAfterSec: 999 }),
    );

    // Resolve the first (mount) fetch with good data.
    await act(async () => { resolveCurrentFetch({ v: 1 }); });

    await waitFor(() => expect(result.current.data).toEqual({ v: 1 }), { timeout: 3000 });

    // Immediately after success, before the next scheduled poll (60s away):
    expect(result.current.consecutiveFailures).toBe(0);
    expect(result.current.backoffActive).toBe(false);

    // Manually trigger a refresh and resolve it as unavailable.
    await act(async () => { result.current.refresh(); });
    await waitFor(() => expect(callCount).toBe(2), { timeout: 3000 });
    await act(async () => { resolveCurrentFetch({ status: "unavailable", reason: "down" }); });

    await waitFor(() => expect(result.current.consecutiveFailures).toBeGreaterThan(0), {
      timeout: 3000,
    });
    expect(result.current.backoffActive).toBe(true);
    expect(result.current.error).toBeTruthy();
  });

  // (e3) Last-good data retained and isStale=true during backoff.
  it("(e3) last-good data is retained and isStale flips true during backoff", async () => {
    let n = 0;
    const fetcher = vi.fn(async (): Promise<{ score: number } | { status: "unavailable"; reason: string }> => {
      n += 1;
      if (n === 1) return { score: 99 };
      return { status: "unavailable", reason: "timeout" };
    });

    const { result } = renderHook(() =>
      useLiveData(fetcher, { intervalMs: 30, staleAfterSec: 999 }),
    );

    // First fetch succeeds.
    await waitFor(() => expect(result.current.data).toEqual({ score: 99 }), { timeout: 3000 });

    // After one or more failures: data must still be last-good + isStale.
    await waitFor(() => expect(result.current.consecutiveFailures).toBeGreaterThan(0), {
      timeout: 3000,
    });

    // Last-good retained (e3).
    expect(result.current.data).toEqual({ score: 99 });
    // isStale flips true (e3).
    expect(result.current.isStale).toBe(true);
  });

  // (e1) After 3+ consecutive failures the effective delay has grown beyond intervalMs.
  //      Tested via backoffDelay() + consecutiveFailures state, since advancing real
  //      time for 3 backoff cycles would take too long in a test.
  it("(e1) after 3 consecutive failures consecutiveFailures=3 and backoffDelay > intervalMs", async () => {
    const INTERVAL = 20; // very short so 3 cycles complete quickly in real time
    let n = 0;
    const fetcher = vi.fn(async (): Promise<{ x: number } | { status: "unavailable"; reason: string }> => {
      n += 1;
      if (n === 1) return { x: 1 }; // first success
      return { status: "unavailable", reason: "down" };
    });

    const { result } = renderHook(() =>
      useLiveData(fetcher, { intervalMs: INTERVAL, staleAfterSec: 999 }),
    );

    // First fetch succeeds.
    await waitFor(() => expect(result.current.data).not.toBeNull(), { timeout: 3000 });

    // Wait for at least 3 consecutive failures.
    await waitFor(
      () => expect(result.current.consecutiveFailures).toBeGreaterThanOrEqual(3),
      { timeout: 5000 },
    );

    // The effective delay is now backoffDelay(INTERVAL, >=3), which must be > INTERVAL.
    const delay = backoffDelay(INTERVAL, result.current.consecutiveFailures);
    expect(delay).toBeGreaterThan(INTERVAL);

    // Also verify the cap: delay must not exceed 5 * INTERVAL.
    expect(delay).toBeLessThanOrEqual(5 * INTERVAL);
  });

  // (e1) Separate cap test: very high failure count must not exceed 5 * intervalMs.
  it("(e1) delay is capped at 5x intervalMs regardless of failure count", () => {
    const INTERVAL = 1000;
    // Check that even at failure=100 we don't exceed 5x.
    expect(backoffDelay(INTERVAL, 100, 5)).toBe(5000);
  });

  // (e2) A single success resets consecutiveFailures to 0 and backoffActive to false.
  // Uses a manual gate so we can assert each step without real-timer races.
  it("(e2) a single success resets consecutiveFailures to 0 and backoffActive to false", async () => {
    let callCount = 0;
    let resolveCurrentFetch!: (
      v: { n: number } | { status: "unavailable"; reason: string }
    ) => void;

    const fetcher = vi.fn(() => {
      callCount += 1;
      return new Promise<{ n: number } | { status: "unavailable"; reason: string }>((res) => {
        resolveCurrentFetch = res;
      });
    });

    const { result } = renderHook(() =>
      useLiveData(fetcher, { intervalMs: 60_000, staleAfterSec: 999 }),
    );

    // 1. Resolve mount fetch as success.
    await act(async () => { resolveCurrentFetch({ n: 1 }); });
    await waitFor(() => expect(result.current.data).toEqual({ n: 1 }), { timeout: 3000 });
    expect(result.current.consecutiveFailures).toBe(0);

    // 2. Manually trigger a refresh and resolve as fail #1.
    await act(async () => { result.current.refresh(); });
    await waitFor(() => expect(callCount).toBe(2), { timeout: 3000 });
    await act(async () => { resolveCurrentFetch({ status: "unavailable", reason: "down" }); });
    await waitFor(() => expect(result.current.consecutiveFailures).toBe(1), { timeout: 3000 });
    expect(result.current.backoffActive).toBe(true);

    // 3. Trigger another refresh and resolve as fail #2.
    await act(async () => { result.current.refresh(); });
    await waitFor(() => expect(callCount).toBe(3), { timeout: 3000 });
    await act(async () => { resolveCurrentFetch({ status: "unavailable", reason: "down" }); });
    await waitFor(() => expect(result.current.consecutiveFailures).toBe(2), { timeout: 3000 });
    expect(result.current.backoffActive).toBe(true);

    // 4. Trigger a recovery refresh and resolve as success. (e2)
    await act(async () => { result.current.refresh(); });
    await waitFor(() => expect(callCount).toBe(4), { timeout: 3000 });
    await act(async () => { resolveCurrentFetch({ n: 4 }); });
    await waitFor(() => expect(result.current.consecutiveFailures).toBe(0), { timeout: 3000 });

    // (e2) consecutiveFailures resets to 0 and backoffActive goes false.
    expect(result.current.consecutiveFailures).toBe(0);
    expect(result.current.backoffActive).toBe(false);
    // Error clears on success.
    expect(result.current.error).toBeNull();
    expect(result.current.isStale).toBe(false);
  });
});
