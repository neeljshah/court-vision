import { describe, expect, it } from "vitest";
import { researchComparisonPolicy } from "./researchComparisonPolicy";
import type { ResearchRow } from "./researchTypes";

const row = (id: string, path: string): ResearchRow => ({ id, label: id, group: id, values: { value: 1 }, sourcePaths: [path] });

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
});
