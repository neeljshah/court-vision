import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import { api, type ClvScoreboard as Clv, type QuantClv } from "@/lib/p5api";
import { ClvFeedbackPanel } from "../ClvFeedbackPanel";
import { PaperHistory } from "../PaperHistory";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

// Percent units from public/demo-data/api_paper_clv.json and api_quant_clv.json.
const PUBLIC_CLV: Clv = {
  n_bets: 1233,
  pct_beat_close: 36.3341,
  mean_clv_pct: 4.368363,
  clv_is_proxy: true,
  by_sport: {
    soccer_intl: { n: 4, pct_beat_close: 100, mean_clv_pct: 26.011333 },
  },
};

function stat(label: string, selector: "div" | "span"): HTMLElement {
  const container = screen.getByText(label, { selector }).parentElement;
  if (!container) throw new Error(`Missing stat container for ${label}`);
  return container;
}

function renderFeedback(summary: Clv = PUBLIC_CLV) {
  const payload: QuantClv = {
    status: "ok",
    clv: { ...summary, by_sport: summary.by_sport ?? {}, vs_close_proven: false },
    edge_claimed: false,
    real_money_enabled: false,
  };
  vi.spyOn(api, "getQuantClv").mockResolvedValue(payload);
  vi.spyOn(api, "getImproveTimeline").mockResolvedValue({
    status: "ok", cycles: [], n_promoted: 0, enabled: false, edge_claimed: false,
  });
  render(<ClvFeedbackPanel />);
}

function renderHistory(summary: Clv = PUBLIC_CLV) {
  vi.spyOn(api, "getPaperTrail").mockResolvedValue({ status: "ok", count: 0, trail: [] });
  vi.spyOn(api, "getPaperClv").mockResolvedValue(summary);
  render(<PaperHistory />);
}

describe("ClvFeedbackPanel percentage contract", () => {
  it("renders the public rate as 36% and preserves mean precision as +4.37%", async () => {
    renderFeedback();
    await waitFor(() => {
      expect(within(stat("beat close", "span")).getByText("36%")).toBeInTheDocument();
      expect(within(stat("mean CLV", "span")).getByText("+4.37%")).toBeInTheDocument();
    });
  });

  it("renders the public per-sport 100% rate without scaling the mean", async () => {
    renderFeedback();
    const row = await screen.findByRole("row", { name: /soccer_intl/ });
    expect(within(row).getByText("100%")).toBeInTheDocument();
    expect(within(row).getByText("+26.01%")).toBeInTheDocument();
  });

  it.each([
    { value: 0, rate: "0%", mean: "+0.00%" },
    { value: 0.4, rate: "0%", mean: "+0.40%" },
    { value: null, rate: "--", mean: "--" },
  ])("preserves $value percent and missing values in both summary and sport", async ({ value, rate, mean }) => {
    renderFeedback({
      ...PUBLIC_CLV,
      pct_beat_close: value,
      mean_clv_pct: value,
      by_sport: { nba: { n: 1, pct_beat_close: value, mean_clv_pct: value } },
    });
    await waitFor(() => {
      expect(within(stat("beat close", "span")).getByText(rate)).toBeInTheDocument();
      expect(within(stat("mean CLV", "span")).getByText(mean)).toBeInTheDocument();
    });
    const cells = within(screen.getByRole("row", { name: /nba/ })).getAllByRole("cell");
    expect(cells[2]).toHaveTextContent(mean);
    expect(cells[3]).toHaveTextContent(rate);
  });

  it("keeps an empty ledger distinct from a graded zero-percent rate", async () => {
    renderFeedback({ ...PUBLIC_CLV, n_bets: 0, pct_beat_close: null, mean_clv_pct: null });
    expect(await screen.findByText(/No graded-vs-close bets yet/)).toBeInTheDocument();
    expect(screen.queryByText("beat close", { selector: "span" })).not.toBeInTheDocument();
  });
});

describe("PaperHistory summary percentage contract", () => {
  it("renders public percentages as 36.3% and +4.4%", async () => {
    renderHistory();
    await waitFor(() => {
      expect(within(stat("% beat close", "div")).getByText("36.3%")).toBeInTheDocument();
      expect(within(stat("Mean CLV", "div")).getByText("+4.4%")).toBeInTheDocument();
    });
  });

  it.each([
    { value: 0, rate: "0.0%", mean: "0.0%" },
    { value: 0.4, rate: "0.4%", mean: "+0.4%" },
    { value: null, rate: "--", mean: "--" },
  ])("preserves $value percent and missing summary values", async ({ value, rate, mean }) => {
    renderHistory({ ...PUBLIC_CLV, pct_beat_close: value, mean_clv_pct: value });
    await waitFor(() => {
      expect(within(stat("% beat close", "div")).getByText(rate)).toBeInTheDocument();
      expect(within(stat("Mean CLV", "div")).getByText(mean)).toBeInTheDocument();
    });
  });
});
