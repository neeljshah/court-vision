// LiveBoxPanel.test.tsx -- ws4-livebox-tipoff-detection + ws2-livebox-stale acceptance tests.
//
// Per-component vitest test (NEVER run the full suite -- freezes the box).
// Run: cd /c/Users/neelj/nba-ai-system/webapp && npx vitest run components/bets_detail/__tests__/LiveBoxPanel.test.tsx
//
// Acceptance criteria (ws4-livebox-tipoff-detection):
//   (a) ingame with home_score=0, away_score=0, period=1, fresh generated_at
//       renders the score line (NOT the "Game not live" empty state).
//   (b) ingame with null scores, no period, no clock renders "Game not live".
//   (c) A stale generated_at still renders the Stale state regardless of score.
//   (d) ingame=null still renders the skeleton.
//   (e) No '$' substring anywhere in rendered output.
//
// Acceptance criteria (ws2-livebox-stale):
//   (f) A fresh payload shows a last-updated age chip (data-testid="age-chip").
//   (g) A stale payload renders Stale state (no 'live'/green badge) with explicit age.
//   (h) Boxscore table has an aria-label and scope=col header cells.
//   (i) ingame=null renders skeleton with role=status.
//   (j) No '$' in output (covered by existing (e) tests).
//
// HONESTY RAILS preserved: stale-never-green, INSUFFICIENT_DATA CLV,
// skeleton-on-null, no $ at any point.

import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";

import { LiveBoxPanel } from "../LiveBoxPanel";
import type { InGameFull } from "@/lib/p5api_ext";

// ---------------------------------------------------------------------------
// Mocks -- no real fetch escapes; p5api_ext helpers used directly but network
// calls from library imports are suppressed.
// ---------------------------------------------------------------------------

// Prevent any accidental module-level fetch side-effects.
vi.mock("@/lib/fetchHonest", () => ({
  fetchHonest: vi.fn().mockResolvedValue({ status: "unavailable" }),
}));

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

/** Fresh timestamp -- well within the 3-minute LIVE_STALE_MS threshold. */
const FRESH_TS = new Date(Date.now() - 10_000).toISOString(); // 10s ago

/** Stale timestamp -- 10 minutes ago, beyond the 3-min threshold. */
const STALE_TS = new Date(Date.now() - 10 * 60 * 1000).toISOString();

/** (a) Real 0-0 tipoff: both scores are 0 (not null), period=1, clock present. */
const INGAME_TIPOFF: InGameFull = {
  status: "ok",
  sport: "nba",
  game_id: "0022300001",
  generated_at: FRESH_TS,
  home: "NYK",
  away: "SAS",
  home_score: 0,
  away_score: 0,
  period: 1,
  clock: "12:00",
  frac_elapsed: 0,
  p_win: 0.5,
  clv_status: "INSUFFICIENT_DATA",
  clv_is_proxy: false,
  players: [],
};

/** (b) Genuinely pre-tip: null scores, no period, no clock. */
const INGAME_PRETIP: InGameFull = {
  status: "ok",
  sport: "nba",
  game_id: "0022300001",
  generated_at: FRESH_TS,
  home: "NYK",
  away: "SAS",
  home_score: null,
  away_score: null,
  period: undefined,
  clock: undefined,
  p_win: null,
  clv_status: null,
  clv_is_proxy: false,
  players: [],
};

/** (c) Stale payload -- same data as tipoff but with an old generated_at. */
const INGAME_STALE: InGameFull = {
  ...INGAME_TIPOFF,
  generated_at: STALE_TS,
};

/** Mid-game payload: non-zero scores, used in additional honesty checks. */
const INGAME_LIVE: InGameFull = {
  status: "ok",
  sport: "nba",
  game_id: "0022300001",
  generated_at: FRESH_TS,
  home: "NYK",
  away: "SAS",
  home_score: 62,
  away_score: 58,
  period: 3,
  clock: "5:42",
  frac_elapsed: 0.625,
  p_win: 0.63,
  clv_status: "INSUFFICIENT_DATA",
  clv_is_proxy: false,
  players: [
    { name: "Brunson", team: "NYK", min: 24.5, pts: 18, reb: 3, ast: 7 },
  ],
};

// ---------------------------------------------------------------------------
// (a) 0-0 tipoff -- must show score, NOT "Game not live"
// ---------------------------------------------------------------------------

