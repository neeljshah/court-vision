import { describe, expect, it } from "vitest";
import { matchupInsights, sharedMeasuredAxisCount } from "./matchupInsights";
import type { ComparisonEntity, ComparisonPack } from "./comparisonData";

const pack: ComparisonPack = { key: "nba_players", nInPack: 2, metricKeys: ["pts", "reb", "missing"], entities: [] };
const entity = (name: string, values: Record<string, unknown>, percentiles: Record<string, number>): ComparisonEntity => ({ slug: name.toLowerCase(), name, values, percentiles });

describe("matchupInsights", () => {
  it("ranks shared numeric axes by percentile gap and keeps raw values", () => {
    const a = entity("Alpha", { pts: 18, reb: 4, missing: "n/a" }, { pts: 20, reb: 80, missing: 10 });
    const b = entity("Beta", { pts: 24, reb: 5, missing: 2 }, { pts: 70, reb: 45, missing: 90 });
    expect(matchupInsights(pack, a, b)).toEqual([
      { field: "pts", label: "PTS", aValue: "18", bValue: "24", aPercentile: 20, bPercentile: 70, gap: 50 },
      { field: "reb", label: "REB", aValue: "4", bValue: "5", aPercentile: 80, bPercentile: 45, gap: 35 },
    ]);
    expect(sharedMeasuredAxisCount(pack, a, b)).toBe(2);
  });

  it("rejects invalid ranks and missing raw values while retaining zero", () => {
    const fields = ["zero", "negative", "over", "nan", "infinite", "missing"];
    const guardedPack = { ...pack, metricKeys: fields };
    const values = { zero: 0, negative: 1, over: 1, nan: 1, infinite: 1, missing: null };
    const a = entity("Alpha", values, { zero: 0, negative: -1, over: 101, nan: NaN, infinite: Infinity, missing: 50 });
    const b = entity("Beta", { ...values, missing: 2 }, { zero: 100, negative: 50, over: 50, nan: 50, infinite: 50, missing: 50 });
    expect(matchupInsights(guardedPack, a, b)).toEqual([
      { field: "zero", label: "zero", aValue: "0", bValue: "0", aPercentile: 0, bPercentile: 100, gap: 100 },
    ]);
    expect(sharedMeasuredAxisCount(guardedPack, a, b)).toBe(1);
  });
});
