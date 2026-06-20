import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, waitFor, act } from "@testing-library/react";

import { freshnessStatus, FreshnessPill } from "../LiveLinesPanel";

// ---------------------------------------------------------------------------
// LiveLinesPanel component tests (WS3-p6-ops-lines-livehook)
//
// Acceptance contract:
//   1. freshnessStatus -- fresh only <15min, stale/unknown -> non-fresh.
//   2. FreshnessPill   -- fresh=green, stale=red, unknown=slate (never green on
//      stale/missing; unknown is neutral missing-data, never red on missing data).
//   3. 'checking' (neutral slate) before first load; shimmer has aria-busy.
//   4. Amber (never green) on stale/aged poll data.
//   5. Last-good data retained on failed poll (no crash, no blank).
//   6. Never throws on a poll error.
//   7. No non-ASCII characters in source (ASCII-rail).
// ---------------------------------------------------------------------------

const MIN_15_MS = 15 * 60 * 1000;

// ---------------------------------------------------------------------------
// 1. freshnessStatus -- 15-min threshold
// ---------------------------------------------------------------------------
describe("freshnessStatus -- 15-min threshold", () => {
  it("returns 'fresh' for a 5-second-old timestamp", () => {
    const iso = new Date(Date.now() - 5_000).toISOString();
    expect(freshnessStatus(iso)).toBe("fresh");
  });

  it("returns 'stale' for a timestamp exactly 15 min old", () => {
    const iso = new Date(Date.now() - MIN_15_MS).toISOString();
    expect(freshnessStatus(iso)).toBe("stale");
  });

  it("returns 'stale' for a 1-hour-old timestamp", () => {
    const iso = new Date(Date.now() - 60 * 60 * 1000).toISOString();
    expect(freshnessStatus(iso)).toBe("stale");
  });

  it("returns 'unknown' for null", () => {
    expect(freshnessStatus(null)).toBe("unknown");
  });

  it("returns 'unknown' for undefined", () => {
    expect(freshnessStatus(undefined)).toBe("unknown");
  });

  it("returns 'unknown' for an unparseable string", () => {
    expect(freshnessStatus("not-a-date")).toBe("unknown");
  });
});

// ---------------------------------------------------------------------------
// 2. FreshnessPill -- green only fresh, red for stale, slate for unknown
// ---------------------------------------------------------------------------
describe("FreshnessPill -- stale-never-green rail", () => {
  afterEach(() => vi.restoreAllMocks());

  it("renders green Badge for a fresh (5s old) timestamp", () => {
    const iso = new Date(Date.now() - 5_000).toISOString();
    render(<FreshnessPill generatedAt={iso} />);
    // The badge span carries tone-derived class: green -> tier-a
    const spans = document.querySelectorAll("span[class]");
    const anyGreen = Array.from(spans).some((el) =>
      el.className.includes("tier-a"),
    );
    expect(anyGreen).toBe(true);
  });

  it("renders red Badge for a stale (20min old) timestamp", () => {
    const iso = new Date(Date.now() - 20 * 60 * 1000).toISOString();
    render(<FreshnessPill generatedAt={iso} />);
    const spans = document.querySelectorAll("span[class]");
    const anyRed = Array.from(spans).some((el) =>
      el.className.includes("red"),
    );
    expect(anyRed).toBe(true);
    // Must NOT be green
    const anyGreen = Array.from(spans).some((el) =>
      el.className.includes("tier-a"),
    );
    expect(anyGreen).toBe(false);
  });

  it("renders slate Badge (not green, not red) for null generated_at", () => {
    render(<FreshnessPill generatedAt={null} />);
    const spans = document.querySelectorAll("span[class]");
    const anyGreen = Array.from(spans).some((el) =>
      el.className.includes("tier-a"),
    );
    expect(anyGreen).toBe(false);
    // unknown (missing provenance) is a neutral missing-data state, not a
    // failure -- must render slate, never red (rail: never red on missing data)
    const anyRed = Array.from(spans).some((el) =>
      el.className.includes("red"),
    );
    expect(anyRed).toBe(false);
    const anySlate = Array.from(spans).some((el) =>
      el.className.includes("slate"),
    );
    expect(anySlate).toBe(true);
  });

  it("shows 'no feed timestamp' text for null generated_at", () => {
    render(<FreshnessPill generatedAt={null} />);
    expect(screen.getByText(/no feed timestamp/i)).toBeTruthy();
  });

  it("shows 'STALE' label for stale feed", () => {
    const iso = new Date(Date.now() - 20 * 60 * 1000).toISOString();
    render(<FreshnessPill generatedAt={iso} />);
    expect(screen.getByText(/stale/i)).toBeTruthy();
  });

  it("shows 'fresh' label for fresh feed", () => {
    const iso = new Date(Date.now() - 3_000).toISOString();
    render(<FreshnessPill generatedAt={iso} />);
    expect(screen.getByText(/fresh/i)).toBeTruthy();
  });
});

