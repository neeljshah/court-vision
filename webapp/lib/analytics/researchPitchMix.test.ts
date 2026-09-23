import { describe, expect, it } from "vitest";
import { snapshot } from "./labHelpers";
import { buildPitchMixResearch } from "./researchPitchMix";

type CountMap = Record<string, number>;
type MixRow = { pitch_type: string; n: number; pct: number };
type AtlasRow = {
  entity: string;
  key_numbers: { n_pitches: number; pct_of_all_pitches: number; count_state_pct?: CountMap };
  floors?: string;
  as_of?: string;
};

const legalCounts = ["0-0", "0-1", "0-2", "1-0", "1-1", "1-2", "2-0", "2-1", "2-2", "3-0", "3-1", "3-2"];
const completeCounts = (overrides: CountMap = {}): CountMap => ({
  "0-0": 10, "0-1": 10, "0-2": 10, "1-0": 10, "1-1": 10, "1-2": 10,
  "2-0": 10, "2-1": 10, "2-2": 5, "3-0": 5, "3-1": 5, "3-2": 5, ...overrides,
});
const statcast = (rows: MixRow[], n_pitches = rows.reduce((sum, row) => sum + row.n, 0)) =>
  ({ n_pitches, pitch_type_distribution: rows });
const atlasRow = (code: string, n: number, pct: number, counts: CountMap | undefined = completeCounts()): AtlasRow => ({
  entity: `pitch_type:${code}`,
  key_numbers: { n_pitches: n, pct_of_all_pitches: pct, ...(counts === undefined ? {} : { count_state_pct: counts }) },
  floors: "all codes retained; small-n rows are descriptive",
  as_of: "2025-09-28",
});
const atlas = (entries: AtlasRow[]) => ({ entries });
const row = (analysis: ReturnType<typeof buildPitchMixResearch>, code: string) =>
  analysis.rows.find(item => item.label === code)!;

