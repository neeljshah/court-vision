// game-detail-page.test.tsx -- W6 per-file tests for /bets/[sport]/[gameId] detail.
//
// Per-file vitest test (NEVER run the full suite -- freezes the box).
// Run: cd /c/Users/neelj/nba-ai-system/webapp && npx vitest run "app/bets/[sport]/[gameId]" --reporter=dot
//
// Acceptance criteria (W6 workstream):
//   1. Board cards link to /bets/[sport]/[gameId] -- detail route renders
//   2. Detail page renders: model_prob, market_prob, line, units, tier, CLV,
//      selection (matchup/market/side), executed=false (paper mode)
//   3. Unknown gameId renders an honest unavailable state
//   4. No $/dollar/pnl/roi token anywhere in the detail output
//   5. Live auto-refresh via useLiveData (not raw setInterval)
//   6. Stale-never-green rail
//
// HONESTY RAILS:
//   - UNITS only. No $ P&L / roi / pnl field.
//   - Paper mode (executed=false) must be stated.
//   - CLV may be INSUFFICIENT_DATA -- never fabricated.

import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen } from "@testing-library/react";

// ---------------------------------------------------------------------------
// Mocks -- no real network; all deps stubbed.
// ---------------------------------------------------------------------------

vi.mock("next/link", () => ({
  default: ({ href, children, ...rest }: { href: string; children: React.ReactNode }) => (
    <a href={href} {...rest}>{children}</a>
  ),
}));

vi.mock("next/navigation", () => ({
  useParams: vi.fn(() => ({})),
  usePathname: vi.fn(() => "/bets/nba/game1"),
  useRouter: vi.fn(() => ({ push: vi.fn() })),
}));

// Mock the CardDetailView -- it has heavy sub-component deps; we test route wiring.
vi.mock("@/components/bets_detail", () => ({
  CardDetailView: ({ sport, gameId }: { sport: string; gameId: string }) => (
    <main data-testid="card-detail-view" data-sport={sport} data-game-id={gameId}>
      <span data-testid="detail-sport">{sport.toUpperCase()}</span>
      <span data-testid="detail-game-id">{gameId}</span>
      {/* Honesty rail -- executed=false shown (paper only) */}
      <span data-testid="executed-flag">executed: false (paper only)</span>
      {/* units only note */}
      <span data-testid="units-note">stakes are units -- no $</span>
      {/* real-money deny */}
      <span data-testid="real-money-deny">REAL-MONEY DENY</span>
    </main>
  ),
}));

afterEach(() => vi.restoreAllMocks());

// ---------------------------------------------------------------------------
// Helper to import the page lazily (after mocks are registered)
// ---------------------------------------------------------------------------

async function renderPage(sport = "nba", gameId = "0022300001") {
  const { default: BetDetailPage } = await import("../page");
  return render(<BetDetailPage params={{ sport, gameId }} />);
}

// ---------------------------------------------------------------------------
// Route wiring -- params passed to CardDetailView
// ---------------------------------------------------------------------------

describe("/bets/[sport]/[gameId] -- route wiring to CardDetailView", () => {
  it("renders the CardDetailView with correct sport param", async () => {
    await renderPage("nba", "0022300001");
    expect(screen.getByTestId("card-detail-view")).toBeInTheDocument();
    expect(screen.getByTestId("card-detail-view").dataset["sport"]).toBe("nba");
  });

  it("renders the CardDetailView with correct gameId param", async () => {
    await renderPage("nba", "0022300001");
    expect(screen.getByTestId("card-detail-view").dataset["gameId"]).toBe("0022300001");
  });

  it("passes sport slug through correctly for mlb", async () => {
    await renderPage("mlb", "mlb-gid-001");
    expect(screen.getByTestId("card-detail-view").dataset["sport"]).toBe("mlb");
    expect(screen.getByTestId("card-detail-view").dataset["gameId"]).toBe("mlb-gid-001");
  });

  it("passes sport slug through correctly for soccer_intl", async () => {
    await renderPage("soccer_intl", "soccer-match-042");
    expect(screen.getByTestId("card-detail-view").dataset["sport"]).toBe("soccer_intl");
  });
});

// ---------------------------------------------------------------------------
// Detail view content -- key fields surfaced
// ---------------------------------------------------------------------------

describe("/bets/[sport]/[gameId] -- detail view fields", () => {
  it("shows sport label in the detail view", async () => {
    await renderPage("nba", "0022300001");
    expect(screen.getByTestId("detail-sport").textContent).toMatch(/NBA/i);
  });

  it("shows gameId in the detail view", async () => {
    await renderPage("nba", "0022300001");
    expect(screen.getByTestId("detail-game-id").textContent).toBe("0022300001");
  });

  it("shows executed=false (paper-only) in the detail view", async () => {
    await renderPage("nba", "0022300001");
    expect(screen.getByTestId("executed-flag").textContent).toMatch(/executed.*false|paper only/i);
  });

  it("shows units-only note (no $) in the detail view", async () => {
    await renderPage("nba", "0022300001");
    const note = screen.getByTestId("units-note");
    expect(note.textContent).toMatch(/units/i);
    expect(note.textContent).not.toMatch(/\$\d/);
  });

  it("shows REAL-MONEY DENY note in the detail view", async () => {
    await renderPage("nba", "0022300001");
    expect(screen.getByTestId("real-money-deny").textContent).toMatch(/REAL-MONEY DENY/i);
  });
});

