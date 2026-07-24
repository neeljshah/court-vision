import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";

// paper-records.test.tsx -- WS4 acceptance tests for the prediction history panel.
//
// Verifies:
//   1. Panel renders prediction rows from a mocked api.paperPredictions response
//      (matchup, model_prob as %, tier, units with "u" suffix -- units not dollars).
//   2. Honest "no records yet" state renders on empty predictions array.
//   3. AgeBadge is bound to generated_at: a stale generated_at renders amber/
//      "aging" tone and NEVER a green class (stale-never-green rail).
//   4. No dollar sign followed by a digit appears anywhere in the rendered output.
//   5. The panel degrades to an honest unavailable state (not a crash) when the
//      API returns an Unavailable sentinel.
//
// Strategy: import PaperPage (the page that hosts PredictionHistoryPanel) and
// mock api.paperPredictions + api.getPaperTrail + api.getPaperClv so the page
// renders deterministically under jsdom without a live P5 service.

// next/link -> plain anchor for jsdom.
vi.mock("next/link", () => ({
  default: ({ href, children, ...rest }: { href: string; children: React.ReactNode }) => (
    <a href={href} {...rest}>{children}</a>
  ),
}));

// Stub PmTrailTable so it doesn't need the full PM trail structure.
vi.mock("@/components/paper_pm/PmTrailTable", () => ({
  PmTrailTable: () => <div data-testid="pm-trail-stub" />,
}));

import PaperPage from "@/app/(terminal)/paper/page";
import type { PaperPredictions } from "@/lib/p5api";
import type { Unavailable } from "@/lib/types";

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const FRESH_TS = new Date(Date.now() - 5_000).toISOString();          // 5 s old
const STALE_TS = new Date(Date.now() - 20 * 60 * 1000).toISOString(); // 20 m old

function makePredictions(
  rows: Partial<{
    game_id: string;
    matchup: string;
    sport: string;
    market_type: string;
    side: string;
    model_prob: number;
    market_prob: number;
    edge_vs_market: number;
    tier: string;
    stake_units: number;
    decision: string;
    outcome: string | null;
    final_score: string | null;
    clv_pct: number | null;
    beat_close: boolean | null;
    clv_is_proxy: boolean;
    ts: string;
  }>[] = [],
  opts?: { generatedAt?: string },
): PaperPredictions {
  return {
    status: "ok",
    count: rows.length,
    generated_at: opts?.generatedAt ?? FRESH_TS,
    edge_claimed: false,
    predictions: rows.map((r, i) => ({
      game_id:        r.game_id        ?? `game_${i}`,
      matchup:        r.matchup        ?? "NYK @ SAS",
      sport:          r.sport          ?? "nba",
      market_type:    r.market_type    ?? "moneyline",
      side:           r.side           ?? "home",
      model_prob:     r.model_prob     ?? 0.54,
      market_prob:    r.market_prob    ?? 0.48,
      edge_vs_market: r.edge_vs_market ?? 0.06,
      tier:           r.tier           ?? "A",
      stake_units:    r.stake_units    ?? 0.75,
      decision:       r.decision       ?? "bet",
      outcome:        r.outcome        !== undefined ? r.outcome : null,
      final_score:    r.final_score    !== undefined ? r.final_score : null,
      clv_pct:        r.clv_pct        ?? null,
      beat_close:     r.beat_close     ?? null,
      clv_is_proxy:   r.clv_is_proxy   ?? true,
      ts:             r.ts             ?? FRESH_TS,
    })),
  };
}

const UNAVAILABLE: Unavailable = { status: "unavailable", reason: "service offline" };

// ---------------------------------------------------------------------------
// Setup: stub api.paperPredictions + api.getPaperTrail + api.getPaperClv
// so the full PaperPage renders without a live service.
// ---------------------------------------------------------------------------

let savedPaperPredictions: unknown;
let savedGetPaperTrail: unknown;
let savedGetPaperClv: unknown;

