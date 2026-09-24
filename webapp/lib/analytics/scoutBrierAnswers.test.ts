import { describe, expect, it } from "vitest";
import bss from "../../public/data/showcase/brier_skill_scores.json";
import calibrationMarket from "../../public/data/ask/calibration-market.json";
import comparisons from "../../public/data/ask/comparisons.json";
import productTour from "../../public/data/ask/product-tour.json";
import systemHonesty from "../../public/data/ask/system-honesty.json";
import served from "../../public/data/ask/corpus.json";
import { resolveQuestion } from "./askSearch";
import { loadScoutCorpus } from "./scoutCorpus.server";
import { scoutIntegrity } from "./scoutIntegrity";

const source = "webapp/public/data/showcase/brier_skill_scores.json";
const corpus = loadScoutCorpus();
const buckets = [calibrationMarket, comparisons, productTour, systemHonesty];
const mlb = bss.sports.mlb;
const soccer = bss.sports.soccer_intl;
const f = (n: number) => n.toFixed(6);
const count = (n: number) => n.toLocaleString("en-US");

const cases = [
  ["In-game, does the win-probability model beat the market's win probability?", [f(mlb.grains.all.brier_model), f(soccer.grains.all.brier_market), String(soccer.grains.all.bss_model_vs_market), count(mlb.n_rows), count(soccer.n_rows)]],
  ["What is a Brier score and what is the model's?", ["mean squared error", "0.25", f(mlb.grains.all.brier_model), f(soccer.grains.all.brier_model)]],
  ["Does the model beat a simple base-rate baseline?", [String(mlb.grains.all.bss_model_vs_clim), String(soccer.grains.all.bss_model_vs_clim), String(soccer.grains.all.bss_market_vs_clim)]],
  ["Which sport has the best-calibrated market probabilities?", ["cannot rank calibration alone", f(mlb.grains.all.brier_market), f(soccer.grains.all.brier_market)]],
  ["Which sport is the most predictable?", ["does not establish", "not an overall cross-sport predictability ranking", String(mlb.grains.all.bss_model_vs_clim)]],
  ["Where is our model furthest behind the market?", [String(soccer.grains.all.bss_model_vs_market), String(soccer.grains["0-15"].bss_model_vs_market), count(soccer.grains["0-15"].n)]],
  ["Does the model do better early or late in an MLB game?", [String(mlb.grains["early(inn1-3)"].bss_model_vs_market), String(mlb.grains["mid(inn4-6)"].bss_model_vs_market), String(mlb.grains["late(inn7+)"].bss_model_vs_market), "different observations"]],
  ["Which sport has the highest base rate for the graded outcome?", [String(soccer.sport_base_rate), String(mlb.sport_base_rate), f(soccer.grains.all.brier_clim)]],
  ["Does the model beat a coin flip?", ["regardless of its observed base rate", "0.25", f(mlb.grains.all.brier_model), f(soccer.grains.all.brier_model), f(soccer.grains.all.brier_market)]],
  ["Compare the market's skill to the model's skill.", [String(mlb.grains.all.bss_market_vs_clim), String(mlb.grains.all.bss_model_vs_clim), String(soccer.grains.all.bss_market_vs_clim), String(soccer.grains.all.bss_model_vs_clim)]],
  ["In which soccer window is the market's advantage largest?", [String(soccer.grains["0-15"].bss_model_vs_market), f(soccer.grains["75-90+"].brier_model), f(soccer.grains["75-90+"].brier_market), f(soccer.grains["75-90+"].brier_model - soccer.grains["75-90+"].brier_market), count(soccer.grains["75-90+"].n)]],
  ["Is any sport's market beatable?", [String(mlb.grains.all.bss_model_vs_market), String(soccer.grains.all.bss_model_vs_market), "does not support naming"]],
  ["What can you show me about soccer?", ["/analytics/m/soccer_calibration_pack", count(soccer.n_rows), f(soccer.grains.all.brier_model)]],
  ["How well does the model do against the market's own probabilities?", [f(mlb.grains.all.brier_model), f(mlb.grains.all.brier_market), f(soccer.grains.all.brier_model), f(soccer.grains.all.brier_market)]],
] as const;

describe("revision 2 Brier Scout answers", () => {
  it("retrieves all 14 direct answers with their bucket and served copies synchronized", () => {
    for (const [question, phrases] of cases) {
      const bucket = buckets.flatMap(file => file.entries).find(entry => entry.q === question);
      const servedEntry = served.entries.find(entry => entry.q === question);
      const result = resolveQuestion(question, corpus);
      expect(result, question).toMatchObject({ kind: "direct", entry: { q: question } });
      expect(bucket, question).toBeDefined();
      expect(servedEntry, question).toBeDefined();
      expect(result?.entry?.a, question).toEqual(bucket?.a);
      expect(servedEntry?.a, question).toEqual(bucket?.a);
      expect(servedEntry?.alt_phrasings, question).toEqual(bucket?.alt_phrasings);
      expect(servedEntry?.tags, question).toEqual(bucket?.tags);
      const answer = result?.entry?.a.answer || "";
      for (const phrase of phrases) expect(answer, question).toContain(phrase);
      expect(answer, question).toContain(`generated ${bss.generated_at.split("T")[0]}`);
      expect(answer, question).toContain("observation window is not published");
      expect(answer, question).toContain("rows, not games");
      expect(result?.entry?.a, question).toMatchObject({
        source_artifact: source,
        as_of: "unknown",
        status: question === "Is any sport's market beatable?" ? "refused" : "ok",
      });
    }
  });

  it("keeps the revision 2 integrity notice attached to the exact source", () => {
    for (const [question] of cases) {
      const answer = corpus.find(entry => entry.q === question)?.a;
      expect(answer).toBeDefined();
      if (!answer) continue;
      const integrity = scoutIntegrity(answer);
      expect(integrity.moduleIds).toContain("brier_skill_scores");
      expect(integrity.notices).toEqual(expect.arrayContaining([expect.objectContaining({ status: "regenerated" })]));
    }
  });

  it("distinguishes the fixed half baseline, climatology, and two window gaps", () => {
    const answer = (question: string) => corpus.find(entry => entry.q === question)?.a.answer || "";
    expect(0.5 ** 2).toBe(0.25);
    expect(mlb.grains.all.brier_model).toBeLessThan(0.25);
    expect(soccer.grains.all.brier_model).toBeGreaterThan(0.25);
    expect(soccer.grains.all.brier_market).toBeLessThan(0.25);
    expect(soccer.grains.all.bss_market_vs_clim).toBeLessThan(0);
    expect(answer("Does the model beat a coin flip?")).toContain("differs from the published sport-base-rate climatology");
    expect(answer("In which soccer window is the market's advantage largest?")).toContain("By relative");
    expect(answer("In which soccer window is the market's advantage largest?")).toContain("By absolute");
    const gaps = Object.entries(soccer.grains).filter(([grain]) => grain !== "all").map(([grain, row]) => ({ grain, gap: row.brier_model - row.brier_market, skill: row.bss_model_vs_market }));
    expect(gaps.reduce((a, b) => a.gap > b.gap ? a : b).grain).toBe("75-90+");
    expect(gaps.reduce((a, b) => a.skill < b.skill ? a : b).grain).toBe("0-15");
  });
});
