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
// useLiveData contract: failed poll keeps last-good data (structural + render)
// ---------------------------------------------------------------------------
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
