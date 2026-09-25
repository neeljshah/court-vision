import { describe, expect, it } from "vitest";
import { labComparisonPolicy } from "./labComparisonPolicy";
import { buildLiveClockLabDataset, getLiveClockLabDataset } from "./labLiveClock";
import { novelDatasets } from "./labNovel";

const result = (overrides: Record<string, unknown> = {}) => ({
  sport: "mlb", unit: "runs", clock_field: "inning", near_median_threshold: 3,
  decided_frac_of_games: 0.5575, n_games_decided: 97, n_games_total: 174,
  live_clock_fraction: 0.7368, ...overrides,
});
const source = (results: unknown[], as_of: unknown = "2026-09-17") => ({ results, as_of });

describe("live-clock lab dataset", () => {
  it("uses the actual source values and keeps the two sport definitions separate", () => {
    const dataset = getLiveClockLabDataset();
    expect(dataset).toMatchObject({
      id: "live-clock", source: "novel_live_clock_fraction", title: "Live-Clock Fraction",
      status: "Incremental metric",
    });
    expect(dataset.fields.map(field => field.key)).toEqual([
      "live_clock_fraction", "decided_frac_of_games", "n_games_total", "n_games_decided",
    ]);
    expect(dataset.fields[2].label).toBe("Games with usable score paths");
    expect(dataset.rows.map(row => [row.id, row.group])).toEqual([
      ["MLB-0", "MLB"], ["INTERNATIONAL SOCCER-1", "INTERNATIONAL SOCCER"],
    ]);
    expect(dataset.rows[0].values).toEqual({
      live_clock_fraction: 0.7368, decided_frac_of_games: 0.5575,
      n_games_total: 174, n_games_decided: 97,
    });
    expect(dataset.rows[1].values).toEqual({
      live_clock_fraction: 0.5994, decided_frac_of_games: 0.4615,
      n_games_total: 26, n_games_decided: 12,
    });
    expect(dataset.rows.map(row => row.definition)).toEqual([
      { sport: "MLB", threshold: 3, unit: "runs", clockField: "inning", population: "174 games with usable score paths" },
      { sport: "INTERNATIONAL SOCCER", threshold: 1, unit: "goals", clockField: "minute", population: "26 games with usable score paths" },
    ]);
    expect(labComparisonPolicy(dataset.rows).compatibility).toBe("incompatible");
    expect(dataset.scope).toContain("MLB: 174 games with usable score paths; INTERNATIONAL SOCCER: 26 games with usable score paths");
    expect(dataset.scope).toContain("Artifact date: 2026-09-17; observation window unavailable");
    expect(dataset.scope).toContain("The LCF artifact does not include stored corpus counts; see the integrity receipt for those counts");
    expect(dataset.description).toContain("median share of the observed game clock");
    expect(dataset.rows[0].note).toContain("novel_live_clock_fraction.json results[0]");
    expect(dataset.rows[0].note).toContain("Threshold: 3 runs. Clock: inning. At this threshold, 97 of 174");
    expect(dataset.rows[1].note).toContain("novel_live_clock_fraction.json results[1]");
    expect(dataset.rows[1].note).toContain("Threshold: 1 goals. Clock: minute. At this threshold, 12 of 26");
    expect(dataset.caveat).toContain("thresholds and clock units are not equivalent");
    expect(dataset.caveat).toContain("does not establish why a lead held or predict a live game's result");
    expect(novelDatasets().find(item => item.id === "live-clock")).toEqual(dataset);
  });

  it("takes counts, date, threshold and clock from changed source metadata", () => {
    const dataset = buildLiveClockLabDataset(source([result({
      n_games_total: 41, n_games_decided: 7, near_median_threshold: 4,
      unit: "runs", clock_field: "period", live_clock_fraction: 0.54321,
    })], "2025-11-09"));
    expect(dataset.scope).toContain("MLB: 41 games with usable score paths");
    expect(dataset.scope).toContain("Artifact date: 2025-11-09");
    expect(dataset.scope).not.toContain("2026-09-17");
    expect(dataset.rows[0].values).toMatchObject({ n_games_total: 41, n_games_decided: 7, live_clock_fraction: 0.54321 });
    expect(dataset.rows[0].definition).toMatchObject({ threshold: 4, clockField: "period", population: "41 games with usable score paths" });
    expect(dataset.rows[0].note).toContain("7 of 41 games with usable score paths");
  });

  it("keeps missing or invalid metadata unavailable and preserves genuine zero", () => {
    const dataset = buildLiveClockLabDataset(source([
      result({ n_games_total: "174", n_games_decided: -1, live_clock_fraction: null, decided_frac_of_games: NaN }),
      result({ sport: "soccer_intl", unit: null, clock_field: null, near_median_threshold: Infinity,
        n_games_total: 0, n_games_decided: 0, live_clock_fraction: 0, decided_frac_of_games: 0 }),
    ], "2026-13-50"));
    expect(dataset.scope).toContain("MLB: unavailable games with usable score paths");
    expect(dataset.scope).toContain("INTERNATIONAL SOCCER: 0 games with usable score paths");
    expect(dataset.scope).toContain("Artifact date: unavailable; observation window unavailable");
    expect(dataset.rows[0].values).toEqual({
      live_clock_fraction: null, decided_frac_of_games: null, n_games_total: null, n_games_decided: null,
    });
    expect(dataset.rows[0].definition).not.toHaveProperty("population");
    expect(dataset.rows[0].note).toContain("unavailable of unavailable games with usable score paths");
    expect(dataset.rows[1].values).toEqual({
      live_clock_fraction: 0, decided_frac_of_games: 0, n_games_total: 0, n_games_decided: 0,
    });
    expect(dataset.rows[1].definition).not.toHaveProperty("threshold");
    expect(dataset.rows[1].definition).not.toHaveProperty("unit");
    expect(dataset.rows[1].definition).not.toHaveProperty("clockField");
    expect(dataset.rows.every(row => row.definition?.observationWindow === undefined)).toBe(true);
  });

  it("accepts only nonnegative safe-integer counts", () => {
    for (const invalid of [null, -1, 0.5, NaN, Infinity, Number.MAX_SAFE_INTEGER + 1, "1"]) {
      const dataset = buildLiveClockLabDataset(source([result({ n_games_total: invalid, n_games_decided: invalid })]));
      expect(dataset.rows[0].values.n_games_total).toBeNull();
      expect(dataset.rows[0].values.n_games_decided).toBeNull();
    }
  });

  it("marks comparison unknown when one row has no valid population denominator", () => {
    const dataset = buildLiveClockLabDataset(source([
      result({ n_games_total: null }),
      result({ sport: "soccer_intl", unit: "goals", clock_field: "minute", near_median_threshold: 1, n_games_total: 26 }),
    ]));
    expect(dataset.rows[0].definition).not.toHaveProperty("population");
    expect(dataset.rows[1].definition?.population).toBe("26 games with usable score paths");
    expect(labComparisonPolicy(dataset.rows).compatibility).toBe("unknown");
  });

  it("fails clearly for malformed required structure", () => {
    expect(() => buildLiveClockLabDataset({})).toThrow("novel_live_clock_fraction.results must be an array");
    expect(() => buildLiveClockLabDataset(source([null]))).toThrow("novel_live_clock_fraction.results[0] must be an object");
    expect(() => buildLiveClockLabDataset(source([result({ sport: null })]))).toThrow("novel_live_clock_fraction.results[0].sport must be a nonempty string");
  });
});
