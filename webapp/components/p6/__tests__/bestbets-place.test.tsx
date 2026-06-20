import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";

import { BestBets } from "../BestBets";
import { api, type GameEdge, type BestBet } from "@/lib/p5api";

// ---------------------------------------------------------------------------
// VIEW A (PT-P0-01): "Place paper bet" flow on a best-bet row.
//   * a "bet" row exposes a Place-paper-bet action; a no_bet row does not
//   * the dialog maps best_book -> book, best_odds -> taken_decimal and POSTs
//     via api.placePaper (paper-only; NO $ field)
//   * a confirmed placement reflects an open paper trade on the row
//   * a rejected placement surfaces the real reason and keeps the dialog open
// ---------------------------------------------------------------------------

function mkBet(over: Partial<BestBet> = {}): BestBet {
  return {
    market_type: "moneyline",
    side: "home",
    model_prob: 0.56,
    market_prob: 0.52,
    best_book: "fanduel",
    best_odds: 1.91,
    line: null,
    edge: 0.04,
    ev: 0.06,
    tier: "A",
    decision: "bet",
    stake_units: 0.5,
    flat_unit: 0.5,
    kelly_units: 0.4,
    clv_is_proxy: true,
    ...over,
  };
}

function mkGame(bets: BestBet[]): GameEdge {
  return {
    game_id: "0042100101",
    status: "ok",
    best_bets: bets,
    candidates: bets,
  };
}

afterEach(() => vi.restoreAllMocks());

describe("BestBets -- place paper bet action", () => {
  it("shows the action only on a bet row, not a no_bet row", () => {
    const game = mkGame([
      mkBet(),
      mkBet({ side: "away", decision: "no_bet" }),
    ]);
    render(<BestBets game={game} sport="nba" />);
    const buttons = screen.getAllByRole("button", { name: /place paper bet/i });
    expect(buttons).toHaveLength(1);
  });

  it("maps best_book/best_odds and POSTs paper-only; reflects open trade", async () => {
    const spy = vi
      .spyOn(api, "placePaper")
      .mockResolvedValue({ status: "ok", bet: {} });
    render(<BestBets game={mkGame([mkBet()])} sport="nba" />);

    fireEvent.click(screen.getByRole("button", { name: /place paper bet/i }));
    fireEvent.click(screen.getByRole("button", { name: /record paper bet/i }));

    await waitFor(() => expect(spy).toHaveBeenCalledTimes(1));
    const payload = spy.mock.calls[0][0];
    expect(payload).toEqual({
      sport: "nba",
      game_id: "0042100101",
      market_type: "moneyline",
      side: "home",
      book: "fanduel", // best_book -> book
      taken_decimal: 1.91, // best_odds -> taken_decimal
    });
    // NO $/amount/stake_units in the placement payload (server sizes units).
    expect(Object.keys(payload)).not.toContain("stake_units");
    expect(JSON.stringify(payload)).not.toContain("$");

    await waitFor(() =>
      expect(screen.getByText(/open paper/i)).toBeTruthy(),
    );
  });

  it("surfaces the rejection reason and keeps the dialog open", async () => {
    vi.spyOn(api, "placePaper").mockResolvedValue({
      status: "rejected",
      reason: "below tier floor",
    });
    render(<BestBets game={mkGame([mkBet()])} sport="nba" />);

    fireEvent.click(screen.getByRole("button", { name: /place paper bet/i }));
    fireEvent.click(screen.getByRole("button", { name: /record paper bet/i }));

    await waitFor(() =>
      expect(screen.getByText(/below tier floor/i)).toBeTruthy(),
    );
    // dialog still open -> the record button is still present
    expect(
      screen.getByRole("button", { name: /record paper bet/i }),
    ).toBeTruthy();
  });
});
