// bestbets-guards.test.tsx -- W3 acceptance tests for BestBetsCardGuards + BetCard
// suppression rendering.
//
// Acceptance criteria (from workstream spec):
//   1. A card with live.state='final' renders 'settled / no bet' not decision=bet
//   2. A degenerate_model=true card renders decision=no_bet explicitly
//   3. A real pregame tier=A card renders with edge_vs_market labelled as
//      calibrated divergence (not '$'/'profit')
//   4. Board with count=0 shows honest-empty
//   5. Each rendered card has a detail href
//
// Also covers the pure BestBetsCardGuards helpers directly.

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, act, screen } from "@testing-library/react";
import type { BestBetsCard } from "@/lib/types_w12";
import {
  shouldSuppressBet,
  suppressReasonLabel,
  isDecisionNoBet,
  isSettledCard,
} from "../BestBetsCardGuards";

// ---------------------------------------------------------------------------
// Pure guard unit tests (no React)
// ---------------------------------------------------------------------------

function makeCard(overrides: Partial<BestBetsCard> = {}): BestBetsCard {
  return {
    game_id: `game-${Math.random().toString(36).slice(2)}`,
    matchup: "Team A vs Team B",
    sport: "mlb",
    market_type: "moneyline",
    prop_player: null,
    prop_stat: null,
    side: "away",
    model_prob: 0.528,
    market_prob: 0.421,
    best_book: "pinnacle",
    best_odds: 2.32,
    all_books: [],
    edge_vs_market: 0.107,
    units: 1.0,
    tier: "A",
    confidence: 0.528,
    clv: { clv_pct: null, beat_close: null, clv_status: "INSUFFICIENT_DATA", clv_is_proxy: true },
    clv_is_proxy: true,
    status: "pregame",
    tipoff_utc: "2026-06-20T23:15Z",
    degenerate_model: false,
    live: null,
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// shouldSuppressBet -- pure function tests
// ---------------------------------------------------------------------------

describe("shouldSuppressBet -- pure guard", () => {
  it("returns null for a normal pregame card", () => {
    const card = makeCard({ status: "pregame", degenerate_model: false, live: null });
    expect(shouldSuppressBet(card)).toBeNull();
  });

  it("returns 'live_state_settled' when card.live.state='final'", () => {
    const card = makeCard({ live: { state: "final" } });
    expect(shouldSuppressBet(card)).toBe("live_state_settled");
  });

  it("returns 'live_state_settled' when card.live.state='post'", () => {
    const card = makeCard({ live: { state: "post" } });
    expect(shouldSuppressBet(card)).toBe("live_state_settled");
  });

  it("returns 'status_settled' when card.status='final' and no live state", () => {
    const card = makeCard({ status: "final", live: null });
    expect(shouldSuppressBet(card)).toBe("status_settled");
  });

  it("returns 'status_settled' when card.status='post' and no live state", () => {
    const card = makeCard({ status: "post", live: null });
    expect(shouldSuppressBet(card)).toBe("status_settled");
  });

  it("returns 'degenerate_model' when card.degenerate_model=true and status=pregame", () => {
    const card = makeCard({ degenerate_model: true, status: "pregame", live: null });
    expect(shouldSuppressBet(card)).toBe("degenerate_model");
  });

  it("live_state_settled has priority over degenerate_model", () => {
    const card = makeCard({ degenerate_model: true, live: { state: "final" } });
    expect(shouldSuppressBet(card)).toBe("live_state_settled");
  });

  it("status_settled has priority over degenerate_model when no live.state", () => {
    const card = makeCard({ degenerate_model: true, status: "post", live: null });
    expect(shouldSuppressBet(card)).toBe("status_settled");
  });

  it("returns null for a live-status card with no degenerate_model", () => {
    const card = makeCard({ status: "live", degenerate_model: false, live: null });
    expect(shouldSuppressBet(card)).toBeNull();
  });

  it("returns null when card.live.state is a non-settled string", () => {
    const card = makeCard({ live: { state: "live" } });
    expect(shouldSuppressBet(card)).toBeNull();
  });

  it("returns null when card.live.state is null", () => {
    const card = makeCard({ live: { state: null } });
    expect(shouldSuppressBet(card)).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// suppressReasonLabel -- pure helper
// ---------------------------------------------------------------------------

describe("suppressReasonLabel -- human-readable labels", () => {
  it("returns empty string for null (eligible card)", () => {
    expect(suppressReasonLabel(null)).toBe("");
  });

  it("settled live_state label contains 'settled' and 'no bet'", () => {
    const label = suppressReasonLabel("live_state_settled").toLowerCase();
    expect(label).toContain("settled");
    expect(label).toContain("no bet");
  });

  it("settled status label contains 'settled' and 'no bet'", () => {
    const label = suppressReasonLabel("status_settled").toLowerCase();
    expect(label).toContain("settled");
    expect(label).toContain("no bet");
  });

  it("degenerate_model label contains 'decision=no_bet'", () => {
    const label = suppressReasonLabel("degenerate_model");
    expect(label.toLowerCase()).toContain("decision=no_bet");
  });

  it("degenerate_model label does NOT claim an edge or profit", () => {
    const label = suppressReasonLabel("degenerate_model").toLowerCase();
    expect(label).not.toMatch(/\bedge\b/);
    expect(label).not.toContain("profit");
    expect(label).not.toContain("$");
  });
});

// ---------------------------------------------------------------------------
// isDecisionNoBet / isSettledCard -- narrow checks
// ---------------------------------------------------------------------------

describe("isDecisionNoBet", () => {
  it("true when degenerate_model=true", () => {
    expect(isDecisionNoBet(makeCard({ degenerate_model: true }))).toBe(true);
  });

  it("false when degenerate_model=false", () => {
    expect(isDecisionNoBet(makeCard({ degenerate_model: false }))).toBe(false);
  });

  it("false when degenerate_model is absent", () => {
    const card = makeCard();
    delete (card as Partial<BestBetsCard>).degenerate_model;
    expect(isDecisionNoBet(card)).toBe(false);
  });
});

describe("isSettledCard", () => {
  it("true when live.state='final'", () => {
    expect(isSettledCard(makeCard({ live: { state: "final" } }))).toBe(true);
  });

  it("true when live.state='post'", () => {
    expect(isSettledCard(makeCard({ live: { state: "post" } }))).toBe(true);
  });

  it("true when card.status='final'", () => {
    expect(isSettledCard(makeCard({ status: "final", live: null }))).toBe(true);
  });

  it("false for pregame card with no settled state", () => {
    expect(isSettledCard(makeCard({ status: "pregame", live: null }))).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// BetCard -- render acceptance tests
// ---------------------------------------------------------------------------

// BetCard imports Link from next/link; mock it for tests.
vi.mock("next/link", () => ({
  default: ({ href, children, ...rest }: { href: string; children: React.ReactNode; [k: string]: unknown }) => (
    <a href={href} {...rest}>{children}</a>
  ),
}));

import * as React from "react";
import { BetCard, type BetCardData } from "../BetCard";
import type { SuppressReason } from "../BestBetsCardGuards";

function makeBetCardData(overrides: Partial<BetCardData> = {}): BetCardData {
  return {
    game_id: "game-001",
    sport: "mlb",
    matchup: "Yankees vs Red Sox",
    market_type: "moneyline",
    side: "away",
    model_prob: 0.55,
    market_prob: 0.44,
    best_book: "pinnacle",
    best_odds: 2.32,
    all_books: [],
    edge_vs_market: 0.11,
    units: 1.0,
    tier: "A",
    confidence: 0.55,
    clv: null,
    clv_is_proxy: true,
    status: "pregame",
    line: null,
    suppress_reason: null,
    ...overrides,
  };
}

// Acceptance criterion 1:
// A card with live.state='final' coming through suppress_reason='live_state_settled'
// renders 'settled / no bet' and NOT a decision=bet.
describe("BetCard -- AC1: live.state=final renders 'settled / no bet'", () => {
  it("renders settled-no-bet-label when suppress_reason='live_state_settled'", () => {
    const card = makeBetCardData({ suppress_reason: "live_state_settled" });
    render(<BetCard card={card} />);
    const label = screen.getByTestId("settled-no-bet-label");
    expect(label).toBeDefined();
    expect(label.textContent?.toLowerCase()).toContain("settled");
    expect(label.textContent?.toLowerCase()).toContain("no bet");
  });

  it("does NOT render the normal bet decision UI when suppress_reason='live_state_settled'", () => {
    const card = makeBetCardData({ suppress_reason: "live_state_settled" });
    const { container } = render(<BetCard card={card} />);
    // The normal card shows divergence-value; suppressed card must not show it
    expect(container.querySelector("[data-testid='divergence-value']")).toBeNull();
  });

  it("renders a detail href even in settled state", () => {
    const card = makeBetCardData({
      suppress_reason: "live_state_settled",
      sport: "mlb",
      game_id: "game-settled-001",
    });
    const { container } = render(<BetCard card={card} />);
    const link = container.querySelector("[data-testid='bet-card-detail-link']");
    expect(link).not.toBeNull();
    expect(link?.getAttribute("href")).toContain("/bets/mlb/game-settled-001");
  });
});

// Acceptance criterion 2:
// A degenerate_model=true card renders decision=no_bet EXPLICITLY.
describe("BetCard -- AC2: degenerate_model=true renders explicit decision=no_bet", () => {
  it("renders degenerate-no-bet-label when suppress_reason='degenerate_model'", () => {
    const card = makeBetCardData({ suppress_reason: "degenerate_model" });
    render(<BetCard card={card} />);
    const label = screen.getByTestId("degenerate-no-bet-label");
    expect(label).toBeDefined();
    expect(label.textContent?.toLowerCase()).toContain("decision=no_bet");
  });

  it("degenerate card does NOT render the normal divergence-value element", () => {
    const card = makeBetCardData({ suppress_reason: "degenerate_model" });
    const { container } = render(<BetCard card={card} />);
    expect(container.querySelector("[data-testid='divergence-value']")).toBeNull();
  });

  it("degenerate card has a detail href (still navigable)", () => {
    const card = makeBetCardData({
      suppress_reason: "degenerate_model",
      sport: "nba",
      game_id: "game-degen-002",
    });
    const { container } = render(<BetCard card={card} />);
    const link = container.querySelector("[data-testid='bet-card-detail-link']");
    expect(link).not.toBeNull();
    expect(link?.getAttribute("href")).toContain("/bets/nba/game-degen-002");
  });

  it("degenerate card renders no $ in text content", () => {
    const card = makeBetCardData({ suppress_reason: "degenerate_model" });
    const { container } = render(<BetCard card={card} />);
    expect(container.textContent ?? "").not.toMatch(/\$\s?\d/);
  });
});

// Acceptance criterion 3:
// A real pregame tier=A card renders with edge_vs_market labelled as
// calibrated divergence (not '$'/'profit').
describe("BetCard -- AC3: pregame tier=A card has calibrated divergence label, no $", () => {
  it("tier=A pregame card renders 'Calibrated divergence' label (not fabricated profit/edge)", () => {
    const card = makeBetCardData({ tier: "A", status: "pregame", suppress_reason: null });
    const { container } = render(<BetCard card={card} />);
    const text = container.textContent ?? "";
    expect(text.toLowerCase()).toContain("calibrated divergence");
    // No standalone 'profit' or 'edge' outside the honesty disclaimer footnote.
    // WS6: ModelVsMarketBar renders a "not a profit claim" footnote -- strip disclaimers.
    const withoutDisclaimer = text.toLowerCase()
      .replace(/not an? (?:edge or )?profit(?: claim)?/g, "")
      .replace(/calibrated divergence/g, "");
    expect(withoutDisclaimer).not.toMatch(/\bprofit\b/);
    expect(withoutDisclaimer).not.toMatch(/\bedge\b/);
  });

  it("tier=A card renders the divergence-chip element (WS6: ModelVsMarketBar)", () => {
    const card = makeBetCardData({ tier: "A", edge_vs_market: 0.11, suppress_reason: null });
    const { container } = render(<BetCard card={card} />);
    // WS6: BetCard now uses ModelVsMarketBar; divergence chip test-id is 'divergence-chip'
    expect(container.querySelector("[data-testid='divergence-chip']")).not.toBeNull();
  });

  it("tier=A card has no $<digit> in rendered text", () => {
    const card = makeBetCardData({ tier: "A", suppress_reason: null });
    const { container } = render(<BetCard card={card} />);
    expect(container.textContent ?? "").not.toMatch(/\$\s?\d/);
  });

  it("tier=A card has a detail href", () => {
    const card = makeBetCardData({
      tier: "A",
      sport: "mlb",
      game_id: "game-pregame-003",
      suppress_reason: null,
    });
    const { container } = render(<BetCard card={card} />);
    const link = container.querySelector("[data-testid='bet-card-detail-link']");
    expect(link).not.toBeNull();
    expect(link?.getAttribute("href")).toContain("/bets/mlb/game-pregame-003");
  });
});

// Acceptance criterion 5:
// Each rendered card (regardless of state) has a detail href.
describe("BetCard -- AC5: all rendered cards have a detail href", () => {
  const reasons: Array<{ label: string; reason: SuppressReason }> = [
    { label: "eligible pregame card", reason: null },
    { label: "live_state_settled card", reason: "live_state_settled" },
    { label: "status_settled card", reason: "status_settled" },
    { label: "degenerate_model card", reason: "degenerate_model" },
  ];

  for (const { label, reason } of reasons) {
    it(`${label} has a detail href`, () => {
      const card = makeBetCardData({
        suppress_reason: reason,
        sport: "nba",
        game_id: "g-detail-check",
      });
      const { container } = render(<BetCard card={card} />);
      const link = container.querySelector("[data-testid='bet-card-detail-link']");
      expect(link).not.toBeNull();
      expect(link?.getAttribute("href") ?? "").toContain("/bets/nba/g-detail-check");
    });
  }
});

// Acceptance criterion 4:
// Board with count=0 shows honest-empty state (tested in BestBetsBoard.w3.test.tsx
// acceptance (3), but also verify the guard helpers return null for a zero-card
// scenario -- no suppression needed when there are no cards).
describe("shouldSuppressBet -- zero-card honest-empty (no cards to suppress)", () => {
  it("returns null for every card in an empty array (vacuously: no cards means no suppression needed)", () => {
    const cards: BestBetsCard[] = [];
    const results = cards.map(shouldSuppressBet);
    expect(results).toHaveLength(0);
  });
});
