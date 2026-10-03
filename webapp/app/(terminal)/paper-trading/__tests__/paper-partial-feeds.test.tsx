import { afterEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, render, screen, waitFor, within } from "@testing-library/react";
import { api } from "@/lib/p5api";
import type { ClvScoreboard, PaperTrailRow, PmTrailRow, PnlSeries } from "@/lib/types";
import clv from "@/public/demo-data/api_paper_clv.json";
import pnlJson from "@/public/demo-data/api_paper_pnl_series.json";
import PaperTradingPage from "../page";

afterEach(() => { cleanup(); vi.restoreAllMocks(); });

const PRIMARY: PaperTrailRow = {
  game_id: "primary-fixture", matchup: "Primary fixture", sport: "nba", side: "home",
  market_type: "moneyline", line: null, taken_book: "fanduel", taken_decimal: 2,
  model_prob: 0.5, model_ev: 0, tier: "B", stake_units: 1, status: "settled",
  graded: true, outcome: "win", clv_pct: 0.4, beat_close: true, clv_is_proxy: false,
  clv_status: "true_close", clv_unavailable: false, clv_note: null, executed: false,
  ts: "2026-09-20T12:00:00Z", settled_at: "2026-09-20T14:00:00Z",
};
const PM: PmTrailRow = {
  bet_id: "pm-fixture", venue: "kalshi", market_id: "PM fixture", model_prob: 0.5,
  confidence: 0.6, units: 1, tier: "B", result: "win", clv: 0.004,
  clv_is_proxy: false, clv_status: "true_close", price_taken: 2,
  ts: "2026-09-20T12:00:00Z",
};
const PNL: PnlSeries = { ...pnlJson, points: [], daily: [] };
const BANK = { start_units: 100, current_units: 101, updated_at: null };
const missing = (name: string) => ({ status: "unavailable" as const, reason: `${name} feed missing` });

function mocks() {
  return {
    trail: vi.spyOn(api, "getPaperTrail").mockResolvedValue({ status: "ok", count: 1, trail: [PRIMARY] }),
    pm: vi.spyOn(api, "pmTrail").mockResolvedValue({ status: "ok", count: 1, generated_at: null, trades: [PM] }),
    clv: vi.spyOn(api, "getPaperClv").mockResolvedValue(clv as ClvScoreboard),
    pnl: vi.spyOn(api, "getPaperPnlSeries").mockResolvedValue(PNL),
    bank: vi.spyOn(api, "getPaperBankroll").mockResolvedValue(BANK),
  };
}

async function summariesLoaded() {
  await waitFor(() => {
    expect(screen.getByTestId("paper-tally-clv")).toHaveTextContent("+13.36%");
    expect(screen.getByTestId("clv-mean-clv")).toHaveTextContent("+4.4%");
  });
}

function noHealthyBadge() {
  const badge = within(screen.getByTestId("live-badge-placeholder")).getByRole("status");
  expect(badge.getAttribute("aria-label")).not.toMatch(/^Live,/);
  expect(badge.getAttribute("aria-label")).not.toMatch(/^Checking/);
}