describe("MLB pitch-mix research", () => {
  it("preserves the real fixture baseline and enriches reconciled count states", () => {
    const stat = snapshot<{ n_pitches: number; pitch_type_distribution: MixRow[] }>("statcast_showcase");
    const manifest = snapshot<{ entries: AtlasRow[] }>("atlas_mlb_pitch_manifest");
    const analysis = buildPitchMixResearch(stat, manifest);
    const ff = row(analysis, "FF");
    const sc = row(analysis, "SC");

    expect(analysis.rows).toHaveLength(19);
    expect(ff.values).toMatchObject({ n: 220235, share: 0.3178, squared_share: 0.3178 ** 2, first_pitch_share: 0.2644, two_strike_share: 0.3003, peak_count_share: 0.2644, count_states: 12 });
    expect(ff.bindingValues?.peak_count).toBe("0-0");
    expect(sc.values).toMatchObject({ n: 7, share: 0, squared_share: 0, first_pitch_share: 0.2857, two_strike_share: null, peak_count_share: null, count_states: 5 });
    expect(sc.note).toMatch(/sparse|small/i);
    expect(row(analysis, "UNK").note).toMatch(/unknown|classification/i);
    expect(analysis.sources).toEqual(expect.arrayContaining([
      expect.objectContaining({ id: "statcast_showcase" }),
      expect.objectContaining({ id: "atlas_mlb_pitch_manifest", asOf: "2025-09-28" }),
    ]));
    expect(JSON.stringify(analysis)).toMatch(/2025.*dates.*not published|dates.*not published.*2025/i);
  });

  it("converts percentages once and uses the published percentage denominator", () => {
    const analysis = buildPitchMixResearch(
      statcast([{ pitch_type: "AA", n: 1, pct: 25 }], 4),
      atlas([atlasRow("AA", 1, 25)]),
    );
    expect(row(analysis, "AA").values).toMatchObject({ share: 0.25, squared_share: 0.0625, n: 1 });
  });

  it("keeps sparse explicit states without imputing missing states as zero", () => {
    const counts = { "0-0": 40, "0-2": 20, "1-2": 20, "2-2": 20 };
    const result = row(buildPitchMixResearch(statcast([{ pitch_type: "AA", n: 10, pct: 100 }]), atlas([atlasRow("AA", 10, 100, counts)])), "AA");
    expect(result.values).toMatchObject({ first_pitch_share: 0.4, two_strike_share: null, peak_count_share: null, count_states: 4 });
  });

  it("preserves explicit zero count shares and reports tied complete peaks", () => {
    const counts = completeCounts({ "0-0": 0, "0-1": 15, "1-0": 15 });
    const result = row(buildPitchMixResearch(statcast([{ pitch_type: "AA", n: 10, pct: 100 }]), atlas([atlasRow("AA", 10, 100, counts)])), "AA");
    expect(result.values).toMatchObject({ first_pitch_share: 0, two_strike_share: 0.3, peak_count_share: 0.15, count_states: 12 });
    expect(result.bindingValues?.peak_count).toContain("0-1");
    expect(result.bindingValues?.peak_count).toContain("1-0");
    expect(result.note).toContain("0-1");
    expect(result.note).toContain("1-0");
  });

  it.each([
    ["upper", completeCounts({ "0-0": 10.06 })],
    ["lower", completeCounts({ "0-0": 9.94 })],
  ])("accepts the inclusive complete-total %s tolerance boundary", (_case, counts) => {
    const result = row(buildPitchMixResearch(statcast([{ pitch_type: "AA", n: 10, pct: 100 }]), atlas([atlasRow("AA", 10, 100, counts)])), "AA");
    expect(result.values.count_states).toBe(12);
    expect(result.values.peak_count_share).not.toBeNull();
  });

  it.each([
    ["illegal key", { ...completeCounts(), "4-0": 0 }],
    ["nonfinite", { ...completeCounts(), "0-0": Number.NaN }],
    ["negative", { ...completeCounts(), "0-0": -1 }],
    ["over 100", { ...completeCounts(), "0-0": 101 }],
    ["empty", {}],
    ["sparse sum above tolerance", { "0-0": 60, "0-1": 40.062 }],
    ["complete sum low", Object.fromEntries(legalCounts.map(key => [key, 8]))],
    ["complete sum high", { ...completeCounts(), "0-0": 10.062 }],
  ])("fails all count fields closed for a malformed %s map", (_case, counts) => {
    const result = row(buildPitchMixResearch(statcast([{ pitch_type: "AA", n: 10, pct: 100 }]), atlas([atlasRow("AA", 10, 100, counts)])), "AA");
    expect(result.values).toMatchObject({ first_pitch_share: null, two_strike_share: null, peak_count_share: null, count_states: null });
    expect(result.bindingValues?.peak_count).toBeNull();
  });

  it.each([
    ["missing atlas row", []],
    ["duplicate atlas rows", [atlasRow("AA", 10, 100), atlasRow("AA", 10, 100)]],
    ["n mismatch", [atlasRow("AA", 9, 100)]],
    ["pct mismatch", [atlasRow("AA", 10, 99.99)]],
  ])("nulls count enrichment on %s without changing original HHI values", (_case, entries) => {
    const result = row(buildPitchMixResearch(statcast([{ pitch_type: "AA", n: 10, pct: 100 }]), atlas(entries)), "AA");
    expect(result.values).toMatchObject({ share: 1, squared_share: 1, n: 10, first_pitch_share: null, two_strike_share: null, peak_count_share: null, count_states: null });
  });

  it("fails reconciliation globally when the Statcast total disagrees with its rows", () => {
    const result = row(buildPitchMixResearch(statcast([{ pitch_type: "AA", n: 10, pct: 100 }], 11), atlas([atlasRow("AA", 10, 100)])), "AA");
    expect(result.values).toMatchObject({ share: 1, squared_share: 1, n: 10, first_pitch_share: null, two_strike_share: null, peak_count_share: null, count_states: null });
  });

  it.each([
    ["duplicate Statcast code", statcast([{ pitch_type: "AA", n: 5, pct: 50 }, { pitch_type: "AA", n: 5, pct: 50 }]), atlas([atlasRow("AA", 5, 50), atlasRow("BB", 5, 50)])],
    ["same-length code substitution", statcast([{ pitch_type: "AA", n: 5, pct: 50 }, { pitch_type: "BB", n: 5, pct: 50 }]), atlas([atlasRow("AA", 5, 50), atlasRow("CC", 5, 50)])],
  ])("fails count enrichment globally for a %s", (_case, stat, manifest) => {
    const analysis = buildPitchMixResearch(stat, manifest);
    expect(analysis.rows.every(item => item.values.count_states === null && item.values.first_pitch_share === null)).toBe(true);
  });

  it("fails closed when count_state_pct is absent and does not mutate either input", () => {
    const stat = statcast([{ pitch_type: "AA", n: 10, pct: 100 }]);
    const entry = atlasRow("AA", 10, 100);
    delete entry.key_numbers.count_state_pct;
    const manifest = atlas([entry]);
    const before = JSON.stringify({ stat, manifest });
    const result = row(buildPitchMixResearch(stat, manifest), "AA");
    expect(result.values).toMatchObject({ first_pitch_share: null, two_strike_share: null, peak_count_share: null, count_states: null });
    expect(JSON.stringify({ stat, manifest })).toBe(before);
  });
});