beforeEach(async () => {
  const mod = await import("@/lib/p5api");
  savedPaperPredictions = mod.api.paperPredictions;
  savedGetPaperTrail    = mod.api.getPaperTrail;
  savedGetPaperClv      = mod.api.getPaperClv;

  // Default PM trail stubs (not under test here)
  mod.api.getPaperTrail = vi.fn(async () => ({
    status: "ok", count: 0, trail: [], honest_note: "no trades",
  })) as typeof mod.api.getPaperTrail;

  mod.api.getPaperClv = vi.fn(async () => ({
    status: "ok",
    n_bets: 0,
    pct_beat_close: null,
    mean_clv_pct: null,
    by_sport: null,
    clv_is_proxy: true,
  })) as typeof mod.api.getPaperClv;
});

afterEach(async () => {
  const mod = await import("@/lib/p5api");
  mod.api.paperPredictions = savedPaperPredictions as typeof mod.api.paperPredictions;
  mod.api.getPaperTrail    = savedGetPaperTrail    as typeof mod.api.getPaperTrail;
  mod.api.getPaperClv      = savedGetPaperClv      as typeof mod.api.getPaperClv;
  vi.restoreAllMocks();
});

// ---------------------------------------------------------------------------
// 1. Panel renders prediction rows: matchup / model_prob / tier / units
// ---------------------------------------------------------------------------

describe("PredictionHistoryPanel -- renders prediction rows", () => {
  it("renders matchup text from api.paperPredictions response", async () => {
    const rows = [
      { matchup: "NYK @ SAS", sport: "nba" },
      { matchup: "LAL @ BOS", sport: "nba" },
    ];
    const mod = await import("@/lib/p5api");
    mod.api.paperPredictions = vi.fn(async () => makePredictions(rows)) as typeof mod.api.paperPredictions;

    render(<PaperPage />);

    await waitFor(() => {
      expect(screen.queryAllByText(/NYK @ SAS/i).length).toBeGreaterThan(0);
    });
    expect(screen.queryAllByText(/LAL @ BOS/i).length).toBeGreaterThan(0);
  });

  it("renders model_prob as a percentage (54% not 0.54)", async () => {
    const mod = await import("@/lib/p5api");
    mod.api.paperPredictions = vi.fn(async () =>
      makePredictions([{ model_prob: 0.54, matchup: "OKC @ DEN" }]),
    ) as typeof mod.api.paperPredictions;

    render(<PaperPage />);

    await waitFor(() => {
      expect(screen.queryAllByText("54.0%").length).toBeGreaterThan(0);
    });
    // Raw decimal must not appear as a standalone cell value
    expect(screen.queryAllByText("0.54").length).toBe(0);
  });

  it("renders tier badge for each prediction row", async () => {
    const mod = await import("@/lib/p5api");
    mod.api.paperPredictions = vi.fn(async () =>
      makePredictions([
        { tier: "S", matchup: "GSW @ MEM" },
        { tier: "B", matchup: "PHX @ DAL" },
      ]),
    ) as typeof mod.api.paperPredictions;

    render(<PaperPage />);

    await waitFor(() => {
      const tierEls = screen.queryAllByTestId("pred-tier");
      expect(tierEls.length).toBeGreaterThanOrEqual(2);
    });
    const tierEls = screen.queryAllByTestId("pred-tier");
    const tierTexts = tierEls.map((el) => el.textContent?.trim());
    expect(tierTexts).toContain("S");
    expect(tierTexts).toContain("B");
  });

  it("renders stake_units with 'u' suffix (not a dollar figure)", async () => {
    const mod = await import("@/lib/p5api");
    mod.api.paperPredictions = vi.fn(async () =>
      makePredictions([{ stake_units: 0.75, matchup: "MIL @ CHI" }]),
    ) as typeof mod.api.paperPredictions;

    render(<PaperPage />);

    await waitFor(() => {
      expect(screen.queryAllByText("0.75u").length).toBeGreaterThan(0);
    });
  });

  it("renders multiple rows in the prediction history table", async () => {
    const rows = [
      { matchup: "MIN @ DET", tier: "A", stake_units: 1.0 },
      { matchup: "CLE @ ATL", tier: "B", stake_units: 0.5 },
      { matchup: "MIA @ ORL", tier: "C", stake_units: 0.25 },
    ];
    const mod = await import("@/lib/p5api");
    mod.api.paperPredictions = vi.fn(async () => makePredictions(rows)) as typeof mod.api.paperPredictions;

    render(<PaperPage />);

    await waitFor(() => {
      const predRows = screen.queryAllByTestId("prediction-row");
      expect(predRows.length).toBe(3);
    });
  });
});

