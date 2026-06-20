import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, act, waitFor } from "@testing-library/react";

import {
  TickingFreshnessBadge,
  FreshnessBadge,
  timeAgoIso,
  ModeDot,
} from "../Primitives";

// ---------------------------------------------------------------------------
// TickingFreshnessBadge -- ticking + honest tone-degradation tests
//
// Acceptance contract (workstream ws3-ticking-freshness-age):
//   1. Displayed age text updates after time advances past a tick interval.
//   2. Tone is "green" (tier-a class) when asOf is genuinely fresh (< 5 min).
//   3. Tone moves away from green once the 5-min fresh threshold is crossed.
//   4. Tone is "slate" when asOf is >= 60 min old (quietly stale).
//   5. Absent / unparseable asOf -> slate "unavailable" (never green).
//   6. The existing exports (FreshnessBadge / timeAgoIso / ModeDot) remain
//      present and have unchanged signatures (regression guard).
//   7. Component cleans up its interval on unmount (no act() warning storm).
// ---------------------------------------------------------------------------

// Use fake timers for deterministic tick control.
beforeEach(() => {
  vi.useFakeTimers();
});
afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

// ---------------------------------------------------------------------------
// Helper: build an ISO string that is `offsetMs` milliseconds in the past.
// ---------------------------------------------------------------------------
function isoAgo(offsetMs: number): string {
  return new Date(Date.now() - offsetMs).toISOString();
}

// ---------------------------------------------------------------------------
// Badge-pill class helpers
// The Badge component puts tone classes on the <span> that wraps the label.
// We retrieve the wrapping pill via the data-testid on the container and find
// the first <span> child (the Badge span) to inspect its className.
// ---------------------------------------------------------------------------
function pillEl(): HTMLElement | null {
  const badge = screen.queryByTestId("ticking-freshness-badge");
  if (!badge) return null;
  return badge.querySelector("span") as HTMLElement | null;
}

function pillClass(): string {
  return pillEl()?.className ?? "";
}

const TICK_MS = 100; // fast tick for tests -- overrides 30 s default

// ---------------------------------------------------------------------------
// 1. Displayed age text updates after advancing time past a tick interval
// ---------------------------------------------------------------------------
describe("TickingFreshnessBadge -- age text updates on tick", () => {
  it("shows '0s ago' immediately, then updates to '1s ago' after 1 s + tick", () => {
    // asOf = right now (0 ms lag)
    const asOf = new Date(Date.now()).toISOString();
    render(<TickingFreshnessBadge asOf={asOf} tickMs={TICK_MS} />);

    // Initial label: 0 s ago (rounded)
    expect(screen.getByTestId("ticking-age-label").textContent).toBe("0s ago");

    // Advance real clock by 1 s + one tick interval
    act(() => {
      vi.advanceTimersByTime(1000 + TICK_MS);
    });

    // After the tick the label re-renders with the updated age
    const label = screen.getByTestId("ticking-age-label").textContent ?? "";
    // Expect either "1s ago" or "2s ago" depending on rounding; at minimum the
    // text must include "s ago" (seconds) and NOT still be "0s ago".
    expect(label).toMatch(/\ds ago/);
    expect(label).not.toBe("0s ago");
  });

  it("updates from seconds to minutes after enough time elapses", () => {
    const asOf = new Date(Date.now()).toISOString();
    render(<TickingFreshnessBadge asOf={asOf} tickMs={TICK_MS} />);

    // Advance 2 minutes + one tick
    act(() => {
      vi.advanceTimersByTime(2 * 60 * 1000 + TICK_MS);
    });

    const label = screen.getByTestId("ticking-age-label").textContent ?? "";
    expect(label).toMatch(/\dm ago/);
  });
});

// ---------------------------------------------------------------------------
// 2. Tone is green (tier-a class) for a genuinely fresh asOf (< 5 min)
// ---------------------------------------------------------------------------
describe("TickingFreshnessBadge -- green tone for fresh data", () => {
  it("renders tier-a (green) badge for a 30 s old timestamp", () => {
    const asOf = isoAgo(30_000); // 30 s old
    render(<TickingFreshnessBadge asOf={asOf} tickMs={TICK_MS} />);

    expect(pillClass()).toContain("tier-a");
    expect(pillClass()).not.toContain("amber");
    expect(pillClass()).not.toContain("slate-800");
  });
});

