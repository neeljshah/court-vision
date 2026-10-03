import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "@/lib/p5api";
import type { ClvScoreboard } from "@/lib/types";
import { fetchPaperCombined } from "../paperTradingHelpers";
import clv from "@/public/demo-data/api_paper_clv.json";
import pnl from "@/public/demo-data/api_paper_pnl_series.json";

afterEach(() => vi.restoreAllMocks());

const GOOD = {
  trail: { status: "ok", count: 0, trail: [] },
  pmTrail: { status: "ok", generated_at: null, count: 0, trades: [] },
  clv,
  pnl,
  bankroll: { start_units: 100, current_units: 101, updated_at: null },
};
type Key = keyof typeof GOOD;
const METHODS = {
  trail: "getPaperTrail", pmTrail: "pmTrail", clv: "getPaperClv",
  pnl: "getPaperPnlSeries", bankroll: "getPaperBankroll",
} as const;

function mocks() {
  return {
    trail: vi.spyOn(api, "getPaperTrail").mockResolvedValue(GOOD.trail),
    pmTrail: vi.spyOn(api, "pmTrail").mockResolvedValue(GOOD.pmTrail),
    clv: vi.spyOn(api, "getPaperClv").mockResolvedValue(GOOD.clv as ClvScoreboard),
    pnl: vi.spyOn(api, "getPaperPnlSeries").mockResolvedValue(GOOD.pnl),
    bankroll: vi.spyOn(api, "getPaperBankroll").mockResolvedValue(GOOD.bankroll),
  };
}

describe("fetchPaperCombined independent feed contracts", () => {
  it.each(Object.keys(GOOD) as Key[])("preserves healthy feeds when %s is unavailable", async (key) => {
    const calls = mocks();
    calls[key].mockResolvedValue({ status: "unavailable", reason: `${key} unavailable` });
    const signal = new AbortController().signal;
    const result = await fetchPaperCombined(signal);
    expect(result).toMatchObject({ ...GOOD, [key]: null, errors: { [key]: `${key} unavailable` } });
    expect(calls.trail).toHaveBeenCalledWith({ limit: 400 }, signal);
    expect(calls.pmTrail).toHaveBeenCalledWith(undefined, signal);
    for (const k of ["clv", "pnl", "bankroll"] as const) {
      expect(api[METHODS[k]]).toHaveBeenCalledWith(signal);
    }
  });

  it("retains genuine zero-count trails without adding errors", async () => {
    mocks();
    const result = await fetchPaperCombined(new AbortController().signal);
    expect(result).toMatchObject(GOOD);
    expect(result).not.toHaveProperty("errors.trail");
    expect(result).not.toHaveProperty("errors.pmTrail");
  });

  it("preserves rejection rather than silently converting thrown failures", async () => {
    const calls = mocks();
    const failure = new Error("transport rejected");
    calls.pmTrail.mockRejectedValue(failure);
    await expect(fetchPaperCombined(new AbortController().signal)).rejects.toBe(failure);
  });

  it("passes an aborted signal to every request and preserves abort rejection", async () => {
    const calls = mocks();
    const controller = new AbortController();
    controller.abort();
    const failure = new DOMException("Request aborted", "AbortError");
    calls.trail.mockRejectedValue(failure);
    await expect(fetchPaperCombined(controller.signal)).rejects.toBe(failure);
    expect(calls.trail).toHaveBeenCalledWith({ limit: 400 }, controller.signal);
    expect(calls.pmTrail).toHaveBeenCalledWith(undefined, controller.signal);
    for (const key of ["clv", "pnl", "bankroll"] as const) {
      expect(calls[key]).toHaveBeenCalledWith(controller.signal);
    }
  });
});
