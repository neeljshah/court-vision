import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { buildTennisGrassSupportResearch, getTennisGrassSupportResearch, type TennisGrassSupportSource } from "./researchTennisGrassSupport";

const FLOOR = "grass_n>=15";
const entry = (name: unknown, grassN: unknown, other: Record<string, unknown> = {}) => ({
  player_name: name, grass_n: grassN, grass_adapt: 0.2, grass_wr: 0.6, ov_wr: 0.4, ...other,
});
const combo = (key: "atp_career" | "atp_recent_form", most: unknown[], least: unknown[], floor = FLOOR) => ({
  status: "ok", source: `data/cache/intel_claims/tennis_surface_context_snapshot_${key}.parquet`,
  n_players_in_snapshot: 100,
  grass_adaptability: { floor, n_qualifying: 50, most_adaptive: most, least_adaptive: least },
});
const source = (career: unknown[], recent: unknown[] = []): TennisGrassSupportSource => ({
  floors: { grass_adaptability: FLOOR },
  combos: {
    atp_career: combo("atp_career", career, []),
    atp_recent_form: combo("atp_recent_form", recent, []),
  },
});

describe("tennis grass match support", () => {
  it("preserves the exact public ATP tails, source paths, windows, counts, and units", () => {
    const analysis = getTennisGrassSupportResearch()[0];
    expect(analysis.id).toBe("tennis-grass-overall-match-support");
    expect(analysis.title).toBe("Tennis grass win rates and match support");
    expect(analysis.question).toBe("How many grass matches support each published grass-versus-overall gap?");
    expect(analysis.description).toContain("describes only the grass win rate");
    expect(analysis.rows).toHaveLength(20);
    expect(analysis.rows.map(row => row.label)).toEqual([
      "Ramkumar Ramanathan (career)", "Florian Mayer (career)", "Billy Harris (career)",
      "Christopher Eubanks (career)", "Nicolas Mahut (career)", "Pablo Carreno Busta (career)",
      "Yoshihito Nishioka (career)", "Roberto Carballes Baena (career)", "Albert Ramos (career)",
      "Dusan Lajovic (career)", "Billy Harris (recent form)", "Alexander Bublik (recent form)",
      "Tallon Griekspoor (recent form)", "Christopher Eubanks (recent form)",
      "Roberto Bautista Agut (recent form)", "Stefanos Tsitsipas (recent form)",
      "Ugo Humbert (recent form)", "Ben Shelton (recent form)", "Miomir Kecmanovic (recent form)",
      "Cameron Norrie (recent form)",
    ]);
    expect(analysis.scope).toContain("ATP career: 10 published extremes from 153 qualifying rows among 1,261 snapshot player rows; dated matches in the pooled 2015-2025 corpus");
    expect(analysis.scope).toContain("ATP recent form: 10 published extremes from 44 qualifying rows among 663 snapshot player rows; matches on or after 2023-01-01");
    expect(analysis.populationDefinition?.status).toBe("unpublished");
    expect(analysis.asOf).toBeUndefined();
    const first = analysis.rows[0];
    expect(first.id).toBe("tennis-grass-atp_career-most_adaptive-0");
    expect(first.values).toEqual({ one_result_step: 1 / 16, grass_adapt: 0.2941, grass_wr: 0.6875, ov_wr: 0.3934, grass_n: 16 });
    expect(first.sourcePaths).toEqual([
      "combos.atp_career.grass_adaptability.most_adaptive[0].player_name",
      "combos.atp_career.grass_adaptability.most_adaptive[0].grass_adapt",
      "combos.atp_career.grass_adaptability.most_adaptive[0].grass_wr",
      "combos.atp_career.grass_adaptability.most_adaptive[0].ov_wr",
      "combos.atp_career.grass_adaptability.most_adaptive[0].grass_n",
    ]);
    expect(first.windows?.grass_n).toContain("2015-2025");
    expect(analysis.rows[15].id).toBe("tennis-grass-atp_recent_form-least_adaptive-0");
    expect(analysis.rows[15].values.one_result_step).toBeCloseTo(1 / 15, 12);
    expect(analysis.rows[15].windows?.grass_n).toContain("2023-01-01");
    expect(analysis.fields.map(field => [field.key, field.unit])).toEqual([
      ["one_result_step", "pp"], ["grass_adapt", "pp"], ["grass_wr", "percent"],
      ["ov_wr", "percent"], ["grass_n", "number"],
    ]);
    expect(analysis.formula).toContain("100 / grass_n percentage points");
    expect(analysis.bindings).toEqual([{ operand: "grass_n", sourcePath: "combos.*.grass_adaptability.*[].grass_n", valueKey: "grass_n", label: "Published grass matches" }]);
    expect(analysis.caveat).toContain("Overall win rate includes grass");
  });

  it("matches every public snapshot selection value and source path in source order", () => {
    const raw = JSON.parse(readFileSync(join(process.cwd(), "public/data/showcase/tennis_surface_transfer.json"), "utf8")) as {
      combos: Record<string, { grass_adaptability: Record<string, unknown> }>;
    };
    const analysis = getTennisGrassSupportResearch()[0];
    let cursor = 0;
    for (const key of ["atp_career", "atp_recent_form"] as const) {
      for (const selection of ["most_adaptive", "least_adaptive"] as const) {
        const entries = raw.combos[key].grass_adaptability[selection] as Array<{
          player_name: string; grass_adapt: number; grass_wr: number; ov_wr: number; grass_n: number;
        }>;
        for (const [index, entry] of entries.entries()) {
          const row = analysis.rows[cursor++];
          const path = `combos.${key}.grass_adaptability.${selection}[${index}]`;
          expect(row.id).toBe(`tennis-grass-${key}-${selection}-${index}`);
          expect(row.label).toBe(`${entry.player_name} (${key === "atp_career" ? "career" : "recent form"})`);
          expect(row.values).toEqual({
            one_result_step: 1 / entry.grass_n,
            grass_adapt: entry.grass_adapt,
            grass_wr: entry.grass_wr,
            ov_wr: entry.ov_wr,
            grass_n: entry.grass_n,
          });
          expect(row.sourcePaths).toEqual(["player_name", "grass_adapt", "grass_wr", "ov_wr", "grass_n"].map(field => `${path}.${field}`));
          expect(row.windows?.grass_n).toContain(key === "atp_career" ? "2015-2025" : "2023-01-01");
        }
      }
    }
    expect(cursor).toBe(20);
    expect(cursor).toBe(analysis.rows.length);
  });

  it("retains sparse and repeated names with source-index IDs while validating every number", () => {
    const analysis = buildTennisGrassSupportResearch(source([
      entry("Missing", null, { grass_adapt: null }),
      entry("Below floor", 14, { grass_wr: -0.1 }),
      entry("Zero", 0, { grass_adapt: 0, grass_wr: 0, ov_wr: 0 }),
      entry("Negative", -1, { ov_wr: 2 }),
      entry("Fractional", 15.5, { grass_adapt: Infinity }),
      entry("Unsafe", Number.MAX_SAFE_INTEGER + 1),
      entry("Repeated", 15, { grass_adapt: 0.2001, grass_wr: 0.6, ov_wr: 0.4 }),
      entry("Repeated", 16, { grass_adapt: -0.2 }),
      entry("", 15),
    ]))[0];
    expect(analysis.rows).toHaveLength(8);
    expect(analysis.rows.map(row => row.id)).toEqual(Array.from({ length: 8 }, (_, index) => `tennis-grass-atp_career-most_adaptive-${index}`));
    expect(analysis.rows[0].values).toMatchObject({ grass_n: null, grass_adapt: null, one_result_step: null });
    expect(analysis.rows[1].values).toMatchObject({ grass_n: 14, grass_wr: null, one_result_step: null });
    expect(analysis.rows[2].values).toMatchObject({ grass_n: 0, grass_adapt: 0, grass_wr: 0, ov_wr: 0, one_result_step: null });
    expect(analysis.rows[3].values).toMatchObject({ grass_n: null, ov_wr: null, one_result_step: null });
    expect(analysis.rows[4].values).toMatchObject({ grass_n: null, grass_adapt: null, one_result_step: null });
    expect(analysis.rows[5].values).toMatchObject({ grass_n: null, one_result_step: null });
    expect(analysis.rows[6].values).toMatchObject({ grass_adapt: 0.2001, one_result_step: 1 / 15 });
    expect(analysis.rows[6].label).toBe("Repeated (career)");
    expect(analysis.rows[7].label).toBe("Repeated (career)");
    expect(analysis.rows[7].sourcePaths?.[0]).toBe("combos.atp_career.grass_adaptability.most_adaptive[7].player_name");
  });

  it("withholds the step when either floor fails and all rows when window provenance fails", () => {
    const topFloor = source([entry("Top floor", 15)]);
    topFloor.floors = { grass_adaptability: "grass_n>=10" };
    expect(buildTennisGrassSupportResearch(topFloor)[0].rows[0].values.one_result_step).toBeNull();
    const groupFloor = source([entry("Group floor", 15)]);
    groupFloor.combos!.atp_career.grass_adaptability!.floor = "grass_n>=10";
    expect(buildTennisGrassSupportResearch(groupFloor)[0].rows[0].values.one_result_step).toBeNull();
    const badWindow = source([entry("Window", 15)]);
    badWindow.combos!.atp_career.source = "another-source";
    const unverified = buildTennisGrassSupportResearch(badWindow)[0];
    expect(unverified.rows).toEqual([]);
    expect(unverified.scope).toContain("source window unverified");
    expect(unverified.scope.split(". ATP recent form:")[0]).not.toContain("snapshot player rows");
  });

  it("keeps source row counts without inventing missing or inconsistent denominators", () => {
    for (const snapshotPlayers of [undefined, null, -1, 1.5, "100", Number.MAX_SAFE_INTEGER + 1, 49]) {
      const fixture = source([entry("Example", 15)]);
      fixture.combos!.atp_career.n_players_in_snapshot = snapshotPlayers;
      const scope = buildTennisGrassSupportResearch(fixture)[0].scope;
      expect(scope).toContain("ATP career: 1 published extremes from 50 qualifying rows");
      expect(scope.split(". ATP recent form:")[0]).not.toContain("snapshot player rows");
    }
    const missing = source([entry("Example", 15)]);
    missing.combos!.atp_career.grass_adaptability!.n_qualifying = null;
    expect(buildTennisGrassSupportResearch(missing)[0].scope).toContain("ATP career: 1 published extremes (qualifier count unavailable)");
    const inconsistent = source([entry("Example", 15), entry("Another", 15)]);
    inconsistent.combos!.atp_career.grass_adaptability!.n_qualifying = 1;
    const scope = buildTennisGrassSupportResearch(inconsistent)[0].scope;
    expect(scope).toContain("from 1 qualifying rows (source row counts inconsistent; snapshot denominator withheld)");
    const empty = source([]);
    empty.combos!.atp_career.grass_adaptability!.n_qualifying = 0;
    empty.combos!.atp_career.n_players_in_snapshot = 0;
    expect(buildTennisGrassSupportResearch(empty)[0].scope).toContain("ATP career: 0 published extremes from 0 qualifying rows among 0 snapshot player rows");
  });

  it("distinguishes missing selection arrays from genuinely empty arrays", () => {
    const missing = source([entry("Kept", 15)]);
    missing.combos!.atp_career.grass_adaptability!.least_adaptive = undefined;
    const partial = buildTennisGrassSupportResearch(missing)[0];
    expect(partial.rows.map(row => row.label)).toEqual(["Kept (career)"]);
    expect(partial.scope).toContain("ATP career: published selection count unavailable from 50 qualifying rows");
    expect(partial.scope).not.toContain("ATP career: 0 published extremes");
    const invalid = source([]);
    invalid.combos!.atp_career.grass_adaptability!.most_adaptive = { length: 0 };
    expect(buildTennisGrassSupportResearch(invalid)[0].scope).toContain("ATP career: published selection count unavailable");
    const empty = source([]);
    expect(buildTennisGrassSupportResearch(empty)[0].scope).toContain("ATP career: 0 published extremes from 50 qualifying rows");
  });

  it("uses a single selection length when assessing potentially overlapping tails", () => {
    const fixture = source(Array.from({ length: 5 }, (_, index) => entry(`Name ${index}`, 15)));
    fixture.combos!.atp_career.grass_adaptability!.least_adaptive = Array.from({ length: 5 }, (_, index) => entry(`Name ${index}`, 15));
    fixture.combos!.atp_career.grass_adaptability!.n_qualifying = 5;
    const analysis = buildTennisGrassSupportResearch(fixture)[0];
    expect(analysis.rows).toHaveLength(10);
    expect(analysis.scope).toContain("ATP career: 10 published extremes from 5 qualifying rows among 100 snapshot player rows");
    expect(analysis.scope).not.toContain("source row counts inconsistent");
  });
});