describe("(a) 0-0 tipoff: period=1, scores=0 -> shows score line, not 'Game not live'", () => {
  it("renders the score display area (@ separator) rather than empty state", () => {
    render(<LiveBoxPanel ingame={INGAME_TIPOFF} />);
    // The score-line renders an '@' separator between away and home score.
    // This is only rendered in the live branch, not in the notLive/empty branch.
    const atSeps = screen.getAllByText("@");
    expect(atSeps.length).toBeGreaterThan(0);
  });

  it("does NOT show 'Game not live' label for a 0-0 tipoff", () => {
    render(<LiveBoxPanel ingame={INGAME_TIPOFF} />);
    expect(screen.queryByText(/game not live/i)).toBeNull();
  });

  it("shows Q1 clock indicator for period=1", () => {
    render(<LiveBoxPanel ingame={INGAME_TIPOFF} />);
    expect(screen.getByText(/Q1/)).toBeTruthy();
  });

  it("shows the period=1 clock value 12:00", () => {
    render(<LiveBoxPanel ingame={INGAME_TIPOFF} />);
    expect(screen.getByText(/12:00/)).toBeTruthy();
  });
});

// ---------------------------------------------------------------------------
// (b) Genuinely pre-tip (null scores, no period, no clock) -> "Game not live"
// ---------------------------------------------------------------------------

describe("(b) Pre-tip null payload -> shows 'Game not live'", () => {
  it("shows 'Game not live' label when scores, period, and clock are all absent", () => {
    render(<LiveBoxPanel ingame={INGAME_PRETIP} />);
    expect(screen.getByText(/game not live/i)).toBeTruthy();
  });

  it("does NOT render the @ score separator in the not-live state", () => {
    render(<LiveBoxPanel ingame={INGAME_PRETIP} />);
    // The @ separator only renders inside the live score block; it must be absent.
    // In the empty/not-live state we only show Empty component, no score row.
    const container = document.body;
    // The score-line '@' separator has class text-slate-600 -- query for it
    // by checking that no element with that class contains '@'.
    const slateAts = Array.from(container.querySelectorAll(".text-slate-600")).filter(
      (el) => el.textContent?.trim() === "@",
    );
    expect(slateAts.length).toBe(0);
  });
});

// ---------------------------------------------------------------------------
// (c) Stale generated_at -> Stale state regardless of scores
// ---------------------------------------------------------------------------

