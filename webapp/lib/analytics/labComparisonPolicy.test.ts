import { describe, expect, it } from "vitest";
import { labComparisonPolicy } from "./labComparisonPolicy";
import type { LabRow } from "./labTypes";

const row = (id: string, definition: LabRow["definition"]): LabRow => ({ id, label: id, group: id, values: { value: 1 }, definition });

describe("labComparisonPolicy", () => {
  it("keeps matching definitions comparable", () => {
    const policy = labComparisonPolicy([row("a", { unit: "runs", clockField: "inning", threshold: 3 }), row("b", { unit: "runs", clockField: "inning", threshold: 3 })]);
    expect(policy.compatible).toBe(true);
    expect(policy.cohorts).toHaveLength(1);
  });
  it("splits rows with different units", () => {
    const policy = labComparisonPolicy([row("a", { unit: "runs" }), row("b", { unit: "goals" })]);
    expect(policy.compatible).toBe(false);
    expect(policy.cohorts).toHaveLength(2);
    expect(policy.reason).toContain("score units");
  });
  it("splits rows with different thresholds", () => {
    const policy = labComparisonPolicy([row("a", { threshold: 2, unit: "runs" }), row("b", { threshold: 3, unit: "runs" })]);
    expect(policy.compatible).toBe(false);
    expect(policy.reason).toContain("score thresholds");
  });
  it("splits rows with different seasons", () => {
    const policy = labComparisonPolicy([row("a", { season: "2024-25" }), row("b", { season: "2025-26" })]);
    expect(policy.compatible).toBe(false);
    expect(policy.cohorts.map(cohort => cohort.definition.season)).toEqual(["2024-25", "2025-26"]);
  });
});
