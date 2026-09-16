import { describe, expect, it } from "vitest";
import { buildPaceVarianceResearch } from "./researchPaceVariance";

const source = {
  as_of: "2026-05-21",
  curves: [{ fav_strength_at_ref_pace: 0.7, by_pace: [{ pace: 102, fav_win_prob: 0.71, upset_prob: 0.29 }, { pace: 98, fav_win_prob: 0.69, upset_prob: 0.31 }] }],
};

describe("pace variance research", () => {
  it("builds a typed analysis with published measurements and source paths", () => {
    const analysis = buildPaceVarianceResearch(source)[0];
    expect(analysis).toMatchObject({ id: "pace-variance-favorite-probability", source: "cf_pace_variance", asOf: "2026-05-21" });
    expect(analysis.fields.map(field => field.key)).toEqual(["pace", "favorite_win_probability", "trailing_win_probability", "reference_favorite_probability"]);
    expect(analysis.rows[0].sourcePaths).toContain("curves[].by_pace[].fav_win_prob");
  });

  it("orders cells by reference strength and pace", () => {
    const analysis = buildPaceVarianceResearch({ curves: [...source.curves, { fav_strength_at_ref_pace: 0.6, by_pace: [{ pace: 104, fav_win_prob: 0.61, upset_prob: 0.39 }] }] })[0];
    expect(analysis.rows.map(row => row.values.pace)).toEqual([104, 98, 102]);
  });

  it("returns an empty row set for missing or malformed curves", () => {
    expect(buildPaceVarianceResearch({ curves: [{ fav_strength_at_ref_pace: 2, by_pace: [{ pace: -1, fav_win_prob: 0.5, upset_prob: 0.5 }] }] })[0].rows).toEqual([]);
    expect(buildPaceVarianceResearch({})[0].rows).toEqual([]);
  });
});
