import { describe, expect, it } from "vitest";
import { summarizeDistribution } from "./distribution";
import type { LabRow } from "./labTypes";
import { basketballResearch } from "./researchBasketball";
const rows = (values: Array<number | null>): LabRow[] => values.map((value, index) => ({ id: String(index), label: String(index), group: "Fixture", values: { value } }));

describe("published row distributions", () => {
  it("uses R7 quartiles and retains missing, zero, and signed coverage separately", () => {
    const input = rows([100, 3, 2, 1, null, NaN, Infinity]);
    const summary = summarizeDistribution(input, "value");
    expect(summary).toMatchObject({ total: 7, measured: 4, missing: 3, min: 1, max: 100, mean: 26.5, q1: 1.75, median: 2.5, q3: 27.25, iqr: 25.5 });
    expect(input[0].values.value).toBe(100);
    expect(summarizeDistribution(rows([-2, -0, 0, 4, null]), "value")).toMatchObject({ measured: 4, zero: 2, negative: 1, positive: 1 });
  });

  it("assigns boundaries once and includes the maximum in the final bin", () => {
    const summary = summarizeDistribution(rows([0, 1, 2, 3, 4, 5, 6, 7, 8]), "value");
    expect(summary.bins.map(bin => bin.count)).toEqual([3, 3, 3]);
    expect(summary.bins[2]).toMatchObject({ high: 8, includesHigh: true });
    expect(summary.bins.reduce((sum, bin) => sum + bin.count, 0)).toBe(summary.measured);
    expect(summarizeDistribution(rows([0, 1, 2, 3]), "value").bins.map(bin => bin.count)).toEqual([2, 2]);
  });

  it("does not invent variation or summary values for constant, single, or missing cohorts", () => {
    expect(summarizeDistribution(rows([0, 0, 0]), "value")).toMatchObject({ median: 0, iqr: 0, bins: [{ low: 0, high: 0, count: 3, includesHigh: true }] });
    expect(summarizeDistribution(rows([5]), "value")).toMatchObject({ mean: 5, q1: 5, q3: 5, iqr: 0 });
    expect(summarizeDistribution(rows([null]), "value")).toMatchObject({ measured: 0, missing: 1, median: null, mean: null, bins: [] });
    expect(summarizeDistribution([], "value")).toMatchObject({ total: 0, missing: 0, q1: null, q3: null });
  });

  it("uses the actual decimal boundaries for the published quarter-shift distribution", () => {
    const dataset = basketballResearch().find(analysis => analysis.id === "nba-q4-role-redistribution")!;
    const summary = summarizeDistribution(dataset.rows, "shift");
    expect(summary.bins.map(bin => bin.count)).toEqual([13, 2, 0, 11, 19, 12, 2, 1]);
    expect(summary.bins.reduce((sum, bin) => sum + bin.count, 0)).toBe(60);
  });
});
