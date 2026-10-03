import { afterEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, render, screen, waitFor, within } from "@testing-library/react";
import { api } from "@/lib/p5api";
import * as honestFetch from "@/lib/fetchHonest";
import type { PnlSeries } from "@/lib/types";
import type { TodayBet } from "@/lib/paperToday";
import pnlJson from "@/public/demo-data/api_paper_pnl_series.json";
import { TodayPlacedBets } from "../TodayPlacedBets";

afterEach(() => { cleanup(); vi.restoreAllMocks(); });

const OFFLINE = { status: "unavailable" as const, reason: "Today feed unavailable" };
const PNL: PnlSeries = {
  ...pnlJson, points: [], daily: [{ day: "2026-10-03", daily_units: 2.5 }],
};
const PLACED: TodayBet = {
  matchup: "Placed fixture", game_id: "placed-fixture", market_type: "moneyline",
  side: "home", stake_units: 1, model_prob: 0.5, tier: "B", outcome: "pending",
};

function mocks() {
  return {
    route: vi.spyOn(honestFetch, "fetchHonest").mockResolvedValue(OFFLINE),
    pnl: vi.spyOn(api, "getPaperPnlSeries").mockResolvedValue(PNL),
    bank: vi.spyOn(api, "getPaperBankroll").mockResolvedValue({
      start_units: 100, current_units: 101, updated_at: null,
    }),
  };
}

function document(placed: TodayBet[] = []) {
  return {
    status: "ok", date: "2026-10-03", placed, pending: [], settled_today: [],
    day_units: 2.5, cumulative_units: 1, current_units: 101, start_units: 100,
    edge_claimed: false,
  };
}

function noFalseEmpty() {
  expect(screen.queryByText(/No bets STAKED today yet/)).not.toBeInTheDocument();
}

describe("TodayPlacedBets history availability", () => {
  it("shows an accessible pending state without declaring a no-bet day", () => {
    mocks().route.mockImplementation(() => new Promise<never>(() => {}));
    render(<TodayPlacedBets />);
    expect(screen.getByRole("status")).toHaveTextContent(/loading|checking/i);
    expect(screen.queryByTestId("today-placed-table")).not.toBeInTheDocument();
    noFalseEmpty();
  });

  it("shows all-offline history as unavailable and finishes the pending state", async () => {
    const calls = mocks();
    calls.pnl.mockResolvedValue(OFFLINE);
    calls.bank.mockResolvedValue(OFFLINE);
    render(<TodayPlacedBets />);
    expect((await screen.findAllByText(/unavailable/i)).length).toBeGreaterThan(0);
    expect(screen.queryByText(/loading placed|checking placed/i)).not.toBeInTheDocument();
    expect(screen.queryByTestId("today-placed-table")).not.toBeInTheDocument();
    noFalseEmpty();
  });

  it("preserves fallback day PnL and its date while identifying unavailable placed history", async () => {
    mocks();
    render(<TodayPlacedBets />);
    expect((await screen.findAllByText(/unavailable/i)).length).toBeGreaterThan(0);
    expect(screen.getByText("2026-10-03", { exact: false })).toBeInTheDocument();
    expect(screen.getByText("+2.50")).toBeInTheDocument();
    noFalseEmpty();
  });

  it.each([
    { name: "missing", value: {} },
    { name: "malformed", value: { placed: "not an array" } },
  ])("keeps successful-route $name placed history unavailable", async ({ value }) => {
    mocks().route.mockResolvedValue({ ...value, status: "ok", date: "2026-10-03", day_units: 2.5 });
    render(<TodayPlacedBets />);
    expect((await screen.findAllByText(/unavailable/i)).length).toBeGreaterThan(0);
    expect(screen.getByText("+2.50")).toBeInTheDocument();
    noFalseEmpty();
  });

  it("renders a genuine no-bet day only for a valid route empty array", async () => {
    mocks().route.mockResolvedValue(document());
    render(<TodayPlacedBets />);
    expect(await screen.findByText("+2.50")).toBeInTheDocument();
    expect(screen.getByText(/No bets STAKED today yet/)).toBeInTheDocument();
    expect(screen.queryByText(/placed.*unavailable/i)).not.toBeInTheDocument();
    expect(screen.queryByTestId("today-placed-table")).not.toBeInTheDocument();
  });

  it("preserves real placed rows, fractional probability and stake units", async () => {
    mocks().route.mockResolvedValue(document([PLACED]));
    render(<TodayPlacedBets />);
    const table = await screen.findByTestId("today-placed-table");
    expect(table).toHaveTextContent("Placed fixture");
    expect(table).toHaveTextContent("50.0%");
    expect(table).toHaveTextContent("1.00u");
    expect(within(table).getAllByRole("row")).toHaveLength(2);
    expect(screen.getByText("2026-10-03", { exact: false })).toBeInTheDocument();
    expect(screen.getByText("+2.50")).toBeInTheDocument();
    noFalseEmpty();
  });

  it("retains prior rows and date on a later failure while surfacing STALE and the error", async () => {
    const calls = mocks();
    calls.route.mockResolvedValue(document([PLACED]));
    vi.spyOn(globalThis.document, "hidden", "get").mockReturnValue(false);
    render(<TodayPlacedBets />);
    const table = await screen.findByTestId("today-placed-table");
    const rows = within(table).getAllByRole("row").map((row) => row.textContent);
    calls.route.mockResolvedValue(OFFLINE);
    calls.pnl.mockResolvedValue(OFFLINE);
    calls.bank.mockResolvedValue(OFFLINE);
    act(() => { globalThis.document.dispatchEvent(new Event("visibilitychange")); });
    expect(await screen.findByText(/STALE$/)).toBeInTheDocument();
    expect(screen.getAllByText(/unavailable/i).length).toBeGreaterThan(0);
    expect(within(screen.getByTestId("today-placed-table")).getAllByRole("row").map((row) => row.textContent)).toEqual(rows);
    expect(screen.getByText("2026-10-03", { exact: false })).toBeInTheDocument();
    expect(screen.getByText("+2.50")).toBeInTheDocument();
    noFalseEmpty();
  });
});
