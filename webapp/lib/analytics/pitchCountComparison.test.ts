import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import type { ComparisonEntity, RawEntry } from "./comparisonData";
import { isPitchTypeComparisonEntity, pitchCountComparison } from "./pitchCountComparison";

const entity = (slug: string, values: Record<string, unknown>, floors = "published floor", asOf = "2025-09-28"): ComparisonEntity => ({
  slug, name: slug.toUpperCase(), sourceEntity: `pitch_type:${slug.toUpperCase()}`, values, percentiles: {}, floors, asOf,
});
const fromEntry = (entry: RawEntry): ComparisonEntity => ({
  slug: entry.card_path.split(/[\\/]/).pop()!.replace(/\.png$/, ""), name: entry.entity,
  sourceEntity: entry.entity, values: entry.key_numbers, percentiles: {}, floors: entry.floors, asOf: entry.as_of,
});

describe("pitchCountComparison", () => {
  it("keeps source percentages, true zero, support, floors, and date unchanged", () => {
    const a = entity("ff", { n_pitches: 220235, count_leverage_pct: { pitcher_ahead: 27.6, even: 43.3, pitcher_behind: 29 } });
    const b = entity("un", { n_pitches: 13, count_leverage_pct: { pitcher_ahead: 53.8, even: 46.2, pitcher_behind: 0 } }, "rare codes retained");
    const result = pitchCountComparison(a, b)!;
    expect(result.rows.map(row => row.key)).toEqual(["pitcher_ahead", "even", "pitcher_behind"]);
    expect(result.rows.map(row => row.b)).toEqual([53.8, 46.2, 0]);
    expect(result.entities).toMatchObject({ a: { nPitches: 220235, floors: "published floor" }, b: { nPitches: 13, floors: "rare codes retained" } });
    expect(result.sameAsOf).toBe(true);
    expect(result.definition).toContain("strikes > balls");
  });

  it("marks missing and invalid nested shares unavailable without renormalizing", () => {
    const a = entity("a", { n_pitches: 10, count_leverage_pct: { pitcher_ahead: 25, even: NaN, pitcher_behind: -1 } });
    const b = entity("b", { n_pitches: 20, count_leverage_pct: { pitcher_ahead: 20, even: 30, pitcher_behind: 101 } });
    const result = pitchCountComparison(a, b)!;
    expect(result.rows).toMatchObject([
      { a: 25, b: 20 }, { a: null, b: 30 }, { a: null, b: null },
    ]);
    expect(result.rows.reduce((sum, row) => sum + (row.a ?? 0), 0)).toBe(25);
  });

  it("returns no panel for team, count-family, or malformed entities", () => {
    const pitch = entity("ff", { n_pitches: 20, count_leverage_pct: { pitcher_ahead: 30, even: 40, pitcher_behind: 30 } });
    const validShape = { n_pitches: 20, count_leverage_pct: { pitcher_ahead: 30, even: 40, pitcher_behind: 30 } };
    expect(pitchCountComparison(pitch, { ...entity("team", validShape), sourceEntity: "team:NYY" })).toBeNull();
    expect(pitchCountComparison(pitch, { ...entity("count", validShape), sourceEntity: "count:1-2" })).toBeNull();
    expect(pitchCountComparison(pitch, { ...entity("unknown", validShape), sourceEntity: undefined })).toBeNull();
    expect(pitchCountComparison(pitch, entity("bad", { n_pitches: Infinity, count_leverage_pct: {} }))).toBeNull();
  });

  it("recognizes exactly the 19 public pitch-type entries and retains SC support", () => {
    const manifest = JSON.parse(readFileSync(join(process.cwd(), "public/data/showcase/atlas_mlb_pitch_manifest.json"), "utf8")) as { entries: RawEntry[] };
    const entries = manifest.entries.map(fromEntry);
    const pitchTypes = entries.filter(isPitchTypeComparisonEntity);
    expect(pitchTypes).toHaveLength(19);
    expect(entries).toHaveLength(61);
    const sc = pitchTypes.find(entry => entry.name === "pitch_type:SC")!;
    expect(sc.values.n_pitches).toBe(7);
    expect(sc.floors).toContain("smallest category n=7 (SC)");
    for (const item of pitchTypes) {
      const result = pitchCountComparison(item, item)!;
      expect(result.rows.every(row => row.a !== null && row.a === row.b)).toBe(true);
      expect(result.entities.a.asOf).toBe("2025-09-28");
    }
  });
});
