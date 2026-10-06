import { describe, expect, it } from "vitest";
import { derivedAsOf, getLibraryEntries } from "./libraryData";
import { collectionMemberIds } from "./readingCollections";
import { getResearchAnalyses } from "./researchData";
import { filterLibrary } from "./libraryTypes";
import { readFileSync } from "node:fs";
import { join } from "node:path";

describe("getLibraryEntries", () => {
  const entries = getLibraryEntries();
  const derived = entries.filter(entry => entry.kind === "derived");
  const sources = entries.filter(entry => entry.kind === "source");

  it("merges the complete source manifest with every derived analysis", () => {
    expect(entries.length).toBeGreaterThan(getResearchAnalyses().length);
    expect(sources).toHaveLength(77);
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

  it("carries source integrity labels into discovery without flagging unrelated MLB data", () => {
    expect(sources.find(entry => entry.id === "calibration_stability")?.integrityNotice).toContain("revision 1 values withdrawn");
    expect(derived.find(entry => entry.id === "brier-skill-score-by-game-phase")?.integrityNotice).toContain("revision 1 values withdrawn");
    expect(entries.find(entry => entry.id === "state-reliability" && entry.kind === "inspector")?.integrityNotice).toContain("revision 1 values withdrawn");
    expect(sources.find(entry => entry.id === "novel_live_clock_fraction")?.integrityNotice).toContain("revision 1 values withdrawn");
    expect(sources.find(entry => entry.id === "ess_ledger")?.integrityNotice).toBe("Source integrity: under review (a stale input awaits recomposition).");
    expect(sources.find(entry => entry.id === "statcast_showcase")?.integrityNotice).toBeUndefined();
    expect(entries.filter(entry => entry.kind === "paper" && entry.integrityNotice).length).toBeGreaterThan(0);
    expect(entries.find(entry => entry.id === "what-calibration-means" && entry.kind === "explainer")?.integrityNotice).toContain("revision 1 values withdrawn");
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

  it.each([
    ["novel_rest_asymmetry", "mlb", "rest asymmetry"],
    ["novel_starter_rest_absorption", "nba", "starter rest absorption"],
  ] as const)("keeps %s in its published sport's source browse results", (id, otherSport, query) => {
    const artifact = JSON.parse(readFileSync(join(process.cwd(), "public", "data", "showcase", `${id}.json`), "utf8"));
    expect(sources.find(entry => entry.id === id)?.sport).toBe(artifact.sport);
    expect(filterLibrary(entries, artifact.sport, "source", query).map(entry => entry.id)).toContain(id);
    expect(filterLibrary(entries, otherSport, "source", query).map(entry => entry.id)).not.toContain(id);
  });

  it.each(["nba", "mlb"] as const)("preserves shared source entries when browsing %s", sport => {
    const selected = filterLibrary(entries, sport, "source", "").map(entry => entry.id);
    expect(selected).toContain("cross_sport_scoreboard");
    expect(selected).toContain("calibration_stability");
  });

  it("finds source cards by visible scope, measurements, and first preview fields", () => {
    const statcast = sources.find(entry => entry.id === "statcast_showcase")!;
    const comeback = sources.find(entry => entry.id === "comeback_atlas")!;
    for (const query of ["19 PITCH TYPES", "693,037", "pitch TYPE ff", "220,235", "PCT 32"]) {
      expect(filterLibrary(entries, "mlb", "source", query).map(entry => entry.id), query)
        .toContain(statcast.id);
    }
    expect(filterLibrary(entries, "nba", "source", "bUcKeTs masked n lt 30").map(entry => entry.id))
      .toContain(comeback.id);
    expect(filterLibrary(entries, "nba", "source", "pitch type ff").map(entry => entry.id))
      .not.toContain(statcast.id);
    expect(filterLibrary(entries, "mlb", "derived", "pitch type ff").map(entry => entry.id))
      .not.toContain(statcast.id);
    expect(filterLibrary(entries, "mlb", "source", "pitch type ff", collectionMemberIds("forecast-calibration")).map(entry => entry.id))
      .not.toContain(statcast.id);
  });

  it("does not index hidden measurement extras or the second source preview row", () => {
    const statcast = sources.find(entry => entry.id === "statcast_showcase")!;
    expect(statcast.sourceSummary?.previewRows[1][0].value).toBe("SI");
    expect(filterLibrary(entries, "mlb", "source", "107,136").map(entry => entry.id))
      .not.toContain(statcast.id);
    const withFourth = sources.find(entry => {
      const summary = entry.sourceSummary;
      if (!summary || summary.measurements.length < 4) return false;
      const visible = [entry.title, entry.description, entry.category, entry.id, summary.scope,
        ...summary.measurements.slice(0, 3).flatMap(item => [item.label, item.value]),
        ...(summary.previewRows[0] || []).slice(0, 3).flatMap(item => [item.label, item.value])].join(" ").toLowerCase();
      return !visible.includes(summary.measurements[3].label.toLowerCase());
    });
    expect(withFourth).toBeDefined();
    const hidden = withFourth!.sourceSummary!.measurements[3].label;
    expect(filterLibrary(entries, withFourth!.sport, "source", hidden).map(entry => entry.id))
      .not.toContain(withFourth!.id);
  });

  it("assigns a distinct card label to every reading kind", () => {
    expect(entries.find((entry) => entry.kind === "source")?.kindLabel).toBe("Source module");
    expect(entries.find((entry) => entry.kind === "derived")?.kindLabel).toBe("Derived analysis");
    expect(entries.find((entry) => entry.kind === "finding")?.kindLabel).toBe("Finding");
    expect(entries.find((entry) => entry.kind === "inspector")?.kindLabel).toBe("Inspector");
    expect(entries.find((entry) => entry.kind === "explainer")?.kindLabel).toBe("Explainer");
  });
});
