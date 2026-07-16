// route.test.ts -- pure reducer test for GET /api/evidence (no disk I/O).

import { describe, it, expect } from "vitest";
import { reduceSeries } from "../_lib";

describe("reduceSeries", () => {
  it("collapses hourly vintages to one daily point per market, last hour wins", () => {
    const lines = [
      JSON.stringify({
        ts: "2026-07-14T10:00:00Z",
        clv_by_market: { moneyline: { median_clv_pct: 1.0, n: 5 } },
      }),
      JSON.stringify({
        ts: "2026-07-14T18:00:00Z",
        clv_by_market: { moneyline: { median_clv_pct: 2.0, n: 8 } },
      }),
      JSON.stringify({
        ts: "2026-07-15T09:00:00Z",
        clv_by_market: { moneyline: { median_clv_pct: -0.5, n: 3 } },
      }),
    ];
    const out = reduceSeries(lines);
    expect(out.n_vintages).toBe(3);
    expect(out.series_by_market.moneyline).toEqual([
      { date: "2026-07-14", median_clv_pct: 2.0, n: 8 }, // 18:00 wins over 10:00
      { date: "2026-07-15", median_clv_pct: -0.5, n: 3 },
    ]);
    expect(out.latest.moneyline).toEqual({ median_clv_pct: -0.5, n: 3 });
  });

  it("skips blank lines and malformed JSON without throwing", () => {
    const out = reduceSeries(["", "  ", "{not json", JSON.stringify({ ts: "2026-07-15T00:00:00Z" })]);
    expect(out.n_vintages).toBe(1);
    expect(out.series_by_market).toEqual({});
  });

  it("returns empty reduction for an empty file", () => {
    const out = reduceSeries([]);
    expect(out.n_vintages).toBe(0);
    expect(out.series_by_market).toEqual({});
    expect(out.latest).toEqual({});
  });
});
