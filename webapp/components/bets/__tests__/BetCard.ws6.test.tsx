// BetCard.ws6.test.tsx -- WS6 acceptance tests for BetCard.
//
// Acceptance criteria (verbatim from WS6-bestbets-board-and-browse spec):
//   1. Each card shows tier A/B badge, model-vs-market bar, units=1.0 UNITS label,
//      tipoff shown, INSUFFICIENT_DATA CLV text.
//   2. Each card deep-links to /bets/{sport}/{gameId}.
//   3. Edge labeled as prob-diff with no '$' glyph.
//   4. ModelVsMarketBar is rendered (data-testid='model-vs-market-bar' present).
//   5. Honest-empty only triggers when count==0; real cards do NOT show false-empty.
//   6. Units rendered as "X.X UNITS" label per WS6 spec.
//   7. Tipoff rendered as "Tipoff ..." text when tipoff_utc is present.
//
// Uses real BetCard component; mocks next/link only.

import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { BetCard, type BetCardData } from "../BetCard";

// Mock next/link -> plain <a>
vi.mock("next/link", () => ({
  default: ({
    href,
    children,
    ...rest
  }: {
    href: string;
    children: React.ReactNode;
    [k: string]: unknown;
  }) => <a href={href} {...rest}>{children}</a>,
}));

// ---------------------------------------------------------------------------
// Fixtures -- mirrors the real /api/bestbets/board?sport=mlb response cards
// ---------------------------------------------------------------------------

function makeMLBCard(overrides: Partial<BetCardData> = {}): BetCardData {
  return {
    game_id: "401815831",
    sport: "mlb",
    matchup: "Houston Astros vs Cleveland Guardians",
    market_type: "moneyline",
    side: "away",
    model_prob: 0.528,
    market_prob: 0.416927,
    best_book: "pinnacle",
    best_odds: 2.34,
    all_books: [],
    edge_vs_market: 0.111073,
    units: 1.0,
    tier: "A",
    confidence: 0.528,
    clv: null,
    clv_is_proxy: true,
    status: "pregame",
    line: null,
    tipoff_utc: "2026-06-20T23:15Z",
    ...overrides,
  };
}

