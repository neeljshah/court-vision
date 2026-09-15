import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import type { ComparisonEntity, RawEntry } from "./comparisonData";
import { soccerVenueComparison } from "./soccerVenueComparison";

const FLOOR = "ppg_home_l10: n_prior_home>=10 | ppg_away_l10: n_prior_away>=10 | clean_sheet_rate_home: n_prior_home>=10 | clean_sheet_rate_away: n_prior_away>=10 (window=trailing10_asof_corpus_end; a metric a team doesn't clear shows n/a, never fabricated)";
const entity = (name: string, values: Record<string, unknown>, floors = FLOOR, asOf = "2026-07-18T17:21:08.108324+00:00"): ComparisonEntity => ({
  slug: name.toLowerCase(), name, sourceEntity: name, values, percentiles: {}, floors, asOf, status: "complete",
});
const fromEntry = (entry: RawEntry): ComparisonEntity => ({
  slug: entry.card_path.split(/[\\/]/).pop()!.replace(/\.png$/, ""), name: entry.entity, sourceEntity: entry.entity,
  values: entry.key_numbers, percentiles: {}, floors: entry.floors, asOf: entry.as_of, status: entry.status,
});

describe("soccerVenueComparison", () => {
  it("preserves venue values and derives signed gaps in their stated units", () => {
    const a = entity("Alpha", { ppg_home_l10: 0, ppg_away_l10: 1.5, clean_sheet_rate_home: .4, clean_sheet_rate_away: .1 });
    const b = entity("Beta", { ppg_home_l10: 2.2, ppg_away_l10: 1.2, clean_sheet_rate_home: 0, clean_sheet_rate_away: .3 });
    const result = soccerVenueComparison(a, b)!;
    expect(result.rows).toEqual([
      { key: "ppg", label: "Points per game", unit: "points_per_game", a: { home: 0, away: 1.5, gap: -1.5, homeAvailability: "published", awayAvailability: "published" }, b: { home: 2.2, away: 1.2, gap: 1, homeAvailability: "published", awayAvailability: "published" } },
      { key: "clean_sheet_rate", label: "Clean-sheet rate", unit: "percentage_points", a: { home: .4, away: .1, gap: 30, homeAvailability: "published", awayAvailability: "published" }, b: { home: 0, away: .3, gap: -30, homeAvailability: "published", awayAvailability: "published" } },
    ]);
    expect(result.entities.a).toMatchObject({ sourceEntity: "Alpha", floors: FLOOR, status: "complete", asOf: a.asOf, sampleCounts: { home: null, away: null } });
  });

  it("rounds derived gaps to published measurement precision", () => {
    const result = soccerVenueComparison(entity("Alpha", { ppg_home_l10: 3, ppg_away_l10: 2.1, clean_sheet_rate_home: .6, clean_sheet_rate_away: .1 }), entity("Beta", {}))!;
    expect(result.rows[0].a.gap).toBe(.9);
    expect(result.rows[1].a.gap).toBe(50);
    expect(result.note).toContain("claim-computation timestamp, not a match cutoff");
  });

  it("keeps missing and malformed values unavailable without deriving a gap", () => {
    const a = entity("Alpha", { ppg_home_l10: 3.1, ppg_away_l10: 1, clean_sheet_rate_home: NaN, clean_sheet_rate_away: 0 });
    const b = entity("Beta", { ppg_home_l10: "2", ppg_away_l10: Infinity, clean_sheet_rate_home: -.1, clean_sheet_rate_away: 1.1 });
    const result = soccerVenueComparison(a, b)!;
    expect(result.rows[0].a).toEqual({ home: null, away: 1, gap: null, homeAvailability: "invalid", awayAvailability: "published" });
    expect(result.rows[0].b).toEqual({ home: null, away: null, gap: null, homeAvailability: "invalid", awayAvailability: "invalid" });
    expect(result.rows[1].a).toEqual({ home: null, away: 0, gap: null, homeAvailability: "invalid", awayAvailability: "published" });
    expect(result.rows[1].b).toEqual({ home: null, away: null, gap: null, homeAvailability: "invalid", awayAvailability: "invalid" });
  });

  it("distinguishes missing source values from present invalid values", () => {
    const result = soccerVenueComparison(entity("Alpha", { ppg_home_l10: null, ppg_away_l10: "1" }), entity("Beta", {}))!;
    expect(result.rows[0].a).toMatchObject({ home: null, away: null, homeAvailability: "missing", awayAvailability: "invalid" });
    expect(result.rows[0].b).toMatchObject({ home: null, away: null, homeAvailability: "missing", awayAvailability: "missing" });
  });

  it("rejects missing identity or mismatched source window and date", () => {
    const values = { ppg_home_l10: 2, ppg_away_l10: 1 };
    const a = entity("Alpha", values);
    expect(soccerVenueComparison({ ...a, sourceEntity: undefined }, entity("Beta", values))).toBeNull();
    expect(soccerVenueComparison(a, entity("Beta", values, "window=other"))).toBeNull();
    expect(soccerVenueComparison(a, entity("Beta", values, "window=trailing10_asof_corpus_end_wrong;"))).toBeNull();
    expect(soccerVenueComparison(a, entity("Beta", values, FLOOR, "2026-07-17"))).toBeNull();
  });

  it("validates all 187 published records without inventing sample counts", () => {
    const manifest = JSON.parse(readFileSync(join(process.cwd(), "public/data/showcase/atlas_soccer_manifest.json"), "utf8")) as { generated_at: string; entries: RawEntry[] };
    const entries = manifest.entries.map(fromEntry);
    expect(entries).toHaveLength(187);
    expect(manifest.generated_at.slice(0, 10)).toBe("2026-07-23");
    for (const item of entries) {
      const result = soccerVenueComparison(item, item)!;
      expect(result).not.toBeNull();
      expect(result.entities.a.sampleCounts).toEqual({ home: null, away: null });
      expect(result.entities.a.asOf.slice(0, 10)).toBe("2026-07-18");
      expect(result.rows[0].a.home).toBe(item.values.ppg_home_l10);
      expect(result.rows[0].a.away).toBe(item.values.ppg_away_l10);
      expect(result.rows[1].a.home).toBe(item.values.clean_sheet_rate_home);
      expect(result.rows[1].a.away).toBe(item.values.clean_sheet_rate_away);
    }
  });
});
