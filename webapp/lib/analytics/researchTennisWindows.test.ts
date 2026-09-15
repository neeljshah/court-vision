import { describe, expect, it } from "vitest";
import { buildTennisWindowResearch, getTennisWindowResearch, type TennisWindowAtlasEntry } from "./researchTennisWindows";

describe("tennis recent-versus-career research", () => {
  const analyses = getTennisWindowResearch();

  it("keeps surfaces separate with exact paired public coverage", () => {
    expect(analyses.map(item => [item.id, item.rows.length])).toEqual([
      ["tennis-hard-recent-career-shift", 113],
      ["tennis-clay-recent-career-shift", 72],
      ["tennis-grass-recent-career-shift", 3],
    ]);
    expect(new Set(analyses.flatMap(item => item.rows.map(row => row.label))).size).toBe(126);
    expect(analyses.every(item => item.scope.includes("independently clears") && item.scope.includes("This analysis includes ATP entries only"))).toBe(true);
  });

  it("preserves both operands and computes the signed difference", () => {
    const hard = analyses[0].rows.find(row => row.label === "Andy Murray (ATP)")!;
    expect(hard.values).toMatchObject({ career_rate: .6732, recent_rate: .4878 });
    expect(hard.values.recent_minus_career).toBeCloseTo(-.1854, 10);
    const clay = analyses[1].rows.find(row => row.label === "Daniil Medvedev (ATP)")!;
    expect(clay.values).toMatchObject({ career_rate: .5679, recent_rate: .7 });
    expect(clay.values.recent_minus_career).toBeCloseTo(.1321, 10);
  });

  it("uses honest units, window language, floors, dates, and sparse caveats", () => {
    for (const item of analyses) {
      expect(item.fields.map(field => [field.key, field.unit])).toEqual([
        ["recent_minus_career", "pp"], ["recent_rate", "percent"], ["career_rate", "percent"],
      ]);
      expect(item.formula).toContain("on or after 2023-01-01");
      expect(item.formula).toContain("documented as 2015-2025");
      expect(item.formula).toContain("100 *");
      expect(item.rows.every(row => row.note?.includes("exact match counts are not published"))).toBe(true);
      expect(item.asOf).toBeTruthy();
    }
    expect(analyses[2].status).toBe("Descriptive sparse subset");
    expect(analyses[2].caveat).toContain(`Only ${analyses[2].rows.length} players qualify`);
    expect(analyses.every(item => !/forecast performance\.$/.test(item.interpretation))).toBe(true);
  });

  it("fails closed on identity, floor, values, and partial dates while preserving zero", () => {
    const base = (entity: string, values: Record<string, unknown>, floors?: string, as_of = "2026-07-19T00:00:00Z"): TennisWindowAtlasEntry => ({ entity, key_numbers: values, floors, as_of, status: "partial" });
    const floor = "hard_wr: hard_n>=30 | clay_wr: clay_n>=30 (per metric, career+recent_form independently; below floor shows n/a)";
    const valid = base("Valid (ATP)", { hard_wr_career: 0, hard_wr_recent: 0 }, floor);
    const atlas = { entries: [
      valid,
      base(" (ATP)", { hard_wr_career: .5, hard_wr_recent: .6 }, floor),
      base("   (ATP)", { hard_wr_career: .5, hard_wr_recent: .6 }, floor),
      base("Wrong tour (WTA)", { hard_wr_career: .5, hard_wr_recent: .6 }, floor),
      base("No floor (ATP)", { hard_wr_career: .5, hard_wr_recent: .6 }),
      base("Prefix floor (ATP)", { hard_wr_career: .5, hard_wr_recent: .6 }, floor.replace("hard_n>=30", "hard_n>=300")),
      base("Missing (ATP)", { hard_wr_career: null, hard_wr_recent: .6 }, floor),
      base("Invalid (ATP)", { hard_wr_career: .5, hard_wr_recent: 2 }, floor),
    ] };
    const hard = buildTennisWindowResearch(atlas)[0];
    expect(hard.rows).toHaveLength(1);
    expect(hard.rows[0].values).toEqual({ recent_minus_career: 0, recent_rate: 0, career_rate: 0 });
    expect(hard.rows[0].note).toContain(`Source floor: ${floor}`);
    const partialDate = buildTennisWindowResearch({ entries: [valid, { ...valid, entity: "Undated (ATP)", as_of: undefined }] })[0];
    expect(partialDate.rows).toHaveLength(2);
    expect(partialDate.asOf).toBeUndefined();
  });
});
