import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { buildResidualAnatomy } from "./residualAnatomy";

const source: unknown = JSON.parse(readFileSync(join(process.cwd(), "public", "data", "showcase", "residual_anatomy.json"), "utf8"));

const fixture = {
  sports: {
    sample: {
      n_files: 2,
      n_records: 12,
      n_skipped: 3,
      segments: [
        { sport: "sample", time_bucket: "early", prob_bucket: ".4-.6", n: 10, mean_abs_residual: 0.2, total_abs_residual_mass: 2 },
        { sport: "sample", time_bucket: "early", prob_bucket: "unbinned", n: 1, mean_abs_residual: 0.8, total_abs_residual_mass: 0.8 },
        { sport: "sample", time_bucket: "late", prob_bucket: "0-.2", n: 1, mean_abs_residual: 0.1, total_abs_residual_mass: 0.1 },
        { sport: "sample", time_bucket: "early", prob_bucket: ".2-.4", n: 1, mean_abs_residual: 0.7, total_abs_residual_mass: 0.7 },
        { sport: "sample", time_bucket: "late", prob_bucket: ".8-1", n: 1, mean_abs_residual: 0.9, total_abs_residual_mass: 0.9 },
        { sport: "sample", time_bucket: "late", prob_bucket: "1-1.2", n: 1, mean_abs_residual: 0.3, total_abs_residual_mass: 0.3 },
      ],
    },
  },
  skipped: [{ sport: "duplicate", reason: "duplicate corpus" }],
};

describe("buildResidualAnatomy", () => {
  it("parses all 38 published segments across sports", () => {
    const data = buildResidualAnatomy(source);
    expect(data.sports.reduce((total, sport) => total + sport.segments.length, 0)).toBe(38);
    expect(data.sports.map(sport => sport.sport)).toEqual(["mlb", "soccer_intl"]);
  });

  it("orders valid probability bins numerically while preserving unknown labels and grid cells", () => {
    const sport = buildResidualAnatomy(fixture).sports[0];
    expect(sport.timeBuckets).toEqual(["early", "late"]);
    expect(sport.probBuckets).toEqual(["0-.2", ".2-.4", ".4-.6", ".8-1", "unbinned", "1-1.2"]);
    expect(sport.grid[0].cells.map(cell => cell?.probBucket || null)).toEqual([null, ".2-.4", ".4-.6", null, "unbinned", null]);
    expect(sport.grid[1].cells.map(cell => cell?.probBucket || null)).toEqual(["0-.2", null, null, ".8-1", null, "1-1.2"]);
  });

  it("keeps volume and per-row error rankings separate", () => {
    const sport = buildResidualAnatomy(fixture).sports[0];
    expect(sport.rankings.byVolume[0].timeBucket).toBe("early");
    expect(sport.rankings.byPerRowError[0].timeBucket).toBe("late");
  });

  it("retains published skipped-row counts and corpus exclusions", () => {
    const data = buildResidualAnatomy(fixture);
    expect(data.sports[0]).toMatchObject({ nRecords: 12, nSkipped: 3 });
    expect(data.exclusions).toEqual([{ sport: "duplicate", reason: "duplicate corpus" }]);
  });
});
