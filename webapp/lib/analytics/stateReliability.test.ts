import { describe, expect, it } from "vitest";
import { loadStateReliability } from "./stateReliability.server";
import { stateReliabilityMetricValue, stateReliabilityRow } from "./stateReliability";

describe("state reliability data", () => {
  it("loads all 83 published state-conditioned rows", () => {
    expect(loadStateReliability().flatMap(sport => sport.rows)).toHaveLength(83);
  });

  it("retains published no-state-field skip counts per sport", () => {
    const sports = loadStateReliability();
    expect(sports.find(sport => sport.sport === "mlb")?.nSkippedNoStateField).toBe(26340);
    expect(sports.find(sport => sport.sport === "soccer_intl")?.nSkippedNoStateField).toBe(5345);
  });

  it("keeps the distinct source supports for the MLB late high-probability cell", () => {
    const mlb = loadStateReliability().find(sport => sport.sport === "mlb");
    expect(mlb).toBeDefined();
    expect(stateReliabilityRow(mlb!, "late(inn7+)", ".8-1", "model")?.n).toBe(5037);
    expect(stateReliabilityRow(mlb!, "late(inn7+)", ".8-1", "market")?.n).toBe(2771);
  });

  it("rounds a derived signed gap before exposing percentage points", () => {
    const row = { sport: "sample", timeBucket: "late", probabilityBucket: ".8-1", source: "model" as const, n: 1, meanP: 0.9211111, meanY: 0.6853333, calibrationError: 0.2357778 };
    expect(stateReliabilityMetricValue(row, "signed-gap")).toBe(-23.57778);
  });
});
