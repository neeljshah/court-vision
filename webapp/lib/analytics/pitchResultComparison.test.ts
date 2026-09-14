import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import type { ComparisonEntity, RawEntry } from "./comparisonData";
import { pitchResultComparison } from "./pitchResultComparison";

const entity = (sourceEntity: string, mix: unknown, nPitches: unknown = 10): ComparisonEntity => ({
  slug: sourceEntity.replace(/[^a-z0-9]+/gi, "_"), name: sourceEntity, sourceEntity,
  values: { n_pitches: nPitches, outcome_mix_pct: mix }, percentiles: {}, asOf: "2025-09-28", floors: "published floor",
});
const fromEntry = (entry: RawEntry): ComparisonEntity => ({
  slug: entry.card_path.split(/[\\/]/).pop()!.replace(/\.png$/, ""), name: entry.entity, sourceEntity: entry.entity,
  values: entry.key_numbers, percentiles: {}, floors: entry.floors, asOf: entry.as_of,
});

describe("pitchResultComparison", () => {
  it("preserves exact serialized percentages, zero, support, and date", () => {
    const result = pitchResultComparison(entity("team:CHC", { ball: 0, strike: 47.3, "in-play": 18.5 }, 21523), entity("team:CWS", { ball: 37.7, strike: 44.9, "in-play": 17.4 }, 23455))!;
    expect(result.family).toBe("team");
    expect(result.rows.map(row => row.a)).toEqual([{ value: 0, serialized: true }, { value: 47.3, serialized: true }, { value: 18.5, serialized: true }]);
    expect(result.entities).toMatchObject({ a: { nPitches: 21523, outcomeAvailable: true, floors: "published floor" }, b: { nPitches: 23455, outcomeAvailable: true, floors: "published floor" } });
    expect(result.sameAsOf).toBe(true);
    expect(result.note).toContain("pull's maximum game date");
  });

  it("keeps absent categories distinct and validates sides independently", () => {
    const result = pitchResultComparison(entity("pitch_type:PO", { ball: 100 }), entity("pitch_type:SC", undefined, Infinity))!;
    expect(result.rows[0]).toMatchObject({ a: { value: 100, serialized: true }, b: { value: null, serialized: false } });
    expect(result.rows[1].a).toEqual({ value: null, serialized: false });
    expect(result.entities).toMatchObject({ a: { outcomeAvailable: true }, b: { outcomeAvailable: false, nPitches: null } });
  });

  it("rejects invalid nested values without changing serialized status", () => {
    for (const invalid of [-1, 101, NaN, Infinity, "25", [], {}]) {
      const result = pitchResultComparison(entity("count:0-0", { ball: invalid }), entity("count:3-0", []))!;
      expect(result.rows[0]).toMatchObject({ a: { value: null, serialized: true }, b: { value: null, serialized: false } });
      expect(result.entities.b.outcomeAvailable).toBe(false);
    }
  });

  it("keeps valid outcome values available when pitch support is malformed", () => {
    for (const invalid of [1.5, null, "10", -1, Infinity]) {
      const result = pitchResultComparison(entity("team:CHC", { ball: 35 }, invalid), entity("team:CWS", { ball: 36 }, 0))!;
      expect(result.entities.a.nPitches).toBeNull();
      expect(result.entities.b.nPitches).toBe(0);
      expect(result.rows[0]).toMatchObject({ a: { value: 35, serialized: true }, b: { value: 36, serialized: true } });
    }
  });

  it("blocks mixed or unknown entity families", () => {
    const mix = { ball: 30, strike: 50, "in-play": 20 };
    expect(pitchResultComparison(entity("team:CHC", mix), entity("count:0-0", mix))).toBeNull();
    expect(pitchResultComparison(entity("other:CHC", mix), entity("other:CWS", mix))).toBeNull();
  });

  it("matches all 61 public rows and preserves rare omissions", () => {
    const manifest = JSON.parse(readFileSync(join(process.cwd(), "public/data/showcase/atlas_mlb_pitch_manifest.json"), "utf8")) as { entries: RawEntry[] };
    const entries = manifest.entries.map(fromEntry);
    expect(entries).toHaveLength(61);
    for (const item of entries) {
      const result = pitchResultComparison(item, item)!;
      expect(result).not.toBeNull();
      expect(result.entities.a).toMatchObject({ outcomeAvailable: true, nPitches: item.values.n_pitches, asOf: "2025-09-28" });
      for (const row of result.rows) {
        const source = item.values.outcome_mix_pct as Record<string, unknown>;
        const serialized = Object.prototype.hasOwnProperty.call(source, row.key);
        expect(row.a).toEqual({ value: serialized ? source[row.key] : null, serialized });
      }
    }
    const po = pitchResultComparison(entries.find(item => item.sourceEntity === "pitch_type:PO")!, entries.find(item => item.sourceEntity === "pitch_type:SC")!)!;
    expect(po.rows.find(row => row.key === "strike")).toMatchObject({ a: { value: null, serialized: false }, b: { value: null, serialized: false } });
    expect(po.rows.find(row => row.key === "in-play")?.a).toEqual({ value: null, serialized: false });
    const un = pitchResultComparison(entries.find(item => item.sourceEntity === "pitch_type:UN")!, entries.find(item => item.sourceEntity === "pitch_type:UN")!)!;
    expect(un.rows.find(row => row.key === "in-play")?.a).toEqual({ value: null, serialized: false });
  });
});
