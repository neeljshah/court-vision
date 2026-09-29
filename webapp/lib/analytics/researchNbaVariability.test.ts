import { describe, expect, it } from "vitest";
import { snapshot } from "./labHelpers";
import { buildNbaVariabilityResearch, type NbaVariabilitySource } from "./researchNbaVariability";

const published = (): NbaVariabilitySource => snapshot<NbaVariabilitySource>("nba_consistency_profiles");
const entry = (name: string) => ({ player_name: name, player_id: 1, pts_cv_shrunk: 0, reb_cv_shrunk: 0.3, ast_cv_shrunk: 0.4, games: 20, shrink_weight: 0.5 });

describe("NBA variability and league baseline", () => {
  it("preserves published rows while deriving signed same-snapshot prior gaps", () => {
    const analysis = buildNbaVariabilityResearch(published());
    expect(analysis.id).toBe("nba-variability-imbalance");
    expect(analysis.title).toBe("NBA variability and its league baseline");
    expect(analysis.fields.map(field => field.key)).toEqual([
      "cv_range", "cv_max", "cv_min", "pts_cv", "reb_cv", "ast_cv", "games",
      "pts_cv_vs_prior", "reb_cv_vs_prior", "ast_cv_vs_prior", "shrink_weight",
    ]);
    expect(analysis.rows).toHaveLength(30);
    expect(analysis.populationDefinition?.status).toBe("unpublished");
    expect(analysis.scope).toContain("579 players meeting the published floor");
    expect(analysis.scope).toContain("2023-24, 2024-25, 2025-26");
    expect(analysis.asOf).toBe("2026-04-12");
    const luka = analysis.rows[0];
    expect([luka.id, luka.label, luka.group]).toEqual(["consistency-0", "Luka Doncic", "Published low-CV subset"]);
    expect(luka.values.pts_cv_vs_prior).toBeCloseTo(-0.2443, 8);
    expect(luka.values.reb_cv_vs_prior).toBeCloseTo(-0.1992, 8);
    expect(luka.values.ast_cv_vs_prior).toBeCloseTo(-0.3850, 8);
    expect(luka.bindingValues).toEqual({ pts_prior: 0.5242, reb_prior: 0.5561, ast_prior: 0.7825 });
    const tucker = analysis.rows[15];
    expect([tucker.id, tucker.label, tucker.group]).toEqual(["consistency-15", "P.J. Tucker", "Published high-CV subset"]);
    expect(tucker.values.pts_cv_vs_prior).toBeCloseTo(0.3620, 8);
    expect(tucker.values.reb_cv_vs_prior).toBeCloseTo(-0.0274, 8);
    expect(tucker.values.ast_cv_vs_prior).toBeCloseTo(0.4573, 8);
    expect(tucker.values.shrink_weight).toBe(0.565);
    expect(tucker.sourcePaths).toEqual([
      "nba_consistency_profiles.least_consistent_top15[0].player_name",
      "nba_consistency_profiles.least_consistent_top15[0].player_id",
      "nba_consistency_profiles.least_consistent_top15[0].pts_cv_shrunk",
      "nba_consistency_profiles.least_consistent_top15[0].reb_cv_shrunk",
      "nba_consistency_profiles.least_consistent_top15[0].ast_cv_shrunk",
      "nba_consistency_profiles.least_consistent_top15[0].games",
      "nba_consistency_profiles.least_consistent_top15[0].shrink_weight",
      "nba_consistency_profiles.methodology.league_mean_cv_raw.pts",
      "nba_consistency_profiles.methodology.league_mean_cv_raw.reb",
      "nba_consistency_profiles.methodology.league_mean_cv_raw.ast",
    ]);
    expect(analysis.bindings?.find(binding => binding.valueKey === "pts_prior")?.sourcePath)
      .toBe("nba_consistency_profiles.methodology.league_mean_cv_raw.pts");
    expect(analysis.bindings?.map(binding => binding.valueKey)).toEqual([
      "pts_cv", "reb_cv", "ast_cv", "pts_prior", "reb_prior", "ast_prior", "games", "shrink_weight",
    ]);
  });

  it("nulls only gaps with missing or invalid prior operands, while retaining zero", () => {
    const source = {
      methodology: { league_mean_cv_raw: { pts: 0, reb: -1, ast: Number.POSITIVE_INFINITY } },
      most_consistent_top15: [entry("Zero")],
    };
    const analysis = buildNbaVariabilityResearch(source);
    const row = analysis.rows[0];
    expect(row.values.pts_cv).toBe(0);
    expect(row.values.pts_cv_vs_prior).toBe(0);
    expect(row.values.reb_cv_vs_prior).toBeNull();
    expect(row.values.ast_cv_vs_prior).toBeNull();
    expect(row.bindingValues).toEqual({ pts_prior: 0, reb_prior: null, ast_prior: null });
    expect(analysis.asOf).toBeUndefined();
    expect(analysis.scope).not.toContain("2023-24");
    expect(analysis.scope).not.toContain("579");
  });

  it("keeps source indices and group membership through malformed rows and uneven arrays", () => {
    const analysis = buildNbaVariabilityResearch({
      as_of: "2026-02-30",
      most_consistent_top15: [null, entry("Same"), entry("Same")],
      least_consistent_top15: [entry("Same"), 4, { player_name: "" }],
      methodology: { league_mean_cv_raw: { pts: 0.2, reb: 0.4, ast: 0.6 } },
    });
    expect(analysis.rows.map(row => row.id)).toEqual(["consistency-1", "consistency-2", "consistency-3"]);
    expect(analysis.rows.map(row => row.group)).toEqual([
      "Published low-CV subset", "Published low-CV subset", "Published high-CV subset",
    ]);
    expect(analysis.rows[2].sourcePaths?.[0]).toBe("nba_consistency_profiles.least_consistent_top15[0].player_name");
    expect(analysis.asOf).toBeUndefined();
    expect(buildNbaVariabilityResearch({ most_consistent_top15: null, least_consistent_top15: 7 }).rows).toEqual([]);
  });

  it("rejects invalid CVs, game counts and weights without discarding unaffected values", () => {
    const base = entry("Invalid");
    const analysis = buildNbaVariabilityResearch({
      methodology: { league_mean_cv_raw: { pts: 0, reb: 0.2, ast: 0.2 } },
      most_consistent_top15: [{ ...base, pts_cv_shrunk: -1, reb_cv_shrunk: Number.NaN, ast_cv_shrunk: 0, games: 4.5, shrink_weight: 1.2 }],
    });
    const values = analysis.rows[0].values;
    expect(values).toMatchObject({
      pts_cv: null, reb_cv: null, ast_cv: 0, cv_min: null, cv_max: null, cv_range: null,
      games: null, shrink_weight: null, pts_cv_vs_prior: null, reb_cv_vs_prior: null,
    });
    expect(values.ast_cv_vs_prior).toBeCloseTo(-0.2, 8);
  });
});
