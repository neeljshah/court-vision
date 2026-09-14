import { describe, expect, it } from "vitest";
import type { ComparisonEntity } from "./comparisonData";
import { tennisSurfaceComparison } from "./tennisSurfaceComparison";

const floor = "hard_wr: hard_n>=30 | clay_wr: clay_n>=30 | grass_wr: grass_n>=30 | clay_minus_hard: clay_n>=25 & hard_n>=25 | grass_adapt: grass_n>=15 (per metric, career+recent_form independently; below floor shows n/a)";
const entity = (name: string, values: Record<string, unknown>, percentiles: Record<string, number> = {}, asOf = "2026-07-18T22:41:37.06664-05:00"): ComparisonEntity => ({
  slug: name.toLowerCase(), name, values, percentiles, asOf, floors: floor, status: "partial (9/10 metrics)",
});

describe("tennisSurfaceComparison", () => {
  it("returns only hard rates and preserves exact evidence metadata", () => {
    const a = entity("A", { hard_wr_career: .6, hard_wr_recent: .5 }, { hard_wr_career: 40, hard_wr_recent: 30 });
    const result = tennisSurfaceComparison(a, entity("B", { hard_wr_career: .7, hard_wr_recent: .65 }), "hard", { hard_wr_career: 44, hard_wr_recent: 0 });
    expect(result.rows.map(row => row.key)).toEqual(["hard_wr_career", "hard_wr_recent"]);
    expect(result.rows.every(row => row.kind === "surface_rate" && row.unit === "percent")).toBe(true);
    expect(result.rows.map(row => row.nRanked)).toEqual([44, 0]);
    expect(result.entities.a).toMatchObject({ floors: floor, status: "partial (9/10 metrics)", asOf: a.asOf });
    expect(result.comparability).toMatchObject({ sameAsOf: true, windows: { career: "2015-2025 pooled", recent: "matches on or after 2023-01-01" } });
  });

  it("does not infer cohort metadata for an unknown raw-only field", () => {
    const result = tennisSurfaceComparison(entity("A", { grass_wr_recent: .6 }), entity("B", {}), "grass", { grass_wr_career: 70 });
    expect(result.rows.find(row => row.key === "grass_wr_career")?.nRanked).toBe(70);
    expect(result.rows.find(row => row.key === "grass_wr_recent")?.nRanked).toBeUndefined();
    expect(result.rows.find(row => row.key === "grass_adapt_recent")?.nRanked).toBeUndefined();
  });

  it("adds the relevant clay delta, retaining zero and asymmetric missing support", () => {
    const a = entity("A", { clay_wr_career: .7, clay_minus_hard_career: 0, clay_wr_recent: null, clay_minus_hard_recent: null }, { clay_wr_career: 55, clay_minus_hard_career: 50, clay_wr_recent: 99 });
    const b = entity("B", { clay_wr_career: .6, clay_minus_hard_career: -.1, clay_wr_recent: .65, clay_minus_hard_recent: .05 });
    const result = tennisSurfaceComparison(a, b, "clay");
    expect(result.rows.map(row => row.key)).toEqual(["clay_wr_career", "clay_minus_hard_career", "clay_wr_recent", "clay_minus_hard_recent"]);
    expect(result.rows[1]).toMatchObject({ unit: "pp", a: { value: 0, percentile: 50 }, b: { value: -.1, percentile: null } });
    expect(result.rows[2].a).toEqual({ value: null, percentile: null });
    expect(result.rows[2].b.value).toBe(.65);
  });

  it("defines grass adaptation as grass minus overall and does not add clay evidence", () => {
    const result = tennisSurfaceComparison(entity("A", { grass_wr_career: .75, grass_adapt_career: .04, grass_wr_recent: .7, grass_adapt_recent: -.02 }), entity("B", {}), "grass");
    expect(result.rows.map(row => row.key)).toEqual(["grass_wr_career", "grass_adapt_career", "grass_wr_recent", "grass_adapt_recent"]);
    expect(result.rows.filter(row => row.kind === "within_player_delta").every(row => row.label === "Grass minus overall win rate")).toBe(true);
    expect(result.rows.some(row => row.key.includes("clay"))).toBe(false);
    expect(result.comparability.note).toContain("not head-to-head results or forecasts");
  });

  it("reports unknown date comparability when either source date is absent", () => {
    const a = { ...entity("A", { hard_wr_career: Infinity }, { hard_wr_career: 100 }), asOf: undefined };
    const result = tennisSurfaceComparison(a, entity("B", { hard_wr_career: .5 }), "hard");
    expect(result.comparability.sameAsOf).toBeNull();
    expect(result.rows[0].a).toEqual({ value: null, percentile: null });
  });

  it("rejects invalid percentiles and never attaches a rank to missing raw data", () => {
    const keys = ["hard_wr_career", "hard_wr_recent"];
    for (const invalid of [-1, 101, NaN, Infinity]) {
      const result = tennisSurfaceComparison(entity("A", { hard_wr_career: .5 }, { hard_wr_career: invalid }), entity("B", {}), "hard", { hard_wr_career: 44 });
      expect(result.rows[0]).toMatchObject({ nRanked: 44, a: { value: .5, percentile: null } });
    }
    const result = tennisSurfaceComparison(entity("A", { hard_wr_career: 0, hard_wr_recent: null }, { hard_wr_career: 0, hard_wr_recent: 50 }), entity("B", {}), "hard");
    expect(result.rows.map(row => row.a)).toEqual([{ value: 0, percentile: 0 }, { value: null, percentile: null }]);
    expect(result.rows.map(row => row.key)).toEqual(keys);
  });
});
