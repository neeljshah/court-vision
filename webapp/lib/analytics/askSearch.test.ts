import { describe, expect, it } from "vitest";
import { resolveQuestion, type AskEntry } from "./askSearch";
import { loadScoutCorpus } from "./scoutCorpus.server";

const entries: AskEntry[] = [
  {
    q: "Is Jokic really passing like a guard from the center position?",
    alt_phrasings: ["Jokic assist rate", "Does Jokic play like a point-center?"],
    tags: ["nba", "player", "jokic", "playmaking"],
    bucket: "players-teams",
    a: { status: "ok", answer: "Jokic records 10.1 assists per 36 minutes.", source_artifact: "jokic.json" },
  },
  {
    q: "How does Jokic create shots for teammates?",
    alt_phrasings: ["Jokic passing profile"],
    tags: ["nba", "jokic", "playmaking"],
    bucket: "players-teams",
    a: { status: "ok", answer: "Jokic creates shots with high assist volume.", source_artifact: "jokic-passing.json" },
  },
  {
    q: "Does the model actually beat the betting market?",
    alt_phrasings: ["can you beat the market", "does it outperform the odds"],
    tags: ["model-vs-market", "efficiency", "brier"],
    bucket: "calibration-market",
    a: { status: "ok", answer: "The measured model does not beat the market.", source_artifact: "market.md" },
  },
];

