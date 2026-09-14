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
});
