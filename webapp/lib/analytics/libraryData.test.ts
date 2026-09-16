import { describe, expect, it } from "vitest";
import { getLibraryEntries } from "./libraryData";

describe("getLibraryEntries", () => {
  const entries = getLibraryEntries();
  const derived = entries.filter(entry => entry.kind === "derived");
  const sources = entries.filter(entry => entry.kind === "source");

  it("merges the complete source manifest with every derived analysis", () => {
    expect(entries).toHaveLength(125);
    expect(sources).toHaveLength(74);
    expect(new Set(entries.map(entry => entry.id)).size).toBe(entries.length);
    expect(derived).toHaveLength(51);
    expect(derived.reduce((sum, entry) => sum + (entry.rows ?? 0), 0)).toBe(2742);
  });

  it("keeps routes public and numeric previews finite", () => {
    expect(sources.every(entry => entry.href === `/analytics/m/${entry.id}/`)).toBe(true);
    expect(derived.every(entry => entry.href === `/analytics/research/${entry.id}/`)).toBe(true);
    expect(entries.every(entry => entry.preview.every(Number.isFinite))).toBe(true);
    expect(entries.every(entry => !/^(?:DESCRIPTIVE_ONLY|NOT_TESTABLE|CONFIRMED_LOCAL)$/.test(entry.description))).toBe(true);
    expect(sources.every(entry => entry.sourceSummary?.scope)).toBe(true);
    expect(sources.find(entry => entry.id === "statcast_showcase")?.sourceSummary?.scope).toBe("693,037 pitches, 19 pitch types");
  });

  it("classifies non-prefixed single-sport sources explicitly", () => {
    const expectedNba = [
      "aging_curve_lite", "box_value_index", "cf_pace_variance", "cf_star_removal",
      "clutch_context", "comeback_atlas", "ctx_lineup_proxy", "ctx_player_splits",
      "ctx_team_states", "home_away_anatomy", "league_parity_index", "lineup_synergy",
      "novel_load_bearing_index", "novel_schedule_fatigue_tax", "on_off_showcase",
      "player_metric_landscape", "rim_deterrence", "schedule_density",
    ];
    for (const id of expectedNba) {
      expect(sources.find(entry => entry.id === id)?.sport, id).toBe("nba");
    }
    expect(sources.find(entry => entry.id === "pitch_sequencing")?.sport).toBe("mlb");
    expect(sources.find(entry => entry.id === "statcast_showcase")?.sport).toBe("mlb");
    expect(sources.find(entry => entry.id === "cross_sport_scoreboard")?.sport).toBe("all");
    expect(sources.find(entry => entry.id === "calibration_stability")?.sport).toBe("all");
  });
});