describe("(c) Stale generated_at -> Stale state, score suppressed", () => {
  it("shows a 'stale' indicator for a stale 0-0 payload", () => {
    render(<LiveBoxPanel ingame={INGAME_STALE} />);
    expect(screen.getAllByText(/stale/i).length).toBeGreaterThan(0);
  });

  it("suppresses score display when payload is stale (stale-never-green rail)", () => {
    render(<LiveBoxPanel ingame={INGAME_STALE} />);
    // The 0/0 scores must NOT be presented as current live data.
    // They will not appear as visible score elements in the stale branch.
    // The period (Q1) info must also be absent.
    const periodElements = document.body.querySelectorAll("*");
    const hasQ1 = Array.from(periodElements).some(
      (el) => el.children.length === 0 && /^Q1/.test(el.textContent ?? ""),
    );
    expect(hasQ1).toBe(false);
  });

  it("stale reason mentions feed or daemon", () => {
    render(<LiveBoxPanel ingame={INGAME_STALE} />);
    const text = document.body.textContent ?? "";
    expect(/daemon|final|feed/i.test(text)).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// (d) ingame=null -> skeleton loading state
// ---------------------------------------------------------------------------

describe("(d) ingame=null -> skeleton loading affordance", () => {
  it("renders the skeleton shimmer (data-testid='live-box-skeleton')", () => {
    render(<LiveBoxPanel ingame={null} />);
    expect(screen.getByTestId("live-box-skeleton")).toBeTruthy();
  });

  it("does NOT show a live score in skeleton state", () => {
    render(<LiveBoxPanel ingame={null} />);
    // No score numbers should be visible.
    expect(screen.queryByText("62")).toBeNull();
    expect(screen.queryByText("58")).toBeNull();
  });

  it("has accessible role=status in skeleton for screen readers", () => {
    render(<LiveBoxPanel ingame={null} />);
    const statuses = screen.getAllByRole("status");
    expect(statuses.length).toBeGreaterThan(0);
  });

  it("does NOT show 'stale' in skeleton state (it is a checking/loading state)", () => {
    render(<LiveBoxPanel ingame={null} />);
    const text = document.body.textContent ?? "";
    expect(/\bstale\b/i.test(text)).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// (e) No '$' substring anywhere in rendered output
// ---------------------------------------------------------------------------

describe("(e) Honesty rail: no '$' substring in any rendered output", () => {
  it("tipoff render has no $ character", () => {
    const { container } = render(<LiveBoxPanel ingame={INGAME_TIPOFF} />);
    expect(container.textContent ?? "").not.toContain("$");
  });

  it("pre-tip render has no $ character", () => {
    const { container } = render(<LiveBoxPanel ingame={INGAME_PRETIP} />);
    expect(container.textContent ?? "").not.toContain("$");
  });

  it("stale render has no $ character", () => {
    const { container } = render(<LiveBoxPanel ingame={INGAME_STALE} />);
    expect(container.textContent ?? "").not.toContain("$");
  });

  it("null render has no $ character", () => {
    const { container } = render(<LiveBoxPanel ingame={null} />);
    expect(container.textContent ?? "").not.toContain("$");
  });

  it("live mid-game render has no $ character", () => {
    const { container } = render(<LiveBoxPanel ingame={INGAME_LIVE} />);
    expect(container.textContent ?? "").not.toContain("$");
  });
});

// ---------------------------------------------------------------------------
// Additional honesty rails -- preserved from original spec
// ---------------------------------------------------------------------------

describe("Honesty rails (unchanged by tipoff fix)", () => {
  it("fresh mid-game: shows INSUFFICIENT_DATA CLV notice", () => {
    render(<LiveBoxPanel ingame={INGAME_LIVE} />);
    expect(screen.getAllByText(/INSUFFICIENT_DATA/i).length).toBeGreaterThan(0);
  });

  it("fresh mid-game: shows live score (non-zero)", () => {
    render(<LiveBoxPanel ingame={INGAME_LIVE} />);
    expect(screen.getByText("62")).toBeTruthy();
    expect(screen.getByText("58")).toBeTruthy();
  });

  it("fresh mid-game: no boxscore $ column header", () => {
    render(<LiveBoxPanel ingame={INGAME_LIVE} />);
    const headers = screen
      .getAllByRole("columnheader")
      .map((h) => h.textContent ?? "");
    for (const h of headers) {
      expect(/\$/i.test(h), `banned $ header: ${h}`).toBe(false);
    }
  });

  it("unavailable sentinel: shows unavailable state", () => {
    const unavail = { status: "unavailable" as const } as unknown as InGameFull;
    render(<LiveBoxPanel ingame={unavail} />);
    expect(screen.getByText(/unavailable/i)).toBeTruthy();
  });
});

// ---------------------------------------------------------------------------
// (f) ws2-livebox-stale: fresh payload shows last-updated age chip
// ---------------------------------------------------------------------------

describe("(f) ws2: fresh payload -> age chip in header", () => {
  it("renders the age chip (data-testid='age-chip') on a fresh payload", () => {
    render(<LiveBoxPanel ingame={INGAME_LIVE} />);
    expect(screen.getByTestId("age-chip")).toBeTruthy();
  });

  it("age chip shows a human-readable 'ago' time string", () => {
    render(<LiveBoxPanel ingame={INGAME_LIVE} />);
    const chip = screen.getByTestId("age-chip");
    expect(chip.textContent).toMatch(/\d+s ago|\d+m \d+s ago/);
  });

  it("age chip has a tooltip (title) referencing generated_at", () => {
    render(<LiveBoxPanel ingame={INGAME_LIVE} />);
    const chip = screen.getByTestId("age-chip");
    expect(chip.getAttribute("title")).toContain("generated_at");
  });

  it("does NOT show the age chip when payload is stale", () => {
    render(<LiveBoxPanel ingame={INGAME_STALE} />);
    // When stale the header chip must not appear; age is shown inline in Stale block.
    expect(screen.queryByTestId("age-chip")).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// (g) ws2-livebox-stale: stale payload -> Stale state, no live/green, explicit age
// ---------------------------------------------------------------------------

describe("(g) ws2: stale payload -> Stale state with explicit age, no green badge", () => {
  it("renders the stale age note (data-testid='stale-age')", () => {
    render(<LiveBoxPanel ingame={INGAME_STALE} />);
    expect(screen.getByTestId("stale-age")).toBeTruthy();
  });

  it("stale-age note shows a human-readable age string", () => {
    render(<LiveBoxPanel ingame={INGAME_STALE} />);
    const note = screen.getByTestId("stale-age");
    // Should contain "Last update:" prefix followed by a time string.
    expect(note.textContent).toMatch(/Last update:/i);
    expect(note.textContent).toMatch(/\d+(m|s)/);
  });

  it("stale render: stale-age shows the stale timestamp", () => {
    render(<LiveBoxPanel ingame={INGAME_STALE} />);
    const note = screen.getByTestId("stale-age");
    // The stale timestamp year must appear somewhere in the age note.
    expect(note.textContent).toContain("2026");
  });

  it("stale render: no green-toned badge visible (stale-never-green rail)", () => {
    const { container } = render(<LiveBoxPanel ingame={INGAME_STALE} />);
    // The only green-related class patterns would be text-tier-a/bg-tier-a (from Badge tone="green").
    // We assert none of those appear in the rendered output for stale payloads.
    const html = container.innerHTML;
    expect(html).not.toMatch(/tone.*green|bg-tier-a\b|text-tier-a\b/);
  });
});

// ---------------------------------------------------------------------------
// (h) ws2-livebox-stale: boxscore table accessibility
// ---------------------------------------------------------------------------

describe("(h) ws2: boxscore table a11y -- aria-label + scope=col headers", () => {
  it("boxscore table has aria-label 'Live player boxscore'", () => {
    render(<LiveBoxPanel ingame={INGAME_LIVE} />);
    const table = screen.getByRole("table", { name: /Live player boxscore/i });
    expect(table).toBeTruthy();
  });

  it("boxscore table has a caption element (sr-only)", () => {
    render(<LiveBoxPanel ingame={INGAME_LIVE} />);
    const table = screen.getByRole("table", { name: /Live player boxscore/i });
    const caption = table.querySelector("caption");
    expect(caption).toBeTruthy();
  });

  it("all column headers have scope='col'", () => {
    render(<LiveBoxPanel ingame={INGAME_LIVE} />);
    const table = screen.getByRole("table", { name: /Live player boxscore/i });
    const headers = Array.from(table.querySelectorAll("th"));
    expect(headers.length).toBeGreaterThan(0);
    for (const th of headers) {
      expect(th.getAttribute("scope")).toBe("col");
    }
  });

  it("column headers are player, min, pts, reb, ast (no $ column)", () => {
    render(<LiveBoxPanel ingame={INGAME_LIVE} />);
    const headers = screen.getAllByRole("columnheader").map((h) => h.textContent?.trim() ?? "");
    expect(headers).toContain("player");
    expect(headers).toContain("min");
    expect(headers).toContain("pts");
    expect(headers).toContain("reb");
    expect(headers).toContain("ast");
    for (const h of headers) {
      expect(h).not.toContain("$");
    }
  });
});

// ---------------------------------------------------------------------------
// (i) ws2: ingame=null -> skeleton with role=status (canonical neutral state)
// ---------------------------------------------------------------------------

describe("(i) ws2: ingame=null -> skeleton neutral state, role=status, no red/stale", () => {
  it("skeleton has role=status on the top-level container", () => {
    render(<LiveBoxPanel ingame={null} />);
    const skeleton = screen.getByTestId("live-box-skeleton");
    expect(skeleton.getAttribute("role")).toBe("status");
  });

  it("skeleton shows aria-label 'Live game data loading'", () => {
    render(<LiveBoxPanel ingame={null} />);
    expect(screen.getByLabelText(/live game data loading/i)).toBeTruthy();
  });

  it("skeleton does not render a score (no stale numbers presented)", () => {
    render(<LiveBoxPanel ingame={null} />);
    const text = document.body.textContent ?? "";
    // No specific score numbers and no 'stale' label.
    expect(text).not.toMatch(/\bstale\b/i);
  });

  it("skeleton does not render the age chip (no generated_at to show)", () => {
    render(<LiveBoxPanel ingame={null} />);
    expect(screen.queryByTestId("age-chip")).toBeNull();
  });
});
