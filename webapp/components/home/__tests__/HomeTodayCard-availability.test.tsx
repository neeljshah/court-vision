import { afterEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import { api } from "@/lib/p5api";
import * as honestFetch from "@/lib/fetchHonest";
import type { PnlSeries } from "@/lib/types";
import { getPaperToday, type TodayBet } from "@/lib/paperToday";
import pnlJson from "@/public/demo-data/api_paper_pnl_series.json";
import { HomeTodayCard } from "../HomeTodayCard";

afterEach(() => { cleanup(); vi.restoreAllMocks(); });

const PNL: PnlSeries = {
  ...pnlJson,
  points: [],
  daily: [{ day: "2026-10-03", daily_units: 2.5 }],
};
const BANK = { start_units: 100, current_units: 101, updated_at: null };
const OFFLINE = { status: "unavailable" as const, reason: "Feed offline" };

function mocks() {
  return {
    route: vi.spyOn(honestFetch, "fetchHonest").mockResolvedValue(OFFLINE),
    pnl: vi.spyOn(api, "getPaperPnlSeries").mockResolvedValue(PNL),
    bank: vi.spyOn(api, "getPaperBankroll").mockResolvedValue(BANK),
    board: vi.spyOn(api, "bestbetsBoard").mockResolvedValue(OFFLINE),
    improve: vi.spyOn(api, "improve").mockResolvedValue(OFFLINE),
  };
}

function todayDocument(placed: TodayBet[] = [], settled: TodayBet[] = []) {
  return {
    status: "ok", date: "2026-10-03", placed, pending: [], settled_today: settled,
    day_units: 2.5, cumulative_units: 1, start_units: 100, current_units: 101,
    edge_claimed: false,
  };
}

function assertUnknownHistory() {
  expect(screen.getByTestId("today-placed-count")).toHaveTextContent(/^--$/);
  expect(screen.getByTestId("today-settled-wl")).toHaveTextContent(/^--$/);
  expect(screen.getByText("placed history unavailable")).toBeInTheDocument();
  expect(screen.getByText("settled history unavailable")).toBeInTheDocument();
}

describe("HomeTodayCard history availability", () => {
  it("preserves fallback bankroll and daily PnL without turning missing histories into zeros", async () => {
    const calls = mocks();
    render(<HomeTodayCard />);
    await waitFor(() => expect(screen.getByTestId("today-day-pnl")).toHaveTextContent("+2.50u"));
    expect(screen.getByTestId("today-bankroll")).toHaveTextContent("101.00");
    expect(screen.getByTestId("today-net")).toHaveTextContent("net +1.00u");
    assertUnknownHistory();
    expect(calls.route).toHaveBeenCalledWith("/api/paper/today", expect.objectContaining({ signal: expect.any(AbortSignal) }));
  });

  it("preserves bank-only fallback while marking histories and day PnL unknown", async () => {
    const calls = mocks();
    calls.pnl.mockResolvedValue(OFFLINE);
    render(<HomeTodayCard />);
    await waitFor(() => expect(screen.getByTestId("today-bankroll")).toHaveTextContent("101.00"));
    expect(screen.getByTestId("today-day-pnl")).toHaveTextContent("--");
    assertUnknownHistory();
  });

  it("preserves PnL-only fallback and the series bankroll while histories remain unknown", async () => {
    const calls = mocks();
    calls.bank.mockResolvedValue(OFFLINE);
    render(<HomeTodayCard />);
    await waitFor(() => expect(screen.getByTestId("today-day-pnl")).toHaveTextContent("+2.50u"));
    expect(screen.getByTestId("today-bankroll")).toHaveTextContent(PNL.summary.current_units.toFixed(2));
    assertUnknownHistory();
  });

  it("renders genuine zero counts for a successful route with valid empty arrays", async () => {
    mocks().route.mockResolvedValue(todayDocument());
    render(<HomeTodayCard />);
    await waitFor(() => expect(screen.getByTestId("today-day-pnl")).toHaveTextContent("+2.50u"));
    expect(screen.getByTestId("today-placed-count")).toHaveTextContent(/^0$/);
    expect(screen.getByTestId("today-settled-wl")).toHaveTextContent("0 - 0");
    expect(screen.queryByText("placed history unavailable")).not.toBeInTheDocument();
    expect(screen.queryByText("settled history unavailable")).not.toBeInTheDocument();
  });

  it("preserves populated route counts and the win/loss/push tally", async () => {
    mocks().route.mockResolvedValue(todayDocument(
      [{ matchup: "First fixture", stake_units: 1 }, { matchup: "Second fixture", stake_units: 0.5 }],
      [{ outcome: "win" }, { outcome: "loss" }, { outcome: "push" }],
    ));
    render(<HomeTodayCard />);
    await waitFor(() => expect(screen.getByTestId("today-placed-count")).toHaveTextContent(/^2$/));
    expect(screen.getByTestId("today-settled-wl")).toHaveTextContent("1 - 1");
    expect(screen.getByText("1 push")).toBeInTheDocument();
    expect(screen.getByText("First fixture")).toBeInTheDocument();
    expect(screen.getByText("Second fixture")).toBeInTheDocument();
  });

  it("keeps a pending route in a loading state without any count placeholders", () => {
    mocks().route.mockImplementation(() => new Promise<never>(() => {}));
    render(<HomeTodayCard />);
    expect(screen.getByTestId("today-card-loading")).toBeInTheDocument();
    expect(screen.queryByTestId("today-placed-count")).not.toBeInTheDocument();
    expect(screen.queryByTestId("today-settled-wl")).not.toBeInTheDocument();
  });

  it.each([
    { name: "missing both arrays", doc: {}, placed: "--", settled: "--" },
    {
      name: "valid placed array and missing settled array",
      doc: { placed: [{ matchup: "Placed fixture" }] },
      placed: "1", settled: "--",
    },
    {
      name: "valid settled array and malformed placed field",
      doc: { placed: "not an array", settled_today: [{ outcome: "win" }, { outcome: "loss" }] },
      placed: "--", settled: "1 - 1",
    },
  ])("preserves route provenance and independent availability for $name", async ({ doc, placed, settled }) => {
    mocks().route.mockResolvedValue(doc);
    const normalized = await getPaperToday();
    expect(normalized.source).toBe("today_route");
    render(<HomeTodayCard />);
    expect(await screen.findByTestId("today-card")).toBeInTheDocument();
    expect(screen.getByTestId("today-placed-count").textContent).toBe(placed);
    expect(screen.getByTestId("today-settled-wl").textContent).toBe(settled);
    if (placed === "--") {
      expect(screen.getByText("placed history unavailable")).toBeInTheDocument();
    } else {
      expect(screen.queryByText("placed history unavailable")).not.toBeInTheDocument();
    }
    if (settled === "--") {
      expect(screen.getByText("settled history unavailable")).toBeInTheDocument();
    } else {
      expect(screen.queryByText("settled history unavailable")).not.toBeInTheDocument();
    }
  });

  it("finishes an all-offline digest without infinite loading or fabricated counts", async () => {
    const calls = mocks();
    calls.pnl.mockResolvedValue(OFFLINE);
    calls.bank.mockResolvedValue(OFFLINE);
    render(<HomeTodayCard />);
    expect(await screen.findByTestId("today-card")).toBeInTheDocument();
    expect(screen.queryByTestId("today-card-loading")).not.toBeInTheDocument();
    assertUnknownHistory();
    expect(screen.getByTestId("today-day-pnl")).toHaveTextContent("--");
    expect(screen.getByTestId("today-bankroll")).toHaveTextContent(/unavailable/i);
    expect(screen.getByTestId("today-bankroll")).not.toHaveTextContent("no paper book yet");
  });

  it("retains the prior digest and marks it stale when a later route and fallback poll fail", async () => {
    const calls = mocks();
    calls.route.mockResolvedValue(todayDocument(
      [{ matchup: "Retained fixture", stake_units: 1 }], [{ outcome: "win" }],
    ));
    vi.spyOn(document, "hidden", "get").mockReturnValue(false);
    render(<HomeTodayCard />);
    await waitFor(() => expect(screen.getByTestId("today-placed-count")).toHaveTextContent(/^1$/));
    const priorDate = screen.getByTestId("today-date").textContent;
    const priorRows = screen.getAllByRole("row").map((row) => row.textContent);
    expect(screen.queryByText(/STALE$/)).not.toBeInTheDocument();
    calls.route.mockResolvedValue(OFFLINE);
    calls.pnl.mockResolvedValue(OFFLINE);
    calls.bank.mockResolvedValue(OFFLINE);
    act(() => { document.dispatchEvent(new Event("visibilitychange")); });
    expect(await screen.findByText(/STALE$/)).toBeInTheDocument();
    expect(screen.getByTestId("today-placed-count")).toHaveTextContent(/^1$/);
    expect(screen.getByTestId("today-settled-wl")).toHaveTextContent("1 - 0");
    expect(screen.getByTestId("today-date").textContent).toBe(priorDate);
    expect(screen.getAllByRole("row").map((row) => row.textContent)).toEqual(priorRows);
    expect(screen.getByTestId("today-day-pnl")).toHaveTextContent("+2.50u");
    expect(screen.queryByText("placed history unavailable")).not.toBeInTheDocument();
  });
});
