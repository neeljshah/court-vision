import { describe, expect, it } from "vitest";
import { selectNovelMeasurement } from "./novelCards";

describe("selectNovelMeasurement", () => {
  it("selects the rest-asymmetry contrast panel", () => {
    const contrast = "0.0892";
    const artifact = {
      headline: "rest headline",
      verdict: "rest verdict",
      caveat: "rest caveat",
      panels: {
        rest_differential: { n_games: "4793" },
        contrast_vs_equal_rest: [{ cell: "home +2 or more", delta_vs_equal: contrast, ci95: ["0.0257", "0.1502"] }],
      },
    };
    const card = selectNovelMeasurement("novel_rest_asymmetry", artifact);

    expect(card.lead).toBe(contrast);
    expect(card.interval).toContain(String(artifact.panels.contrast_vs_equal_rest[0].ci95[0]));
    expect(card.denominator).toContain("NBA games");
  });

  it("selects the starter-rest bucket frequencies", () => {
    const buckets = [
      { cell: "4", win_frequency: "0.5027", ci95: ["0.4984", "0.5069"] },
      { cell: "5", win_frequency: "0.5023", ci95: ["0.4970", "0.5077"] },
      { cell: "6 or more", win_frequency: "0.4999", ci95: ["0.4914", "0.5079"] },
    ];
    const artifact = { headline: "starter headline", verdict: "Recorded as a null.", caveat: "starter caveat", panels: { rest_buckets: { n_starts: "52078", cells: buckets } } };
    const card = selectNovelMeasurement("novel_starter_rest_absorption", artifact);

    expect(card.lead).toBe(buckets.map((bucket) => bucket.win_frequency).join(" / "));
    expect(card.interval).toContain(String(buckets[0].ci95[0]));
    expect(card.verdict).toBe("null");
  });

  it("selects the repeat-pitch overall panel and its contradicted claims", () => {
    const overall = { n_pairs: "511807", excess: "0.0367", ci95: ["0.0348", "0.0385"] };
    const claims = [{ claim: "Claim one.", verdict: "CONFIRMED" }, { claim: "Claim two.", verdict: "CONTRADICTED" }];
    const artifact = { headline: "pitch headline", caveat: "pitch caveat", panels: { overall: { cells: [overall] } }, preregistered_claims: claims };
    const card = selectNovelMeasurement("novel_pitch_repeat_excess", artifact);

    expect(card.lead).toBe(overall.excess);
    expect(card.interval).toContain(String(overall.ci95[0]));
    expect(card.result).toContain(claims[1].claim.replace(/[.!?]+$/, ""));
    expect(card.verdict).toBe("contradicted");
  });
});
