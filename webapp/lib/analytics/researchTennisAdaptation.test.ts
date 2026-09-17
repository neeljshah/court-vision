import { describe, expect, it } from "vitest";
import { buildTennisAdaptationResearch, getTennisAdaptationResearch, type TennisAdaptationEntry } from "./researchTennisAdaptation";

describe("tennis surface-gap window research", () => {
  const analyses = getTennisAdaptationResearch();

  it("matches the independently qualified ATP public coverage", () => {
    expect(analyses.map(item => [item.id, item.rows.length])).toEqual([
      ["tennis-clay-gap-window-shift", 69],
      ["tennis-grass-gap-window-shift", 44],
    ]);
    expect(analyses.every(item => item.source === "atlas_tennis_manifest" && item.scope.includes("ATP players"))).toBe(true);
  });

  it("preserves rounded operands and computes signed shifts", () => {
    const zverev = analyses[0].rows.find(row => row.label === "Alexander Zverev (ATP)")!;
    expect(zverev.values).toMatchObject({ recent_gap: .0598, career_gap: .056 });
    expect(zverev.values.recent_minus_career).toBeCloseTo(.0038, 10);
    const djokovic = analyses[1].rows.find(row => row.label === "Novak Djokovic (ATP)")!;
    expect(djokovic.values).toMatchObject({ recent_gap: .0239, career_gap: .0591 });
    expect(djokovic.values.recent_minus_career).toBeCloseTo(-.0352, 10);
  });

  it("states units, definitions, floors, overlap, provenance, and limitations", () => {
    for (const item of analyses) {
      expect(item.fields.map(field => [field.key, field.unit])).toEqual([
        ["recent_minus_career", "pp"], ["recent_gap", "pp"], ["career_gap", "pp"],
      ]);
      expect(item.fields.map(field => field.label)).toEqual(["Recent minus corpus", "Recent gap", "Corpus gap"]);
      expect(item.description).toContain("available 2015-2025");
      expect(item.description).toContain("on or after 2023-01-01");
      expect(item.scope).toContain("available 2015-2025");
      expect(item.scope).toContain("on or after 2023-01-01");
      expect(item.formula).toMatch(/^displayed shift \(pp\) = 100 \* \(recent_gap - career_gap\)/);
      expect(item.caveat).toContain("overlap");
      expect(item.caveat).toContain("Exact match counts");
      expect(item.caveat).toContain("source-rounded");
      expect(item.caveat).toContain("claim-computation timestamp");
      expect(item.asOf).toBe("2026-07-19T03:41:37.066640+00:00");
      expect(item.references[0].url).toContain("tennis_surface_context_claims.py");
      expect(item.rows.every(row => row.note?.includes("qualify independently"))).toBe(true);
      expect(item.rows.every(row => row.sourcePaths?.length === 2)).toBe(true);
    }
    expect(analyses[1].description).toContain("overall includes grass");
  });

  it("fails closed while preserving valid zero gaps", () => {
    const floor = "clay_minus_hard: clay_n>=25 & hard_n>=25 | grass_adapt: grass_n>=15 (per metric, career+recent_form independently; below floor shows n/a)";
    const entry = (entity: string, values: Record<string, unknown>, status = "partial (2/10 metrics)", as_of: string | undefined = "2026-07-19T00:00:00Z"): TennisAdaptationEntry =>
      ({ entity, key_numbers: values, floors: floor, status, as_of });
    const zero = entry("Zero (ATP)", { clay_minus_hard_career: 0, clay_minus_hard_recent: 0 });
    const duplicate = entry("Duplicate (ATP)", { clay_minus_hard_career: .1, clay_minus_hard_recent: .2 });
    const clay = buildTennisAdaptationResearch({ entries: [
      zero, duplicate, { ...duplicate },
      entry("Wrong tour (WTA)", { clay_minus_hard_career: .1, clay_minus_hard_recent: .2 }),
      entry("Bad status (ATP)", { clay_minus_hard_career: .1, clay_minus_hard_recent: .2 }, "ready"),
      entry("Out of range (ATP)", { clay_minus_hard_career: -1.01, clay_minus_hard_recent: .2 }),
      entry("NaN (ATP)", { clay_minus_hard_career: Number.NaN, clay_minus_hard_recent: .2 }),
      entry("Infinity (ATP)", { clay_minus_hard_career: Number.POSITIVE_INFINITY, clay_minus_hard_recent: .2 }),
      entry("String (ATP)", { clay_minus_hard_career: "0.1", clay_minus_hard_recent: .2 }),
      entry("Missing (ATP)", { clay_minus_hard_career: null, clay_minus_hard_recent: .2 }),
      { ...entry("Wrong floor (ATP)", { clay_minus_hard_career: .1, clay_minus_hard_recent: .2 }), floors: floor.replace("clay_n>=25", "clay_n>=250") },
      { ...entry("Contradictory floor (ATP)", { clay_minus_hard_career: .1, clay_minus_hard_recent: .2 }), floors: floor.replace("clay_n>=25 & hard_n>=25", "clay_n>=25 & hard_n>=25 but waived") },
    ] })[0];
    expect(clay.rows).toHaveLength(1);
    expect(clay.rows[0].values).toEqual({ recent_minus_career: 0, recent_gap: 0, career_gap: 0 });
    expect(clay.asOf).toBe("2026-07-19T00:00:00Z");
    const undated = { ...entry("Other (ATP)", { clay_minus_hard_career: .1, clay_minus_hard_recent: .2 }, "complete"), as_of: undefined };
    expect(buildTennisAdaptationResearch({ entries: [zero, undated] })[0].asOf).toBeUndefined();

    const grassValues = { grass_adapt_career: 0, grass_adapt_recent: 0 };
    const malformedGrass = { ...entry("Grass (ATP)", grassValues), floors: floor.replace("grass_n>=15", "grass_n>=150") };
    expect(buildTennisAdaptationResearch({ entries: [malformedGrass] })[1].rows).toHaveLength(0);
  });
});
