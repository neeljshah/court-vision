import { describe, it, expect, vi, afterEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { useStream } from "../useStream";

// ---------------------------------------------------------------------------
// useStream connection-state honesty. In jsdom EventSource is undefined, so the
// hook takes its poll fallback. These gate that a poll fallback which keeps
// failing flips the mode to an HONEST "disconnected" (so the UI can say "live
// feed unavailable") instead of presenting a frozen/last-good frame as live --
// and that a returned Unavailable sentinel counts as a failed poll.
// ---------------------------------------------------------------------------

afterEach(() => vi.restoreAllMocks());

describe("useStream -- honest disconnected state", () => {
  it("a pollFn that throws repeatedly -> mode 'disconnected', data null", async () => {
    const pollFn = vi.fn().mockRejectedValue(new Error("backend down"));
    const { result } = renderHook(() =>
      useStream<{ x: number }>({ pollFn, pollMs: 10 }),
    );
    await waitFor(() => expect(result.current.mode).toBe("disconnected"), {
      timeout: 1000,
    });
    expect(result.current.data).toBeNull();
  });

  it("a pollFn that resolves to the Unavailable sentinel counts as failure", async () => {
    const pollFn = vi
      .fn()
      .mockResolvedValue({ status: "unavailable", reason: "HTTP 500" });
    const { result } = renderHook(() =>
      useStream<{ status: string }>({ pollFn, pollMs: 10 }),
    );
    await waitFor(() => expect(result.current.mode).toBe("disconnected"), {
      timeout: 1000,
    });
    // last-good data is never fabricated from the sentinel.
    expect(result.current.data).toBeNull();
  });

  it("recovers to 'poll' once the feed returns real data", async () => {
    let n = 0;
    const pollFn = vi.fn(async () => {
      n += 1;
      if (n <= 2) return { status: "unavailable" } as unknown as { v: number };
      return { v: 1 };
    });
    const { result } = renderHook(() =>
      useStream<{ v: number }>({ pollFn, pollMs: 10 }),
    );
    await waitFor(() => expect(result.current.data).toEqual({ v: 1 }), {
      timeout: 1000,
    });
    expect(result.current.mode).toBe("poll");
  });
});