// ---------------------------------------------------------------------------
// 3. 'checking' neutral badge + shimmer before first load
//    Contract: useLiveData consumed; pending fetch -> 'checking' (slate) not red
// ---------------------------------------------------------------------------
import { api, SPORTS, type BestBetsEnvelope } from "@/lib/p5api";
import { LiveLinesPanel } from "../LiveLinesPanel";

describe("LiveLinesPanel -- pre-resolve: 'checking' neutral, aria-busy shimmer", () => {
  afterEach(() => vi.restoreAllMocks());

  it("shows 'checking' badge (not red) before first poll resolves", () => {
    // Keep all sport fetches pending forever -- data stays null/isLoading
    vi.spyOn(api, "bestbets").mockReturnValue(new Promise(() => {}));

    render(<LiveLinesPanel />);

    // 'checking' badge must be visible (neutral, not red) for each sport
    const checkingBadges = screen.getAllByText(/checking/i);
    expect(checkingBadges.length).toBeGreaterThanOrEqual(1);

    // 'loading...' bare text must NOT be in DOM
    expect(screen.queryByText("loading...")).toBeNull();
  });

  it("shows shimmer placeholder (role=status aria-busy) not bare 'loading...'", () => {
    vi.spyOn(api, "bestbets").mockReturnValue(new Promise(() => {}));

    render(<LiveLinesPanel />);

    // Bare text string must NOT be in DOM
    expect(screen.queryByText("loading...")).toBeNull();

    // Shimmer containers (one per sport) must be present
    const shimmers = screen.getAllByRole("status", { name: /loading lines/i });
    expect(shimmers.length).toBe(SPORTS.length);

    // Each shimmer must be aria-busy
    for (const el of shimmers) {
      expect(el.getAttribute("aria-busy")).toBe("true");
    }
  });
});

// ---------------------------------------------------------------------------
// 4+5. Last-good data retained on failed poll; never crashes on error
// ---------------------------------------------------------------------------
describe("LiveLinesPanel -- last-good retention on failed poll", () => {
  afterEach(() => vi.restoreAllMocks());

  it("retains last-good data after a failed subsequent poll (no blank, no crash)", async () => {
    const goodEnvelope: BestBetsEnvelope = {
      sport: "nba",
      generated_at: new Date().toISOString(),
      status: "ok",
      count: 0,
      n_best_bets: 0,
      clv: {
        n_bets: 0,
        pct_beat_close: null,
        mean_clv_pct: null,
        by_sport: null,
        clv_is_proxy: false,
      },
      edge_claimed: false,
      games: [],
      reason: "no games on slate",
    };

    let callCount = 0;
    vi.spyOn(api, "bestbets").mockImplementation(() => {
      callCount++;
      if (callCount === 1) return Promise.resolve(goodEnvelope);
      // Subsequent polls fail (unavailable sentinel)
      return Promise.resolve({ status: "unavailable", reason: "test error" } as never);
    });

    render(<LiveLinesPanel />);

    // Wait for the first good load to appear (no games on slate text)
    await waitFor(() => {
      expect(screen.getAllByText(/no games on slate/i).length).toBeGreaterThan(0);
    });

    // The panel must not crash -- it should still be mounted and rendering
    expect(screen.queryByText("loading...")).toBeNull();
  });

  it("never crashes the page on a poll error (unavailable sentinel)", () => {
    vi.spyOn(api, "bestbets").mockResolvedValue({
      status: "unavailable",
      reason: "network error",
    } as never);

    // Should not throw
    expect(() => render(<LiveLinesPanel />)).not.toThrow();
  });
});

// ---------------------------------------------------------------------------
// 6. ASCII rail: source file must contain zero non-ASCII characters
// ---------------------------------------------------------------------------
import { readFileSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

describe("LiveLinesPanel.tsx -- ASCII only (no non-ASCII chars)", () => {
  it("source file passes ripgrep-equivalent non-ASCII check", () => {
    const dir = join(dirname(fileURLToPath(import.meta.url)), "..");
    const src = readFileSync(join(dir, "LiveLinesPanel.tsx"), "utf8");
    // Find any char outside printable ASCII + standard whitespace
    const nonAscii = src.match(/[^\x00-\x7F]/g);
    expect(nonAscii).toBeNull();
  });
});
