// gamecard-polish.test.tsx -- Acceptance tests for GameCard polish (r4 lane).
//
// Verifies:
//   * card <Link> carries a descriptive aria-label
//   * card <Link> has the focus-visible ring Tailwind classes
//   * 'no bet (below floor)' honest state renders when chip.decision !== 'bet'
//   * tier + units render correctly for a real bet
//   * no $<digit> string appears anywhere in the rendered DOM
//   * proxy flag renders in markets (amber marker, no $ fabrication)
//
// No network is hit. The api layer is not needed here (GameCard is pure).
// This lane owns ONLY app/games/GameCard.tsx; it does NOT edit shared
// components. Shared-component bugs are reported.

import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";

import { GameCard } from "../GameCard";
import type { PredictRecord, GameEdge } from "@/lib/p5api";

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

function predRec(over: Partial<PredictRecord> = {}): PredictRecord {
  return {
    sport: "nba",
    game_id: "0042600401",
    home: "San Antonio Spurs",
    away: "New York Knicks",
    tipoff: "2026-06-19T00:30Z",
    pregame_probs: { home_ml: 0.585, away_ml: 0.415 },
    markets: [
      {
        sport: "nba",
        game_id: "0042600401",
        market_type: "moneyline",
        side: "home",
        line: null,
        odds: 1.71,
        book: "dk",
        devigged_prob: 0.585,
        captured_at: null,
        is_close: false,
        clv_is_proxy: true,
      },
      {
        sport: "nba",
        game_id: "0042600401",
        market_type: "total",
        side: "over",
        line: 221.5,
        odds: 1.9,
        book: "dk",
        devigged_prob: 0.51,
        captured_at: null,
        is_close: false,
        clv_is_proxy: false,
      },
    ],
    leak_guard: { in_sample: false },
    produced_at: null,
    ...over,
  };
}

function betEdge(tier = "A", units = 2.25): GameEdge {
  return {
    game_id: "0042600401",
    status: "ok",
    best_bets: [
      {
        market_type: "moneyline",
        side: "home",
        model_prob: 0.585,
        market_prob: 0.55,
        best_book: "dk",
        best_odds: 1.71,
        line: null,
        edge: 0.035,
        ev: 0.03,
        tier,
        decision: "bet",
        stake_units: units,
        flat_unit: 1,
        kelly_units: 0.25,
        clv_is_proxy: true,
      },
    ],
  };
}

function noBetEdge(): GameEdge {
  return { game_id: "0042600401", status: "ok", best_bets: [] };
}

// ---------------------------------------------------------------------------
// A11y: aria-label on the card Link
// ---------------------------------------------------------------------------

describe("GameCard a11y -- aria-label on card Link", () => {
  it("card Link has a descriptive aria-label including both team names", () => {
    render(<GameCard sport="nba" rec={predRec()} edge={null} />);
    const link = screen.getByRole("link");
    const label = link.getAttribute("aria-label") ?? "";
    expect(label).toMatch(/New York Knicks/i);
    expect(label).toMatch(/San Antonio Spurs/i);
  });

  it("aria-label contains 'open game detail' so purpose is clear", () => {
    render(<GameCard sport="nba" rec={predRec()} edge={null} />);
    const link = screen.getByRole("link");
    expect(link.getAttribute("aria-label")).toMatch(/open game detail/i);
  });
});

// ---------------------------------------------------------------------------
// A11y: focus-visible ring classes on the card Link
// ---------------------------------------------------------------------------

describe("GameCard a11y -- focus-visible ring on card Link", () => {
  it("card Link element has focus-visible:ring-2 Tailwind class", () => {
    render(<GameCard sport="nba" rec={predRec()} edge={null} />);
    const link = screen.getByRole("link");
    // Tailwind class is present as a string in the className attribute.
    expect(link.className).toMatch(/focus-visible:ring-2/);
  });

  it("card Link has focus-visible:ring-ring class for design-system colour", () => {
    render(<GameCard sport="nba" rec={predRec()} edge={null} />);
    const link = screen.getByRole("link");
    expect(link.className).toMatch(/focus-visible:ring-ring/);
  });

  it("card Link has focus-visible:outline-none to suppress default browser ring", () => {
    render(<GameCard sport="nba" rec={predRec()} edge={null} />);
    const link = screen.getByRole("link");
    expect(link.className).toMatch(/focus-visible:outline-none/);
  });
});

// ---------------------------------------------------------------------------
// Honest bet state: tier + units chip
// ---------------------------------------------------------------------------

