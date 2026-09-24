import { describe, expect, it } from "vitest";
import {
  buildSoccerFormGapResearch,
  getSoccerFormGapResearch,
  type SoccerFormGapEntry,
} from "./researchSoccerFormGap";

const FLOOR = "ppg_l10: n_prior>=10 | ppg_home_l10: n_prior_home>=10 | ppg_away_l10: n_prior_away>=10 (window=trailing10_asof_corpus_end; below floor shows n/a)";
const entry = (entity: unknown, home: unknown, away: unknown, floors: unknown = FLOOR): SoccerFormGapEntry => ({
  entity, key_numbers: { ppg_home_l10: home, ppg_away_l10: away }, floors, as_of: "2026-07-18T17:21:08.108324+00:00",
});

describe("soccer home-versus-away trailing form", () => {
  it("covers the public atlas and preserves example operands", () => {
    const analysis = getSoccerFormGapResearch()[0];
    expect(analysis).toMatchObject({ id: "soccer-home-away-trailing-form-gap", title: "Soccer form: home versus away", source: "atlas_soccer_manifest" });
    expect(analysis.populationDefinition).toEqual({
      status: "unpublished",
      reason: "The source pools six divisions but does not publish each team's league or match dates; a comparable population cannot be verified.",
    });
    expect(analysis.rows).toHaveLength(187);
    expect(analysis.rows.slice(0, 3).map(row => row.label)).toEqual(["Ajaccio", "Ajaccio GFCO", "Alaves"]);
    expect(analysis.fields.map(field => field.key)).toEqual(["home_minus_away_ppg", "ppg_home_l10", "ppg_away_l10"]);
    expect(analysis.rows.find(row => row.label === "Brest")?.values).toEqual({ home_minus_away_ppg: 1.3, ppg_home_l10: 1.9, ppg_away_l10: 0.6 });
    expect(analysis.rows.find(row => row.label === "Barcelona")?.values).toEqual({ home_minus_away_ppg: 0.9, ppg_home_l10: 3, ppg_away_l10: 2.1 });
    expect(analysis.rows.find(row => row.label === "Bologna")?.values).toEqual({ home_minus_away_ppg: -1.5, ppg_home_l10: 0.7, ppg_away_l10: 2.2 });
  });

  it("provides operand provenance and honest window semantics", () => {
    const analysis = getSoccerFormGapResearch()[0];
    expect(analysis.rows.every(row => JSON.stringify(row.sourcePaths) === JSON.stringify([
      "entries[].key_numbers.ppg_home_l10", "entries[].key_numbers.ppg_away_l10",
    ]))).toBe(true);
    expect(analysis.rows.every(row => row.note?.includes(`Team: ${row.label}. Source floors:`))).toBe(true);
    expect(analysis.scope).toContain("independently clears its 10-match venue floor");
    expect(analysis.scope).toContain("Claim computation timestamp:");
    expect(analysis.scope).toContain("Public artifact generation timestamp:");
    expect(analysis.asOf).toBeUndefined();
    expect(analysis.caveat).toContain("can span different dates");
    expect(analysis.caveat).toContain("does not publish team-specific match dates");
    expect(`${analysis.title} ${analysis.description} ${analysis.interpretation}`.toLowerCase()).not.toMatch(/home advantage|venue effect|predict|causal/);
  });

  it("uses stable normalized labels and rejects ambiguous duplicates", () => {
    const unique = entry("Real Sociedad", 2, 1);
    const duplicateA = entry("Atletico-MG", 2, 1);
    const duplicateB = entry("Atletico MG", 1, 2);
    const rows = buildSoccerFormGapResearch({ entries: [duplicateB, unique, duplicateA] })[0].rows;
    expect(rows.map(row => [row.id, row.label])).toEqual([["soccer-form-gap-real-sociedad", "Real Sociedad"]]);
    const reordered = buildSoccerFormGapResearch({ entries: [unique] })[0].rows[0];
    expect(reordered.id).toBe("soccer-form-gap-real-sociedad");
  });

  it("keeps valid rows in source order even when their gaps differ or another entry is rejected", () => {
    const rows = buildSoccerFormGapResearch({ entries: [
      entry("Low", 0, 2), entry("Rejected", null, 1), entry("High", 3, 1), entry("Even", 1, 1),
    ] })[0].rows;
    expect(rows.map(row => [row.label, row.values.home_minus_away_ppg])).toEqual([
      ["Low", -2], ["High", 2], ["Even", 0],
    ]);
    expect(rows.map(row => row.sourcePaths)).toEqual(Array(3).fill([
      "entries[].key_numbers.ppg_home_l10", "entries[].key_numbers.ppg_away_l10",
    ]));
  });

  it("fails closed on missing, nonfinite, out-of-range, or unfloored inputs", () => {
    const malformed = [
      entry("Missing", null, 1), entry("Infinite", Infinity, 1), entry("Negative", -0.1, 1), entry("Too high", 3.1, 1),
      entry("   ", 1, 1), entry("Bad home floor", 1, 1, FLOOR.replace("n_prior_home>=10", "n_prior_home>=100")),
      entry("Bad away floor", 1, 1, FLOOR.replace("n_prior_away>=10", "n_prior_away>=10.5")),
      entry("Wrong window", 1, 1, FLOOR.replace("trailing10_asof_corpus_end", "trailing20_asof_corpus_end")),
      entry("Prefixed window", 1, 1, FLOOR.replace("window=trailing10", "notwindow=trailing10")),
      entry("No floor", 1, 1, null),
    ];
    expect(buildSoccerFormGapResearch({ entries: malformed })[0].rows).toEqual([]);
    expect(buildSoccerFormGapResearch({})[0].rows).toEqual([]);
    expect(buildSoccerFormGapResearch({ entries: [null, "bad"] })[0].rows).toEqual([]);
  });

  it("retains zero and bounded negative values without floating artifacts", () => {
    const rows = buildSoccerFormGapResearch({ entries: [
      entry("Zero", 0, 0), entry("Decimal", 0.3, 0.2), entry("Lower bound", 0, 3), entry("Upper bound", 3, 0),
    ] })[0].rows;
    expect(rows.find(row => row.label === "Zero")?.values.home_minus_away_ppg).toBe(0);
    expect(rows.find(row => row.label === "Decimal")?.values.home_minus_away_ppg).toBe(0.1);
    expect(rows.find(row => row.label === "Lower bound")?.values.home_minus_away_ppg).toBe(-3);
    expect(rows.find(row => row.label === "Upper bound")?.values.home_minus_away_ppg).toBe(3);
  });

  it("accepts the public zoned timestamp but suppresses malformed or mixed dates", () => {
    const publicAnalysis = getSoccerFormGapResearch()[0];
    expect(publicAnalysis.scope).toContain("Claim computation timestamp: 2026-07-18T17:21:08.108324+00:00");
    const valid = entry("Valid date", 2, 1);
    const bare = { ...entry("Bare date", 2, 1), as_of: "0" };
    const mixed = buildSoccerFormGapResearch({ generated_at: "0", entries: [valid, bare] })[0];
    expect(mixed.scope).toContain("Claim computation timestamp is unavailable or inconsistent.");
    expect(mixed.scope).not.toContain("Public artifact generation timestamp:");
    const rollover = buildSoccerFormGapResearch({ entries: [{ ...valid, as_of: "2026-02-30T00:00:00Z" }] })[0];
    expect(rollover.scope).toContain("Claim computation timestamp is unavailable or inconsistent.");
  });
});
