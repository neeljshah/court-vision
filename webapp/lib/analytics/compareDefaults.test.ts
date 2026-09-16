import { describe, expect, it } from "vitest";
import { marqueePair, nonNullMeasurementCount } from "./compareDefaults";
import type { ComparisonEntity } from "./comparisonData";

function entity(slug: string, values: Record<string, unknown>): ComparisonEntity {
  return { slug, name: slug, values, percentiles: {} };
}

describe("comparison marquee defaults", () => {
  it("selects the two entities with the most non-null published fields", () => {
    const entries = [entity("thin", { a: 1 }), entity("full_a", { a: 1, b: 2 }), entity("full_b", { a: 1, b: 2 })];
    expect(nonNullMeasurementCount(entity("partial", { a: 1, b: null, c: undefined }))).toBe(1);
    expect(marqueePair("soccer", entries)).toEqual(["full_a", "full_b"]);
  });

  it("uses only an existing preferred slug to break a coverage tie", () => {
    const entries = [entity("lebron_james", { a: 1, b: 2 }), entity("nikola_jokic", { a: 1, b: 2 }), entity("giannis_antetokounmpo", { a: 1, b: 2 })];
    expect(marqueePair("nba_players", entries)).toEqual(["nikola_jokic", "giannis_antetokounmpo"]);
  });

  it("does not return a pair for an incomplete pack", () => {
    expect(marqueePair("tennis", [entity("jannik_sinner_atp", { a: 1 })])).toBeUndefined();
  });
});
