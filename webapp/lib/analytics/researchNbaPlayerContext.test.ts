import { describe, expect, it } from "vitest";
import { buildNbaPlayerContextResearch, getNbaPlayerContextResearch } from "./researchNbaPlayerContext";

function source() {
  return {
    consistency: { as_of: "2026-04-12", most_consistent_top15: [{ player_name: "Alpha One", composite_cv_shrunk: 0.4 }], least_consistent_top15: [] },
    q4: { generated_at: "2026-07-24T00:00:00Z", pts_shift: { top_risers: [{ player_name: "Bravo Two", shift: 3 }] }, reb_shift: { top_risers: [] }, ast_shift: { top_risers: [] } },
    context: { players: [{ player_name: "Bravo Two", context_sensitivity_score: 0.2, splits: { home_away: { delta_ts_pct: 0.01 } } }] },
    onOff: { seasons: { "2025_26": { top_15: [{ player_name: "Bravo Two", net_rating_delta: 4, min_on: 600.25 }], bottom_15: [] } } },
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
    expect(buildNbaPlayerContextResearch(source())[0].bindings?.every(binding => binding.valueKey in row.values || binding.valueKey in (row.bindingValues || {}))).toBe(true);
    const analysis = buildNbaPlayerContextResearch(source())[0];
    expect(analysis.fields.find(field => field.key === "q4_points_shift")?.sourceId).toBe("nba_q4_shift");
    expect(analysis.sources?.find(item => item.id === "on_off_showcase")?.fields).toEqual(["net_rating_delta", "on_off_minutes"]);
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

  it("keeps minutes and season attached to the latest published list entry for each name", () => {
    const analysis = buildNbaPlayerContextResearch({ ...source(), onOff: { seasons: {
      "2024_25": { top_15: [{ player_name: "Bravo Two", net_rating_delta: 99, min_on: 999 }, { player_name: "Alpha One", net_rating_delta: 2, min_on: 700 }] },
      "2025_26": { bottom_15: [{ player_name: "Bravo Two", net_rating_delta: -3, min_on: 600.25 }] },
    } } })[0];
    const bravo = analysis.rows.find(row => row.label === "Bravo Two")!;
    expect(bravo.values).toMatchObject({ net_rating_delta: -3, on_off_minutes: 600.25 });
    expect(bravo.windows).toEqual({ net_rating_delta: "2025-26", on_off_minutes: "2025-26" });
    expect(bravo.bindingValues?.on_off_season).toBe("2025-26");
    expect(bravo.sourcePaths).toContain("on_off_showcase.seasons.2025_26.bottom_15[].min_on");
    const alpha = analysis.rows.find(row => row.label === "Alpha One")!;
    expect(alpha.windows?.net_rating_delta).toBe("2024-25");
    expect(alpha.note).toContain("not necessarily the latest season played");
    expect(analysis.sources?.find(item => item.id === "on_off_showcase")?.rowWindows).toEqual({ net_rating_delta: ["2024-25", "2025-26"], on_off_minutes: ["2024-25", "2025-26"] });
  });

  it.each([undefined, null, NaN, Infinity])("preserves unavailable on-court minutes (%s) without taking them from an older season", (minutes) => {
    const analysis = buildNbaPlayerContextResearch({ ...source(), onOff: { seasons: {
      "2024_25": { top_15: [{ player_name: "Bravo Two", net_rating_delta: 99, min_on: 999 }] },
      "2025_26": { top_15: [{ player_name: "Bravo Two", net_rating_delta: 4, min_on: minutes }] },
    } } })[0];
    const bravo = analysis.rows.find(row => row.label === "Bravo Two")!;
    expect(bravo.values.on_off_minutes).toBeNull();
    expect(bravo.windows?.on_off_minutes).toBe("2025-26");
    const alpha = analysis.rows.find(row => row.label === "Alpha One")!;
    expect(alpha.values.on_off_minutes).toBeNull();
    expect(alpha.bindingValues?.on_off_season).toBeNull();
    expect(alpha.windows?.net_rating_delta).toBeUndefined();
  });

  it("preserves an explicitly published zero instead of converting it to missing", () => {
    const input = source();
    input.onOff.seasons["2025_26"].top_15[0].min_on = 0;
    expect(buildNbaPlayerContextResearch(input)[0].rows.find(row => row.label === "Bravo Two")?.values.on_off_minutes).toBe(0);
  });

  it("matches two different retained seasons in the real public snapshot and explains the per-48 scale", () => {
    const analysis = getNbaPlayerContextResearch()[0];
    const zion = analysis.rows.find(row => row.label === "Zion Williamson")!;
    const victor = analysis.rows.find(row => row.label === "Victor Wembanyama")!;
    expect(zion.values).toMatchObject({ net_rating_delta: 15.772, on_off_minutes: 857.25 });
    expect(zion.windows?.net_rating_delta).toBe("2024-25");
    expect(victor.values).toMatchObject({ net_rating_delta: 17.043, on_off_minutes: 2489.02 });
    expect(victor.windows?.net_rating_delta).toBe("2025-26");
    expect(analysis.formula).toContain("net_rating_on_per48 minus net_rating_off_per48");
    expect(analysis.interpretation).toContain("not per-100-possession NBA NetRtg");
    expect(analysis.rows.filter(row => row.values.on_off_minutes !== null)).toHaveLength(57);
  });
});
