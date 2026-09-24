import { describe, expect, it } from "vitest";
import murphy from "../../public/data/showcase/murphy_decomposition.json";
import stability from "../../public/data/showcase/calibration_stability.json";
import byType from "../../public/data/showcase/calibration_by_market_type.json";
import overTime from "../../public/data/showcase/calibration_over_time.json";
import soccerPack from "../../public/data/showcase/soccer_calibration_pack.json";
import kernel from "../../public/data/showcase/kernel_transfer.json";
import calibration from "../../public/data/ask/calibration-market.json";
import comparisons from "../../public/data/ask/comparisons.json";
import methodology from "../../public/data/ask/methodology.json";
import honesty from "../../public/data/ask/system-honesty.json";
import served from "../../public/data/ask/corpus.json";
import { resolveQuestion } from "./askSearch";
import { loadScoutCorpus } from "./scoutCorpus.server";
import { scoutIntegrity } from "./scoutIntegrity";

const buckets = [calibration, comparisons, methodology, honesty];
const corpus = loadScoutCorpus();
const path = (id: string) => `webapp/public/data/showcase/${id}.json`;
const n = (value: number) => value.toLocaleString("en-US");
const f = (value: number) => value.toFixed(6);
const signed = (value: number) => `${value >= 0 ? "+" : ""}${f(value)}`;
const gap = (sport: typeof murphy.sports.mlb, component: "reliability" | "resolution") =>
  sport.model_prob[component] - sport.market_prob[component];
const sourceDates = {
  murphy_decomposition: murphy.as_of,
  calibration_stability: stability.as_of,
  calibration_by_market_type: byType.as_of,
  calibration_over_time: overTime.as_of,
  soccer_calibration_pack: soccerPack.as_of,
};
const mlbType = byType.market_types.mlb_moneyline;
const soccerType = byType.market_types.soccer_match;
const mlbMurphy = murphy.sports.mlb;
const soccerMurphy = murphy.sports.soccer_intl;
const high = stability.sports.mlb.sides.model_prob.bins.at(-1)!;
const kernelReliabilityGap = kernel.rows[0].reliability_gap;
if (kernelReliabilityGap === null) throw new Error("MLB moneyline reliability gap is missing");
const answer = (q: string) => served.entries.find(entry => entry.q === q)?.a.answer || "";

const cases = [
  ["Why doesn't being accurate mean beating the market?", "murphy_decomposition", [f(mlbMurphy.model_prob.brier), f(mlbMurphy.market_prob.brier), signed(gap(mlbMurphy, "reliability")), signed(gap(mlbMurphy, "resolution"))]],
  ["Are the predictions actually well calibrated?", "calibration_stability", ["3/10", "0/10", "8/9", "7/9", n(stability.sports.mlb.n_rows), n(stability.sports.soccer_intl.n_rows)]],
  ["Is the model overconfident?", "calibration_stability", [n(high.n), String(high.n_games), String(high.mean_p), String(high.mean_y), String(high.gap), String(high.gap_ci[0]), String(high.gap_ci[1])]],
  ["How do the model's and market's ECE compare?", "calibration_by_market_type", [f(mlbType.model_ece), f(mlbType.market_ece), f(soccerType.model_ece), f(soccerType.market_ece)]],
  ["Is calibration improving month over month?", "calibration_over_time", [Object.keys(overTime.mlb)[0], Object.keys(overTime.mlb)[1], String(overTime.mlb["2026-06"].model_brier), String(overTime.mlb["2026-07"].market_brier), String(overTime.soccer_intl["2026-07"].model_ece)]],
  ["How good is the soccer model's calibration?", "soccer_calibration_pack", [n(soccerPack.n_rows), f(soccerPack.murphy.model_prob.brier), f(soccerPack.murphy.market_prob.brier), String(soccerPack.minute_ece.overall_weighted_ece), n(soccerPack.minute_ece.n)]],
  ["Is the model-vs-market gap fixable by recalibrating?", "murphy_decomposition", [signed(gap(mlbMurphy, "reliability")), signed(gap(mlbMurphy, "resolution")), signed(gap(soccerMurphy, "reliability")), signed(gap(soccerMurphy, "resolution")), "does not test"]],
  ["Which sport has the widest model-vs-market calibration gap?", "murphy_decomposition", [signed(gap(soccerMurphy, "reliability")), signed(gap(mlbMurphy, "reliability")), "reliability", "Brier"]],
  ["How big are the corpora behind these calibration numbers?", "calibration_stability", [n(stability.sports.mlb.n_rows), String(stability.sports.mlb.n_games), n(stability.sports.soccer_intl.n_rows), String(stability.sports.soccer_intl.n_games)]],
  ["Are single-fold results trustworthy?", "soccer_calibration_pack", [n(soccerPack.n_rows), "single-fold", "not durable"]],
  ["Which in-game market is best calibrated?", "calibration_by_market_type", [f(mlbType.market_ece), f(soccerType.market_ece), n(mlbType.n_rows), n(soccerType.n_rows)]],
  ["How big is the Brier gap between the model and the market by sport?", "calibration_by_market_type", [f(mlbType.brier_gap_model_minus_market), f(soccerType.brier_gap_model_minus_market), f(mlbType.model_brier), f(soccerType.market_brier)]],
  ["Compare the model and the market on MLB in-game moneyline.", "kernel_transfer", [n(kernel.rows[0].n), f(kernelReliabilityGap), mlbMurphy.model_prob.brier.toFixed(4), mlbMurphy.market_prob.brier.toFixed(4)]],
  ["Compare the in-game corpora by size.", "calibration_by_market_type", [n(mlbType.n_rows), String(mlbType.n_files), n(soccerType.n_rows), String(soccerType.n_files)]],
  ["How do you avoid double-counting duplicate corpora?", "calibration_by_market_type", ["mlb_clean", n(mlbType.n_rows), String(mlbType.n_files)]],
  ["Where does the model lose to the market -- calibration or information?", "murphy_decomposition", [f(soccerMurphy.model_prob.brier), f(soccerMurphy.market_prob.brier), signed(gap(soccerMurphy, "reliability")), signed(gap(soccerMurphy, "resolution"))]],
] as const;