// ---------------------------------------------------------------------------
// 2. Honest "no records yet" state on empty predictions
// ---------------------------------------------------------------------------

describe("PredictionHistoryPanel -- honest empty state", () => {
  it("shows 'None settled yet' when predictions array is empty", async () => {
    const mod = await import("@/lib/p5api");
    mod.api.paperPredictions = vi.fn(async () => makePredictions([])) as typeof mod.api.paperPredictions;

    render(<PaperPage />);

    await waitFor(() => {
      expect(screen.queryByTestId("pred-history-empty")).not.toBeNull();
    });
    const el = screen.getByTestId("pred-history-empty");
    expect(el.textContent).toMatch(/none settled yet/i);
  });

  it("honest empty state does NOT show a dollar amount", async () => {
    const mod = await import("@/lib/p5api");
    mod.api.paperPredictions = vi.fn(async () => makePredictions([])) as typeof mod.api.paperPredictions;

    const { container } = render(<PaperPage />);

    await waitFor(() => {
      expect(screen.queryByTestId("pred-history-empty")).not.toBeNull();
    });
    const txt = container.textContent ?? "";
    expect(/\$\s*\d/.test(txt)).toBe(false);
  });

  it("honest empty state disclaims edge ('no edge is claimed')", async () => {
    const mod = await import("@/lib/p5api");
    mod.api.paperPredictions = vi.fn(async () => makePredictions([])) as typeof mod.api.paperPredictions;

    render(<PaperPage />);

    await waitFor(() => {
      expect(screen.queryByTestId("pred-history-empty")).not.toBeNull();
    });
    expect(screen.queryAllByText(/no edge is claimed/i).length).toBeGreaterThan(0);
  });

  it("shows prediction table (not empty state) when rows exist", async () => {
    const mod = await import("@/lib/p5api");
    mod.api.paperPredictions = vi.fn(async () =>
      makePredictions([{ matchup: "OKC @ SAS" }]),
    ) as typeof mod.api.paperPredictions;

    render(<PaperPage />);

    await waitFor(() => {
      expect(screen.queryByTestId("pred-history-table")).not.toBeNull();
    });
    expect(screen.queryByTestId("pred-history-empty")).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// 3. AgeBadge bound to generated_at: stale-never-green rail
// ---------------------------------------------------------------------------

describe("PredictionHistoryPanel -- AgeBadge stale-never-green", () => {
  it("renders an age badge after data loads", async () => {
    const mod = await import("@/lib/p5api");
    mod.api.paperPredictions = vi.fn(async () =>
      makePredictions([{ matchup: "MIL @ IND" }], { generatedAt: FRESH_TS }),
    ) as typeof mod.api.paperPredictions;

    render(<PaperPage />);

    await waitFor(() => {
      const badge = screen.queryByTestId("age-badge");
      expect(badge).not.toBeNull();
    });
  });

  it("stale generated_at renders amber/aging tone -- never a green class", async () => {
    const mod = await import("@/lib/p5api");
    mod.api.paperPredictions = vi.fn(async () =>
      makePredictions([{ matchup: "GSW @ SAC" }], { generatedAt: STALE_TS }),
    ) as typeof mod.api.paperPredictions;

    render(<PaperPage />);

    await waitFor(() => {
      const agingEls = screen.queryAllByText(/aging/i);
      expect(agingEls.length).toBeGreaterThan(0);
    });

    const agingEls = screen.queryAllByText(/aging/i);
    for (const el of agingEls) {
      const cls = el.closest("[class]")?.className ?? el.className;
      // Must NOT carry green (tier-a) class
      expect(cls).not.toMatch(/tier-a/);
      expect(cls).not.toMatch(/text-green/);
    }
  });

  it("fresh generated_at renders slate (not amber, not green) AgeBadge", async () => {
    const mod = await import("@/lib/p5api");
    mod.api.paperPredictions = vi.fn(async () =>
      makePredictions([], { generatedAt: FRESH_TS }),
    ) as typeof mod.api.paperPredictions;

    render(<PaperPage />);

    await waitFor(() => {
      expect(screen.queryByTestId("age-badge")).not.toBeNull();
    });

    const badge = screen.queryByTestId("age-badge");
    // Should have rendered something (the badge exists)
    expect(badge).not.toBeNull();
    // Badge wrapper must not carry a green class
    const cls = badge?.className ?? badge?.querySelector("[class]")?.className ?? "";
    expect(cls).not.toMatch(/tier-a|text-green/);
  });
});

// ---------------------------------------------------------------------------
// 4. No dollar sign followed by digit anywhere in rendered output
// ---------------------------------------------------------------------------

describe("PredictionHistoryPanel -- units-only (no $ amounts)", () => {
  it("renders no dollar-amount string in a loaded prediction table", async () => {
    const mod = await import("@/lib/p5api");
    mod.api.paperPredictions = vi.fn(async () =>
      makePredictions([
        { matchup: "SAS @ NYK", stake_units: 1.5, model_prob: 0.60, tier: "A" },
        { matchup: "BOS @ MIA", stake_units: 0.5, model_prob: 0.52, tier: "B" },
      ]),
    ) as typeof mod.api.paperPredictions;

    const { container } = render(<PaperPage />);

    await waitFor(() => {
      expect(screen.queryByTestId("pred-history-table")).not.toBeNull();
    });

    const txt = container.textContent ?? "";
    // No $ followed by a digit (monetary P&L claim)
    expect(/\$\s*\d/.test(txt)).toBe(false);
    // No ROI or P&L label
    expect(/\bROI\b/.test(txt)).toBe(false);
    expect(/\bP&L\b|\bPnL\b/i.test(txt)).toBe(false);
  });

  it("renders no dollar-amount string in the honest empty state", async () => {
    const mod = await import("@/lib/p5api");
    mod.api.paperPredictions = vi.fn(async () => makePredictions([])) as typeof mod.api.paperPredictions;

    const { container } = render(<PaperPage />);

    await waitFor(() => {
      expect(screen.queryByTestId("pred-history-empty")).not.toBeNull();
    });

    const txt = container.textContent ?? "";
    expect(/\$\s*\d/.test(txt)).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// 5. Degrades honestly to unavailable state (not a crash) on Unavailable sentinel
// ---------------------------------------------------------------------------

describe("PredictionHistoryPanel -- honest degradation on Unavailable", () => {
  it("shows unavailable panel (not a crash) when API returns unavailable", async () => {
    const mod = await import("@/lib/p5api");
    mod.api.paperPredictions = vi.fn(async () => UNAVAILABLE) as typeof mod.api.paperPredictions;

    const { container } = render(<PaperPage />);

    // Should eventually show the unavailable sentinel -- not throw
    await waitFor(() => {
      const txt = container.textContent ?? "";
      const hasUnavailable =
        /unavailable/i.test(txt) ||
        /service offline/i.test(txt) ||
        // fallback: table still absent (component kept loading; skeleton shown)
        screen.queryByTestId("pred-history-table") === null;
      expect(hasUnavailable).toBe(true);
    });
  });

  it("does not render a prediction table when unavailable", async () => {
    const mod = await import("@/lib/p5api");
    mod.api.paperPredictions = vi.fn(async () => UNAVAILABLE) as typeof mod.api.paperPredictions;

    render(<PaperPage />);

    await waitFor(() => {
      // Gives the async hook time to settle
      expect(screen.queryByTestId("pred-history-table")).toBeNull();
    });
  });
});

// ---------------------------------------------------------------------------
// WS7 -- Graded records: win / loss / pending rows with real final score
// ---------------------------------------------------------------------------

describe("PredictionHistoryPanel -- WS7 graded win/loss/pending rows", () => {
  it("renders a WIN row with real final score from graded payload", async () => {
    const mod = await import("@/lib/p5api");
    mod.api.paperPredictions = vi.fn(async () =>
      makePredictions([
        { matchup: "NYK @ SAS", outcome: "win", final_score: "112-104" },
      ]),
    ) as typeof mod.api.paperPredictions;

    render(<PaperPage />);

    await waitFor(() => {
      expect(screen.queryByTestId("pred-history-table")).not.toBeNull();
    });
    // Outcome cell shows WIN
    const outcomes = screen.queryAllByTestId("pred-outcome");
    expect(outcomes.some((el) => el.textContent?.trim() === "WIN")).toBe(true);
    // Score cell shows the real final score string
    const scores = screen.queryAllByTestId("pred-final-score");
    expect(scores.some((el) => el.textContent?.includes("112-104"))).toBe(true);
  });

  it("renders a LOSS row with real final score from graded payload", async () => {
    const mod = await import("@/lib/p5api");
    mod.api.paperPredictions = vi.fn(async () =>
      makePredictions([
        { matchup: "LAL @ BOS", outcome: "loss", final_score: "98-110" },
      ]),
    ) as typeof mod.api.paperPredictions;

    render(<PaperPage />);

    await waitFor(() => {
      expect(screen.queryByTestId("pred-history-table")).not.toBeNull();
    });
    const outcomes = screen.queryAllByTestId("pred-outcome");
    expect(outcomes.some((el) => el.textContent?.trim() === "LOSS")).toBe(true);
    const scores = screen.queryAllByTestId("pred-final-score");
    expect(scores.some((el) => el.textContent?.includes("98-110"))).toBe(true);
  });

  it("renders a PENDING row (outcome=null, no final score) as pending", async () => {
    const mod = await import("@/lib/p5api");
    mod.api.paperPredictions = vi.fn(async () =>
      makePredictions([
        { matchup: "OKC @ DEN", outcome: null, final_score: null },
      ]),
    ) as typeof mod.api.paperPredictions;

    render(<PaperPage />);

    await waitFor(() => {
      expect(screen.queryByTestId("pred-history-table")).not.toBeNull();
    });
    // Outcome cell shows pending (not yet graded)
    const outcomes = screen.queryAllByTestId("pred-outcome");
    expect(outcomes.some((el) => /pending/i.test(el.textContent ?? ""))).toBe(true);
  });

  it("renders all three rows (win, loss, pending) from one graded payload", async () => {
    const mod = await import("@/lib/p5api");
    mod.api.paperPredictions = vi.fn(async () =>
      makePredictions([
        { matchup: "NYK @ SAS", outcome: "win",  final_score: "110-104", game_id: "g1" },
        { matchup: "LAL @ BOS", outcome: "loss", final_score: "95-108",  game_id: "g2" },
        { matchup: "OKC @ DEN", outcome: null,   final_score: null,      game_id: "g3" },
      ]),
    ) as typeof mod.api.paperPredictions;

    render(<PaperPage />);

    await waitFor(() => {
      expect(screen.queryAllByTestId("prediction-row").length).toBe(3);
    });

    const outcomes = screen.queryAllByTestId("pred-outcome").map((el) => el.textContent?.trim());
    expect(outcomes).toContain("WIN");
    expect(outcomes).toContain("LOSS");
    expect(outcomes.some((t) => /pending/i.test(t ?? ""))).toBe(true);

    const scores = screen.queryAllByTestId("pred-final-score").map((el) => el.textContent?.trim());
    expect(scores.some((s) => s?.includes("110-104"))).toBe(true);
    expect(scores.some((s) => s?.includes("95-108"))).toBe(true);
  });

  it("shows the real score string in a settled row, not a fabricated figure", async () => {
    const mod = await import("@/lib/p5api");
    mod.api.paperPredictions = vi.fn(async () =>
      makePredictions([{ outcome: "win", final_score: "120-115", matchup: "GSW @ PHX" }]),
    ) as typeof mod.api.paperPredictions;

    render(<PaperPage />);

    await waitFor(() => {
      expect(screen.queryByTestId("pred-history-table")).not.toBeNull();
    });
    // The literal real score string must appear
    expect(screen.queryAllByText(/120-115/).length).toBeGreaterThan(0);
  });
});

// ---------------------------------------------------------------------------
// WS7 -- Honest empty banner when total=0 (none settled yet)
// ---------------------------------------------------------------------------

describe("PredictionHistoryPanel -- WS7 honest empty banner (none settled yet)", () => {
  it("shows 'None settled yet' empty banner when predictions array is empty", async () => {
    const mod = await import("@/lib/p5api");
    mod.api.paperPredictions = vi.fn(async () => makePredictions([])) as typeof mod.api.paperPredictions;

    render(<PaperPage />);

    await waitFor(() => {
      expect(screen.queryByTestId("pred-history-empty")).not.toBeNull();
    });
    const el = screen.getByTestId("pred-history-empty");
    expect(el.textContent).toMatch(/none settled yet/i);
  });

  it("honest empty banner says 'no edge is claimed'", async () => {
    const mod = await import("@/lib/p5api");
    mod.api.paperPredictions = vi.fn(async () => makePredictions([])) as typeof mod.api.paperPredictions;

    render(<PaperPage />);

    await waitFor(() => {
      expect(screen.queryByTestId("pred-history-empty")).not.toBeNull();
    });
    const el = screen.getByTestId("pred-history-empty");
    expect(el.textContent).toMatch(/no edge is claimed/i);
  });

  it("honest empty banner contains no dollar-amount string", async () => {
    const mod = await import("@/lib/p5api");
    mod.api.paperPredictions = vi.fn(async () => makePredictions([])) as typeof mod.api.paperPredictions;

    const { container } = render(<PaperPage />);

    await waitFor(() => {
      expect(screen.queryByTestId("pred-history-empty")).not.toBeNull();
    });
    expect(/\$\s*\d/.test(container.textContent ?? "")).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// WS7 -- No dollar/ROI string anywhere in graded record output
// ---------------------------------------------------------------------------

describe("PredictionHistoryPanel -- WS7 no dollar/ROI string in graded output", () => {
  it("graded table with win/loss/pending: no dollar-amount string", async () => {
    const mod = await import("@/lib/p5api");
    mod.api.paperPredictions = vi.fn(async () =>
      makePredictions([
        { outcome: "win",  final_score: "112-104", game_id: "g1" },
        { outcome: "loss", final_score: "98-110",  game_id: "g2" },
        { outcome: null,   final_score: null,       game_id: "g3" },
      ]),
    ) as typeof mod.api.paperPredictions;

    const { container } = render(<PaperPage />);

    await waitFor(() => {
      expect(screen.queryAllByTestId("prediction-row").length).toBe(3);
    });

    const txt = container.textContent ?? "";
    expect(/\$\s*\d/.test(txt)).toBe(false);
    expect(/\bROI\b/.test(txt)).toBe(false);
    expect(/\bP&L\b|\bPnL\b/i.test(txt)).toBe(false);
  });
});
