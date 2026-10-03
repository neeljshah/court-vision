import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { api, type ClvScoreboard as Clv } from "@/lib/p5api";
import { HomeRecordsHero } from "@/components/home/HomeRecordsHero";
import { BetsMoneyHeadline } from "@/components/bets/BetsMoneyHeadline";
import { RecordsClvStrip } from "@/components/records/RecordsClvStrip";
import PaperTradingPage from "@/app/(terminal)/paper-trading/page";

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

describe("HomeRecordsHero CLV rate units", () => {
  it.each([
    { value: 36.3341, expected: "beat close: 36.3%" },
    { value: 0, expected: "beat close: 0.0%" },
    { value: null, expected: "beat-close: pending" },
  ])("preserves $value percent and missing-rate semantics", async ({ value, expected }) => {
    mockFeeds({ ...PUBLIC_CLV, pct_beat_close: value });
    render(<HomeRecordsHero />);
    await waitFor(() => {
      expect(screen.getByTestId("clv-value")).toHaveTextContent(expected);
    });
  });
});

describe("BetsMoneyHeadline CLV rate units", () => {
  it.each([
    { value: 36.3341, expected: /1233 graded vs close; beat-close 36%\./ },
    { value: 0, expected: /1233 graded vs close; beat-close 0%\./ },
    { value: null, expected: /1233 graded vs close; beat-close pending\./ },
  ])("preserves $value percent and missing-rate semantics", async ({ value, expected }) => {
    mockFeeds({ ...PUBLIC_CLV, pct_beat_close: value });
    render(<BetsMoneyHeadline />);
    expect(await screen.findByText(expected)).toBeInTheDocument();
  });
});

describe("PaperTradingPage CLV mean units", () => {
  it.each([
    { value: 4.368363, expected: "+4.4%" },
    { value: 0, expected: "0.0%" },
    { value: null, expected: "--" },
  ])("preserves $value percent and missing-mean semantics", async ({ value, expected }) => {
    mockFeeds({ ...PUBLIC_CLV, mean_clv_pct: value });
    render(<PaperTradingPage />);
    // The proxy note appears only after the combined feed resolves, including
    // when the loaded null mean and the loading placeholder both read "--".
    expect(await screen.findByText("(proxy close)")).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByTestId("clv-mean-clv")).toHaveTextContent(expected);
    });
  });
});

describe("RecordsClvStrip percentage units", () => {
  it.each([
    { rate: 36.3341, mean: 4.368363, expectedRate: "36.3%", expectedMean: "+4.4%" },
    { rate: 0, mean: 0, expectedRate: "0.0%", expectedMean: "+0.0%" },
    { rate: null, mean: null, expectedRate: "--", expectedMean: "--" },
    { rate: 0.4, mean: 0.4, expectedRate: "0.4%", expectedMean: "+0.4%" },
  ])("preserves rate $rate and mean $mean as percentages", ({ rate, mean, expectedRate, expectedMean }) => {
    render(
      <RecordsClvStrip
        clv={{ ...PUBLIC_CLV, pct_beat_close: rate, mean_clv_pct: mean }}
      />,
    );
    expect(screen.getByTestId("clv-strip-beat-close")).toHaveTextContent(expectedRate);
    expect(screen.getByTestId("clv-strip-mean-clv")).toHaveTextContent(expectedMean);
  });
});
