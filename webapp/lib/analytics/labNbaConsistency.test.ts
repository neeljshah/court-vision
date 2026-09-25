import { describe, expect, it } from "vitest";
import { buildNbaConsistencyLabDataset, getNbaConsistencyLabDataset } from "./labNbaConsistency";
import { displayMeasurement } from "./labTypes";
import { labComparisonPolicy } from "./labComparisonPolicy";

const player = (overrides: Record<string, unknown> = {}) => ({
  player_name: "Test Player", player_id: 123, games: 15, shrink_weight: 0.429,
  composite_cv_shrunk: 0.5, pts_per36_mean: 16, pts_cv_shrunk: 0.4,
  reb_cv_shrunk: 0.5, ast_cv_shrunk: 0.6, ...overrides,
});
const source = (top: unknown = [player()], bottom: unknown = []) => ({
  most_consistent_top15: top, least_consistent_top15: bottom,
  as_of: "2030-01-02",
  methodology: { seasons_pooled: ["2028-29", "2029-30"], min_game_minutes_floor: 12, min_qualifying_games_floor: 18, shrink_k_games: 30 },
  input_coverage: { players_meeting_floor: 90, unique_players: 120 },
});

describe("NBA consistency lab dataset", () => {
  it("preserves all 30 published rows, original values, source order, and identity", () => {
    const dataset = getNbaConsistencyLabDataset();
    expect(dataset.id).toBe("nba-consistency");
    expect(dataset.title).toBe("Player consistency");
    expect(dataset.source).toBe("nba_consistency_profiles");
    expect(dataset.rows).toHaveLength(30);
    expect(dataset.rows.map(row => row.group)).toEqual([
      ...Array(15).fill("Most consistent"), ...Array(15).fill("Least consistent"),
    ]);
    expect(dataset.rows.map(row => row.id)).toEqual([
      ...Array.from({ length: 15 }, (_, i) => `Most consistent-${i}`),
      ...Array.from({ length: 15 }, (_, i) => `Least consistent-${i}`),
    ]);
    expect(dataset.fields.map(field => field.key)).toEqual([
      "composite_cv_shrunk", "pts_per36_mean", "pts_cv_shrunk", "reb_cv_shrunk", "ast_cv_shrunk", "games", "shrink_weight",
    ]);
    expect(dataset.fields.find(field => field.key === "games")?.label).toBe("Qualifying game appearances");
    const weight = dataset.fields.find(field => field.key === "shrink_weight")!;
    expect(weight).toEqual({ key: "shrink_weight", label: "Player-data blend weight", unit: "percent", digits: 1 });
    expect(dataset.rows[0].label).toBe("Luka Doncic");
    expect(dataset.rows[0].values).toEqual({
      composite_cv_shrunk: 0.3448, pts_per36_mean: 31.87, pts_cv_shrunk: 0.2799,
      reb_cv_shrunk: 0.3569, ast_cv_shrunk: 0.3975, games: 184, shrink_weight: 0.902,
    });
    expect(displayMeasurement(dataset.rows[0].values.shrink_weight, weight)).toBe("90.2%");
    expect(dataset.rows[15].label).toBe("P.J. Tucker");
    expect(dataset.rows[15].values.games).toBe(26);
    expect(dataset.rows[15].values.shrink_weight).toBe(0.565);
    expect(dataset.rows[24].label).toBe("Moses Brown");
    expect(dataset.rows[24].values.games).toBe(15);
    expect(dataset.rows[24].values.shrink_weight).toBe(0.429);
    expect(dataset.rows[0].note).toContain("most_consistent_top15[0]");
    expect(dataset.rows[0].note).toContain("player_id: 1629029");
    expect(dataset.rows[15].note).toContain("least_consistent_top15[0]");
    expect(dataset.rows[15].note).toContain("player_id: 200782");
    expect(labComparisonPolicy(dataset.rows).compatibility).toBe("unknown");
  });

  it("states the source date, pooled window, qualifying floors, population, and limits", () => {
    const dataset = getNbaConsistencyLabDataset();
    expect(dataset.scope).toContain("15 most consistent and 15 least consistent published rows from 579 eligible players among 807 source unique players");
    for (const text of ["2026-04-12", "2023-24, 2024-25, 2025-26", "at least 10 minutes", "at least 15 qualifying appearances", "20 games", "not complete season coverage"]) {
      expect(dataset.scope).toContain(text);
    }
    expect(dataset.description).toContain("equal mean of their three shrunk coefficients of variation");
    expect(dataset.description).toContain("qualified league mean CV");
    expect(dataset.description).toContain("qualifying games / (qualifying games + K)");
    expect(dataset.caveat).toContain("not the complete player population");
    expect(dataset.caveat).toContain("low means can inflate CV");
    expect(dataset.caveat).toContain("does not forecast");
    expect(dataset.rows[0].note).toContain("not valid observations for each stat");
    expect(dataset.rows[0].note).toContain("rounded to three decimals");
    expect(dataset.rows[0].note).toContain("not a confidence, probability, or effectiveness score");
    expect(dataset.rows[0].note).toContain("Per-stat valid counts and raw standard deviations are unavailable");
  });

  it("uses source metadata dynamically and reports missing values honestly", () => {
    const custom = buildNbaConsistencyLabDataset(source());
    expect(custom.scope).toContain("1 most consistent and 0 least consistent published rows from 90 eligible players among 120 source unique players");
    expect(custom.scope).toContain("2030-01-02");
    expect(custom.scope).toContain("2028-29, 2029-30");
    expect(custom.scope).toContain("at least 12 minutes");
    expect(custom.scope).toContain("at least 18 qualifying appearances");
    expect(custom.scope).toContain("30 games");
    const missing = buildNbaConsistencyLabDataset({ most_consistent_top15: [], least_consistent_top15: [] });
    expect(missing.rows).toEqual([]);
    expect(missing.status).toBe("No published rows");
    expect(missing.eligiblePopulation).toBeUndefined();
    for (const text of ["as of unavailable", "pooled seasons unavailable", "an unavailable number of eligible players", "source player count unavailable", "Qualifying minutes floor unavailable", "an unavailable number of qualifying appearances", "Published shrinkage K: unavailable"]) {
      expect(missing.scope).toContain(text);
    }
    expect(missing.scope).not.toContain("579");
  });

  it("accepts boundary weights, rejects invalid weights and counts, and never derives weight from games", () => {
    const weights = [0, 1, "0.5", NaN, Infinity, -0.1, 1.1, null];
    const rows = weights.map((weight, i) => player({ player_name: `Player ${i}`, shrink_weight: weight, games: i === 0 ? 999 : 15 }));
    const dataset = buildNbaConsistencyLabDataset(source(rows));
    expect(dataset.rows.map(row => row.values.shrink_weight)).toEqual([0, 1, null, null, null, null, null, null]);
    expect(dataset.rows[0].values.games).toBe(999);
    expect(dataset.rows[0].values.shrink_weight).toBe(0);
    const invalidCounts = [-1, 1.5, "15", Infinity, Number.MAX_SAFE_INTEGER + 1];
    const counts = buildNbaConsistencyLabDataset(source(invalidCounts.map((games, i) => player({ player_name: `Count ${i}`, games }))));
    expect(counts.rows.map(row => row.values.games)).toEqual([null, null, null, null, null]);
    expect(counts.rows.map(row => row.values.shrink_weight)).toEqual(Array(5).fill(0.429));
  });

  it("rejects missing arrays, nonobject rows, and blank names", () => {
    expect(() => buildNbaConsistencyLabDataset({})).toThrow("most_consistent_top15 must be an array");
    expect(() => buildNbaConsistencyLabDataset({ most_consistent_top15: [] })).toThrow("least_consistent_top15 must be an array");
    expect(() => buildNbaConsistencyLabDataset(source([null]))).toThrow("most_consistent_top15[0] must be an object");
    expect(() => buildNbaConsistencyLabDataset(source([], [42]))).toThrow("least_consistent_top15[0] must be an object");
    expect(() => buildNbaConsistencyLabDataset(source([player({ player_name: " " })]))).toThrow("player_name must be a nonempty string");
  });
});