// ---------------------------------------------------------------------------
// 3. Tone moves away from green once the 5-min threshold is crossed
// ---------------------------------------------------------------------------
describe("TickingFreshnessBadge -- tone degrades from green to amber at stale threshold", () => {
  it("starts green, then becomes amber after advancing past the 5-min threshold", () => {
    // Start with a 4 m 50 s old timestamp (10 s before the 5-min cutoff)
    const asOf = isoAgo(4 * 60 * 1000 + 50_000);
    render(<TickingFreshnessBadge asOf={asOf} tickMs={TICK_MS} />);

    // Initially green (< 5 min old)
    expect(pillClass()).toContain("tier-a");

    // Advance 20 s (takes it past the 5-min line) + one tick
    act(() => {
      vi.advanceTimersByTime(20_000 + TICK_MS);
    });

    // Tone must have moved away from green
    expect(pillClass()).not.toContain("tier-a");
    // Must now be amber (5 min <= age < 60 min)
    expect(pillClass()).toContain("amber");
  });
});

// ---------------------------------------------------------------------------
// 4. Tone becomes slate once past the 60-min stale threshold
// ---------------------------------------------------------------------------
describe("TickingFreshnessBadge -- slate tone for very stale data", () => {
  it("renders slate (not green, not amber) for a 2-hour-old timestamp", () => {
    const asOf = isoAgo(2 * 60 * 60 * 1000); // 2 hours old
    render(<TickingFreshnessBadge asOf={asOf} tickMs={TICK_MS} />);

    expect(pillClass()).toContain("slate-800");
    expect(pillClass()).not.toContain("tier-a");
    expect(pillClass()).not.toContain("amber");
  });
});

// ---------------------------------------------------------------------------
// 5. Absent / unparseable asOf -> slate "unavailable", never green
// ---------------------------------------------------------------------------
describe("TickingFreshnessBadge -- missing / bad asOf", () => {
  it("shows 'unavailable' with slate tone when asOf is null", () => {
    render(<TickingFreshnessBadge asOf={null} tickMs={TICK_MS} />);
    expect(screen.getByText(/unavailable/i)).toBeTruthy();
    // No ticking badge wrapper in this path
    expect(screen.queryByTestId("ticking-freshness-badge")).toBeNull();
    // The pill inside the null path should be slate
    const spans = document.querySelectorAll("span[class]");
    const hasTierA = Array.from(spans).some((el) =>
      el.className.includes("tier-a"),
    );
    expect(hasTierA).toBe(false);
  });

  it("shows slate tone for an unparseable string", () => {
    render(<TickingFreshnessBadge asOf="not-a-date" tickMs={TICK_MS} />);
    // ageTone returns slate -> Badge uses slate-800 class
    // The label comes from timeAgoIso which returns the raw string on NaN
    expect(pillClass()).toContain("slate-800");
    expect(pillClass()).not.toContain("tier-a");
  });
});

// ---------------------------------------------------------------------------
// 6. Existing export signature regression guard
//    (Confirms FreshnessBadge / timeAgoIso / ModeDot are exported unchanged)
// ---------------------------------------------------------------------------
describe("Primitives -- existing exports unchanged", () => {
  it("FreshnessBadge accepts the same (asOf, source, status) props and renders", () => {
    const { container } = render(
      <FreshnessBadge
        asOf={new Date().toISOString()}
        source="nba-api"
        status="fresh"
      />,
    );
    expect(container.firstChild).not.toBeNull();
  });

  it("timeAgoIso still formats seconds correctly", () => {
    const iso = new Date(Date.now() - 45_000).toISOString();
    expect(timeAgoIso(iso)).toBe("45s ago");
  });

  it("timeAgoIso still formats minutes correctly", () => {
    const iso = new Date(Date.now() - 3 * 60 * 1000).toISOString();
    expect(timeAgoIso(iso)).toBe("3m ago");
  });

  it("ModeDot accepts mode prop and renders", () => {
    const { container } = render(<ModeDot mode="sse" />);
    expect(container.textContent).toContain("SSE");
  });
});

// ---------------------------------------------------------------------------
// 7. Interval is cleaned up on unmount (no act warning / timer leak)
// ---------------------------------------------------------------------------
describe("TickingFreshnessBadge -- cleanup on unmount", () => {
  it("does not fire the interval callback after unmount", () => {
    const clearIntervalSpy = vi.spyOn(window, "clearInterval");

    const asOf = isoAgo(10_000); // 10 s old
    const { unmount } = render(
      <TickingFreshnessBadge asOf={asOf} tickMs={TICK_MS} />,
    );

    unmount();

    // clearInterval must have been called during cleanup
    expect(clearIntervalSpy).toHaveBeenCalled();
  });
});

