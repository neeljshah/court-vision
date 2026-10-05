import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import type { ClvScoreboard, PaperBankroll, PnlSeries } from "@/lib/types";
import type { PaperToday } from "@/lib/paperToday";
import pnlFixture from "@/public/demo-data/api_paper_pnl_series.json";
import bankFixture from "@/public/demo-data/api_paper_bankroll.json";
import clvFixture from "@/public/demo-data/api_paper_clv.json";

type HookState = {
  data: unknown;
  isStale: boolean;
  isLoading: boolean;
  error: string | null;
  ageSec: number;
  lastUpdatedAt: number;
};
const mockHooks = vi.hoisted(() => ({ states: [] as HookState[], index: 0 }));
vi.mock("@/lib/useLiveData", () => ({
  useLiveData: () => mockHooks.states[mockHooks.index++],
}));

import { BetsMoneyHeadline } from "../BetsMoneyHeadline";
import { TodayPlacedBets } from "../TodayPlacedBets";

function state(data: unknown, isStale = false): HookState {
  return {
    data, isStale, isLoading: false, error: null, ageSec: 3,
    lastUpdatedAt: Date.now(),
  };
}

function hero(pnl: PnlSeries, bank: PaperBankroll, clv: ClvScoreboard, stale = false) {
  mockHooks.states = [state(pnl, stale), state(bank), state(clv)];
  mockHooks.index = 0;
  render(<BetsMoneyHeadline />);
}

const PNL = { ...pnlFixture, points: [] } as PnlSeries;
const BANK = bankFixture as PaperBankroll;
const CLV = clvFixture as ClvScoreboard;

function today(source: PaperToday["source"], date: string | null, stale = false) {
  const data: PaperToday = {
    status: "ok", source, date, placed: [], pending: [], settled_today: [],
    placed_available: source === "today_route", day_units: 2.5,
    cumulative_units: 1, bankroll: 101, start_units: 100, edge_claimed: false,
    reason: source === "fallback" ? "Placed history unavailable." : null,
  };
  mockHooks.states = [state(data, stale)];
  mockHooks.index = 0;
  render(<TodayPlacedBets />);
}

describe("bets summary source provenance", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-10-05T12:00:00Z"));
  });
  afterEach(() => vi.useRealTimers());

  it("shows published P&L and bankroll source times separately from the current fetch", () => {
    hero(PNL, BANK, CLV);

    const headline = screen.getByTestId("bets-money-headline");
    expect(headline).toHaveTextContent("P&L snapshot generated: 2026-07-16 01:37:24 UTC");
    expect(headline).toHaveTextContent("Bankroll updated: 2026-07-16 01:37:24 UTC");
    expect(headline.querySelectorAll("time")[0]).toHaveAttribute("dateTime", "2026-07-16T01:37:24.782Z");
    expect(headline.querySelectorAll("time")[1]).toHaveAttribute("dateTime", "2026-07-16T01:37:24.968Z");
    expect(screen.getByText("CLV scoreboard time: unavailable")).toBeInTheDocument();
    expect(screen.getByTestId("bets-money-headline")).not.toHaveTextContent("2026-10-05");
    expect(headline).not.toHaveTextContent(/as of/i);
    expect(screen.getByTestId("money-net-units")).toHaveTextContent("+101.54u");
    expect(screen.getByTestId("money-nbets")).toHaveTextContent("1316");
  });

  it.each([null, "2026-07-16T01:37:24", "not-a-date"])(
    "marks absent, unzoned, or invalid source times unavailable (%s)", (timestamp) => {
      hero(
        { ...PNL, generated_at: timestamp } as PnlSeries,
        { ...BANK, updated_at: timestamp },
        CLV,
      );
      expect(screen.getByText("P&L snapshot generated: unavailable")).toBeInTheDocument();
      expect(screen.getByText("Bankroll updated: unavailable")).toBeInTheDocument();
      expect(screen.getByTestId("bets-money-headline")).not.toHaveTextContent("2026-10-05");
    },
  );

  it("retains a visible stale warning without forging a source time", () => {
    hero({ ...PNL, generated_at: null } as PnlSeries, BANK, CLV, true);
    expect(screen.getByTestId("money-headline-stale")).toHaveTextContent(/stale/i);
    expect(screen.getByText("P&L snapshot generated: unavailable")).toBeInTheDocument();
  });

  it("converts an offset source stamp across UTC midnight", () => {
    hero({ ...PNL, generated_at: "2026-07-15T23:30:00-04:00" } as PnlSeries, BANK, CLV);
    expect(screen.getByTestId("bets-money-headline"))
      .toHaveTextContent("P&L snapshot generated: 2026-07-16 03:30:00 UTC");
  });

  it("labels a primary placed-bet route day as its reported date", () => {
    today("today_route", "2026-07-15");
    expect(screen.getByText("2026-07-15").parentElement).toHaveTextContent("Reported date: 2026-07-15");
    expect(screen.getByText("2026-07-15")).toHaveAttribute("dateTime", "2026-07-15");
    expect(screen.getByRole("region", { name: "today's placed paper bets" })).not.toHaveTextContent(/as of/i);
    expect(screen.getByText("+2.50")).toBeInTheDocument();
  });

  it("labels a fallback day as P&L date while keeping placed history unavailable", () => {
    today("fallback", "2026-07-15");
    expect(screen.getByText("2026-07-15").parentElement).toHaveTextContent("P&L reported date: 2026-07-15");
    expect(screen.getByText(/Placed history unavailable/i)).toBeInTheDocument();
    expect(screen.getByText("+2.50")).toBeInTheDocument();
  });

  it.each([null, "2026-02-30", "2026-07-15T00:00:00Z"])(
    "does not present an invalid day as a reported placed-bet date (%s)", (date) => {
      today("today_route", date);
      expect(screen.getByText("Reported date: unavailable")).toBeInTheDocument();
      expect(screen.getByText("+2.50")).toBeInTheDocument();
    },
  );

  it("retains STALE for previously fetched placed history", () => {
    today("today_route", "2026-07-15", true);
    expect(screen.getByText(/STALE/)).toBeInTheDocument();
    expect(screen.getByText("2026-07-15").parentElement).toHaveTextContent("Reported date: 2026-07-15");
  });
});