function makeTierBCard(overrides: Partial<BetCardData> = {}): BetCardData {
  return {
    game_id: "401815838",
    sport: "mlb",
    matchup: "Arizona Diamondbacks vs Minnesota Twins",
    market_type: "moneyline",
    side: "home",
    model_prob: 0.5801,
    market_prob: 0.53576,
    best_book: "pinnacle",
    best_odds: 1.833333,
    all_books: [],
    edge_vs_market: 0.04434,
    units: 1.0,
    tier: "B",
    confidence: 0.5801,
    clv: null,
    clv_is_proxy: true,
    status: "pregame",
    line: null,
    tipoff_utc: "2026-06-21T02:10Z",
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// WS6 AC1: Tier badge rendered
// ---------------------------------------------------------------------------

describe("WS6 -- BetCard tier badge", () => {
  it("tier A card shows 'A' tier badge", () => {
    const { container } = render(<BetCard card={makeMLBCard()} />);
    const badge = container.querySelector("[data-testid='tier-badge']");
    expect(badge).not.toBeNull();
    expect(badge?.textContent).toBe("A");
  });

  it("tier B card shows 'B' tier badge", () => {
    const { container } = render(<BetCard card={makeTierBCard()} />);
    const badge = container.querySelector("[data-testid='tier-badge']");
    expect(badge?.textContent).toBe("B");
  });
});

// ---------------------------------------------------------------------------
// WS6 AC1: ModelVsMarketBar wired -- model vs market bar rendered
// ---------------------------------------------------------------------------

describe("WS6 -- ModelVsMarketBar is rendered in BetCard", () => {
  it("BetCard renders model-vs-market-bar component", () => {
    const { container } = render(<BetCard card={makeMLBCard()} />);
    const bar = container.querySelector("[data-testid='model-vs-market-bar']");
    expect(bar).not.toBeNull();
  });

  it("model bar reflects model_prob", () => {
    const { container } = render(<BetCard card={makeMLBCard({ model_prob: 0.528 })} />);
    const modelBar = container.querySelector("[data-testid='model-bar']");
    expect(modelBar).not.toBeNull();
    // Bar width is set by style; value from aria-valuenow
    const value = Number(modelBar?.getAttribute("aria-valuenow"));
    expect(value).toBe(53); // Math.round(0.528 * 100)
  });

  it("market bar reflects market_prob", () => {
    const { container } = render(<BetCard card={makeMLBCard({ market_prob: 0.417 })} />);
    const marketBar = container.querySelector("[data-testid='market-bar']");
    expect(marketBar).not.toBeNull();
    const value = Number(marketBar?.getAttribute("aria-valuenow"));
    expect(value).toBe(42); // Math.round(0.417 * 100)
  });

  it("divergence chip shows in bar (data-testid='divergence-chip')", () => {
    const { container } = render(<BetCard card={makeMLBCard()} />);
    const chip = container.querySelector("[data-testid='divergence-chip']");
    expect(chip).not.toBeNull();
  });

  it("divergence chip aria-label mentions 'calibrated divergence'", () => {
    const { container } = render(<BetCard card={makeMLBCard()} />);
    const chip = container.querySelector("[data-testid='divergence-chip']");
    const label = chip?.getAttribute("aria-label") ?? "";
    expect(label.toLowerCase()).toContain("calibrated divergence");
  });

  it("divergence is labeled as prob-diff (pp format) -- no '$' glyph", () => {
    const { container } = render(<BetCard card={makeMLBCard({ edge_vs_market: 0.111 })} />);
    const chip = container.querySelector("[data-testid='divergence-chip']");
    const text = chip?.textContent ?? "";
    // Should contain pp suffix (formatDivergence returns "+11.1pp")
    expect(text).toContain("pp");
    expect(text).not.toContain("$");
  });
});

// ---------------------------------------------------------------------------
// WS6 AC1: units=1.0 UNITS label explicit
// ---------------------------------------------------------------------------

describe("WS6 -- units=1.0 UNITS label", () => {
  it("units shows as '1.0 UNITS' (not '1.00u')", () => {
    const { container } = render(<BetCard card={makeMLBCard({ units: 1.0 })} />);
    const unitsEl = container.querySelector("[data-testid='units-value']");
    expect(unitsEl).not.toBeNull();
    const text = unitsEl?.textContent ?? "";
    expect(text).toContain("1.0");
    expect(text.toUpperCase()).toContain("UNITS");
    expect(text).not.toContain("$");
  });

  it("units label is 'UNITS' not '$'", () => {
    const { container } = render(<BetCard card={makeMLBCard({ units: 1.0 })} />);
    const unitsEl = container.querySelector("[data-testid='units-value']");
    const text = unitsEl?.textContent ?? "";
    // Must contain "UNITS" (case insensitive)
    expect(text.toUpperCase()).toContain("UNITS");
    // Must NOT contain dollar sign attached to a number
    expect(text).not.toMatch(/\$\d/);
  });
});

// ---------------------------------------------------------------------------
// WS6 AC1: tipoff shown when tipoff_utc present
// ---------------------------------------------------------------------------

describe("WS6 -- tipoff display", () => {
  it("shows tipoff text when tipoff_utc is present", () => {
    const { container } = render(<BetCard card={makeMLBCard({ tipoff_utc: "2026-06-20T23:15Z" })} />);
    const tipoffEl = container.querySelector("[data-testid='tipoff-display']");
    expect(tipoffEl).not.toBeNull();
    expect(tipoffEl?.textContent?.toLowerCase()).toContain("tipoff");
  });

  it("tipoff not shown when tipoff_utc is null", () => {
    const { container } = render(<BetCard card={makeMLBCard({ tipoff_utc: null })} />);
    const tipoffEl = container.querySelector("[data-testid='tipoff-display']");
    expect(tipoffEl).toBeNull();
  });

  it("tipoff not shown when tipoff_utc is absent", () => {
    const card = makeMLBCard();
    delete (card as Partial<BetCardData>).tipoff_utc;
    const { container } = render(<BetCard card={card} />);
    const tipoffEl = container.querySelector("[data-testid='tipoff-display']");
    expect(tipoffEl).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// WS6 AC1: CLV = INSUFFICIENT_DATA shown honestly
// ---------------------------------------------------------------------------

describe("WS6 -- CLV INSUFFICIENT_DATA shown honestly", () => {
  it("clv=null renders INSUFFICIENT_DATA text", () => {
    render(<BetCard card={makeMLBCard({ clv: null })} />);
    expect(screen.getByText(/INSUFFICIENT_DATA/)).toBeInTheDocument();
  });

  it("CLV INSUFFICIENT_DATA text is amber-colored (not green)", () => {
    const { container } = render(<BetCard card={makeMLBCard({ clv: null })} />);
    const clvEl = Array.from(container.querySelectorAll("*")).find(
      (el) => el.textContent?.includes("INSUFFICIENT_DATA"),
    );
    expect(clvEl?.className ?? "").not.toMatch(/text-green/);
    expect(clvEl?.className ?? "").not.toMatch(/text-tier-a/);
  });
});

// ---------------------------------------------------------------------------
// WS6 AC2: Deep-link to /bets/{sport}/{gameId}
// ---------------------------------------------------------------------------

describe("WS6 -- deep-link to /bets/{sport}/{gameId}", () => {
  it("tier A card links to /bets/mlb/{game_id}", () => {
    const { container } = render(
      <BetCard card={makeMLBCard({ sport: "mlb", game_id: "401815831" })} />
    );
    const link = container.querySelector("[data-testid='bet-card-detail-link']");
    expect(link).not.toBeNull();
    expect(link?.getAttribute("href")).toBe("/bets/mlb/401815831");
  });

  it("tier B card also has deep-link", () => {
    const { container } = render(
      <BetCard card={makeTierBCard({ sport: "mlb", game_id: "401815838" })} />
    );
    const link = container.querySelector("[data-testid='bet-card-detail-link']");
    expect(link?.getAttribute("href")).toBe("/bets/mlb/401815838");
  });

  it("link accessible name names the matchup", () => {
    const { container } = render(
      <BetCard card={makeMLBCard({ matchup: "Houston Astros vs Cleveland Guardians" })} />
    );
    const link = container.querySelector("[data-testid='bet-card-detail-link']");
    const label = link?.getAttribute("aria-label") ?? "";
    expect(label).toContain("Houston Astros vs Cleveland Guardians");
  });
});

// ---------------------------------------------------------------------------
// WS6 AC3: No '$' glyph anywhere in rendered card
// ---------------------------------------------------------------------------

describe("WS6 -- no '$' in rendered card", () => {
  it("tier A card has no dollar sign attached to a number", () => {
    const { container } = render(<BetCard card={makeMLBCard()} />);
    const text = container.textContent ?? "";
    expect(text).not.toMatch(/\$\d/);
    expect(text).not.toMatch(/\$\s\d/);
  });

  it("tier B card has no dollar sign", () => {
    const { container } = render(<BetCard card={makeTierBCard()} />);
    const text = container.textContent ?? "";
    expect(text).not.toMatch(/\$\d/);
  });
});

// ---------------------------------------------------------------------------
// WS6 AC5: Honest-empty only when count==0 -- real cards rendered (not false-empty)
// ---------------------------------------------------------------------------

describe("WS6 -- card renders fully (no false-empty) when data is present", () => {
  it("card with all real fields renders article element", () => {
    render(<BetCard card={makeMLBCard()} />);
    const article = screen.getByRole("article");
    expect(article).toBeInTheDocument();
  });

  it("card shows matchup text", () => {
    render(<BetCard card={makeMLBCard({ matchup: "Houston Astros vs Cleveland Guardians" })} />);
    expect(screen.getByText("Houston Astros vs Cleveland Guardians")).toBeInTheDocument();
  });

  it("card shows best_book", () => {
    render(<BetCard card={makeMLBCard({ best_book: "pinnacle" })} />);
    expect(screen.getByText(/pinnacle/i)).toBeInTheDocument();
  });
});
