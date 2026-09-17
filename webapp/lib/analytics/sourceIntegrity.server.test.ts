import { describe, expect, it } from "vitest";
import { getResearchAnalyses } from "./researchData";
import { loadScoutCorpus } from "./scoutCorpus.server";
import { scoutIntegrity } from "./scoutIntegrity";
import { moduleIdsForCitations } from "./sourceIntegrity.server";

const corpus = loadScoutCorpus();

describe("Scout server integrity lineage", () => {
  it("expands a cited Ask JSON file through its structured answer sources", () => {
    const ids = moduleIdsForCitations([
      "webapp/public/data/ask/calibration-market.json",
      "docs/evidence/calibration-decomposition.md",
    ]);
    expect(ids).toEqual(expect.arrayContaining([
      "calibration_stability",
      "murphy_decomposition",
      "brier_skill_scores",
      "state_conditioned_calibration",
    ]));
    expect(ids).not.toContain("calibration-market");
  });

  it("warns on actual indirect, direct-explainer, and paper sources", () => {
    const answerAt = (path: string) => corpus.find(entry => entry.a.explore_path === path)!.a;
    const indirect = answerAt("/analytics/explainers/what-calibration-means/");
    const direct = answerAt("/analytics/explainers/how-to-read-a-reliability-diagram/");
    const paper = answerAt("/analytics/papers/brier-decomposition-reliability-resolution/");

    expect(indirect.source_module_ids).toContain("calibration_stability");
    expect(scoutIntegrity(indirect).notices.length).toBeGreaterThan(0);
    expect(direct.source_module_ids).toEqual(["calibration_stability"]);
    expect(scoutIntegrity(direct).notices.length).toBeGreaterThan(0);
    expect(paper.source_module_ids).toEqual(["murphy_decomposition", "brier_skill_scores"]);
    expect(scoutIntegrity(paper).notices.length).toBeGreaterThan(0);
    expect([indirect, direct, paper].every(answer => scoutIntegrity(answer).notices.every(notice => notice.status === "regenerated" || notice.status === "under-review"))).toBe(true);
  });

  it("records every source for generated multi-source analyses", () => {
    const analysis = getResearchAnalyses().find(item => item.sources?.length);
    expect(analysis).toBeDefined();
    const answer = corpus.find(entry => entry.a.explore_path === `/analytics/research/${analysis!.id}/`)!.a;
    const expected = Array.from(new Set([analysis!.source, ...analysis!.sources!.map(source => source.id)]));
    expect(answer.source_module_ids).toEqual(expected);
  });
});
