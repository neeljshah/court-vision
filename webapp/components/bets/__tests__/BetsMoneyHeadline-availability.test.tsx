import { afterEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import { api } from "@/lib/p5api";
import type { ClvScoreboard, PaperBankroll, PnlSeries } from "@/lib/types";
import pnlJson from "@/public/demo-data/api_paper_pnl_series.json";
import bankJson from "@/public/demo-data/api_paper_bankroll.json";
import clvJson from "@/public/demo-data/api_paper_clv.json";
import { BetsMoneyHeadline } from "../BetsMoneyHeadline";

const PNL = { ...pnlJson, points: [] } as PnlSeries;
const BANK = bankJson as PaperBankroll;
const CLV = clvJson as ClvScoreboard;
const OFFLINE = { status: "unavailable" as const, reason: "feed unavailable" };

function feeds(pnl: unknown = PNL, bank: unknown = BANK, clv: unknown = CLV) {
  const pnlCall = vi.spyOn(api, "getPaperPnlSeries").mockResolvedValue(pnl as PnlSeries);
  const bankCall = vi.spyOn(api, "getPaperBankroll").mockResolvedValue(bank as PaperBankroll);
  const clvCall = vi.spyOn(api, "getPaperClv").mockResolvedValue(clv as ClvScoreboard);
  return { pnlCall, bankCall, clvCall };
}

async function show() {
  render(<BetsMoneyHeadline />);
  await waitFor(() => expect(api.getPaperPnlSeries).toHaveBeenCalled());
  await waitFor(() => expect(api.getPaperBankroll).toHaveBeenCalled());
  await waitFor(() => expect(api.getPaperClv).toHaveBeenCalled());
  await act(async () => { await Promise.resolve(); });
}

function value(id: string) { return screen.getByTestId(id); }

afterEach(() => { cleanup(); vi.restoreAllMocks(); });

describe("BetsMoneyHeadline feed availability", () => {
  it("shows unknown metrics while all three feeds are pending", () => {
    const pending = new Promise<never>(() => {});
    feeds(pending, pending, pending);
    // A pending promise must be returned by the spies, not resolved as data.
    vi.mocked(api.getPaperPnlSeries).mockReturnValue(pending);
    vi.mocked(api.getPaperBankroll).mockReturnValue(pending);
    vi.mocked(api.getPaperClv).mockReturnValue(pending);
    render(<BetsMoneyHeadline />);
    expect(value("money-nbets")).toHaveTextContent("--");
    expect(value("money-record")).toHaveTextContent("--");
    expect(value("money-bankroll")).toHaveTextContent("--");
    expect(value("money-net-units")).toHaveTextContent("--");
    expect(value("money-clv")).toHaveTextContent("--");
    expect(screen.getByTestId("bets-money-headline")).toHaveTextContent("CLV scoreboard unavailable.");
  });

  it("keeps unavailable feeds unknown rather than inventing a zero record or balance", async () => {
    feeds(OFFLINE, OFFLINE, OFFLINE);
    await show();
    expect(value("money-nbets")).toHaveTextContent("--");
    expect(value("money-record")).toHaveTextContent("--");
    expect(value("money-bankroll")).toHaveTextContent("--");
    expect(value("money-net-units")).toHaveTextContent("--");
    expect(screen.getByTestId("bets-money-headline")).toHaveTextContent("CLV scoreboard unavailable.");
  });

  it("preserves genuine zero counts and a zero-zero record", async () => {
    feeds({ ...PNL, summary: { ...PNL.summary, n_bets: 0, n_win: 0, n_loss: 0, n_push: 0 } },
      { ...BANK, start_units: 100, current_units: 100 }, { ...CLV, n_bets: 0 });
    await show();
    expect(value("money-nbets")).toHaveTextContent("0");
    expect(value("money-record")).toHaveTextContent("0-0");
    expect(value("money-net-units")).toHaveTextContent("+0.00u");
    expect(screen.getByTestId("bets-money-headline")).toHaveTextContent("CLV vs-close INSUFFICIENT_DATA");
  });

  it("withholds an incomplete record but retains a known graded count", async () => {
    feeds({ ...PNL, summary: { ...PNL.summary, n_bets: 9, n_win: undefined, n_loss: 4 } }, BANK, CLV);
    await show();
    expect(value("money-nbets")).toHaveTextContent("9");
    expect(value("money-record")).toHaveTextContent("--");
  });

  it("uses P&L total when bankroll is missing without presenting starting capital as current", async () => {
    feeds(PNL, OFFLINE, CLV);
    await show();
    expect(value("money-bankroll")).toHaveTextContent("--");
    expect(value("money-net-units")).toHaveTextContent("+101.54u");
    expect(value("money-nbets")).toHaveTextContent("1316");
  });

  it("does not combine a bankroll current balance with P&L starting capital", async () => {
    feeds(PNL, { ...BANK, start_units: null, current_units: 104 }, CLV);
    await show();
    expect(value("money-bankroll")).toHaveTextContent("104.00u");
    expect(value("money-net-units")).toHaveTextContent("+101.54u");
  });

  it("rejects malformed numeric inputs rather than coercing them to zero", async () => {
    feeds(
      { ...PNL, summary: { ...PNL.summary, total_units: null, n_bets: NaN, n_win: 0, n_loss: Infinity } },
      { ...BANK, current_units: "104", start_units: 100 }, OFFLINE,
    );
    await show();
    expect(value("money-bankroll")).toHaveTextContent("--");
    expect(value("money-net-units")).toHaveTextContent("--");
    expect(value("money-nbets")).toHaveTextContent("--");
    expect(value("money-record")).toHaveTextContent("--");
  });

  it("keeps missing P&L summary unknown while preserving an independent bankroll", async () => {
    feeds({ ...PNL, summary: null }, BANK, CLV);
    await show();
    expect(value("money-nbets")).toHaveTextContent("--");
    expect(value("money-record")).toHaveTextContent("--");
    expect(value("money-clv")).toHaveTextContent("--");
    expect(value("money-bankroll")).toHaveTextContent("201.54u");
  });

  it.each([null, undefined, NaN])(
    "keeps a present summary with missing or invalid mean CLV unknown (%s)", async (mean) => {
      feeds({ ...PNL, summary: { ...PNL.summary, mean_clv_pct_or_INSUFFICIENT: mean } }, BANK, CLV);
      await show();
      expect(value("money-clv")).toHaveTextContent("--");
    },
  );

  it("retains the published fixture metrics exactly when all feeds are present", async () => {
    feeds();
    await show();
    expect(value("money-net-units")).toHaveTextContent("+101.54u");
    expect(value("money-bankroll")).toHaveTextContent("201.54u");
    expect(value("money-nbets")).toHaveTextContent("1316");
    expect(value("money-record")).toHaveTextContent("664-649-3");
  });

  it("retains a last-good bankroll and marks the headline stale after a later failure", async () => {
    const calls = feeds();
    vi.spyOn(globalThis.document, "hidden", "get").mockReturnValue(false);
    await show();
    calls.bankCall.mockResolvedValue(OFFLINE);
    act(() => { globalThis.document.dispatchEvent(new Event("visibilitychange")); });
    await waitFor(() => expect(calls.bankCall).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(screen.getByTestId("money-headline-stale")).toHaveTextContent(/stale/i));
    expect(value("money-bankroll")).toHaveTextContent("201.54u");
    expect(value("money-net-units")).toHaveTextContent("+101.54u");
  });
});
