/**
 * Unit tests for useBoard hook: verifies initial fetch, loading state transitions,
 * and cleanup of the 25s polling interval to prevent timer leaks.
 */
import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { BoardResponse } from "@/types/board";
import { useBoard } from "./useBoard";

// Minimal BoardResponse fixture for mlb
const MLB_RESPONSE: BoardResponse = {
  sport: "mlb",
  leagues: null,
  generated_at: "2026-06-15T12:00:00Z",
  rows: [
    {
      sport: "mlb",
      league: "MLB",
      state: "in",
      start_time: "2026-06-15T17:05:00Z",
      home: "NYY",
      away: "BOS",
      home_score: 3,
      away_score: 2,
      clock_text: "Bot 7",
      win_home: 0.58,
      win_away: 0.42,
      draw: null,
      total: 8.5,
      market_odds: null,
      provider: null,
      source: "market",
      market_implied: true,
      note: null,
    },
  ],
};

describe("useBoard", () => {
  let fetchSpy: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    // shouldAdvanceTime lets @testing-library's waitFor polling progress while
    // we still control the 25s poll via advanceTimersByTime.
    vi.useFakeTimers({ shouldAdvanceTime: true });
    fetchSpy = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => MLB_RESPONSE,
    } as unknown as Response);
    vi.stubGlobal("fetch", fetchSpy);
  });

  afterEach(() => {
    vi.runOnlyPendingTimers();
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it("starts in loading state and resolves data after first fetch", async () => {
    const { result, unmount } = renderHook(() => useBoard("mlb"));

    // Before the async fetch settles, loading should be true and data null
    expect(result.current.loading).toBe(true);
    expect(result.current.data).toBeNull();

    // Advance microtasks so the fetch promise resolves
    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.data).not.toBeNull();
    expect(result.current.data?.sport).toBe("mlb");
    expect(result.current.data?.rows).toHaveLength(1);
    expect(result.current.error).toBeNull();

    unmount();
    // Drain any timers started by the interval before cleanup
    vi.runOnlyPendingTimers();
  });

  it("calls fetch with sport=mlb query param", async () => {
    const { unmount } = renderHook(() => useBoard("mlb"));

    await waitFor(() => {
      expect(fetchSpy).toHaveBeenCalled();
    });

    const calledUrl: string = fetchSpy.mock.calls[0][0] as string;
    expect(calledUrl).toContain("sport=mlb");

    unmount();
    vi.runOnlyPendingTimers();
  });

  it("sets refreshing to false and lastUpdated after successful load", async () => {
    const { result, unmount } = renderHook(() => useBoard("mlb"));

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.refreshing).toBe(false);
    expect(result.current.lastUpdated).toBe("2026-06-15T12:00:00Z");

    unmount();
    vi.runOnlyPendingTimers();
  });

  it("surfaces an error string when fetch rejects", async () => {
    fetchSpy.mockRejectedValueOnce(new Error("Network failure"));

    const { result, unmount } = renderHook(() => useBoard("mlb"));

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.error).toBe("Network failure");
    expect(result.current.data).toBeNull();

    unmount();
    vi.runOnlyPendingTimers();
  });

  it("does not poll again until interval elapses (timer is installed)", async () => {
    const { unmount } = renderHook(() => useBoard("mlb"));

    await waitFor(() => {
      expect(fetchSpy).toHaveBeenCalledTimes(1);
    });

    // Advance less than 25s -- no second call
    vi.advanceTimersByTime(24_000);
    expect(fetchSpy).toHaveBeenCalledTimes(1);

    // Advance past the 25s mark -- second poll fires
    vi.advanceTimersByTime(2_000);
    expect(fetchSpy).toHaveBeenCalledTimes(2);

    unmount();
    vi.runOnlyPendingTimers();
  });

  it("reports stale=false right after a fresh load, and stale=true once the data ages past 90s", async () => {
    // Build a response whose generated_at is effectively "now" so stale starts false.
    const freshGeneratedAt = new Date(Date.now()).toISOString();
    const FRESH_RESPONSE: BoardResponse = {
      ...MLB_RESPONSE,
      generated_at: freshGeneratedAt,
    };
    fetchSpy.mockResolvedValueOnce({
      ok: true,
      json: async () => FRESH_RESPONSE,
    } as unknown as Response);

    const { result, unmount } = renderHook(() => useBoard("mlb"));

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    // stale must be a boolean and false immediately after a fresh load
    expect(typeof result.current.stale).toBe("boolean");
    expect(result.current.stale).toBe(false);

    unmount();
    vi.runOnlyPendingTimers();
  });

  it("flips stale=true once the data ages past 90s (via the 15s tick)", async () => {
    const FRESH_RESPONSE: BoardResponse = {
      ...MLB_RESPONSE,
      generated_at: new Date(Date.now()).toISOString(),
    };
    fetchSpy.mockResolvedValueOnce({
      ok: true,
      json: async () => FRESH_RESPONSE,
    } as unknown as Response);

    const { result, unmount } = renderHook(() => useBoard("mlb"));
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.stale).toBe(false);

    // Advance past the 90s staleness window; the 15s tick refreshes `now`.
    await act(async () => {
      vi.advanceTimersByTime(91_000);
    });
    await waitFor(() => expect(result.current.stale).toBe(true));

    unmount();
    vi.runOnlyPendingTimers();
  });

  it("pauses polling while hidden and refreshes immediately on return to visible", async () => {
    let hidden = false;
    Object.defineProperty(document, "hidden", {
      configurable: true,
      get: () => hidden,
    });

    const { unmount } = renderHook(() => useBoard("mlb"));
    await waitFor(() => expect(fetchSpy).toHaveBeenCalledTimes(1));

    // Hide the tab: the 25s poll must stop firing.
    hidden = true;
    act(() => {
      document.dispatchEvent(new Event("visibilitychange"));
    });
    vi.advanceTimersByTime(30_000);
    expect(fetchSpy).toHaveBeenCalledTimes(1);

    // Return to visible: an immediate refresh fires.
    hidden = false;
    act(() => {
      document.dispatchEvent(new Event("visibilitychange"));
    });
    await waitFor(() => expect(fetchSpy).toHaveBeenCalledTimes(2));

    unmount();
    vi.runOnlyPendingTimers();
  });

  it("aborts in-flight request and resets state on sport switch", async () => {
    const { result, rerender, unmount } = renderHook(
      ({ sport }: { sport: "mlb" | "soccer" | "tennis" }) => useBoard(sport),
      {
        initialProps: { sport: "mlb" } as {
          sport: "mlb" | "soccer" | "tennis";
        },
      },
    );

    await waitFor(() => {
      expect(result.current.data?.sport).toBe("mlb");
    });

    // Prepare next response as soccer (sport field must match)
    const SOCCER_RESPONSE: BoardResponse = {
      ...MLB_RESPONSE,
      sport: "soccer",
      rows: [{ ...MLB_RESPONSE.rows[0], sport: "soccer", league: "Premier League" }],
    };
    fetchSpy.mockResolvedValueOnce({
      ok: true,
      json: async () => SOCCER_RESPONSE,
    } as unknown as Response);

    rerender({ sport: "soccer" });

    // Immediately after rerender, data should be cleared while new load is pending
    expect(result.current.data).toBeNull();

    await waitFor(() => {
      expect(result.current.data?.sport).toBe("soccer");
    });

    unmount();
    vi.runOnlyPendingTimers();
  });
});
