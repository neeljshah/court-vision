import { describe, expect, it } from "vitest";
import { buildSoccerScoringResearch, getSoccerScoringResearch, type SoccerScoringEntry } from "./researchSoccerScoring";

const FLOOR = "gf_l10: n_prior>=10 | ga_l10: n_prior>=10 | gd_l10: n_prior>=10 | clean_sheet_rate_l10: n_prior>=10 (window=trailing10_asof_corpus_end; below floor shows n/a)";
const entry = (entity: unknown, gf: unknown, ga: unknown, gd: unknown, floors: unknown = FLOOR, cs: unknown = 0.3): SoccerScoringEntry => ({
  entity, key_numbers: { gf_l10: gf, ga_l10: ga, gd_l10: gd, clean_sheet_rate_l10: cs }, floors, as_of: "2026-07-18T17:21:08.108324+00:00",
});
const row = (analysis: ReturnType<typeof buildSoccerScoringResearch>, label: string) => analysis.rows.find(item => item.label === label)!;

describe("soccer trailing attack and defense", () => {
  it("covers the real snapshot with published values and provenance", () => {
    const analysis = getSoccerScoringResearch();
    expect(analysis).toMatchObject({ id: "soccer-trailing-attack-defense", title: "Soccer form: attack and defense", source: "atlas_soccer_manifest" });
    expect(analysis.populationDefinition).toEqual({
      status: "unpublished",
      reason: "The source pools six divisions but does not publish each team's league or match dates; a comparable population cannot be verified.",
    });
    expect(analysis.rows).toHaveLength(187);
    expect(analysis.rows.filter(item => typeof item.values.clean_sheet_rate_l10 === "number")).toHaveLength(187);
    expect(analysis.fields.map(field => [field.key, field.unit, field.digits])).toEqual([
      ["gd_l10", "number", 2], ["gf_l10", "number", 2], ["ga_l10", "number", 2], ["clean_sheet_rate_l10", "percent", 1],
    ]);
    expect(row(analysis, "Bayern Munich").values).toEqual({ gd_l10: 1.8, gf_l10: 3.2, ga_l10: 1.4, clean_sheet_rate_l10: 0.3 });
    expect(row(analysis, "Arsenal").values).toMatchObject({ ga_l10: 0.6, clean_sheet_rate_l10: 0.6 });
    expect(row(analysis, "Ajaccio").values).toEqual({ gd_l10: -2.4, gf_l10: 0.2, ga_l10: 2.6, clean_sheet_rate_l10: 0.2 });
    expect(row(analysis, "Barcelona").values).toEqual({ gd_l10: 1.5, gf_l10: 2.2, ga_l10: 0.7, clean_sheet_rate_l10: 0.4 });
    expect(row(analysis, "Ajaccio").sourcePaths).toEqual([
      "entries[0].key_numbers.gd_l10", "entries[0].key_numbers.gf_l10", "entries[0].key_numbers.ga_l10", "entries[0].key_numbers.clean_sheet_rate_l10",
    ]);
    expect(analysis.sources?.[0]).toMatchObject({ id: "atlas_soccer_manifest", asOf: "2026-07-18T17:21:08.108324+00:00" });
    expect(analysis.sources?.[0].fields).toEqual(["gd_l10", "gf_l10", "ga_l10", "clean_sheet_rate_l10"]);
    expect(analysis.bindings).toContainEqual({ operand: "clean_sheet_rate_l10", sourcePath: "entries[i].key_numbers.clean_sheet_rate_l10", valueKey: "clean_sheet_rate_l10", label: "Published clean-sheet rate over 10 prior matches" });
    expect(row(analysis, "Arsenal").windows?.clean_sheet_rate_l10).toBe("exactly 10 strictly prior all-venue matches; latest per-team match dropped");
    expect(analysis.sources?.[0].rowWindows?.clean_sheet_rate_l10).toContain("per-team match dates not published");
    expect(analysis.scope).toContain("Public artifact generation timestamp: 2026-07-23T01:57:24.440710+00:00");
  });

  it("retains unique named rows while nulling missing, invalid, and negative fields independently", () => {
    const analysis = buildSoccerScoringResearch({ entries: [
      entry("Missing", null, 1, -1), entry("Nonfinite", Infinity, 1, -1), entry("Negative", -0.1, 1, -1), entry("Zero", 0, 0, 0),
    ] });
    expect(row(analysis, "Missing").values).toEqual({ gf_l10: null, ga_l10: 1, gd_l10: null, clean_sheet_rate_l10: 0.3 });
    expect(row(analysis, "Nonfinite").values).toEqual({ gf_l10: null, ga_l10: 1, gd_l10: null, clean_sheet_rate_l10: 0.3 });
    expect(row(analysis, "Negative").values).toEqual({ gf_l10: null, ga_l10: 1, gd_l10: null, clean_sheet_rate_l10: 0.3 });
    expect(row(analysis, "Zero").values).toEqual({ gf_l10: 0, ga_l10: 0, gd_l10: 0, clean_sheet_rate_l10: 0.3 });
  });

  it("does not fabricate goal difference from a missing operand", () => {
    const result = row(buildSoccerScoringResearch({ entries: [entry("One operand", 2, null, 1)] }), "One operand");
    expect(result.values).toEqual({ gf_l10: 2, ga_l10: null, gd_l10: null, clean_sheet_rate_l10: 0.3 });
  });

  it("nulls incoherent published goal difference while preserving valid operands", () => {
    const result = row(buildSoccerScoringResearch({ entries: [entry("Mismatch", 2, 1, 1.0001)] }), "Mismatch");
    expect(result.values).toEqual({ gf_l10: 2, ga_l10: 1, gd_l10: null, clean_sheet_rate_l10: 0.3 });
    expect(result.note).toContain("could not be verified");
  });

  it("enforces each field's exact floor and the exact trailing window", () => {
    const badGf = FLOOR.replace("gf_l10: n_prior>=10", "gf_l10: n_prior>=9");
    const badGa = FLOOR.replace("ga_l10: n_prior>=10", "ga_l10: n_prior>=10.5");
    const badGd = FLOOR.replace("gd_l10: n_prior>=10", "gd_l10: n_prior>=100");
    const wrongWindow = FLOOR.replace("trailing10_asof_corpus_end", "trailing20_asof_corpus_end");
    expect(row(buildSoccerScoringResearch({ entries: [entry("GF", 2, 1, 1, badGf)] }), "GF").values).toEqual({ gf_l10: null, ga_l10: 1, gd_l10: null, clean_sheet_rate_l10: 0.3 });
    expect(row(buildSoccerScoringResearch({ entries: [entry("GA", 2, 1, 1, badGa)] }), "GA").values).toEqual({ gf_l10: 2, ga_l10: null, gd_l10: null, clean_sheet_rate_l10: 0.3 });
    expect(row(buildSoccerScoringResearch({ entries: [entry("GD", 2, 1, 1, badGd)] }), "GD").values).toEqual({ gf_l10: 2, ga_l10: 1, gd_l10: null, clean_sheet_rate_l10: 0.3 });
    expect(row(buildSoccerScoringResearch({ entries: [entry("Window", 2, 1, 1, wrongWindow)] }), "Window").values).toEqual({ gf_l10: null, ga_l10: null, gd_l10: null, clean_sheet_rate_l10: null });
    const unfloored = row(buildSoccerScoringResearch({ entries: [entry("Window", 2, 1, 1, wrongWindow)] }), "Window");
    expect(unfloored.windows?.gf_l10).toContain("unavailable");
    expect(buildSoccerScoringResearch({ entries: [entry("Window", 2, 1, 1, wrongWindow)] }).sources?.[0].rowWindows?.gf_l10).toContain(unfloored.windows?.gf_l10);
  });

  it("accepts only the published clean-sheet fraction with its own exact floor and window", () => {
    const missing = { ...entry("Missing clean sheets", 2, 0, 2), key_numbers: { gf_l10: 2, ga_l10: 0, gd_l10: 2 } };
    const inputs: [string, SoccerScoringEntry, number | null][] = [
      ["Missing clean sheets", missing, null],
      ["String", entry("String", 2, 1, 1, FLOOR, "0.3"), null],
      ["NaN", entry("NaN", 2, 1, 1, FLOOR, NaN), null],
      ["Infinity", entry("Infinity", 2, 1, 1, FLOOR, Infinity), null],
      ["Negative", entry("Negative", 2, 1, 1, FLOOR, -0.1), null],
      ["Above one", entry("Above one", 2, 1, 1, FLOOR, 1.1), null],
      ["Zero", entry("Zero", 2, 1, 1, FLOOR, 0), 0],
      ["One", entry("One", 2, 1, 1, FLOOR, 1), 1],
      ["No floor", entry("No floor", 2, 1, 1, FLOOR.replace(" | clean_sheet_rate_l10: n_prior>=10", "")), null],
      ["Short floor", entry("Short floor", 2, 1, 1, FLOOR.replace("clean_sheet_rate_l10: n_prior>=10", "clean_sheet_rate_l10: n_prior>=9")), null],
      ["Near floor", entry("Near floor", 2, 1, 1, FLOOR.replace("clean_sheet_rate_l10: n_prior>=10", "clean_sheet_rate_l10: n_prior>=10.5")), null],
      ["Long floor", entry("Long floor", 2, 1, 1, FLOOR.replace("clean_sheet_rate_l10: n_prior>=10", "clean_sheet_rate_l10: n_prior>=100")), null],
      ["Wrong window", entry("Wrong window", 2, 1, 1, FLOOR.replace("trailing10_asof_corpus_end", "trailing20_asof_corpus_end")), null],
    ];
    const analysis = buildSoccerScoringResearch({ entries: inputs.map(([, source]) => source) });
    for (const [label, , expected] of inputs) {
      expect(row(analysis, label).values.clean_sheet_rate_l10).toBe(expected);
      if (label === "Missing clean sheets") expect(row(analysis, label).values).toMatchObject({ gd_l10: 2, ga_l10: 0 });
      if (label === "No floor") expect(row(analysis, label).windows?.clean_sheet_rate_l10).toContain("unavailable");
    }
    expect(analysis.sources?.[0].rowWindows?.clean_sheet_rate_l10).toContain("unavailable: exact n_prior>=10 floor and trailing10_asof_corpus_end window not verified");
  });

  it("rejects ambiguous normalized names and assigns stable ids", () => {
    const analysis = buildSoccerScoringResearch({ entries: [
      entry("Atletico-MG", 2, 1, 1), entry("Real Sociedad", 2, 1, 1), entry("Atletico MG", 1, 2, -1), entry(" ", 1, 1, 0),
    ] });
    expect(analysis.rows.map(item => [item.id, item.label])).toEqual([["soccer-scoring-real-sociedad", "Real Sociedad"]]);
    expect(buildSoccerScoringResearch({ entries: [entry("Real Sociedad", 2, 1, 1)] }).rows[0].id).toBe("soccer-scoring-real-sociedad");
  });

  it("records row-window limits and avoids unsupported claims", () => {
    const analysis = getSoccerScoringResearch();
    expect(analysis.rows[0].windows?.gd_l10).toContain("strictly prior");
    expect(analysis.rows[0].windows?.clean_sheet_rate_l10).toContain("latest per-team match dropped");
    expect(analysis.sources?.[0].rowWindows?.gd_l10).toContain("per-team match dates not published");
    expect(analysis.sources?.[0].rowWindows?.gf_l10).toContain(analysis.rows[0].windows?.gf_l10);
    expect(analysis.caveat).toMatch(/six divisions.*2015-2026/i);
    expect(analysis.caveat).toMatch(/league partition|opponent-strength adjustment/i);
    expect(analysis.caveat).toContain("not independent");
    expect(`${analysis.title} ${analysis.description} ${analysis.interpretation}`.toLowerCase()).not.toMatch(/expected goals|forecast|causal/);
    expect(analysis.formula).toContain("share of matches with zero goals conceded");
    expect(analysis.formula).toContain("same 10 strictly prior matches across home and away");
    expect(analysis.interpretation).toContain("not the average number conceded");
  });

  it("preserves source array indexes across malformed entries and malformed key numbers", () => {
    const analysis = buildSoccerScoringResearch({ entries: [null, entry("Indexed", 2, 1, 1), "bad", { ...entry("Numbers", 2, 1, 1), key_numbers: null }] });
    expect(row(analysis, "Indexed").sourcePaths?.[0]).toBe("entries[1].key_numbers.gd_l10");
    expect(row(analysis, "Numbers").values).toEqual({ gd_l10: null, gf_l10: null, ga_l10: null, clean_sheet_rate_l10: null });
  });

  it("handles empty atlases and suppresses malformed or mixed timestamps", () => {
    expect(buildSoccerScoringResearch({}).rows).toEqual([]);
    expect(buildSoccerScoringResearch({ entries: null }).rows).toEqual([]);
    const malformed = { ...entry("Malformed date", 2, 1, 1), as_of: "2026-02-30T00:00:00Z" };
    const mixed = buildSoccerScoringResearch({ generated_at: "bad", entries: [entry("Valid date", 2, 1, 1), malformed] });
    expect(mixed.sources?.[0].asOf).toBe("not published or inconsistent");
    expect(mixed.scope).toContain("Public artifact generation timestamp: not published");
    expect(row(mixed, "Malformed date").bindingValues?.source_claim_timestamp).toBeNull();
  });
});
