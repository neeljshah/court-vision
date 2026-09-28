import { describe, expect, it } from "vitest";
import { resolveQuestion } from "./askSearch";
import { buildSoccerCleanSheetAnswers } from "./scoutSoccerAnswers";
import { loadScoutCorpus } from "./scoutCorpus.server";
import type { SoccerScoringEntry } from "./researchSoccerScoring";
import atlas from "../../public/data/showcase/atlas_soccer_manifest.json";

const FLOOR = "clean_sheet_rate_l10: n_prior>=10 (window=trailing10_asof_corpus_end; below floor shows n/a)";
const entry = (entity: string, rate: unknown, floors: unknown = FLOOR, as_of: unknown = "2026-07-18T17:21:08.108324+00:00"): SoccerScoringEntry => ({
  entity, key_numbers: { clean_sheet_rate_l10: rate }, floors, as_of,
});
const answers = buildSoccerCleanSheetAnswers(atlas);
const corpus = loadScoutCorpus();
const answerFor = (team: string) => answers.find(answer => answer.q === `How often does ${team} keep clean sheets?`)!;

describe("Scout soccer clean-sheet answers", () => {
  it("resolves every published team's full question to its own answer in the complete corpus", () => {
    for (const answer of answers) {
      const result = resolveQuestion(answer.q, corpus);
      expect(result?.kind, answer.q).toBe("direct");
      expect(result?.entry?.a.explore_path, answer.q).toBe(answer.a.explore_path);
    }
  }, 30000);

  it("preserves existing soccer analysis follow-ups without arbitrary team suggestions", () => {
    const query = "Soccer form: attack and defense";
    const previous = corpus.filter(answer => answer.bucket !== "public-soccer-clean-sheets");
    const result = resolveQuestion(query, corpus);
    expect(result?.entry?.bucket).toBe("public-derived-analysis");
    expect(result?.followUps).toEqual(resolveQuestion(query, previous)?.followUps);
    expect(result?.followUps.some(question => question.includes("keep clean sheets"))).toBe(false);
  });

  it("uses all 187 validated public rows and reports source values without a new identity", () => {
    expect(answers).toHaveLength(187);
    expect(new Set(answers.map(answer => answer.q)).size).toBe(187);
    expect(answerFor("Chelsea").a.answer).toContain("0.0%");
    for (const [team, percentage] of [["Arsenal", "60.0%"], ["Bayern Munich", "30.0%"], ["Ajaccio", "20.0%"]]) {
      const answer = answerFor(team);
      expect(answer).toMatchObject({ bucket: "public-soccer-clean-sheets", exactOnly: true, a: {
        status: "ok", source_artifact: "webapp/public/data/showcase/atlas_soccer_manifest.json",
        source_module_ids: ["atlas_soccer_manifest"], as_of: "2026-07-18T17:21:08.108324+00:00",
      } });
      expect(answer.entity).toBeUndefined();
      expect(answer.a.answer).toContain(percentage);
      expect(answer.a.answer).toContain("zero goals conceded");
      expect(answer.a.answer).toContain("exactly 10 strictly prior all-venue (home or away) matches");
      expect(answer.a.answer).toContain("latest match was dropped");
      expect(answer.a.answer).toContain("Per-team match dates are unpublished");
      expect(answer.a.answer).toContain("historical descriptive snapshot, not a current result or forecast");
      const link = new URL(answer.a.explore_path!, "https://example.test");
      expect(link.pathname).toBe("/analytics/research/soccer-trailing-attack-defense/");
      expect(Object.fromEntries(link.searchParams)).toEqual({ q: team, metric: "clean_sheet_rate_l10", row: `soccer-scoring-${team.toLowerCase().replace(/[^a-z0-9]+/g, "-")}` });
    }
    expect(answers.some(answer => /\b(best|ranked|league leader)\b/i.test(answer.a.answer))).toBe(false);
  });

  it("omits missing, malformed, out-of-range, unfloored and wrong-window values independently", () => {
    const invalid = [
      entry("Missing", undefined), entry("Null", null), entry("String", "0.3"),
      entry("NaN", NaN), entry("Infinity", Infinity), entry("Negative", -0.1), entry("Above one", 1.1),
      entry("No floor", 0.3, "window=trailing10_asof_corpus_end"),
      entry("Short floor", 0.3, FLOOR.replace("n_prior>=10", "n_prior>=9")),
      entry("Near floor", 0.3, FLOOR.replace("n_prior>=10", "n_prior>=10.5")),
      entry("Long floor", 0.3, FLOOR.replace("n_prior>=10", "n_prior>=100")),
      entry("Wrong window", 0.3, FLOOR.replace("trailing10_asof_corpus_end", "trailing20_asof_corpus_end")),
    ];
    const result = buildSoccerCleanSheetAnswers({ entries: [...invalid, entry("Zero", 0), entry("One", 1)] });
    expect(result.map(answer => answer.q)).toEqual(["How often does Zero keep clean sheets?", "How often does One keep clean sheets?"]);
    expect(result.map(answer => answer.a.answer.match(/\d+\.\d%/)?.[0])).toEqual(["0.0%", "100.0%"]);
  });

  it("drops normalized duplicate team names and keeps malformed claim timestamps unknown", () => {
    const result = buildSoccerCleanSheetAnswers({ entries: [
      entry("Same Team", 0.2), entry("Same-Team", 0.5), entry("Unique", 0.4, FLOOR, "2026-02-30T00:00:00Z"),
    ] });
    expect(result).toHaveLength(1);
    expect(result[0].q).toBe("How often does Unique keep clean sheets?");
    expect(result[0].a.as_of).toBe("unknown");
    expect(result[0].a.answer).toContain("Source claim timestamp: unknown");
    expect(result[0].a.answer).not.toContain("2026-02-30");
  });

  it("resolves only explicit full-question or alias matches to these answers", () => {
    const arsenal = answerFor("Arsenal");
    for (const query of [arsenal.q, ...arsenal.alt_phrasings]) {
      expect(resolveQuestion(query, corpus)).toMatchObject({ kind: "direct", entry: { q: arsenal.q, a: { source_artifact: "webapp/public/data/showcase/atlas_soccer_manifest.json" } } });
    }
    expect(resolveQuestion("Bayern Munich clean sheets", corpus)).toMatchObject({ kind: "direct", entry: { q: "How often does Bayern Munich keep clean sheets?" } });
    for (const query of [
      "Arsenal clean sheets this season", "Arsenal home clean sheets", "Arsenal away clean-sheet rate",
      "How often does Arsenal keep clean sheets currently?", "Arsenal clean sheets now",
      "Arsenal does not keep clean sheets", "How often did Arsenal keep clean sheets in 2025?",
      "clean sheets Arsenal", "Arsenal and Bayern Munich clean sheets",
      "Arsenal MLB clean sheets", "Unknown Team clean sheets",
    ]) {
      const result = resolveQuestion(query, corpus);
      expect(result?.entry?.bucket, query).not.toBe("public-soccer-clean-sheets");
    }
  });
});