describe("PaperTradingPage independent feed failures", () => {
  it("keeps healthy PM and summaries when the primary trail is unavailable", async () => {
    mocks().trail.mockResolvedValue(missing("Primary"));
    render(<PaperTradingPage />);
    await summariesLoaded();
    expect(screen.getByRole("grid", { name: "PM paper trade trail" })).toHaveTextContent("PM fixture");
    expect(screen.getAllByText(/Primary feed missing/).length).toBeGreaterThan(0);
    expect(screen.queryByTestId("no-settled-records")).not.toBeInTheDocument();
    expect(screen.getByTestId("done-total")).toHaveTextContent("--");
    expect(screen.getByTestId("scope-all")).toBeDisabled();
    expect(screen.getByTestId("scope-all")).toHaveTextContent("--");
    noHealthyBadge();
  });

  it("keeps the primary book and summaries when the PM trail is unavailable", async () => {
    mocks().pm.mockResolvedValue(missing("PM"));
    render(<PaperTradingPage />);
    await summariesLoaded();
    expect(screen.getByTestId("settled-records-table")).toHaveTextContent("Primary fixture");
    expect(screen.getAllByText(/PM feed missing/).length).toBeGreaterThan(0);
    expect(screen.getByTestId("tally-open")).toHaveTextContent("--");
    expect(screen.queryByTestId("no-paper-trades")).not.toBeInTheDocument();
    expect(screen.queryByTestId("pm-total-count")).not.toBeInTheDocument();
    expect(screen.queryByText("No PM markets right now.")).not.toBeInTheDocument();
    noHealthyBadge();
  });

  it("preserves summaries but avoids false zero counts when both trails are missing", async () => {
    const calls = mocks();
    calls.trail.mockResolvedValue(missing("Primary"));
    calls.pm.mockResolvedValue(missing("PM"));
    render(<PaperTradingPage />);
    await summariesLoaded();
    for (const id of ["done-total", "done-win", "done-units-staked", "tally-open", "tally-win", "tally-units-staked"]) {
      expect(screen.getByTestId(id)).toHaveTextContent("--");
    }
    expect(screen.queryByTestId("no-paper-trades")).not.toBeInTheDocument();
    expect(screen.queryByTestId("open-positions-empty")).not.toBeInTheDocument();
    expect(screen.queryByTestId("no-settled-records")).not.toBeInTheDocument();
    expect(within(screen.getByTestId("venue-summary-section")).getAllByText(/unavailable/i).length).toBeGreaterThan(0);
    noHealthyBadge();
  });

  it("settles an all-unavailable response without loading forever or fabricating zeros", async () => {
    const calls = mocks();
    calls.trail.mockResolvedValue(missing("Primary"));
    calls.pm.mockResolvedValue(missing("PM"));
    calls.clv.mockResolvedValue(missing("CLV"));
    calls.pnl.mockResolvedValue(missing("PnL"));
    calls.bank.mockResolvedValue(missing("Bankroll"));
    render(<PaperTradingPage />);
    expect(await screen.findByRole("status", { name: "Unavailable paper data" })).toBeInTheDocument();
    await waitFor(() => expect(screen.getByTestId("done-total")).toHaveTextContent("--"));
    expect(screen.getByTestId("tally-open")).toHaveTextContent("--");
    expect(screen.getByTestId("clv-mean-clv")).toHaveTextContent("--");
    expect(screen.queryByTestId("paper-equity-chart")).not.toBeInTheDocument();
    expect(screen.queryByTestId("no-paper-trades")).not.toBeInTheDocument();
    expect(screen.queryByTestId("open-positions-loading")).not.toBeInTheDocument();
    noHealthyBadge();
  });

  it("retains genuine empty-ledger messages and real zero counts on healthy empty feeds", async () => {
    const calls = mocks();
    calls.trail.mockResolvedValue({ status: "ok", count: 0, trail: [] });
    calls.pm.mockResolvedValue({ status: "ok", count: 0, generated_at: null, trades: [] });
    render(<PaperTradingPage />);
    await summariesLoaded();
    expect(screen.getByTestId("no-paper-trades")).toHaveTextContent("No live PM game markets right now");
    expect(screen.getByTestId("open-positions-empty")).toBeInTheDocument();
    expect(screen.getByTestId("no-settled-records")).toBeInTheDocument();
    expect(screen.getByTestId("done-total")).toHaveTextContent("0");
    expect(screen.getByTestId("tally-open")).toHaveTextContent("0");
  });

  it("drops failed primary rows after a good poll while retaining healthy PM and summaries", async () => {
    const calls = mocks();
    vi.spyOn(document, "hidden", "get").mockReturnValue(false);
    render(<PaperTradingPage />);
    await summariesLoaded();
    expect(screen.getByTestId("settled-records-table")).toHaveTextContent("Primary fixture");
    calls.trail.mockResolvedValue(missing("Primary"));
    act(() => { document.dispatchEvent(new Event("visibilitychange")); });
    await waitFor(() => expect(screen.getAllByText(/Primary feed missing/).length).toBeGreaterThan(0));
    expect(screen.queryAllByText("Primary fixture")).toHaveLength(0);
    expect(screen.queryByTestId("settled-records-table")).not.toBeInTheDocument();
    expect(screen.getByRole("grid", { name: "PM paper trade trail" })).toHaveTextContent("PM fixture");
    await summariesLoaded();
    noHealthyBadge();
  });

  it("keeps a valid bankroll balance when PnL is unavailable without showing a fabricated daily series", async () => {
    mocks().pnl.mockResolvedValue(missing("PnL"));
    render(<PaperTradingPage />);
    await waitFor(() => expect(screen.getByTestId("paper-balance-headline")).toHaveTextContent("101.00"));
    expect(screen.queryByTestId("paper-equity-chart")).not.toBeInTheDocument();
    expect(screen.queryByTestId("paper-daily-empty")).not.toBeInTheDocument();
    expect(within(screen.getByTestId("paper-equity-panel")).getAllByText(/unavailable/i).length).toBeGreaterThan(0);
    noHealthyBadge();
  });
});
