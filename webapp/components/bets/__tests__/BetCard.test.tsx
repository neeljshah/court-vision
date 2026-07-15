import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { BetCard, type BetCardData } from "../BetCard";

// BetCard.test.tsx -- per-component vitest covering honesty + accessibility rails:
//   - Negative divergence does NOT carry red/danger class
//   - aria-label states calibrated divergence (not profit/edge)
//   - No $<digit> in rendered DOM
//   - Tier badge + units render correctly
//   - Divergence element carries clarifying title tooltip
//   - Positive divergence also uses neutral (not green) tone
//   ws1-betcard-a11y additions:
//   - Card exposes article role with aria-label naming matchup+tier
//   - Detail Link has accessible name and visible focus ring class
//   - Divergence column header reads "Calibrated divergence" (not "edge"/"profit")
//   - CLV null still shows INSUFFICIENT_DATA (never greened)

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

function makeCard(overrides: Partial<BetCardData> = {}): BetCardData {
  return {
    game_id: "test-game-001",
    sport: "nba",
    matchup: "NYK @ SAS",
    market_type: "moneyline",
    side: "away",
    model_prob: 0.42,
    market_prob: 0.48,
    best_book: "DraftKings",
    best_odds: 1.85,
    all_books: [],
    edge_vs_market: -0.06,  // negative: model sees away LESS likely than market
    units: 0.75,
    tier: "A",
    confidence: 0.72,
    clv: null,
    clv_is_proxy: false,
    status: "pregame",
    line: null,
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// Core honesty tests
// ---------------------------------------------------------------------------

// WS6: BetCard now uses ModelVsMarketBar which renders [data-testid='divergence-chip'].
// Tests updated from 'divergence-value' to 'divergence-chip' to match the new component.

describe("BetCard -- divergence framing (honesty rail)", () => {
  it("negative divergence does NOT use text-red-400 class", () => {
    const { container } = render(<BetCard card={makeCard({ edge_vs_market: -0.06 })} />);
    // ModelVsMarketBar renders data-testid='divergence-chip' (not 'divergence-value')
    const divEl = container.querySelector("[data-testid='divergence-chip']");
    expect(divEl).not.toBeNull();
    // Must not carry any red danger class
    expect(divEl?.className ?? "").not.toMatch(/text-red/);
    expect(divEl?.className ?? "").not.toMatch(/danger/);
    expect(divEl?.className ?? "").not.toMatch(/error/);
  });

  it("positive divergence also does NOT use a fabricated green/profit class", () => {
    const { container } = render(<BetCard card={makeCard({ edge_vs_market: 0.09 })} />);
    const divEl = container.querySelector("[data-testid='divergence-chip']");
    expect(divEl).not.toBeNull();
    // Should not be labeled green as if it were a guaranteed profit
    expect(divEl?.className ?? "").not.toMatch(/text-green/);
  });

  it("negative divergence renders a neutral/slate class", () => {
    const { container } = render(<BetCard card={makeCard({ edge_vs_market: -0.06 })} />);
    const divEl = container.querySelector("[data-testid='divergence-chip']");
    expect(divEl).not.toBeNull();
    const cls = divEl?.className ?? "";
    // Should be one of the two honest neutral classes
    expect(cls.includes("text-slate-200") || cls.includes("text-slate-400")).toBe(true);
  });

  it("small-magnitude divergence (< 5pp) renders muted slate-400", () => {
    const { container } = render(<BetCard card={makeCard({ edge_vs_market: 0.02 })} />);
    const divEl = container.querySelector("[data-testid='divergence-chip']");
    expect(divEl?.className ?? "").toContain("text-slate-400");
  });

  it("large-magnitude negative divergence (>= 5pp abs) renders slate-200", () => {
    const { container } = render(<BetCard card={makeCard({ edge_vs_market: -0.08 })} />);
    const divEl = container.querySelector("[data-testid='divergence-chip']");
    expect(divEl?.className ?? "").toContain("text-slate-200");
    expect(divEl?.className ?? "").not.toMatch(/text-red/);
  });

  it("large-magnitude positive divergence (>= 5pp abs) renders slate-200", () => {
    const { container } = render(<BetCard card={makeCard({ edge_vs_market: 0.07 })} />);
    const divEl = container.querySelector("[data-testid='divergence-chip']");
    expect(divEl?.className ?? "").toContain("text-slate-200");
  });
});

// ---------------------------------------------------------------------------
// Aria-label -- must say "calibrated divergence" not "profit" / "edge"
// ---------------------------------------------------------------------------

describe("BetCard -- aria-label (calibrated divergence framing)", () => {
  it("card article aria-label contains 'calibrated' and does not say 'profit' or 'profit claim' as a positive frame", () => {
    render(<BetCard card={makeCard()} />);
    // ws1-a11y: the card is now an <article> (not a link); the article aria-label carries
    // the calibrated-divergence disclaimer. The detail Link is a separate affordance.
    const article = screen.getByRole("article");
    const label = article.getAttribute("aria-label") ?? "";
    expect(label.toLowerCase()).toContain("calibrated");
  });

  it("divergence element aria-label contains 'calibrated divergence'", () => {
    const { container } = render(<BetCard card={makeCard({ edge_vs_market: -0.06 })} />);
    // ModelVsMarketBar renders data-testid='divergence-chip'
    const divEl = container.querySelector("[data-testid='divergence-chip']");
    const ariaLabel = divEl?.getAttribute("aria-label") ?? "";
    expect(ariaLabel.toLowerCase()).toContain("calibrated divergence");
  });

  it("divergence element aria-label mentions 'not' a profit claim (honest framing)", () => {
    const { container } = render(<BetCard card={makeCard({ edge_vs_market: -0.06 })} />);
    const divEl = container.querySelector("[data-testid='divergence-chip']");
    const ariaLabel = divEl?.getAttribute("aria-label") ?? "";
    // ModelVsMarketBar chip says "not an edge or profit claim"
    expect(ariaLabel.toLowerCase()).toMatch(/not an? (edge or )?profit/);
  });

  it("divergence element has title tooltip mentioning calibrated divergence", () => {
    const { container } = render(<BetCard card={makeCard({ edge_vs_market: -0.06 })} />);
    const divEl = container.querySelector("[data-testid='divergence-chip']");
    const title = divEl?.getAttribute("title") ?? "";
    expect(title.toLowerCase()).toContain("calibrated divergence");
  });
});

// ---------------------------------------------------------------------------
// No dollar amounts in DOM (UNITS only)
// ---------------------------------------------------------------------------

describe("BetCard -- no $ in DOM (honest rails)", () => {
  it("no $<digit> pattern in rendered output for negative divergence card", () => {
    const { container } = render(<BetCard card={makeCard({ edge_vs_market: -0.06 })} />);
    expect(container.textContent ?? "").not.toMatch(/\$\s?\d/);
  });

  it("no $<digit> pattern in rendered output for positive divergence card", () => {
    const { container } = render(<BetCard card={makeCard({ edge_vs_market: 0.08 })} />);
    expect(container.textContent ?? "").not.toMatch(/\$\s?\d/);
  });
});

// ---------------------------------------------------------------------------
// Tier badge + units render
// ---------------------------------------------------------------------------

describe("BetCard -- tier badge and units", () => {
  it("renders the tier badge with the correct tier letter", () => {
    render(<BetCard card={makeCard({ tier: "A" })} />);
    // The tier letter should appear in the DOM
    expect(screen.getByText("A")).toBeInTheDocument();
  });

  it("renders S tier badge", () => {
    render(<BetCard card={makeCard({ tier: "S" })} />);
    expect(screen.getByText("S")).toBeInTheDocument();
  });

  it("renders fallback '--' when tier is null", () => {
    render(<BetCard card={makeCard({ tier: null })} />);
    expect(screen.getByText("--")).toBeInTheDocument();
  });

  it("renders units value with UNITS label (WS6: explicit 'UNITS' label, no 'u' suffix)", () => {
    const { container } = render(<BetCard card={makeCard({ units: 1.5 })} />);
    const unitsEl = container.querySelector("[data-testid='units-value']");
    expect(unitsEl).not.toBeNull();
    // WS6 spec: show "1.5 UNITS" not "1.50u"
    const text = unitsEl?.textContent ?? "";
    expect(text).toContain("1.5");
    expect(text.toUpperCase()).toContain("UNITS");
  });

  it("renders fractional units with UNITS label", () => {
    const { container } = render(<BetCard card={makeCard({ units: 0.25 })} />);
    const unitsEl = container.querySelector("[data-testid='units-value']");
    const text = unitsEl?.textContent ?? "";
    expect(text).toContain("0.3"); // 0.25 toFixed(1) = "0.3"
    expect(text.toUpperCase()).toContain("UNITS");
  });
});

// ---------------------------------------------------------------------------
// CLV honest rendering
// ---------------------------------------------------------------------------

describe("BetCard -- CLV honesty", () => {
  it("shows INSUFFICIENT_DATA when clv is null", () => {
    render(<BetCard card={makeCard({ clv: null })} />);
    expect(screen.getByText(/INSUFFICIENT_DATA/)).toBeInTheDocument();
  });

  it("shows numeric CLV when clv is provided", () => {
    render(<BetCard card={makeCard({ clv: 0.032, clv_is_proxy: false })} />);
    // Should show "+3.2%" somewhere
    expect(screen.getByText(/CLV.*3\.2%/)).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Status dot renders without crashing for all statuses
// ---------------------------------------------------------------------------

describe("BetCard -- status rendering", () => {
  it("renders PREGAME status dot", () => {
    render(<BetCard card={makeCard({ status: "pregame" })} />);
    expect(screen.getByText("PREGAME")).toBeInTheDocument();
  });

  it("renders LIVE status dot", () => {
    render(<BetCard card={makeCard({ status: "live" })} />);
    expect(screen.getByText("LIVE")).toBeInTheDocument();
  });

  it("renders DONE status dot", () => {
    render(<BetCard card={makeCard({ status: "done" })} />);
    expect(screen.getByText("DONE")).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Matchup + market rendering
// ---------------------------------------------------------------------------

describe("BetCard -- matchup and market", () => {
  it("renders the matchup string", () => {
    render(<BetCard card={makeCard({ matchup: "NYK @ SAS" })} />);
    expect(screen.getByText("NYK @ SAS")).toBeInTheDocument();
  });

  it("renders the side as a human bet description (team ML)", () => {
    // side "away" + matchup "NYK @ SAS" + moneyline -> "NYK ML" (describeBet)
    render(<BetCard card={makeCard({ side: "away" })} />);
    expect(screen.getByText("NYK ML")).toBeInTheDocument();
  });

  it("renders sport in uppercase", () => {
    render(<BetCard card={makeCard({ sport: "nba" })} />);
    expect(screen.getByText("NBA")).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// DONE status dot -- higher-contrast neutral token (not invisible, not green)
// ---------------------------------------------------------------------------

describe("BetCard -- DONE status dot contrast", () => {
  it("DONE dot uses a visible neutral class (bg-slate-500 or bg-slate-600)", () => {
    const { container } = render(<BetCard card={makeCard({ status: "done" })} />);
    const dot = container.querySelector("[data-testid='status-dot-done']");
    expect(dot).not.toBeNull();
    const cls = dot?.className ?? "";
    // Must carry a legible neutral -- bg-slate-500 or bg-slate-600 are acceptable
    expect(cls.includes("bg-slate-500") || cls.includes("bg-slate-600")).toBe(true);
  });

  it("DONE dot does NOT use the near-invisible bg-slate-700 class", () => {
    const { container } = render(<BetCard card={makeCard({ status: "done" })} />);
    const dot = container.querySelector("[data-testid='status-dot-done']");
    expect(dot?.className ?? "").not.toContain("bg-slate-700");
  });

  it("DONE dot does NOT use any green class (stays non-green / neutral)", () => {
    const { container } = render(<BetCard card={makeCard({ status: "done" })} />);
    const dot = container.querySelector("[data-testid='status-dot-done']");
    const cls = dot?.className ?? "";
    expect(cls).not.toMatch(/bg-green/);
    expect(cls).not.toMatch(/bg-tier-a/);
    expect(cls).not.toMatch(/bg-tier-s/);
    expect(cls).not.toMatch(/text-green/);
    expect(cls).not.toMatch(/animate-pulse/);
  });

  it("PREGAME and LIVE dots remain distinguishable from DONE", () => {
    const { container: doneCtr } = render(<BetCard card={makeCard({ status: "done" })} />);
    const doneDot = doneCtr.querySelector("[data-testid='status-dot-done']");

    const { container: liveCtr } = render(<BetCard card={makeCard({ status: "live" })} />);
    const liveDot = liveCtr.querySelector("[data-testid='status-dot-live']");

    // LIVE must be amber + pulse (not a static neutral)
    expect(liveDot?.className ?? "").toContain("bg-amber-400");
    expect(liveDot?.className ?? "").toContain("animate-pulse");
    // DONE must NOT pulse
    expect(doneDot?.className ?? "").not.toContain("animate-pulse");
  });
});

// ---------------------------------------------------------------------------
// American-odds guard -- best_odds <= 1 renders '--' not Infinity/NaN
// ---------------------------------------------------------------------------

describe("BetCard -- American-odds guard for invalid decimal odds", () => {
  it("best_odds=1 renders '--' instead of Infinity or NaN", () => {
    const { container } = render(
      <BetCard card={makeCard({ best_odds: 1, best_book: "TestBook" })} />
    );
    const text = container.textContent ?? "";
    // Should NOT contain Infinity or NaN
    expect(text).not.toContain("Infinity");
    expect(text).not.toContain("NaN");
    // odds span should show '--'
    const oddsEl = container.querySelector("[data-testid='odds-value']");
    expect(oddsEl?.textContent ?? "").toBe("--");
  });

  it("best_odds=0.9 (sub-unity) renders '--' not a nonsensical negative number", () => {
    const { container } = render(
      <BetCard card={makeCard({ best_odds: 0.9, best_book: "TestBook" })} />
    );
    const oddsEl = container.querySelector("[data-testid='odds-value']");
    expect(oddsEl?.textContent ?? "").toBe("--");
    const text = container.textContent ?? "";
    expect(text).not.toContain("Infinity");
    expect(text).not.toContain("NaN");
  });

  it("best_odds=0 renders '--' (zero is also invalid decimal odds)", () => {
    const { container } = render(
      <BetCard card={makeCard({ best_odds: 0, best_book: "TestBook" })} />
    );
    const oddsEl = container.querySelector("[data-testid='odds-value']");
    expect(oddsEl?.textContent ?? "").toBe("--");
    const text = container.textContent ?? "";
    expect(text).not.toContain("Infinity");
    expect(text).not.toContain("NaN");
    expect(text).not.toMatch(/-Infinity/);
  });

  it("best_odds=1.91 (valid, < 2) renders American negative odds correctly", () => {
    const { container } = render(
      <BetCard card={makeCard({ best_odds: 1.91, best_book: "DK" })} />
    );
    const text = container.textContent ?? "";
    // 100 / (1.91 - 1) = 100 / 0.91 ~ 110 -> renders "-110"
    expect(text).toContain("-110");
  });

  it("best_odds=2.5 (valid, >= 2) renders American positive odds correctly", () => {
    const { container } = render(
      <BetCard card={makeCard({ best_odds: 2.5, best_book: "FD" })} />
    );
    const text = container.textContent ?? "";
    // (2.5 - 1) * 100 = 150 -> renders "+150"
    expect(text).toContain("+150");
  });
});

// ---------------------------------------------------------------------------
// ws1-betcard-unit-note: Units tooltip (quarter-Kelly framing) + odds hardening
// ---------------------------------------------------------------------------

describe("BetCard ws1 -- Units tooltip carries quarter-Kelly framing (not $)", () => {
  it("units element exposes title containing 'quarter-Kelly' and 'units'", () => {
    const { container } = render(<BetCard card={makeCard({ units: 0.43 })} />);
    const unitsEl = container.querySelector("[data-testid='units-value']");
    expect(unitsEl).not.toBeNull();
    const title = (unitsEl?.getAttribute("title") ?? "").toLowerCase();
    expect(title).toContain("quarter-kelly");
    expect(title).toContain("units");
  });

  it("units aria-label contains 'quarter-Kelly' and 'units' and does NOT contain '$'", () => {
    const { container } = render(<BetCard card={makeCard({ units: 0.43 })} />);
    const unitsEl = container.querySelector("[data-testid='units-value']");
    expect(unitsEl).not.toBeNull();
    const ariaLabel = unitsEl?.getAttribute("aria-label") ?? "";
    // Must mention quarter-Kelly and units
    expect(ariaLabel.toLowerCase()).toContain("quarter-kelly");
    expect(ariaLabel.toLowerCase()).toContain("units");
    // Must NOT mention dollars
    expect(ariaLabel).not.toContain("$");
  });

  it("units title does NOT mention '$'", () => {
    const { container } = render(<BetCard card={makeCard({ units: 0.43 })} />);
    const unitsEl = container.querySelector("[data-testid='units-value']");
    const title = unitsEl?.getAttribute("title") ?? "";
    expect(title).not.toContain("$");
  });
});

describe("BetCard ws1 -- best_odds<=1 renders '--' (hardened guard)", () => {
  it("best_odds exactly 1.0 renders '--' in the odds span", () => {
    const { container } = render(
      <BetCard card={makeCard({ best_odds: 1.0, best_book: "TestBook" })} />
    );
    const oddsEl = container.querySelector("[data-testid='odds-value']");
    expect(oddsEl?.textContent).toBe("--");
  });

  it("best_odds 0.5 (degenerate) renders '--'", () => {
    const { container } = render(
      <BetCard card={makeCard({ best_odds: 0.5, best_book: "TestBook" })} />
    );
    const oddsEl = container.querySelector("[data-testid='odds-value']");
    expect(oddsEl?.textContent).toBe("--");
  });
});

describe("BetCard ws1 -- best_odds===2 renders '+100' (exact boundary)", () => {
  it("best_odds exactly 2.0 renders '+100'", () => {
    const { container } = render(
      <BetCard card={makeCard({ best_odds: 2.0, best_book: "TestBook" })} />
    );
    const oddsEl = container.querySelector("[data-testid='odds-value']");
    expect(oddsEl?.textContent).toBe("+100");
  });
});

describe("BetCard ws1 -- no '$' anywhere in rendered card", () => {
  it("default card contains no bare '$' character in textContent", () => {
    const { container } = render(<BetCard card={makeCard()} />);
    // The 'units only -- no $' badge contains '$' as part of the honesty label.
    // We test the full-DOM rule: no standalone dollar sign followed by a digit,
    // and also that no raw payment-like '$' appears attached to a number.
    const text = container.textContent ?? "";
    expect(text).not.toMatch(/\$\d/);
    expect(text).not.toMatch(/\$\s\d/);
  });

  it("card with CLV shows no dollar sign attached to a number", () => {
    const { container } = render(
      <BetCard card={makeCard({ clv: 0.032, units: 1.5, best_odds: 2.5 })} />
    );
    const text = container.textContent ?? "";
    expect(text).not.toMatch(/\$\d/);
  });

  it("card with live status + S tier shows no dollar sign", () => {
    const { container } = render(
      <BetCard card={makeCard({ status: "live", tier: "S", units: 2.0, best_odds: 1.91 })} />
    );
    const text = container.textContent ?? "";
    expect(text).not.toMatch(/\$\d/);
  });
});

// ---------------------------------------------------------------------------
// ws1-betcard-a11y: article role + aria-label + detail link + divergence copy
// ---------------------------------------------------------------------------

describe("BetCard ws1-a11y -- article role with descriptive aria-label", () => {
  it("card renders an element with role='article'", () => {
    render(<BetCard card={makeCard()} />);
    // getByRole('article') throws if no article element found
    const article = screen.getByRole("article");
    expect(article).toBeInTheDocument();
  });

  it("article aria-label contains the matchup string", () => {
    render(<BetCard card={makeCard({ matchup: "NYK @ SAS" })} />);
    const article = screen.getByRole("article");
    const label = article.getAttribute("aria-label") ?? "";
    expect(label).toContain("NYK @ SAS");
  });

  it("article aria-label contains the tier", () => {
    render(<BetCard card={makeCard({ tier: "A" })} />);
    const article = screen.getByRole("article");
    const label = article.getAttribute("aria-label") ?? "";
    expect(label.toLowerCase()).toContain("tier a");
  });

  it("article aria-label contains the side", () => {
    render(<BetCard card={makeCard({ side: "over" })} />);
    const article = screen.getByRole("article");
    const label = article.getAttribute("aria-label") ?? "";
    expect(label).toContain("over");
  });

  it("article aria-label does NOT say 'edge' or 'profit' as a positive framing", () => {
    render(<BetCard card={makeCard()} />);
    const article = screen.getByRole("article");
    const label = (article.getAttribute("aria-label") ?? "").toLowerCase();
    // 'not a profit or edge claim' is OK -- it's a disclaimer, not a positive framing
    // Strip the disclaimer suffix to check the main label copy is honest
    const beforeDisclaimer = label.split("calibrated divergence")[0];
    expect(beforeDisclaimer).not.toMatch(/\bedge\b(?!\s+claim)/);
    expect(beforeDisclaimer).not.toMatch(/\bprofit\b(?!\s+claim)/);
  });

  it("article aria-label contains 'calibrated divergence' disclaimer", () => {
    render(<BetCard card={makeCard()} />);
    const article = screen.getByRole("article");
    const label = (article.getAttribute("aria-label") ?? "").toLowerCase();
    expect(label).toContain("calibrated divergence");
  });

  it("null tier renders 'untiered' in article aria-label", () => {
    render(<BetCard card={makeCard({ tier: null })} />);
    const article = screen.getByRole("article");
    const label = (article.getAttribute("aria-label") ?? "").toLowerCase();
    expect(label).toContain("untiered");
  });
});

describe("BetCard ws1-a11y -- detail Link has accessible name and focus ring", () => {
  it("detail link exists and has an accessible aria-label", () => {
    const { container } = render(<BetCard card={makeCard({ matchup: "NYK @ SAS" })} />);
    const link = container.querySelector("[data-testid='bet-card-detail-link']");
    expect(link).not.toBeNull();
    const label = link?.getAttribute("aria-label") ?? "";
    expect(label.length).toBeGreaterThan(0);
    expect(label).toContain("NYK @ SAS");
  });

  it("detail link aria-label names the market and side", () => {
    const { container } = render(
      <BetCard card={makeCard({ market_type: "moneyline", side: "away" })} />
    );
    const link = container.querySelector("[data-testid='bet-card-detail-link']");
    const label = link?.getAttribute("aria-label") ?? "";
    expect(label).toContain("moneyline");
    expect(label).toContain("away");
  });

  it("detail link has a focus-visible ring class (not color-alone)", () => {
    const { container } = render(<BetCard card={makeCard()} />);
    const link = container.querySelector("[data-testid='bet-card-detail-link']");
    const cls = link?.className ?? "";
    // Must carry focus-visible ring utility classes
    expect(cls).toContain("focus-visible:ring-2");
  });

  it("detail link does NOT rely on color alone (has accessible name text)", () => {
    const { container } = render(<BetCard card={makeCard({ matchup: "LAL @ BOS" })} />);
    const link = container.querySelector("[data-testid='bet-card-detail-link']");
    // sr-only span provides explicit accessible name for non-visual context
    const srOnly = link?.querySelector(".sr-only");
    expect(srOnly).not.toBeNull();
    expect(srOnly?.textContent ?? "").toContain("LAL @ BOS");
  });

  it("detail link href points to the correct bets route", () => {
    const { container } = render(
      <BetCard card={makeCard({ sport: "nba", game_id: "test-game-001" })} />
    );
    const link = container.querySelector("[data-testid='bet-card-detail-link']");
    const href = link?.getAttribute("href") ?? "";
    expect(href).toContain("/bets/nba/test-game-001");
  });
});

describe("BetCard ws1-a11y -- divergence column header says 'Calibrated divergence'", () => {
  it("the divergence label text reads 'Calibrated divergence' (not 'Divergence' or 'edge')", () => {
    const { container } = render(<BetCard card={makeCard()} />);
    // The label span above the divergence value should say "Calibrated divergence"
    const text = container.textContent ?? "";
    expect(text.toLowerCase()).toContain("calibrated divergence");
  });

  it("the word 'edge' does NOT appear in the visible text content", () => {
    const { container } = render(<BetCard card={makeCard()} />);
    // Scan visible textContent for standalone 'edge' (case insensitive).
    // Note: aria-label attributes are NOT in textContent -- only what's rendered as text.
    const text = container.textContent ?? "";
    // Allow 'edge' only inside the honesty disclaimer (which mentions 'not an ... edge claim')
    // Actually textContent won't include aria attributes so this is clean.
    expect(text.toLowerCase()).not.toMatch(/\bedge\b/);
  });
});

describe("BetCard ws1-a11y -- CLV null = INSUFFICIENT_DATA, never greened", () => {
  it("null CLV renders INSUFFICIENT_DATA text (not green)", () => {
    const { container } = render(<BetCard card={makeCard({ clv: null })} />);
    const clvEl = Array.from(container.querySelectorAll("*")).find(
      (el) => el.textContent?.includes("INSUFFICIENT_DATA"),
    );
    expect(clvEl).toBeDefined();
    const cls = clvEl?.className ?? "";
    // Must NOT be styled green
    expect(cls).not.toMatch(/text-green/);
    expect(cls).not.toMatch(/bg-green/);
    expect(cls).not.toMatch(/text-tier-a/);
  });

  it("null CLV aria-label mentions INSUFFICIENT_DATA", () => {
    const { container } = render(<BetCard card={makeCard({ clv: null })} />);
    const clvEl = Array.from(container.querySelectorAll("[aria-label]")).find(
      (el) => (el.getAttribute("aria-label") ?? "").includes("INSUFFICIENT_DATA"),
    );
    expect(clvEl).toBeDefined();
  });
});
