import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { api } from "@/lib/p5api";
import type { PnlSeries, PnlSummary } from "@/lib/types";
import { BetsMoneyHeadline } from "@/components/bets/BetsMoneyHeadline";
import { PaperEquityPanel } from "@/components/paper/PaperEquityPanel";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

function series(mean: PnlSummary["mean_clv_pct_or_INSUFFICIENT"]): PnlSeries {
  return {
    status: "ok",
    start_units: 100,
    points: [],
    daily: [],
    summary: {
      total_units: 0,
      current_units: 100,
      n_bets: 2,
      n_win: 1,
      n_loss: 1,
      n_push: 0,
      win_rate: 0.5,
      mean_clv_pct_or_INSUFFICIENT: mean,
    },
    edge_claimed: false,
    executed: false,
  };
}

// Public api_paper_pnl_series.json mean is already a percentage. Adjacent
// win_rate remains a fraction, so it must still be multiplied by 100 for display.
const CASES = [
  { mean: 13.360639, bets: "+13.4%", equity: "+13.36%" },
  { mean: -3.182161, bets: "-3.2%", equity: "-3.18%" },
  { mean: 0.4, bets: "+0.4%", equity: "+0.40%" },
  { mean: 0.008, bets: "+0.0%", equity: "+0.01%" },
  { mean: 0, bets: "+0.0%", equity: "+0.00%" },
  { mean: null, bets: "--", equity: "INSUFFICIENT_DATA" },
  { mean: "INSUFFICIENT_DATA", bets: "INSUFFICIENT_DATA", equity: "INSUFFICIENT_DATA" },
  { mean: "UNPROVEN", bets: "UNPROVEN", equity: "UNPROVEN" },
];

describe("BetsMoneyHeadline PnL mean CLV percentage contract", () => {
  it.each(CASES)("preserves $mean CLV while keeping the fraction win rate", async ({ mean, bets }) => {
    vi.spyOn(api, "getPaperPnlSeries").mockResolvedValue(series(mean));
    vi.spyOn(api, "getPaperBankroll").mockResolvedValue({
      start_units: 100, current_units: 100, updated_at: null,
    });
    vi.spyOn(api, "getPaperClv").mockResolvedValue({
      n_bets: 0, pct_beat_close: null, mean_clv_pct: null,
      by_sport: null, clv_is_proxy: false,
    });
    render(<BetsMoneyHeadline />);
    await waitFor(() => {
      // Also confirms that the PnL response has loaded before sentinel assertions.
      expect(screen.getByTestId("money-winrate")).toHaveTextContent("50%");
      expect(screen.getByTestId("money-clv")).toHaveTextContent(bets);
    });
  });
});

describe("PaperEquityPanel PnL mean CLV percentage contract", () => {
  it.each(CASES)("preserves $mean CLV while keeping the fraction win rate", ({ mean, equity }) => {
    render(<PaperEquityPanel series={series(mean)} bankroll={null} />);
    expect(screen.getByTestId("paper-tally-winrate")).toHaveTextContent("50%");
    expect(screen.getByTestId("paper-tally-clv")).toHaveTextContent(equity);
  });
});