describe("resolveQuestion", () => {
  it("resolves multiword paraphrases to the cited answer", () => {
    const result = resolveQuestion("what is Jokic's assist rate?", entries);
    expect(result).toMatchObject({ kind: "direct", entry: { q: entries[0].q } });
    expect(result?.followUps).toContain(entries[1].q);
  });

  it("only suggests answers with a shared subject or cited source", () => {
    const result = resolveQuestion("what is Jokic's assist rate?", entries);
    expect(result?.followUps).toContain(entries[1].q);
    expect(result?.followUps).not.toContain(entries[2].q);
  });

  it("keeps a derived analysis within its cited source module", () => {
    const derived: AskEntry[] = [
      {
        q: "Explain the analysis: Observed monthly calibration shift",
        alt_phrasings: ["Observed monthly calibration shift"],
        tags: ["all", "derived-analysis", "observed", "monthly", "calibration", "shift"],
        bucket: "public-derived-analysis",
        a: { status: "ok", answer: "Published monthly shift analysis.", source_artifact: "webapp/public/data/showcase/calibration_over_time.json", explore_path: "/analytics/research/observed-cohort-shift/" },
      },
      {
        q: "What does the calibration-over-time module cover?",
        alt_phrasings: ["calibration over time"],
        tags: ["analytics-module", "calibration", "time"],
        bucket: "public-analytics-module",
        a: { status: "ok", answer: "Published source module.", source_artifact: "webapp/public/data/showcase/calibration_over_time.json" },
      },
      {
        q: "Explain the analysis: Fourth-quarter role shift",
        alt_phrasings: ["Fourth-quarter role shift"],
        tags: ["nba", "derived-analysis", "role", "shift"],
        bucket: "public-derived-analysis",
        a: { status: "ok", answer: "A tempting but unrelated shift analysis.", source_artifact: "webapp/public/data/showcase/nba_q4_shift.json", explore_path: "/analytics/research/nba-q4-role-shift/" },
      },
    ];
    const result = resolveQuestion(derived[0].q, derived);
    expect(result?.followUps).toEqual([derived[1].q]);
  });

  it("normalizes sports and odds vocabulary without generating an answer", () => {
    const result = resolveQuestion("does the basketball model outperform market odds", entries);
    expect(result).toMatchObject({ kind: "direct", entry: { q: entries[2].q } });
  });

  it("does not pass off a different named player as a direct answer", () => {
    const result = resolveQuestion("what is LeBron's assist rate?", entries);
    expect(result?.kind).not.toBe("direct");
  });

  it("does not offer another resolved person with the same surname", () => {
    const stephen = { name: "Stephen Curry", pack: "nba_players", slug: "stephen_curry" };
    const seth = { name: "Seth Curry", pack: "nba_players", slug: "seth_curry" };
    const playerEntries: AskEntry[] = [
      { q: "What does Stephen Curry's profile record?", alt_phrasings: ["Stephen Curry"], tags: ["nba"], bucket: "players", entity: stephen, a: { status: "ok", answer: "Stephen profile.", source_artifact: "curry.json" } },
      { q: "What does Seth Curry's profile record?", alt_phrasings: ["Seth Curry"], tags: ["nba"], bucket: "players", entity: seth, a: { status: "ok", answer: "Seth profile.", source_artifact: "curry.json" } },
      { q: "How is the NBA player atlas measured?", alt_phrasings: [], tags: ["nba"], bucket: "players", a: { status: "ok", answer: "Published method.", source_artifact: "curry.json" } },
    ];
    const result = resolveQuestion("What does Stephen Curry's profile record?", playerEntries);
    expect(result?.followUps).not.toContain(playerEntries[1].q);
    expect(result?.followUps).toContain(playerEntries[2].q);
  });

  it("keeps scanning ranked follow-ups after rejecting a different identity", () => {
    const stephen = { name: "Stephen Curry", pack: "nba_players", slug: "stephen_curry" };
    const seth = { name: "Seth Curry", pack: "nba_players", slug: "seth_curry" };
    const selected: AskEntry = { q: "Stephen Curry shooting profile", alt_phrasings: [], tags: ["nba"], bucket: "players", entity: stephen, a: { status: "ok", answer: "Stephen profile.", source_artifact: "curry.json" } };
    const validQuestions = ["Alpha measurement method", "Beta measurement method", "Gamma measurement method"];
    const playerEntries: AskEntry[] = [
      selected,
      { q: "How does Seth Curry's shooting profile compare?", alt_phrasings: [], tags: ["nba"], bucket: "players", a: { status: "ok", answer: "Seth profile.", source_artifact: "curry.json" } },
      { q: "Seth Curry shooting profile", alt_phrasings: [], tags: ["nba"], bucket: "players", entity: seth, a: { status: "ok", answer: "Seth profile.", source_artifact: "curry.json" } },
      ...validQuestions.slice().reverse().map((q) => ({ q, alt_phrasings: [], tags: ["nba"], bucket: "methods", a: { status: "ok" as const, answer: "Published method.", source_artifact: "curry.json" } })),
    ];

    expect(resolveQuestion(selected.q, playerEntries)?.followUps).toEqual(validQuestions);
  });

  it("keeps the requested identities for an explicit comparison", () => {
    const jokic = { name: "Nikola Jokic", pack: "nba_players", slug: "nikola_jokic" };
    const giannis = { name: "Giannis Antetokounmpo", pack: "nba_players", slug: "giannis_antetokounmpo" };
    const pairQuestion = "Which published records cover Nikola Jokic and Giannis Antetokounmpo?";
    const lukaQuestion = "How does Luka Doncic compare with Nikola Jokic?";
    const entityEntries: AskEntry[] = [
      { q: "Nikola Jokic profile", alt_phrasings: [], tags: ["nba"], bucket: "public-entity-profile", entity: jokic, a: { status: "ok", answer: "Nikola Jokic profile.", source_artifact: "jokic.json" } },
      { q: "Giannis Antetokounmpo profile", alt_phrasings: [], tags: ["nba"], bucket: "public-entity-profile", entity: giannis, a: { status: "ok", answer: "Giannis profile.", source_artifact: "giannis.json" } },
      { q: "How does Giannis affect team production?", alt_phrasings: [], tags: ["nba"], bucket: "players-teams", a: { status: "ok", answer: "Nikola Jokic is mentioned only in this answer.", source_artifact: "giannis-team.json" } },
      { q: lukaQuestion, alt_phrasings: [], tags: ["nba"], bucket: "players-teams", a: { status: "ok", answer: "Published comparison.", source_artifact: "luka-jokic.json" } },
      { q: pairQuestion, alt_phrasings: [], tags: ["nba"], bucket: "players-teams", a: { status: "ok", answer: "Published pair note.", source_artifact: "pair.json" } },
    ];
    const result = resolveQuestion("Compare Nikola Jokic and Giannis Antetokounmpo", entityEntries);

    expect(result).toMatchObject({
      kind: "related",
      entry: { q: pairQuestion },
      compareOffer: {
        label: "Compare Nikola Jokic and Giannis Antetokounmpo",
        href: "/analytics/compare?pack=nba_players&a=nikola_jokic&b=giannis_antetokounmpo",
      },
    });
    expect(result?.entry?.q).not.toBe(lukaQuestion);
  });

  it("returns an explicit empty result for unsupported topics", () => {
    expect(resolveQuestion("how do cricket fielding positions work", entries)).toEqual({
      entry: null,
      kind: "none",
      followUps: [],
    });
  });

  it("keeps inspector aliases ahead of unrelated entity notes and accepts paper routes", () => {
    const corpus = loadScoutCorpus();
    for (const query of ["observation dependence", "count context"]) {
      expect(resolveQuestion(query, corpus)).toMatchObject({ kind: "direct", entry: { bucket: "public-inspector" } });
    }
    const paper = corpus.find(entry => entry.bucket === "public-paper");
    expect(paper?.a.explore_path).toMatch(/^\/analytics\/papers\/[a-z0-9-]+\/$/);
  });

  it("describes every calibration probability-band profile from its four published fields", () => {
    const corpus = loadScoutCorpus();
    const bands = corpus.filter(entry => entry.entity?.pack === "calibration" && / band /i.test(entry.entity.name));
    expect(bands).toHaveLength(10);
    for (const band of bands) {
      expect(band.a.answer).toContain("overall observed outcome rate:");
      expect(band.a.answer).toContain("band reference:");
      expect(band.a.answer).toContain("published support:");
      expect(band.a.answer).toContain("time-bucket observations:");
      expect(band.a.answer).not.toContain("no configured numeric metrics");
    }
  });
});
