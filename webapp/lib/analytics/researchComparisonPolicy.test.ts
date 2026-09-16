import { describe, expect, it } from "vitest";
import { getResearchAnalyses } from "./researchData";
import { matchesResearchPopulation, researchComparisonPolicy } from "./researchComparisonPolicy";
import type { ResearchRow } from "./researchTypes";

const row = (id: string, path: string): ResearchRow => ({ id, label: id, group: id, values: { value: 1 }, sourcePaths: [path] });
const plain = (id: string, group: string, label: string): ResearchRow => ({ id, label, group, values: { value: 1 } });

describe("researchComparisonPolicy", () => {
  it("keeps an aggregate apart from its component phases", () => {
    const policy = researchComparisonPolicy([row("all", "sports.mlb.grains.all.brier_model"), row("early", "sports.mlb.grains.early.brier_model")]);
    expect(policy.compatibility).toBe("incompatible");
    expect(policy.aggregateRows.map(item => item.id)).toEqual(["all"]);
    expect(policy.populations).toMatchObject([{ key: "sport=mlb", rowCount: 1 }]);
  });

  it("marks different sports incompatible", () => {
    expect(researchComparisonPolicy([row("mlb", "checkpoints.mlb.1.model_brier"), row("soccer", "checkpoints.soccer_intl.15.model_brier")]).compatibility).toBe("incompatible");
  });

  it("marks a missing published field unknown", () => {
    expect(researchComparisonPolicy([row("phase", "sports.mlb.grains.early.brier_model"), row("missing", "entries[].value")]).compatibility).toBe("unknown");
  });

  it("accepts one sport and one grain", () => {
    expect(researchComparisonPolicy([row("early", "sports.mlb.grains.early.brier_model")]).compatibility).toBe("compatible");
  });

  it("is unknown by default when no row identifies a population", () => {
    const policy = researchComparisonPolicy([plain("stress", "Coverage stress", "Answerable prompts"), plain("regression", "Fail-closed QA", "Regression-bank checks")]);
    expect(policy.compatibility).toBe("unknown");
    expect(policy.compatible).toBe(false);
    expect(policy.populations.map(population => population.compatibility)).toEqual(["unknown"]);
    expect(policy.reason).toContain("do not identify a population");
  });

  it("does not inherit a population from an unrelated analysis sport", () => {
    const rows = [plain("mlb", "mlb", "Model"), plain("soccer", "soccer", "Model")];
    expect(researchComparisonPolicy(rows, { sport: "all" }).compatibility).toBe("incompatible");
    expect(researchComparisonPolicy(rows, { sport: "nba" }).compatibility).toBe("compatible");
  });

  it("refuses to pool the published QA rates", () => {
    const analysis = getResearchAnalyses().find(candidate => candidate.id === "answer-evidence-coverage")!;
    expect(analysis.caveat).toContain("must not be pooled");
    const policy = researchComparisonPolicy(analysis.rows, analysis);
    expect(policy.compatible).toBe(false);
    expect(policy.compatibility).toBe("unknown");
  });

  it("matches a row to its population by published row identity", () => {
    const rows = [row("mlb", "checkpoints.mlb.1.model_brier"), row("soccer", "checkpoints.soccer_intl.15.model_brier")];
    const policy = researchComparisonPolicy(rows);
    const mlb = policy.populations.find(population => population.key === "sport=mlb")!;
    expect(rows.filter(item => matchesResearchPopulation(item, mlb)).map(item => item.id)).toEqual(["mlb"]);
  });
});
