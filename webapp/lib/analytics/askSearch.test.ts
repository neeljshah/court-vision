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
    q: "What does Luka Doncic's production look like?",
    alt_phrasings: ["Tell me about Luka Doncic", "Luka stat line"],
    tags: ["nba", "player", "luka", "profile"],
    bucket: "players-teams",
    a: { status: "ok", answer: "Luka averages 8.6 assists per 36 minutes.", source_artifact: "luka.json" },
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
