import { describe, expect, it } from "vitest";
import { resolveQuestion, type AskEntry } from "./askSearch";

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

  it("returns an explicit empty result for unsupported topics", () => {
    expect(resolveQuestion("how do cricket fielding positions work", entries)).toEqual({
      entry: null,
      kind: "none",
      followUps: [],
    });
  });
});
