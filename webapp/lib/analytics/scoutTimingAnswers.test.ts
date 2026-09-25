import { describe, expect, it } from "vitest";
import lcf from "../../public/data/showcase/novel_live_clock_fraction.json";
import mfp from "../../public/data/showcase/novel_market_foresight_premium.json";
import novel from "../../public/data/ask/novel-stats.json";
import comparisons from "../../public/data/ask/comparisons.json";
import tour from "../../public/data/ask/product-tour.json";
import served from "../../public/data/ask/corpus.json";
import { resolveQuestion, type AskEntry } from "./askSearch";
import { loadScoutCorpus } from "./scoutCorpus.server";
import { scoutIntegrity } from "./scoutIntegrity";

const corpus = loadScoutCorpus();
const buckets = [novel, comparisons, tour] as unknown as Array<{ bucket: string; entries: AskEntry[] }>;
const LCF = "novel_live_clock_fraction";
const MFP = "novel_market_foresight_premium";
const specs: Array<[string, string, string]> = [
  ["What is the Live-Clock Fraction?", "novel-stats", LCF],
  ["Which sport stays competitive the longest?", "novel-stats", LCF],
  ["Why is there no NBA Live-Clock Fraction?", "novel-stats", LCF],
  ["How is the Live-Clock Fraction threshold chosen?", "novel-stats", LCF],
  ["Is the Live-Clock Fraction a new method?", "novel-stats", LCF],
  ["How small are the Live-Clock Fraction samples?", "novel-stats", LCF],
  ["What is the Market Foresight Premium?", "novel-stats", MFP],
  ["How is the Market Foresight Premium computed?", "novel-stats", MFP],
  ["How does the Market Foresight Premium behave in MLB?", "novel-stats", MFP],
  ["How does the Market Foresight Premium behave in soccer?", "novel-stats", MFP],
  ["In which sport does the market have the biggest in-game information advantage?", "novel-stats", MFP],
  ["Does a high Market Foresight Premium mean our model is bad?", "novel-stats", MFP],
  ["What prior work does the Market Foresight Premium build on?", "novel-stats", MFP],
  ["What is the model's in-game skill score at each MLB checkpoint?", "novel-stats", MFP],
  ["Do the novel stats agree with each other about which sports are hardest to read?", "novel-stats", LCF],
  ["Which novel stat is the weakest?", "novel-stats", LCF],
  ["Is there a novel stat for tennis?", "novel-stats", LCF],
  ["Which sport stays contested the longest?", "comparisons", LCF],
  ["Where does the in-game market know the most that the scoreboard doesn't?", "comparisons", MFP],
  ["Compare how MLB and soccer markets converge during a game.", "comparisons", MFP],
  ["Compare model performance at the very start versus the very end of a game.", "comparisons", MFP],
  ["Which is more informative, the score or the market price?", "comparisons", MFP],
  ["What can you show me about in-game information arrival?", "product-tour", MFP],
];
const answer = (q: string) => served.entries.find(entry => entry.q === q)?.a.answer || "";
const phrase = "Published snapshot dated 2026-09-17; the observation window is not published";

