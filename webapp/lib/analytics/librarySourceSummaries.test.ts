import { describe, expect, it } from "vitest";
import { summarizeLibrarySource } from "./librarySourceSummaries";

describe("summarizeLibrarySource", () => {
  it("adapts the Statcast artifact with named pitch units", () => {
    const summary = summarizeLibrarySource("statcast_showcase", { n_pitches: 693037, pitch_type_distribution: [{ pitch_type: "FF", pitches: 12 }], velo_percentiles_by_pitch_type: [] });
    expect(summary.scope).toBe("693,037 pitches, 1 pitch types");
    expect(summary.measurements).toContainEqual({ label: "Pitches", value: "693,037" });
  });
  it("adapts player splits from its coverage object", () => {
    const summary = summarizeLibrarySource("ctx_player_splits", { coverage: { players_analysed: 50, seasons: 3 }, players: [{ player_name: "A Player", total_games: 20 }] });
    expect(summary.scope).toBe("50 players, 3 seasons");
    expect(summary.previewRows[0][0]).toEqual({ label: "Player Name", value: "A Player" });
  });
  it("adapts a lineup artifact with its qualification count", () => {
    const summary = summarizeLibrarySource("lineup_synergy", { n_qualified: 102, season: "2024-25", top: [{ team: "MEM", synergy_residual: 3.2 }] });
    expect(summary.scope).toBe("102 qualified five-man lineups, 2024-25");
  });
  it("names generic numeric and array facts from their JSON keys", () => {
    const summary = summarizeLibrarySource("other", { n_games: 42, observations: [{ team: "A", count: 4 }] });
    expect(summary.measurements).toContainEqual({ label: "Games", value: "42" });
    expect(summary.measurements).toContainEqual({ label: "Observations", value: "1 entries" });
  });
  it("marks non-buildable or empty artifacts unavailable", () => {
    expect(summarizeLibrarySource("other", { not_buildable: true, rows: [] }).availability).toBe("unavailable");
  });
});
