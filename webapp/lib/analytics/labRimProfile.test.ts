import { describe, expect, it } from "vitest";
import { labComparisonPolicy } from "./labComparisonPolicy";
import { buildRimProfileLabDataset, getRimProfileLabDataset } from "./labRimProfile";
import { displayMeasurement } from "./labTypes";

const leader = (overrides: Record<string, unknown> = {}) => ({
  rank: 1, player_name: "Example Player", min_on: 600,
  rim_share_allowed_on: 0.25, rim_share_allowed_off: 0.5,
  delta: -0.2499, rim_efg_delta: -0.01, ...overrides,
});
const source = (leaders: unknown[], metadata: Record<string, unknown> = {}) => ({
  seasons: [{ season: "Example season", n_qualified: 10, min_on_floor: 500, leaders, ...metadata }],
});

describe("rim profile lab dataset", () => {
  it("retains all published player-season rows, original values, and cohort definitions", () => {
    const dataset = getRimProfileLabDataset();
    expect(dataset.rows).toHaveLength(30);
    expect(dataset.rows.filter(row => row.group === "2025-26")).toHaveLength(15);
    expect(dataset.rows.filter(row => row.group === "2024-25")).toHaveLength(15);
    expect(new Set(dataset.rows.map(row => row.id)).size).toBe(30);
    expect(dataset.rows[0].id).toBe("2025-26-0");
    expect(dataset.rows[15].id).toBe("2024-25-0");
    expect(dataset.rows[0].label).toBe("Victor Wembanyama");
    expect(dataset.rows[0].values).toEqual({
      delta: -0.0618, rim_share_allowed_on: 0.25, rim_share_allowed_off: 0.3118,
      rim_efg_delta: -0.0287, min_on: 2489,
      relative_rim_share_difference: (0.25 - 0.3118) / 0.3118,
    });
    expect(dataset.rows[15].label).toBe("Rudy Gobert");
    expect(dataset.rows[15].values.relative_rim_share_difference).toBeCloseTo(-0.185, 3);
    expect(dataset.rows[15].values.delta).toBe(-0.0632);
    expect(dataset.rows[0].definition).toEqual({ sport: "NBA", season: "2025-26" });
    expect(labComparisonPolicy(dataset.rows).compatibility).toBe("incompatible");
    expect(dataset.fields.map(field => field.key)).toEqual([
      "delta", "rim_share_allowed_on", "rim_share_allowed_off", "rim_efg_delta", "min_on",
      "relative_rim_share_difference",
    ]);
    expect(dataset.fields[5]).toEqual({
      key: "relative_rim_share_difference", label: "Relative rim-share difference", unit: "percent", digits: 2,
    });
    expect(displayMeasurement(dataset.rows[0].values.relative_rim_share_difference, dataset.fields[5])).toBe("-19.82%");
    expect(displayMeasurement(dataset.rows[15].values.relative_rim_share_difference, dataset.fields[5])).toBe("-18.5%");
    expect(displayMeasurement(dataset.rows[0].values.delta, dataset.fields[0])).toBe("-6.18 pp");
    expect(dataset.scope).toContain("2025-26: 15 selected player-season rows from 370 qualified players; 500 on-court minute floor");
    expect(dataset.scope).toContain("2024-25: 15 selected player-season rows from 387 qualified players; 500 on-court minute floor");
    expect(dataset.caveat).toContain("not a census or a count of unique players");
    expect(dataset.caveat).toContain("does not publish exact calendar endpoints");
    expect(dataset.rows[0].note).toContain("rim_deterrence.json seasons[0].leaders[0]");
    expect(dataset.rows[15].note).toContain("rim_deterrence.json seasons[1].leaders[0]");
    expect(dataset.rows[0].note).toContain("Original source rank: 1");
    expect(dataset.rows[0].note).toContain("off-court share is the baseline");
    expect(dataset.rows[0].note).toContain("Opponent shot-attempt counts and off-court minutes are unavailable");
  });

  it("uses rounded source shares and preserves the original delta independently", () => {
    const dataset = buildRimProfileLabDataset(source([
      leader(), leader({ rim_share_allowed_on: 0.5 }), leader({ rim_share_allowed_on: 0 }),
    ]));
    expect(dataset.rows.map(row => row.values.relative_rim_share_difference)).toEqual([-0.5, 0, -1]);
    expect(dataset.rows[0].values.delta).toBe(-0.2499);
    expect(dataset.rows[0].note).toContain("published rounded on share");
    expect(dataset.rows[0].note).toContain("not an independent metric");
  });

  it("reports invalid proportions and denominators as unavailable without coercion", () => {
    const invalid = [null, "0.2", NaN, Infinity, -0.1, 1.1];
    const dataset = buildRimProfileLabDataset(source([
      ...invalid.map(value => leader({ rim_share_allowed_on: value })),
      ...invalid.map(value => leader({ rim_share_allowed_off: value })),
      leader({ rim_share_allowed_off: 0 }),
      leader({ rim_share_allowed_on: Number.MIN_VALUE, rim_share_allowed_off: Number.MIN_VALUE / 2 }),
      leader({ rim_share_allowed_on: 1, rim_share_allowed_off: Number.MIN_VALUE }),
      leader({ delta: "-0.2", rim_efg_delta: Infinity, min_on: null }),
    ]));
    expect(dataset.rows.slice(0, 15).every(row => row.values.relative_rim_share_difference === null)).toBe(true);
    expect(dataset.rows[15].values).toMatchObject({ delta: null, rim_efg_delta: null, min_on: null });
    expect(dataset.rows[15].values.relative_rim_share_difference).toBe(-0.5);
  });

  it("does not emit a finite ratio that overflows when displayed as a percentage", () => {
    const dataset = buildRimProfileLabDataset(source([
      leader({ rim_share_allowed_on: 1, rim_share_allowed_off: 1e-307 }),
    ]));
    expect(Number.isFinite((1 - 1e-307) / 1e-307)).toBe(true);
    expect(dataset.rows[0].values.relative_rim_share_difference).toBeNull();
    expect(displayMeasurement(dataset.rows[0].values.relative_rim_share_difference, dataset.fields[5])).toBe("Unavailable");
  });

  it("uses source counts and floors dynamically and labels missing metadata", () => {
    const changed = buildRimProfileLabDataset(source([leader({ rank: 7 })], { n_qualified: 12, min_on_floor: 300 }));
    expect(changed.scope).toContain("1 selected player-season rows from 12 qualified players; 300 on-court minute floor");
    expect(changed.rows[0].note).toContain("Original source rank: 7");
    expect(changed.rows[0].note).toContain("Season qualifiers: 12; 300 on-court minute floor");
    const missing = buildRimProfileLabDataset(source([leader({ rank: null })], { n_qualified: "12", min_on_floor: null }));
    expect(missing.scope).toContain("an unavailable number of qualified players; on-court minute floor unavailable");
    expect(missing.rows[0].note).toContain("Original source rank: unavailable");
    expect(missing.rows[0].note).toContain("Season qualifiers: unavailable");
    expect(buildRimProfileLabDataset(source([])).rows).toEqual([]);
    expect(buildRimProfileLabDataset({ seasons: [] }).rows).toEqual([]);
  });

  it("fails clearly for missing required structure", () => {
    expect(() => buildRimProfileLabDataset({})).toThrow("rim_deterrence.seasons must be an array");
    expect(() => buildRimProfileLabDataset({ seasons: [null] })).toThrow("rim_deterrence.seasons[0] must be an object");
    expect(() => buildRimProfileLabDataset({ seasons: [{ leaders: [] }] })).toThrow("rim_deterrence.seasons[0].season must be a nonempty string");
    expect(() => buildRimProfileLabDataset({ seasons: [{ season: "x" }] })).toThrow("rim_deterrence.seasons[0].leaders must be an array");
    expect(() => buildRimProfileLabDataset(source([null]))).toThrow("rim_deterrence.seasons[0].leaders[0] must be an object");
    expect(() => buildRimProfileLabDataset(source([leader({ player_name: null })]))).toThrow("rim_deterrence.seasons[0].leaders[0].player_name must be a nonempty string");
  });
});
