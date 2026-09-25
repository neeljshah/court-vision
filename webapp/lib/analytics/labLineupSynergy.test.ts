import { describe, expect, it } from "vitest";
import { buildLineupSynergyLabDataset, getLineupSynergyLabDataset } from "./labLineupSynergy";
import { labComparisonPolicy } from "./labComparisonPolicy";

const roster = ["One Full Name", "Two Full Name", "Three Full Name", "Four Full Name", "Five Full Name"];
const row = (overrides: Record<string, unknown> = {}) => ({
  rank: 1, members: roster, team_id: 1610612763, n_games: 2, min: 10,
  net_per48: 4.01, expected_net_per48: 1.01, synergy_residual: 2.99,
  ...overrides,
});

describe("lineup synergy lab dataset", () => {
  it("keeps all 23 distinct published extremes, values, groups and identifiers", () => {
    const dataset = getLineupSynergyLabDataset();
    expect(dataset.rows).toHaveLength(23);
    expect(dataset.rows.filter(item => item.group === "Top residuals")).toHaveLength(15);
    expect(dataset.rows.filter(item => item.group === "Bottom residuals")).toHaveLength(8);
    expect(dataset.rows[0].id).toBe("Top residuals-0");
    expect(dataset.rows[15].id).toBe("Bottom residuals-0");
    expect(dataset.rows[0].values).toEqual({
      synergy_residual: 24.32, net_per48: 29.87, expected_net_per48: 5.55,
      min: 221.8, n_games: 25, minutes_per_game: 221.8 / 25,
    });
    expect(dataset.rows[15].values.minutes_per_game).toBe(136.9 / 13);
    expect(dataset.rows[0].label).toContain("Memphis Grizzlies");
    expect(dataset.rows[0].note).toContain("Jaren Jackson Jr., Ja Morant, Desmond Bane, Zach Edey, Jaylen Wells");
    expect(dataset.rows[0].note).toContain("lineup_synergy.json top[0]");
    expect(dataset.rows[0].note).toContain("Source team_id: 1610612763");
    expect(dataset.rows[0].note).toContain("ctx_lineup_proxy.json and atlas_nba_teams_manifest.json for identity only");
    expect(dataset.rows[15].note).toContain("lineup_synergy.json bottom[0]");
    expect(dataset.fields.map(field => field.key)).toEqual([
      "synergy_residual", "net_per48", "expected_net_per48", "min", "n_games", "minutes_per_game",
    ]);
    expect(dataset.fields.map(field => field.label)).toEqual([
      "Residual points / 48 min", "Observed net points / 48 min", "Expected net points / 48 min",
      "On-court minutes", "Recorded games", "Minutes per recorded game",
    ]);
    expect(dataset.scope).toContain("15 top and 8 bottom selected lineups from 102 qualified lineups; 2024-25");
    expect(dataset.scope).toContain("all five members");
    expect(dataset.caveat).toContain("not points per 100 possessions");
    expect(labComparisonPolicy(dataset.rows).compatibility).toBe("unknown");
  });

  it("uses original residual and derives minutes only for valid support", () => {
    const input = [
      row({ min: 0, n_games: 2 }),
      row({ min: null }), row({ min: -1 }), row({ min: Infinity }),
      row({ n_games: 0 }), row({ n_games: -1 }), row({ n_games: 1.5 }),
      row({ n_games: "2" }), row({ n_games: Number.MAX_SAFE_INTEGER + 1 }),
    ];
    const dataset = buildLineupSynergyLabDataset({ top: input, bottom: [], season: "custom", n_qualified: 12 });
    expect(dataset.rows.map(item => item.values.minutes_per_game)).toEqual([0, null, null, null, null, null, null, null, null]);
    expect(dataset.rows[0].values.synergy_residual).toBe(2.99);
    expect(dataset.rows[0].values.net_per48).toBe(4.01);
    expect(dataset.rows[0].values.expected_net_per48).toBe(1.01);
    expect(dataset.rows[0].note).toContain("rounded independently");
    expect(dataset.rows[0].note).toContain("published rounded on-court minute total");
    expect(dataset.scope).toContain("9 top and 0 bottom selected lineups from 12 qualified lineups; custom");
  });

  it("keeps invalid published operands unavailable and unknown metadata honest", () => {
    const dataset = buildLineupSynergyLabDataset({
      top: [row({ team_id: 999, net_per48: "4", expected_net_per48: NaN, synergy_residual: null, min: "10", n_games: "2" })],
      bottom: [], season: null, n_qualified: "12",
    });
    expect(dataset.rows[0].label).toContain("Unknown team (ID 999)");
    expect(dataset.rows[0].note).toContain("Team name unavailable in public team mapping");
    expect(dataset.rows[0].values).toEqual({
      synergy_residual: null, net_per48: null, expected_net_per48: null,
      min: null, n_games: null, minutes_per_game: null,
    });
    expect(dataset.scope).toContain("season unavailable");
    expect(dataset.scope).toContain("unavailable number");
    expect(dataset.nQualifying).toBeUndefined();
  });

  it("fails clearly for malformed required arrays and rows", () => {
    expect(() => buildLineupSynergyLabDataset({})).toThrow("lineup_synergy.top must be an array");
    expect(() => buildLineupSynergyLabDataset({ top: [] })).toThrow("lineup_synergy.bottom must be an array");
    expect(() => buildLineupSynergyLabDataset({ top: [null], bottom: [] })).toThrow("lineup_synergy.top[0] must be an object");
    expect(() => buildLineupSynergyLabDataset({ top: [], bottom: [42] })).toThrow("lineup_synergy.bottom[0] must be an object");
    expect(() => buildLineupSynergyLabDataset({ top: [row({ members: [] })], bottom: [] })).toThrow("lineup_synergy.top[0].members must contain five names");
  });

  it("does not assign a team name when identity sources conflict or are incomplete", () => {
    const source = { top: [row()], bottom: [] };
    const teams = { players: [{ team_id: 1610612763, team: "MEM" }] };
    const atlas = { entries: [{ entity: "MEM", key_numbers: { team_full_name: "Memphis Grizzlies" } }] };
    expect(buildLineupSynergyLabDataset(source, teams, atlas).rows[0].label).toContain("Memphis Grizzlies");
    const conflictingIds = { players: [...teams.players, { team_id: 1610612763, team: "BOS" }] };
    const conflictingNames = { entries: [...atlas.entries, { entity: "MEM", key_numbers: { team_full_name: "Another team" } }] };
    for (const dataset of [
      buildLineupSynergyLabDataset(source, conflictingIds, atlas),
      buildLineupSynergyLabDataset(source, teams, conflictingNames),
      buildLineupSynergyLabDataset(source, teams),
    ]) {
      expect(dataset.rows[0].label).toContain("Unknown team (ID 1610612763)");
      expect(dataset.rows[0].note).toContain("Source team_id: 1610612763");
      expect(dataset.rows[0].values.minutes_per_game).toBe(5);
    }
  });
});