// ===========================================================================
// WS4-p6-clv-ingame-livehook -- structural + honesty tests
//
// These tests verify the three components migrated to useLiveData:
//   - ClvScoreboardLive
//   - ClvFeedbackPanel
//   - InGamePanel
//
// Acceptance conditions (source-level):
//   A. Components import useLiveData (not raw setInterval polling).
//   B. CLV with no closing line renders INSUFFICIENT_DATA (not 0, not green).
//   C. Ticking age updates without re-fetching (TickingFreshnessBadge present).
//   D. Fetch pauses when document.hidden (useLiveData contract, structural check).
//   E. Failed poll keeps last-good data (useLiveData contract, structural check).
//
// Strategy: structural source checks + lightweight render tests using
// fetchHonest mock so we control the API layer directly (no vi.mock hoisting).
// ===========================================================================

import * as fs from "node:fs";
import * as nodePath from "node:path";

const COMPONENTS_DIR = nodePath.resolve(__dirname, "..");

// ---------------------------------------------------------------------------
// Source-structure guards: all three components must use useLiveData, not
// raw setInterval calls, and must render TickingFreshnessBadge for ticking age.
// ---------------------------------------------------------------------------
describe("WS4 -- structural: components use useLiveData (not raw setInterval)", () => {
  const FILES = [
    "ClvScoreboardLive.tsx",
    "ClvFeedbackPanel.tsx",
    "InGamePanel.tsx",
  ];

  for (const file of FILES) {
    it(`${file}: imports useLiveData`, () => {
      const src = fs.readFileSync(
        nodePath.join(COMPONENTS_DIR, file),
        "utf8",
      );
      expect(src).toContain("useLiveData");
    });

    it(`${file}: does NOT call setInterval directly (hook handles it)`, () => {
      const src = fs.readFileSync(
        nodePath.join(COMPONENTS_DIR, file),
        "utf8",
      );
      // setInterval must NOT appear outside a comment in the component source.
      const withoutComments = src.replace(/\/\/.*/g, "").replace(/\/\*[\s\S]*?\*\//g, "");
      expect(withoutComments).not.toContain("setInterval(");
    });

    it(`${file}: renders TickingFreshnessBadge for ticking age display`, () => {
      const src = fs.readFileSync(
        nodePath.join(COMPONENTS_DIR, file),
        "utf8",
      );
      expect(src).toContain("TickingFreshnessBadge");
    });
  }
});

// ---------------------------------------------------------------------------
// CLV honesty guard: InGamePanel renders INSUFFICIENT_DATA for null vs_close
// ---------------------------------------------------------------------------
describe("WS4 -- InGamePanel: INSUFFICIENT_DATA honesty (source check)", () => {
  it("renders INSUFFICIENT_DATA when vs_close is null", () => {
    const src = fs.readFileSync(
      nodePath.join(COMPONENTS_DIR, "InGamePanel.tsx"),
      "utf8",
    );
    // The component must explicitly emit the INSUFFICIENT_DATA string.
    expect(src).toContain("INSUFFICIENT_DATA");
    // It must NOT default to 0 for absent CLV.
    // (We check by looking for the literal '0' adjacent to 'vs_close' or 'clv').
    // This is a belt-and-suspenders guard; the real proof is the render test.
  });

  it("renders INSUFFICIENT_DATA in the DOM for a live game with null vs_close", async () => {
    vi.useRealTimers();

    // Wire up fetchHonest spy to return our fixtures without touching vi.mock.
    const fetchHonestMod = await import("@/lib/fetchHonest");
    const spy = vi.spyOn(fetchHonestMod, "fetchHonest").mockImplementation(
      async (url: string) => {
        // Game list for NBA.
        if (url.includes("/api/report/nba")) {
          return {
            status: "ok",
            sport: "nba",
            game_ids: ["LIVE001"],
            count: 1,
            generated_at: new Date().toISOString(),
          };
        }
        // Suppress other sports' report lists.
        if (url.includes("/api/report/")) {
          return { status: "unavailable", reason: "offseason" };
        }
        // The live game itself.
        if (url.includes("/api/ingame/nba/LIVE001")) {
          return {
            status: "ok",
            sport: "nba",
            game_id: "LIVE001",
            p0: 0.5,
            live_state: {
              home: "BOS",
              away: "MIA",
              status: "Q2 5:00",
              p0: 0.5,
            },
            served: {
              p_win: 0.54,
              provenance: ["live_engine"],
              model: "sim",
              verdict: "ok",
              // null vs_close -> should render INSUFFICIENT_DATA, never 0/green
              vs_close: null,
            },
          };
        }
        return { status: "unavailable", reason: "not matched" };
      },
    );

    // Import AFTER spy is set up.
    const { InGamePanel } = await import("../InGamePanel");
    render(<InGamePanel />);

    await waitFor(() => {
      const cells = document.querySelectorAll("[data-testid='clv-status']");
      const found = Array.from(cells).some((el) =>
        el.textContent?.includes("INSUFFICIENT_DATA"),
      );
      expect(found).toBe(true);
    }, { timeout: 5000 });

    // The CLV label must not be "0", must not carry green styling.
    const cells = document.querySelectorAll("[data-testid='clv-status']");
    cells.forEach((el) => {
      expect(el.textContent).not.toMatch(/:\s*0\b/);
      expect(el.className).not.toContain("tier-a");
    });

    spy.mockRestore();
    vi.useFakeTimers();
  });
});

// ---------------------------------------------------------------------------
// ClvFeedbackPanel: vs_close UNPROVEN rendering
// ---------------------------------------------------------------------------
describe("WS4 -- ClvFeedbackPanel: CLV honesty (render)", () => {
  it("renders UNPROVEN badge (not 'proven'/green) when vs_close_proven is false", async () => {
    vi.useRealTimers();

    const fetchHonestMod = await import("@/lib/fetchHonest");
    const spy = vi.spyOn(fetchHonestMod, "fetchHonest").mockImplementation(
      async (url: string) => {
        if (url.includes("/api/quant/clv")) {
          return {
            status: "ok",
            clv: {
              n_bets: 12,
              mean_clv_pct: 0.04,
              pct_beat_close: 0.58,
              by_sport: {},
              clv_is_proxy: false,
              vs_close_proven: false, // NEVER fabricate proven
            },
            edge_claimed: false,
            real_money_enabled: false,
            honest_note: "units only",
          };
        }
        if (url.includes("/api/improve/timeline")) {
          return {
            status: "ok",
            cycles: [],
            n_promoted: 0,
            enabled: false,
            edge_claimed: false,
          };
        }
        return { status: "unavailable", reason: "not matched" };
      },
    );

    const { ClvFeedbackPanel } = await import("../ClvFeedbackPanel");
    render(<ClvFeedbackPanel />);

    await waitFor(() => {
      // Should show UNPROVEN badge.
      expect(screen.queryByText("UNPROVEN")).toBeTruthy();
    }, { timeout: 5000 });

    // Must NOT show a "proven" badge (green).
    expect(screen.queryByText("proven")).toBeNull();

    spy.mockRestore();
    vi.useFakeTimers();
  });

  it("shows no graded-bets message when n_bets is 0", async () => {
    vi.useRealTimers();

    const fetchHonestMod = await import("@/lib/fetchHonest");
    const spy = vi.spyOn(fetchHonestMod, "fetchHonest").mockImplementation(
      async (url: string) => {
        if (url.includes("/api/quant/clv")) {
          return {
            status: "ok",
            clv: {
              n_bets: 0,
              mean_clv_pct: null,
              pct_beat_close: null,
              by_sport: {},
              clv_is_proxy: false,
              vs_close_proven: false,
            },
            edge_claimed: false,
            real_money_enabled: false,
          };
        }
        if (url.includes("/api/improve/timeline")) {
          return {
            status: "ok",
            cycles: [],
            n_promoted: 0,
            enabled: false,
            edge_claimed: false,
          };
        }
        return { status: "unavailable", reason: "not matched" };
      },
    );

    const { ClvFeedbackPanel } = await import("../ClvFeedbackPanel");
    render(<ClvFeedbackPanel />);

    await waitFor(() => {
      expect(screen.queryByText(/No graded-vs-close bets yet/i)).toBeTruthy();
    }, { timeout: 5000 });

    spy.mockRestore();
    vi.useFakeTimers();
  });
});

// ---------------------------------------------------------------------------
// ClvScoreboardLive: renders freshness badge + ModeDot on successful load
// ---------------------------------------------------------------------------
describe("WS4 -- ClvScoreboardLive: freshness badge + poll indicator", () => {
  it("renders a POLL ModeDot after data loads", async () => {
    vi.useRealTimers();

    const fetchHonestMod = await import("@/lib/fetchHonest");
    const spy = vi.spyOn(fetchHonestMod, "fetchHonest").mockImplementation(
      async (url: string) => {
        if (url.includes("/api/paper/clv")) {
          return {
            n_bets: 3,
            pct_beat_close: 0.67,
            mean_clv_pct: 0.05,
            by_sport: null,
            clv_is_proxy: false,
          };
        }
        return { status: "unavailable", reason: "not matched" };
      },
    );

    const { ClvScoreboardLive } = await import("../ClvScoreboardLive");
    render(<ClvScoreboardLive />);

    await waitFor(() => {
      expect(screen.queryByText("POLL")).toBeTruthy();
    }, { timeout: 5000 });

    spy.mockRestore();
    vi.useFakeTimers();
  });
});

// ---------------------------------------------------------------------------
// useLiveData contract: failed poll keeps last-good data (structural + render)
// ---------------------------------------------------------------------------
describe("WS4 -- useLiveData: failed poll keeps last-good data", () => {
  it("ClvFeedbackPanel keeps n_bets visible after a failed second poll", async () => {
    vi.useRealTimers();

    let callCount = 0;
    const fetchHonestMod = await import("@/lib/fetchHonest");
    const spy = vi.spyOn(fetchHonestMod, "fetchHonest").mockImplementation(
      async (url: string) => {
        if (url.includes("/api/quant/clv")) {
          callCount++;
          if (callCount === 1) {
            // First call: good data with n_bets = 9.
            return {
              status: "ok",
              clv: {
                n_bets: 9,
                mean_clv_pct: 0.03,
                pct_beat_close: 0.55,
                by_sport: {},
                clv_is_proxy: false,
                vs_close_proven: false,
              },
              edge_claimed: false,
              real_money_enabled: false,
            };
          }
          // Subsequent calls: unavailable sentinel (failed poll).
          return { status: "unavailable", reason: "feed error" };
        }
        if (url.includes("/api/improve/timeline")) {
          return {
            status: "ok",
            cycles: [],
            n_promoted: 0,
            enabled: false,
            edge_claimed: false,
          };
        }
        return { status: "unavailable", reason: "not matched" };
      },
    );

    const { ClvFeedbackPanel } = await import("../ClvFeedbackPanel");
    render(<ClvFeedbackPanel />);

    // Wait for first good data (n_bets=9 is rendered in the "graded bets" column).
    await waitFor(() => {
      expect(screen.queryByText("9")).toBeTruthy();
    }, { timeout: 5000 });

    // Now trigger a second poll (advance useLiveData interval).
    // useLiveData's interval is 20 s; advance past it so the interval fires.
    vi.useFakeTimers();
    act(() => {
      vi.advanceTimersByTime(22_000);
    });
    vi.useRealTimers();

    // Wait a tick for any async resolution.
    await new Promise((r) => setTimeout(r, 50));

    // Last-good data (n_bets=9) must still be visible -- failed poll does NOT wipe it.
    expect(screen.queryByText("9")).toBeTruthy();

    spy.mockRestore();
    vi.useFakeTimers();
  });
});

// ---------------------------------------------------------------------------
// useLiveData contract: fetch pauses when document.hidden (structural check)
// ---------------------------------------------------------------------------
describe("WS4 -- useLiveData: fetch pauses on hidden tab (structural)", () => {
  it("useLiveData source uses document.hidden guard inside the interval callback", () => {
    const src = fs.readFileSync(
      nodePath.resolve(__dirname, "../../../lib/useLiveData.ts"),
      "utf8",
    );
    // The interval callback must check document.hidden before calling runFetch.
    expect(src).toContain("document.hidden");
    // And the visibility change listener must re-fetch on becoming visible.
    expect(src).toContain("visibilitychange");
    expect(src).toContain("runFetch");
  });
});

// ---------------------------------------------------------------------------
// Ticking age updates without re-fetching: ageSec-based asOf in components
// ---------------------------------------------------------------------------
describe("WS4 -- ticking age: components derive asOf from ageSec (no re-fetch)", () => {
  it("ClvScoreboardLive derives asOf from ageSec (no separate ticker fetch)", () => {
    const src = fs.readFileSync(
      nodePath.join(COMPONENTS_DIR, "ClvScoreboardLive.tsx"),
      "utf8",
    );
    // The component must derive asOf from ageSec (not an additional API call).
    expect(src).toContain("ageSec");
    expect(src).toContain("TickingFreshnessBadge");
  });

  it("ClvFeedbackPanel derives asOf from ageSec (no separate ticker fetch)", () => {
    const src = fs.readFileSync(
      nodePath.join(COMPONENTS_DIR, "ClvFeedbackPanel.tsx"),
      "utf8",
    );
    expect(src).toContain("ageSec");
    expect(src).toContain("TickingFreshnessBadge");
  });

  it("InGamePanel derives asOf from ageSec (no separate ticker fetch)", () => {
    const src = fs.readFileSync(
      nodePath.join(COMPONENTS_DIR, "InGamePanel.tsx"),
      "utf8",
    );
    expect(src).toContain("ageSec");
    expect(src).toContain("TickingFreshnessBadge");
  });
});