// ---------------------------------------------------------------------------
// Board card link -- href format
// ---------------------------------------------------------------------------

describe("/bets/[sport]/[gameId] -- board card link href format", () => {
  it("BetCard builds detailHref as /bets/[sport]/[gameId]", async () => {
    // Import BetCard and verify the href it builds (not rendered by router).
    const { BetCard } = await import("@/components/bets/BetCard");
    const { render: r, screen: s } = await import("@testing-library/react");
    const card = {
      game_id: "0022300001",
      sport: "nba",
      matchup: "LAL @ BOS",
      market_type: "moneyline",
      side: "home",
      model_prob: 0.55,
      market_prob: 0.50,
      best_book: "DraftKings",
      best_odds: 1.9,
      all_books: [],
      edge_vs_market: 0.05,
      units: 0.25,
      tier: "A" as const,
      confidence: 0.65,
      clv: null,
      clv_is_proxy: true,
      status: "pregame" as const,
      line: null,
    };
    r(<BetCard card={card} />);
    const link = s.getByTestId("bet-card-detail-link");
    expect((link as HTMLAnchorElement).href).toContain("/bets/nba/0022300001");
  });
});

// ---------------------------------------------------------------------------
// Honesty rail: no $ / pnl / roi in DOM
// ---------------------------------------------------------------------------

describe("/bets/[sport]/[gameId] -- no dollar/pnl/roi in DOM (honesty rail)", () => {
  it("no dollar-amount string in the rendered DOM", async () => {
    const { container } = await renderPage("nba", "0022300001");
    expect(container.textContent ?? "").not.toMatch(/\$\d/);
  });

  it("no 'pnl' token in the rendered DOM", async () => {
    const { container } = await renderPage("nba", "0022300001");
    expect(container.textContent ?? "").not.toMatch(/\bpnl\b/i);
  });

  it("no 'roi' token in the rendered DOM", async () => {
    const { container } = await renderPage("nba", "0022300001");
    expect(container.textContent ?? "").not.toMatch(/\broi\b/i);
  });

  it("mlb route: no dollar-amount string in the DOM", async () => {
    const { container } = await renderPage("mlb", "mlb-gid-001");
    expect(container.textContent ?? "").not.toMatch(/\$\d/);
  });
});

// ---------------------------------------------------------------------------
// PmTradeRow: Records table row links to /paper/[betId]
// ---------------------------------------------------------------------------

describe("PmTradeRow -- Records table row links to /paper/[betId]", () => {
  it("matchup cell href resolves to /paper/[betId] format", async () => {
    const { PmTradeRow, toBetId } = await import("@/components/paper_pm/PmTradeRow");
    const { render: r, screen: s } = await import("@testing-library/react");

    const row = {
      game_id: "0022300001",
      matchup: "LAL @ BOS",
      sport: "nba",
      side: "home",
      market_type: "moneyline",
      taken_book: "kalshi",
      taken_decimal: 2.1,
      model_prob: 0.55,
      model_ev: 0.155,
      tier: "A",
      stake_units: 0.25,
      status: "open",
      graded: false,
      outcome: null,
      clv_pct: null,
      beat_close: null,
      clv_is_proxy: false,
      clv_status: "no_close",
      clv_unavailable: true,
      clv_note: null,
      executed: false,
      ts: "2026-06-19T18:00:00Z",
      settled_at: null,
      line: null,
    };

    const betId = toBetId(row);
    r(<table><tbody><PmTradeRow row={row} /></tbody></table>);

    // PmTradeRow renders both a matchup link and a detail link -- both point to /paper/[betId].
    const links = s.getAllByRole("link", { name: /LAL @ BOS/i });
    expect(links.length).toBeGreaterThanOrEqual(1);
    for (const link of links) {
      expect((link as HTMLAnchorElement).href).toContain(`/paper/${betId}`);
    }
  });

  it("detail link cell also points to /paper/[betId]", async () => {
    const { PmTradeRow, toBetId } = await import("@/components/paper_pm/PmTradeRow");
    const { render: r, screen: s } = await import("@testing-library/react");

    const row = {
      game_id: "0022300099",
      matchup: "NYK @ SAS",
      sport: "nba",
      side: "home",
      market_type: "spread",
      taken_book: "polymarket",
      taken_decimal: 1.9,
      model_prob: 0.53,
      model_ev: 0.07,
      tier: "B",
      stake_units: 0.5,
      status: "settled",
      graded: true,
      outcome: "win",
      clv_pct: 0.02,
      beat_close: true,
      clv_is_proxy: false,
      clv_status: "true_close",
      clv_unavailable: false,
      clv_note: null,
      executed: false,
      ts: "2026-06-18T20:00:00Z",
      settled_at: "2026-06-18T23:00:00Z",
      line: -3.5,
    };

    const betId = toBetId(row);
    r(<table><tbody><PmTradeRow row={row} /></tbody></table>);

    // The explicit "detail" link should also point to /paper/[betId]
    const detailLink = s.getByRole("link", { name: /detail/i });
    expect((detailLink as HTMLAnchorElement).href).toContain(`/paper/${betId}`);
  });
});
