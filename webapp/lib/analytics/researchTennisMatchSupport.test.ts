import { describe, expect, it } from "vitest";
import { buildTennisMatchSupportResearch, getTennisMatchSupportResearch, type TennisMatchSupportSource } from "./researchTennisMatchSupport";

const FLOOR = "clay_n>=25 AND hard_n>=25";
const entry = (name: unknown, clay: unknown, hard: unknown, other: Record<string, unknown> = {}) => ({
  player_name: name, clay_n: clay, hard_n: hard, clay_wr: 0.6, hard_wr: 0.4, clay_minus_hard: 0.2, ...other,
});
const combo = (key: "atp_career" | "atp_recent_form", top: unknown[], bottom: unknown[], floor = FLOOR) => ({
  status: "ok", source: `data/cache/intel_claims/tennis_surface_context_snapshot_${key}.parquet`,
  clay_hard_gap: { floor, n_qualifying: 100, most_clay_favoring: top, most_hard_favoring: bottom },
});
const source = (career: unknown[], recent: unknown[] = []): TennisMatchSupportSource => ({
  floors: { clay_hard_gap: FLOOR },
  combos: {
    atp_career: combo("atp_career", career, []),
    atp_recent_form: combo("atp_recent_form", recent, []),
  },
});

describe("tennis clay-hard match support", () => {
  it("preserves the public extremes in source order, windows, source paths, and published gap", () => {
    const analysis = getTennisMatchSupportResearch()[0];
    expect(analysis.id).toBe("tennis-clay-hard-match-support");
    expect(analysis.rows).toHaveLength(20);
    expect(analysis.scope).toContain("ATP career: 10 published extremes from 184 qualifiers; dated matches in the pooled 2015-2025 corpus");
    expect(analysis.scope).toContain("ATP recent form: 10 published extremes from 69 qualifiers; matches on or after 2023-01-01");
    expect(analysis.populationDefinition?.status).toBe("unpublished");
    expect(analysis.asOf).toBeUndefined();
    expect(analysis.rows[0].label).toBe("Luciano Darderi (career)");
    expect(analysis.rows[10].label).toBe("Luciano Darderi (recent form)");
    const mannarino = analysis.rows.find(row => row.label === "Adrian Mannarino (career)")!;
    expect(mannarino.id).toBe("tennis-clay-hard-atp_career-most_hard_favoring-3");
    expect(mannarino.values).toMatchObject({ clay_n: 59, hard_n: 386, clay_minus_hard: -0.2823, clay_wr: 0.2203, hard_wr: 0.5026 });
    expect(mannarino.values.smaller_surface_match_share).toBeCloseTo(59 / 445, 12);
    expect(mannarino.sourcePaths).toEqual([
      "combos.atp_career.clay_hard_gap.most_hard_favoring[3].player_name",
      "combos.atp_career.clay_hard_gap.most_hard_favoring[3].clay_minus_hard",
      "combos.atp_career.clay_hard_gap.most_hard_favoring[3].clay_wr",
      "combos.atp_career.clay_hard_gap.most_hard_favoring[3].hard_wr",
      "combos.atp_career.clay_hard_gap.most_hard_favoring[3].clay_n",
      "combos.atp_career.clay_hard_gap.most_hard_favoring[3].hard_n",
    ]);
    expect(mannarino.windows?.clay_n).toContain("2015-2025");
    expect(analysis.fields.map(field => [field.key, field.unit])).toEqual([
      ["smaller_surface_match_share", "percent"], ["clay_minus_hard", "pp"],
      ["clay_wr", "percent"], ["hard_wr", "percent"], ["clay_n", "number"], ["hard_n", "number"],
    ]);
  });

  it("keeps named sparse and duplicate rows but never fills missing operands with zero", () => {
    const analysis = buildTennisMatchSupportResearch(source([
      entry("Missing", null, 50, { clay_wr: null, clay_minus_hard: -0.1 }),
      entry("Below floor", 24, 50, { hard_wr: 2 }),
      entry("Zero", 0, 50, { clay_wr: 0, hard_wr: 0, clay_minus_hard: 0 }),
      entry("Unsafe sum", Number.MAX_SAFE_INTEGER - 25, 50, { clay_minus_hard: Infinity }),
      entry("Repeated", 25, 25, { clay_wr: 0.8, hard_wr: 0.7, clay_minus_hard: 0.2 }),
      entry("Repeated", 30, 40),
      entry("", 25, 25),
    ]))[0];
    expect(analysis.rows).toHaveLength(6);
    expect(analysis.rows.map(row => row.id)).toEqual([0, 1, 2, 3, 4, 5].map(index => `tennis-clay-hard-atp_career-most_clay_favoring-${index}`));
    expect(analysis.rows[0].values).toMatchObject({ clay_n: null, hard_n: 50, clay_wr: null, clay_minus_hard: -0.1, smaller_surface_match_share: null });
    expect(analysis.rows[1].values).toMatchObject({ clay_n: 24, hard_n: 50, hard_wr: null, smaller_surface_match_share: null });
    expect(analysis.rows[2].values).toMatchObject({ clay_n: 0, hard_n: 50, clay_wr: 0, hard_wr: 0, smaller_surface_match_share: null });
    expect(analysis.rows[3].values).toMatchObject({ clay_n: Number.MAX_SAFE_INTEGER - 25, hard_n: 50, clay_minus_hard: null, smaller_surface_match_share: null });
    expect(analysis.rows[4].values).toMatchObject({ clay_minus_hard: 0.2, smaller_surface_match_share: 0.5 });
    expect(analysis.rows[4].label).toBe("Repeated (career)");
    expect(analysis.rows[5].label).toBe("Repeated (career)");
    expect(analysis.rows[5].sourcePaths?.[0]).toBe("combos.atp_career.clay_hard_gap.most_clay_favoring[5].player_name");
  });

  it("withholds the balance when the source floor or window provenance is unverified", () => {
    const badFloor = source([entry("Floor", 25, 25)]);
    badFloor.floors = { clay_hard_gap: "clay_n>=20 AND hard_n>=20" };
    const floorAnalysis = buildTennisMatchSupportResearch(badFloor)[0];
    expect(floorAnalysis.rows[0].values.smaller_surface_match_share).toBeNull();
    const badWindow = source([entry("Window", 25, 25)]);
    badWindow.combos!.atp_career.source = "another-source";
    const windowAnalysis = buildTennisMatchSupportResearch(badWindow)[0];
    expect(windowAnalysis.rows).toEqual([]);
    expect(windowAnalysis.scope).toContain("source window unverified");
  });
});
