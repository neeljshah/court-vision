import { describe, expect, it } from "vitest";
import { buildMicroAbsorptionResearch } from "./researchMicroAbsorption";

const source = (mean = 0.02) => ({ buckets_minutes: [{ label: "6h+" }], sports: { mlb: { status: "ok", n_series_used: 4, move_by_bucket: { "6h+": { n: 20, mean_abs_move: mean } } } } });

describe("time-to-close movement research", () => {
  it("builds published movement measurements with source paths", () => {
    const analysis = buildMicroAbsorptionResearch(source())[0];
    expect(analysis).toMatchObject({ id: "devigged-movement-by-time-to-close", source: "micro_absorption" });
    expect(analysis.rows[0].values).toMatchObject({ mean_absolute_devigged_probability_movement: 0.02, move_pairs: 20, series_used: 4 });
    expect(analysis.rows[0].sourcePaths).toContain("sports.mlb.move_by_bucket.6h+.mean_abs_move");
  });

  it("orders rows by sport and bucket label", () => {
    const rows = buildMicroAbsorptionResearch({ buckets_minutes: [{ label: "0-1h" }, { label: "6h+" }], sports: { wnba: { status: "ok", n_series_used: 2, move_by_bucket: { "0-1h": { n: 2, mean_abs_move: 0.1 }, "6h+": { n: 3, mean_abs_move: 0.2 } } }, mlb: { status: "ok", n_series_used: 1, move_by_bucket: { "0-1h": { n: 4, mean_abs_move: 0.3 }, "6h+": { n: 5, mean_abs_move: 0.4 } } } } })[0].rows;
    expect(rows.map(row => row.label)).toEqual(["MLB | 0-1h", "MLB | 6h+", "WNBA | 0-1h", "WNBA | 6h+"]);
  });

  it("returns no rows for missing or malformed buckets", () => {
    expect(buildMicroAbsorptionResearch({ buckets_minutes: [{ label: "6h+" }], sports: { mlb: { status: "ok", n_series_used: 1, move_by_bucket: { "6h+": { n: 2, mean_abs_move: -0.1 } } } } })[0].rows).toEqual([]);
    expect(buildMicroAbsorptionResearch({})[0].rows).toEqual([]);
  });
});
