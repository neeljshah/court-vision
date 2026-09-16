import { describe, expect, it } from "vitest";
import { labComparisonPolicy } from "./labComparisonPolicy";
import type { LabRow } from "./labTypes";

const row = (id: string, definition: LabRow["definition"]): LabRow => ({ id, label: id, group: id, values: { value: 1 }, definition });

describe("labComparisonPolicy", () => {
  it("keeps matching definitions comparable", () => {
    const policy = labComparisonPolicy([row("a", { unit: "runs", clockField: "inning", threshold: 3 }), row("b", { unit: "runs", clockField: "inning", threshold: 3 })]);
    expect(policy.compatible).toBe(true);
    expect(policy.compatibility).toBe("compatible");
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
    expect(policy.compatibility).toBe("incompatible");
    expect(policy.cohorts.map(cohort => cohort.definition.season)).toEqual(["2024-25", "2025-26"]);
  });
  it("marks absent cohort definitions as unknown rather than comparable", () => {
    const policy = labComparisonPolicy([row("defined", { season: "2025-26" }), row("missing", undefined)]);
    expect(policy.compatibility).toBe("unknown");
    expect(policy.compatible).toBe(false);
    expect(policy.reason).toContain("compatibility is unknown");
  });
  it("keeps all-unknown rows out of pooled comparisons", () => {
    const policy = labComparisonPolicy([row("a", undefined), row("b", undefined)]);
    expect(policy.compatibility).toBe("unknown");
    expect(policy.cohorts[0].compatibility).toBe("unknown");
    expect(policy.compatible).toBe(false);
  });
  it("marks mixed known and missing seasons as unknown", () => {
    const policy = labComparisonPolicy([row("known", { season: "2025-26" }), row("missing", { sport: "NBA" })]);
    expect(policy.compatibility).toBe("unknown");
    expect(policy.cohorts.at(-1)?.compatibility).toBe("unknown");
  });
  it("splits differing observation windows", () => {
    const policy = labComparisonPolicy([row("early", { sport: "MLB", observationWindow: "Checkpoints 1 to 10" }), row("late", { sport: "MLB", observationWindow: "Checkpoints 2 to 10" })]);
    expect(policy.compatibility).toBe("incompatible");
    expect(policy.reason).toContain("observation windows");
  });
  it("accepts identical complete published definitions", () => {
    const definition = { sport: "MLB", population: "178 games", observationWindow: "2026-06-18 to 2026-07-17", unit: "runs", clockField: "inning", threshold: 3, season: "2025-26" };
    const policy = labComparisonPolicy([row("a", definition), row("b", definition)]);
    expect(policy.compatibility).toBe("compatible");
    expect(policy.cohorts).toHaveLength(1);
  });
});
