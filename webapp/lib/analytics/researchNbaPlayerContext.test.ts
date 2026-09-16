import { describe, expect, it } from "vitest";
import { buildNbaPlayerContextResearch } from "./researchNbaPlayerContext";

function source() {
  return {
    consistency: { as_of: "2026-04-12", most_consistent_top15: [{ player_name: "Alpha One", composite_cv_shrunk: 0.4 }], least_consistent_top15: [] },
    q4: { generated_at: "2026-07-24T00:00:00Z", pts_shift: { top_risers: [{ player_name: "Bravo Two", shift: 3 }] }, reb_shift: { top_risers: [] }, ast_shift: { top_risers: [] } },
    context: { players: [{ player_name: "Bravo Two", context_sensitivity_score: 0.2, splits: { home_away: { delta_ts_pct: 0.01 } } }] },
    onOff: { seasons: { "2025_26": { top_15: [{ player_name: "Bravo Two", net_rating_delta: 4 }], bottom_15: [] } } },
    atlas: { entries: [
      { entity: "Alpha One", card_path: "cards/alpha.png", key_numbers: { career_pts_per36: 12, career_reb_per36: 5, career_ast_per36: 3 }, as_of: "2026-04-12" },
      { entity: "Bravo Two", card_path: "cards/bravo.png", key_numbers: { career_pts_per36: 18, career_reb_per36: 6, career_ast_per36: 4 }, as_of: "2026-04-12" },
    ] },
  };
}

describe("NBA player context research", () => {
  it("joins published player measurements with module-specific paths", () => {
    const row = buildNbaPlayerContextResearch(source())[0].rows.find(item => item.label === "Bravo Two")!;
    expect(row.values).toMatchObject({ q4_points_shift: 3, context_sensitivity: 0.2, home_away_ts_difference: 0.01, net_rating_delta: 4, career_points_per36: 18 });
    expect(row.sourcePaths).toContain("ctx_player_splits.players[].context_sensitivity_score");
    expect(row.href).toBe("/analytics/players/nba_players/bravo");
    expect(buildNbaPlayerContextResearch(source())[0].bindings?.every(binding => binding.valueKey in row.values)).toBe(true);
    const analysis = buildNbaPlayerContextResearch(source())[0];
    expect(analysis.fields.find(field => field.key === "q4_points_shift")?.sourceId).toBe("nba_q4_shift");
    expect(analysis.sources?.find(item => item.id === "on_off_showcase")?.fields).toEqual(["net_rating_delta"]);
  });

  it("reports a source-only player instead of silently adding it", () => {
    const input = source();
    input.q4.pts_shift.top_risers.push({ player_name: "Solo Three", shift: 2 });
    const analysis = buildNbaPlayerContextResearch(input)[0];
    expect(analysis.rows.map(row => row.label)).not.toContain("Solo Three");
    expect(analysis.caveat).toContain("Solo Three");
  });

  it("keeps a null when a published source omits a measurement", () => {
    const input = source();
    input.context.players[0].splits.home_away.delta_ts_pct = null as unknown as number;
    const row = buildNbaPlayerContextResearch(input)[0].rows.find(item => item.label === "Bravo Two")!;
    expect(row.values.home_away_ts_difference).toBeNull();
    expect(row.values.q4_rebounds_shift).toBeNull();
  });

  it("orders retained players by normalized display name", () => {
    expect(buildNbaPlayerContextResearch(source())[0].rows.map(row => row.label)).toEqual(["Alpha One", "Bravo Two"]);
  });
});