describe("revision 2 calibration Scout answers", () => {
  it("retrieves all 16 answers with synchronized served copies and exact sources", () => {
    expect(cases).toHaveLength(16);
    for (const [q, id, phrases] of cases) {
      const bucket = buckets.flatMap(file => file.entries).find(entry => entry.q === q);
      const copy = served.entries.find(entry => entry.q === q);
      const result = resolveQuestion(q, corpus);
      expect(result, q).toMatchObject({ kind: "direct", entry: { q } });
      if (!result?.entry) throw new Error(`Missing Scout answer: ${q}`);
      expect(bucket, q).toBeDefined();
      expect(copy, q).toBeDefined();
      expect(copy, q).toMatchObject(bucket!);
      expect(result?.entry?.a, q).toEqual(bucket?.a);
      expect(bucket?.a, q).toMatchObject({ status: "ok", source_artifact: path(id), as_of: "unknown" });
      for (const phrase of phrases) expect(answer(q), q).toContain(phrase);
      if (id === "calibration_over_time") {
        expect(answer(q), q).toContain("exact first and last observation dates are not published");
      } else {
        expect(answer(q), q).toContain("observation window is not published");
      }
      if (id === "kernel_transfer") {
        expect(answer(q)).toContain(`Generated ${kernel.generated_at.slice(0, 10)} UTC`);
      } else {
        expect(answer(q)).toContain(`Published snapshot dated ${sourceDates[id]}`);
      }
      const integrity = scoutIntegrity(result.entry.a);
      expect(integrity.moduleIds).toContain(id);
      if (id !== "kernel_transfer") {
        expect(integrity.notices, q).toEqual(expect.arrayContaining([expect.objectContaining({ status: "regenerated" })]));
      }
    }
  });

  it("grounds the bin and corpus caveats in the exhibits", () => {
    expect(high.bin_lo).toBe(0.9);
    expect(high.gap).toBeGreaterThan(0);
    expect(high.gap_ci[0]).toBeLessThan(0);
    expect(high.gap_ci[1]).toBeGreaterThan(0);
    expect(answer("Is the model overconfident?")).toContain("neither overconfidence, underconfidence, nor calibration");
    expect(stability.sports.mlb.sides.model_prob.n_significant_bins).toBe(3);
    expect(stability.sports.mlb.sides.market_prob.n_significant_bins).toBe(0);
    expect(stability.sports.soccer_intl.low_power).toBe(true);
    expect(answer("Are the predictions actually well calibrated?")).toContain("pointwise");
    expect(answer("How do the model's and market's ECE compare?")).toContain("Files here are source files");
    expect(answer("How good is the soccer model's calibration?")).toContain("aggregation differs");
    expect(answer("How good is the soccer model's calibration?")).not.toContain(f(soccerType.model_ece));
    expect(soccerPack.minute_ece.overall_weighted_ece).not.toBe(soccerType.model_ece);
    expect(soccerPack.minute_ece.buckets.reduce((sum, bucket) => sum + bucket.n, 0)).toBe(soccerPack.minute_ece.n);
    expect(soccerPack.minute_ece.n).toBeLessThan(soccerPack.n_rows);
    expect(answer("How good is the soccer model's calibration?")).toContain(n(soccerPack.minute_ece.n));
  });

  it("keeps dates, decomposition signs, and recalibration limits honest", () => {
    expect(overTime.mlb["2026-06"].n + overTime.mlb["2026-07"].n).toBe(mlbType.n_rows);
    expect(overTime.soccer_intl["2026-06"].n + overTime.soccer_intl["2026-07"].n).toBe(soccerType.n_rows);
    expect(answer("Is calibration improving month over month?")).toContain("not a durable trend");
    expect(gap(mlbMurphy, "reliability")).toBeGreaterThan(0);
    expect(gap(mlbMurphy, "resolution")).toBeLessThan(0);
    expect(Math.abs(gap(mlbMurphy, "resolution"))).toBeGreaterThan(gap(mlbMurphy, "reliability"));
    expect(gap(soccerMurphy, "reliability")).toBeGreaterThan(0);
    expect(gap(soccerMurphy, "resolution")).toBeLessThan(0);
    expect(gap(soccerMurphy, "reliability")).toBeGreaterThan(Math.abs(gap(soccerMurphy, "resolution")));
    expect(answer("Is the model-vs-market gap fixable by recalibrating?")).toContain("not established");
    expect(answer("Where does the model lose to the market -- calibration or information?")).toContain("not causal proof");
    expect(byType.skipped[0].reason).toContain("byte-identical duplicate");
    expect(answer("How do you avoid double-counting duplicate corpora?")).toContain("without adding that duplicate");
  });
});
