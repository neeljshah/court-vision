import { describe, expect, it } from "vitest";
import { buildMechanismSurvivalResearch } from "./researchMechanismSurvival";

const summary = (n = 10) => ({ n, n_testable: 8, n_confirmed: 4, n_not_testable: 2, survival_rate: 0.5, not_testable_share: 0.2 });

describe("mechanism survival research", () => {
  it("builds published hypothesis counts with source paths", () => {
    const analysis = buildMechanismSurvivalResearch({ by_category: { rest_fatigue: summary() } })[0];
    expect(analysis).toMatchObject({ id: "hypothesis-survival-by-mechanism", source: "mechanism_survival" });
    expect(analysis.rows[0].values).toMatchObject({ hypotheses: 10, testable_hypotheses: 8, confirmed_hypotheses: 4, survival_share: 0.5 });
    expect(analysis.rows[0].sourcePaths).toContain("by_category.rest_fatigue.survival_rate");
  });

  it("orders mechanism families before sports", () => {
    const rows = buildMechanismSurvivalResearch({ by_sport: { tennis: summary() }, by_category: { travel: summary(), matchup: summary() } })[0].rows;
    expect(rows.map(row => `${row.group} | ${row.label}`)).toEqual(["Mechanism family | Matchup", "Mechanism family | Travel", "Sport | Tennis"]);
  });

  it("returns no rows for missing or malformed summaries", () => {
    expect(buildMechanismSurvivalResearch({ by_sport: { mlb: { ...summary(), survival_rate: 2 } } })[0].rows).toEqual([]);
    expect(buildMechanismSurvivalResearch({})[0].rows).toEqual([]);
  });
});
