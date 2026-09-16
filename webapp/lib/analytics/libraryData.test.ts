import { describe, expect, it } from "vitest";
import { derivedAsOf, getLibraryEntries } from "./libraryData";
import { collectionMemberIds } from "./readingCollections";
import { getResearchAnalyses } from "./researchData";
import { filterLibrary } from "./libraryTypes";

describe("getLibraryEntries", () => {
  const entries = getLibraryEntries();
  const derived = entries.filter(entry => entry.kind === "derived");
  const sources = entries.filter(entry => entry.kind === "source");

  it("merges the complete source manifest with every derived analysis", () => {
    expect(entries.length).toBeGreaterThan(getResearchAnalyses().length);
    expect(sources).toHaveLength(76);
    expect(new Set(entries.map(entry => entry.id)).size).toBe(entries.length);
    expect(derived).toHaveLength(getResearchAnalyses().length);
    expect(derived.reduce((sum, entry) => sum + (entry.rows ?? 0), 0)).toBe(getResearchAnalyses().reduce((sum, analysis) => sum + analysis.rows.length, 0));
  });

  it("keeps routes public and numeric previews finite", () => {
    expect(sources.every(entry => entry.href === `/analytics/m/${entry.id}/`)).toBe(true);
    expect(derived.every(entry => entry.href === `/analytics/research/${entry.id}/`)).toBe(true);
    expect(entries.every(entry => entry.preview.every(Number.isFinite))).toBe(true);
    expect(entries.every(entry => !/^(?:DESCRIPTIVE_ONLY|NOT_TESTABLE|CONFIRMED_LOCAL)$/.test(entry.description))).toBe(true);
    expect(sources.every(entry => entry.sourceSummary?.scope)).toBe(true);
    expect(sources.find(entry => entry.id === "statcast_showcase")?.sourceSummary?.scope).toBe("693,037 pitches, 19 pitch types");
  });

  it("uses a published analysis source date when an analysis has no direct date", () => {
    expect(derivedAsOf({ sources: [{ id: "source", asOf: "2026-07-25" }] })).toBe("2026-07-25");
    expect(derivedAsOf({ asOf: "2026-07-26", sources: [{ id: "source", asOf: "2026-07-25" }] })).toBe("2026-07-26");
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

  it("limits a collection view to its registered library entries", () => {
    const selected = filterLibrary(entries, "all", "all", "", collectionMemberIds("forecast-calibration"));
    expect(selected.map((entry) => entry.id).every((id) => collectionMemberIds("forecast-calibration").includes(id))).toBe(true);
    expect(selected.length).toBeGreaterThan(0);
  });

  it("assigns a distinct card label to every reading kind", () => {
    expect(entries.find((entry) => entry.kind === "source")?.kindLabel).toBe("Source module");
    expect(entries.find((entry) => entry.kind === "derived")?.kindLabel).toBe("Derived analysis");
    expect(entries.find((entry) => entry.kind === "finding")?.kindLabel).toBe("Finding");
    expect(entries.find((entry) => entry.kind === "inspector")?.kindLabel).toBe("Inspector");
    expect(entries.find((entry) => entry.kind === "explainer")?.kindLabel).toBe("Explainer");
  });
});
