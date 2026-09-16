import { describe, expect, it } from "vitest";
import { buildBrierSkillScoresResearch } from "./researchBrierSkillScores";

const grain = (n = 40) => ({ n, brier_model: 0.24, brier_market: 0.2, brier_clim: 0.25, bss_model_vs_clim: 0.04, bss_market_vs_clim: 0.2, bss_model_vs_market: -0.2, below_floor: false });

describe("Brier skill scores research", () => {
  it("builds Brier and skill-score measurements with as-of date", () => {
    const analysis = buildBrierSkillScoresResearch({ generated_at: "2026-07-25T11:12:35.314040+00:00", sports: { mlb: { grains: { all: grain() } } } })[0];
    expect(analysis).toMatchObject({ id: "brier-skill-score-by-game-phase", source: "brier_skill_scores", asOf: "2026-07-25" });
    expect(analysis.rows[0].values).toMatchObject({ model_brier: 0.24, model_vs_market_bss: -0.2, scored_rows: 40 });
    expect(analysis.rows[0].sourcePaths).toContain("sports.mlb.grains.all.bss_model_vs_market");
    expect(analysis.bindings?.every(binding => binding.valueKey in analysis.rows[0].values)).toBe(true);
  });

  it("orders sport-phase rows and retains a flagged source row", () => {
    const rows = buildBrierSkillScoresResearch({ sports: { soccer_intl: { grains: { "0-15": { ...grain(), below_floor: true } } }, mlb: { grains: { late: grain() } } } })[0].rows;
    expect(rows.map(item => item.label)).toEqual(["International soccer | 0-15", "MLB | late"]);
    expect(rows[0].note).toContain("below its support floor");
  });

  it("returns no rows for missing or malformed grains", () => {
    expect(buildBrierSkillScoresResearch({ sports: { mlb: { grains: { all: { ...grain(), brier_clim: -1 } } } } })[0].rows).toEqual([]);
    expect(buildBrierSkillScoresResearch({})[0].rows).toEqual([]);
  });
});