describe("GameCard -- tier + units chip for a real bet", () => {
  it("renders tier label inside the chip", () => {
    render(<GameCard sport="nba" rec={predRec()} edge={betEdge("A", 2.25)} />);
    expect(screen.getByText(/tier A/i)).toBeInTheDocument();
  });

  it("renders stake units inside the chip (e.g. 2.25u)", () => {
    render(<GameCard sport="nba" rec={predRec()} edge={betEdge("A", 2.25)} />);
    expect(screen.getByText(/2\.25u/)).toBeInTheDocument();
  });

  it("renders an aria-label on the bet chip span for screen readers", () => {
    render(<GameCard sport="nba" rec={predRec()} edge={betEdge("B", 1.5)} />);
    const chipWrap = screen.getByLabelText(/best bet: tier B/i);
    expect(chipWrap).toBeInTheDocument();
  });

  it("does NOT show 'no bet' text when a real bet is present", () => {
    render(<GameCard sport="nba" rec={predRec()} edge={betEdge("A", 2.25)} />);
    expect(screen.queryByText(/no bet \(below floor\)/i)).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// Honest no-bet state: chip.decision !== 'bet'
// ---------------------------------------------------------------------------

describe("GameCard -- honest 'no bet (below floor)' state", () => {
  it("renders 'no bet (below floor)' when edge has no qualifying bets", () => {
    render(<GameCard sport="nba" rec={predRec()} edge={noBetEdge()} />);
    expect(screen.getByText(/no bet \(below floor\)/i)).toBeInTheDocument();
  });

  it("renders 'no bet (below floor)' when edge is null (no edge data)", () => {
    render(<GameCard sport="nba" rec={predRec()} edge={null} />);
    expect(screen.getByText(/no bet \(below floor\)/i)).toBeInTheDocument();
  });

  it("renders 'no bet (below floor)' for an unavailable edge", () => {
    const unavailEdge: GameEdge = {
      game_id: "0042600401",
      status: "unavailable",
      reason: "edge service down",
    };
    render(<GameCard sport="nba" rec={predRec()} edge={unavailEdge} />);
    expect(screen.getByText(/no bet \(below floor\)/i)).toBeInTheDocument();
  });

  it("does NOT show a tier chip when the bet state is no-bet", () => {
    render(<GameCard sport="nba" rec={predRec()} edge={noBetEdge()} />);
    expect(screen.queryByText(/^tier [A-DS]/i)).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// Honesty rail: no $ followed by a digit in the rendered DOM
// ---------------------------------------------------------------------------

describe("GameCard -- no $<digit> in DOM (honesty rail)", () => {
  it("bet state: no dollar-amount string in the rendered output", () => {
    const { container } = render(
      <GameCard sport="nba" rec={predRec()} edge={betEdge("A", 3)} />,
    );
    expect(container.textContent ?? "").not.toMatch(/\$\d/);
  });

  it("no-bet state: no dollar-amount string in the rendered output", () => {
    const { container } = render(
      <GameCard sport="nba" rec={predRec()} edge={noBetEdge()} />,
    );
    expect(container.textContent ?? "").not.toMatch(/\$\d/);
  });

  it("null edge: no dollar-amount string in the rendered output", () => {
    const { container } = render(
      <GameCard sport="nba" rec={predRec()} edge={null} />,
    );
    expect(container.textContent ?? "").not.toMatch(/\$\d/);
  });
});

// ---------------------------------------------------------------------------
// Visual polish: proxy flag on market rows
// ---------------------------------------------------------------------------

describe("GameCard -- proxy flag on market rows", () => {
  it("shows 'proxy' label for a market with clv_is_proxy=true", () => {
    render(<GameCard sport="nba" rec={predRec()} edge={null} />);
    expect(screen.getByText(/proxy/i)).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Hierarchy: matchup headline is readable (not empty or just symbols)
// ---------------------------------------------------------------------------

describe("GameCard -- matchup headline", () => {
  it("renders both team names in the matchup header", () => {
    render(<GameCard sport="nba" rec={predRec()} edge={null} />);
    expect(screen.getAllByText(/San Antonio Spurs/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/New York Knicks/).length).toBeGreaterThan(0);
  });

  it("shows tipoff in the card metadata area", () => {
    render(<GameCard sport="nba" rec={predRec()} edge={null} />);
    expect(screen.getByText(/2026-06-19/)).toBeInTheDocument();
  });
});
