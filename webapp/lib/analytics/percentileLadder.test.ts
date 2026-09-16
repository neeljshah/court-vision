import { describe, expect, it } from "vitest";
import { sharedPercentileLadder } from "./percentileLadder";
import type { ComparisonEntity, ComparisonPack } from "./comparisonData";

const a: ComparisonEntity = { slug: "a", name: "A", values: { close: 2, far: 3, missing: 4 }, percentiles: { close: 55, far: 10, missing: 50 } };
const b: ComparisonEntity = { slug: "b", name: "B", values: { close: 1, far: 2, missing: null }, percentiles: { close: 45, far: 90, missing: 10 } };
const pack: ComparisonPack = { key: "nba_players", nInPack: 2, metricKeys: ["close", "far", "missing"], entities: [a, b] };

describe("shared percentile ladder", () => {
  it("keeps measured shared axes and sorts by the published percentile gap", () => {
    expect(sharedPercentileLadder(pack, a, b)).toEqual([
      { field: "far", aPercentile: 10, bPercentile: 90, gap: 80 },
      { field: "close", aPercentile: 55, bPercentile: 45, gap: 10 },
    ]);
  });
});
