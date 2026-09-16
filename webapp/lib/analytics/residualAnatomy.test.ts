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
        { sport: "sample", time_bucket: "early", prob_bucket: "0-.2", n: 10, mean_abs_residual: 0.2, total_abs_residual_mass: 2 },
        { sport: "sample", time_bucket: "late", prob_bucket: ".2-.4", n: 1, mean_abs_residual: 0.8, total_abs_residual_mass: 0.8 },
      ],
    },
  },
  skipped: [{ sport: "duplicate", reason: "duplicate corpus" }],
};

describe("buildResidualAnatomy", () => {
  it("parses all 39 published segments across sports", () => {
    const data = buildResidualAnatomy(source);
    expect(data.sports.reduce((total, sport) => total + sport.segments.length, 0)).toBe(39);
    expect(data.sports.map(sport => sport.sport)).toEqual(["mlb", "soccer_intl"]);
  });

  it("preserves absent bucket intersections as blank cells", () => {
    const sport = buildResidualAnatomy(fixture).sports[0];
    expect(sport.grid[0].cells).toEqual([expect.any(Object), null]);
    expect(sport.grid[1].cells).toEqual([null, expect.any(Object)]);
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
