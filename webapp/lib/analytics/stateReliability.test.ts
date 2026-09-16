import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { loadStateReliability } from "./stateReliability.server";
import { stateReliabilityMetricValue, stateReliabilityRow } from "./stateReliability";

type ArtifactSport = { n_records: number; n_skipped_no_state_field: number; buckets: Array<{ time_bucket: string; prob_bucket: string }> };

function artifactSports(): Record<string, ArtifactSport> {
  const path = join(process.cwd(), "public", "data", "showcase", "state_conditioned_calibration.json");
  return (JSON.parse(readFileSync(path, "utf-8")) as { sports: Record<string, ArtifactSport> }).sports;
}

describe("state reliability data", () => {
  it("sorts numeric probability buckets identically for every sport and game phases in order", () => {
    const sports = loadStateReliability();
    const buckets = ["0-.2", ".2-.4", ".4-.6", ".6-.8", ".8-1"];
    expect(sports.map(sport => sport.probabilityBuckets)).toEqual(sports.map(() => buckets));
    expect(sports.find(sport => sport.sport === "mlb")?.timeBuckets).toEqual(["early(inn1-3)", "mid(inn4-6)", "late(inn7+)"]);
    expect(sports.find(sport => sport.sport === "soccer_intl")?.timeBuckets).toEqual(["0-15", "15-30", "30-45", "45-60", "60-75", "75-90+"]);
  });

  it("computes coverage counts from the published artifact fields", () => {
    const expected = artifactSports();
    for (const sport of loadStateReliability()) {
      const source = expected[sport.sport];
      expect(sport.nForecastObservations).toBe(source.n_records);
      expect(sport.nSkippedNoStateField).toBe(source.n_skipped_no_state_field);
      expect(sport.nCells).toBe(new Set(source.buckets.map(row => `${row.time_bucket}|${row.prob_bucket}`)).size);
    }
  });

  it("keeps the distinct source supports for the MLB late high-probability cell", () => {
    const mlb = loadStateReliability().find(sport => sport.sport === "mlb");
    expect(stateReliabilityRow(mlb!, "late(inn7+)", ".8-1", "model")?.n).toBe(2369);
    expect(stateReliabilityRow(mlb!, "late(inn7+)", ".8-1", "market")?.n).toBe(2666);
  });

  it("rounds a derived signed gap before exposing percentage points", () => {
    const row = { sport: "sample", timeBucket: "late", probabilityBucket: ".8-1", source: "model" as const, n: 1, meanP: 0.9211111, meanY: 0.6853333, calibrationError: 0.2357778 };
    expect(stateReliabilityMetricValue(row, "signed-gap")).toBe(-23.57778);
  });
});
