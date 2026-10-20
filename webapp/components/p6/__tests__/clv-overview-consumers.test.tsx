import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { api, type ClvScoreboard as Clv } from "@/lib/p5api";
import PaperTradingPage from "@/app/(terminal)/paper-trading/page";
import { CLV_UNAVAILABLE } from "@/lib/clvUnavailable";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

// Public api_paper_clv.json rates and means are already in percent units.
const PUBLIC_CLV: Clv = {
  n_bets: 1233,
  pct_beat_close: 36.3341,
  mean_clv_pct: 4.368363,
  by_sport: null,
  clv_is_proxy: true,
};

function mockFeeds(clv: Clv) {
  vi.spyOn(api, "getPaperClv").mockResolvedValue(clv);
  vi.spyOn(api, "getPaperPredictions").mockResolvedValue({
    status: "ok", count: 0, predictions: [], edge_claimed: false,
  });
  vi.spyOn(api, "getPaperTrail").mockResolvedValue({ status: "ok", count: 0, trail: [] });
  vi.spyOn(api, "pmTrail").mockResolvedValue({
    status: "ok", generated_at: null, count: 0, trades: [],
  });
  // Secondary feeds are irrelevant to these CLV assertions; keep them honest-empty.
  vi.spyOn(api, "getPaperPnlSeries").mockResolvedValue({ status: "unavailable", reason: "No series" });
  vi.spyOn(api, "getPaperBankroll").mockResolvedValue({ status: "unavailable", reason: "No bankroll" });
}

describe("CLV consumers render only the site-wide Unavailable sentence", () => {
  it.each([4.368363, 0, null])("PaperTradingPage shows no mean CLV (%s)", async (value) => {
    mockFeeds({ ...PUBLIC_CLV, mean_clv_pct: value });
    render(<PaperTradingPage />);
    await waitFor(() => {
      expect(screen.getByTestId("clv-mean-clv")).toHaveTextContent(CLV_UNAVAILABLE);
    });
    expect(screen.queryByText("+4.4%")).toBeNull();
  });
});