describe("revision 2 timing Scout answers", () => {
  it("retrieves all 23 identities from synchronized bucket and served copies", () => {
    expect(specs).toHaveLength(23);
    for (const [q, bucketName, id] of specs) {
      const bucket = buckets.find(file => file.bucket === bucketName)?.entries.find(entry => entry.q === q);
      const copy = served.entries.find(entry => entry.q === q);
      const result = resolveQuestion(q, corpus);
      expect(bucket, q).toBeDefined();
      expect(copy, q).toMatchObject(bucket!);
      expect(result, q).toMatchObject({ kind: "direct", entry: { q } });
      expect(result?.entry?.a, q).toEqual(bucket?.a);
      expect(bucket?.a, q).toMatchObject({
        source_artifact: `webapp/public/data/showcase/${id}.json`,
        explore_path: `/analytics/m/${id}`,
        as_of: "unknown",
      });
      if (q === "Is there a novel stat for tennis?") {
        expect(answer(q)).toContain("LCF published snapshot dated 2026-09-17; its observation window is not published");
      } else {
        expect(answer(q), q).toContain(phrase);
      }
      expect(scoutIntegrity(bucket!.a).moduleIds, q).toContain(id);
    }
  });

  it("uses the exhibit's LCF denominators and retrospective observed clock", () => {
    const mlb = lcf.results.find(row => row.sport === "mlb")!;
    const soccer = lcf.results.find(row => row.sport === "soccer_intl")!;
    expect([mlb.n_games_total, mlb.n_games_decided, mlb.near_median_threshold]).toEqual([174, 97, 3]);
    expect([soccer.n_games_total, soccer.n_games_decided, soccer.near_median_threshold]).toEqual([26, 12, 1]);
    const threshold = answer("How is the Live-Clock Fraction threshold chosen?");
    for (const row of [mlb, soccer]) {
      for (const value of [row.live_clock_fraction, row.decided_frac_of_games]) {
        expect(threshold).toContain(String(value));
      }
    }
    expect(threshold).toContain("final observed clock");
    expect(answer("What is the Live-Clock Fraction?")).toContain("final observed tick");
    expect(answer("How small are the Live-Clock Fraction samples?")).toContain("178 MLB and 27 soccer stored");
    expect(answer("How small are the Live-Clock Fraction samples?")).toContain("not the LCF denominators");
    expect(answer("Which sport stays contested the longest?")).toContain("not equated");
  });

  it("uses current non-monotonic MFP values and checkpoint observations", () => {
    const baseball = mfp.results.mlb;
    const soccer = mfp.results.soccer_intl;
    const mlbAnswer = answer("How does the Market Foresight Premium behave in MLB?");
    for (const row of [baseball.checkpoints[0], baseball.checkpoints[8], baseball.checkpoints[9]]) {
      expect(mlbAnswer).toContain(String(row.mfp));
      expect(mlbAnswer).toContain(row.n.toLocaleString("en-US"));
    }
    expect(mlbAnswer).toContain("non-monotonic");
    expect(mlbAnswer).toContain("checkpoint observations, not games");
    expect(baseball.checkpoints[8].mfp).toBeLessThan(baseball.checkpoints[0].mfp);
    const soccerAnswer = answer("How does the Market Foresight Premium behave in soccer?");
    expect(soccerAnswer).toContain(String(soccer.checkpoints[0].mfp));
    expect(soccerAnswer).toContain(String(soccer.checkpoints.at(-1)!.mfp));
    expect(soccerAnswer).toContain("non-monotonic");
    expect(soccerAnswer).toContain("n=33");
    const skill = answer("What is the model's in-game skill score at each MLB checkpoint?");
    for (const row of baseball.checkpoints.slice(4, 9)) {
      expect(row.model_skill).toBeGreaterThan(0);
      expect(skill).toContain(`+${row.model_skill.toFixed(4)}`);
    }
    expect(skill).toContain("positive at checkpoints 5-9");
  });

  it("states the reference, attribution and no-data limits", () => {
    for (const [q] of specs.filter(([, , module]) => module === MFP)) {
      expect(answer(q).toLowerCase(), q).toContain("closing reference");
      expect(answer(q), q).not.toContain("rises steadily");
    }
    for (const q of [
      "In which sport does the market have the biggest in-game information advantage?",
      "Where does the in-game market know the most that the scoreboard doesn't?",
      "Which is more informative, the score or the market price?",
    ]) expect(answer(q)).toMatch(/cannot|does not/);
    const mixed = buckets[0].entries.find(entry => entry.q === "Do the novel stats agree with each other about which sports are hardest to read?")!;
    expect(mixed.a.source_module_ids).toEqual([LCF, MFP]);
    expect(answer(mixed.q)).toContain("do not support one hardest-to-read ranking");
    const tennis = buckets[0].entries.find(entry => entry.q === "Is there a novel stat for tennis?")!;
    expect(tennis.a.source_module_ids).toEqual([LCF, "novel_line_half_life"]);
    expect(answer(tennis.q)).toContain("not games");
    const missing = buckets[0].entries.find(entry => entry.q === "Why is there no NBA Live-Clock Fraction?")!;
    expect(missing.a.status).toBe("no_data");
    expect(answer(missing.q)).toContain("not_buildable");
  });
});
